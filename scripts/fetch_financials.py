"""OpenDART(전자공시) 공식 API로 종목별 재무 추이를 페치한다.

저평가 진단의 데이터 토대: 매출·영업이익·순이익 5~6년 추세 + 마진.
"싼 게 정당한가(이익 무너지는 중 = 구조적 함정)/일시적인가(이익 멀쩡 = 기회)"를
WebSearch 내러티브가 아니라 공식 공시 데이터로 판정할 수 있게 한다.
ranker §4.3 Value Trap 판별과 fundamental-analyst의 undervaluation_cause.nature 입력.

데이터 소스: OpenDART `fnlttSinglAcnt.json` (단일회사 주요계정).
한 보고서가 당기/전기/전전기 3개년을 반환하므로 2개 사업연도로 5~6년 커버.

출력: data/financials/{code}.json + data/financials/_index.json
- 키(DART_API_KEY)는 .env에서만 로드, 절대 commit/출력 금지.

사용:
  python scripts/fetch_financials.py                 # Top 10 (triple_cross.json)
  python scripts/fetch_financials.py --codes 035720,215000
  python scripts/fetch_financials.py --refresh-corpmap
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

try:  # XXE/billion-laughs 방어 (가능하면 defusedxml, 없으면 stdlib 폴백)
    import defusedxml.ElementTree as ET
except ImportError:
    from xml.etree import ElementTree as ET

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
SCREEN_PATH = ROOT / "data" / "screens" / "triple_cross.json"
UNIVERSE_PATH = ROOT / "data" / "universe.json"
OUT_DIR = ROOT / "data" / "financials"
CORPMAP_PATH = OUT_DIR / "_dart_corpmap.json"

DART_BASE = "https://opendart.fss.or.kr/api"
REPRT_ANNUAL = "11011"  # 사업보고서
# 분기 보고서 우선순위 (최근 분기 스냅샷, 누적 기준)
REPRT_QUARTERS = [("11014", "3Q"), ("11012", "반기"), ("11013", "1Q")]

# 전체재무제표(fnlttSinglAcntAll)를 account_id 표준 XBRL 태그로 매칭 (연도·종목 무관 안정).
# account_id가 비표준이면 account_nm으로 폴백. CFS(연결) 우선, OFS(별도) 폴백.
REVENUE_IDS = {"ifrs-full_Revenue", "ifrs-full_RevenueFromContractsWithCustomers"}
OP_INCOME_IDS = {"dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities"}
NET_INCOME_IDS = {"ifrs-full_ProfitLoss"}
REVENUE_NAMES = {"매출액", "수익(매출액)", "영업수익", "보험료수익"}
OP_INCOME_NAMES = {"영업이익", "영업이익(손실)"}
NET_INCOME_NAMES = {"당기순이익", "당기순이익(손실)"}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def _get(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def build_corpmap(key: str) -> dict:
    """corpCode.xml(zip) 다운로드 → {stock_code: corp_code} (상장사만)."""
    raw = _get(f"{DART_BASE}/corpCode.xml?crtfc_key={key}")
    zf = zipfile.ZipFile(io.BytesIO(raw))
    xml_name = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
    root = ET.fromstring(zf.read(xml_name))
    mapping = {}
    for el in root.iter("list"):
        stock_code = (el.findtext("stock_code") or "").strip()
        corp_code = (el.findtext("corp_code") or "").strip()
        if stock_code and corp_code and len(stock_code) == 6:
            mapping[stock_code] = corp_code
    return mapping


def load_or_build_corpmap(key: str, refresh: bool) -> dict:
    if CORPMAP_PATH.exists() and not refresh:
        return json.loads(CORPMAP_PATH.read_text(encoding="utf-8"))
    print("[financials] corpCode.xml 다운로드 (상장사 code→corp_code 매핑)...")
    mapping = build_corpmap(key)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CORPMAP_PATH.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    print(f"[financials] 매핑 {len(mapping)}개 종목 → {CORPMAP_PATH.relative_to(ROOT)}")
    return mapping


def _parse_amount(s):
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s in ("", "-"):
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return None


def _pick(rows, ids, names, period_field):
    """account_id(표준 XBRL 태그) 우선, 없으면 account_nm으로 period_field 금액을 뽑는다.
    rows는 이미 단일 fs_div(CFS 또는 OFS)로 필터된 상태."""
    for r in rows:
        if r.get("account_id") in ids:
            v = _parse_amount(r.get(period_field))
            if v is not None:
                return v
    for r in rows:
        if r.get("account_nm") in names:
            v = _parse_amount(r.get(period_field))
            if v is not None:
                return v
    return None


def _margin(num, den):
    if num is None or den is None or den == 0:
        return None
    return round(num / den, 4)


def fetch_report(key: str, corp_code: str, bsns_year: int, reprt_code: str):
    """전체재무제표(fnlttSinglAcntAll). CFS(연결) 우선, 비면 OFS(별도). (rows, fs_div) 반환."""
    for fs in ("CFS", "OFS"):
        url = (
            f"{DART_BASE}/fnlttSinglAcntAll.json?crtfc_key={key}"
            f"&corp_code={corp_code}&bsns_year={bsns_year}"
            f"&reprt_code={reprt_code}&fs_div={fs}"
        )
        d = json.loads(_get(url))
        if d.get("status") == "000" and d.get("list"):
            return d["list"], fs
        time.sleep(0.15)
    return None, None


def extract_annual_from_report(rows, bsns_year, fs):
    """한 보고서(3개년)에서 연도별 {year: {revenue, op_income, net_income, fs_div}} 추출."""
    out = {}
    period_map = {
        "thstrm_amount": bsns_year,
        "frmtrm_amount": bsns_year - 1,
        "bfefrmtrm_amount": bsns_year - 2,
    }
    for field, year in period_map.items():
        rev = _pick(rows, REVENUE_IDS, REVENUE_NAMES, field)
        op = _pick(rows, OP_INCOME_IDS, OP_INCOME_NAMES, field)
        net = _pick(rows, NET_INCOME_IDS, NET_INCOME_NAMES, field)
        if rev is None and op is None and net is None:
            continue
        out[year] = {
            "year": year,
            "revenue": rev,
            "op_income": op,
            "op_margin": _margin(op, rev),
            "net_income": net,
            "net_margin": _margin(net, rev),
            "fs_div": fs,
        }
    return out


def fetch_annual_series(key: str, corp_code: str, this_year: int):
    """최근 2개 사업보고서로 5~6년 시계열을 구성. 최신 연도가 미공시면 한 해 뒤로."""
    annual = {}
    # 1) 앵커 연도 탐색: this_year-1 → this_year-2
    anchor = None
    for cand in (this_year - 1, this_year - 2):
        rows, fs = fetch_report(key, corp_code, cand, REPRT_ANNUAL)
        if rows:
            annual.update(extract_annual_from_report(rows, cand, fs))
            anchor = cand
            break
        time.sleep(0.2)
    if anchor is None:
        return []
    # 2) 두 번째 보고서: 앵커-3 (3개년 추가, 겹침 없음)
    time.sleep(0.2)
    rows2, fs2 = fetch_report(key, corp_code, anchor - 3, REPRT_ANNUAL)
    if rows2:
        for y, v in extract_annual_from_report(rows2, anchor - 3, fs2).items():
            annual.setdefault(y, v)
    return [annual[y] for y in sorted(annual)]


def fetch_latest_quarter(key: str, corp_code: str, this_year: int):
    """최근 분기 보고서 1건(누적 기준) 스냅샷. best-effort."""
    for year in (this_year, this_year - 1):
        for reprt_code, label in REPRT_QUARTERS:
            rows, fs = fetch_report(key, corp_code, year, reprt_code)
            time.sleep(0.15)
            if not rows:
                continue
            rev = _pick(rows, REVENUE_IDS, REVENUE_NAMES, "thstrm_amount")
            op = _pick(rows, OP_INCOME_IDS, OP_INCOME_NAMES, "thstrm_amount")
            net = _pick(rows, NET_INCOME_IDS, NET_INCOME_NAMES, "thstrm_amount")
            if rev is None and op is None and net is None:
                continue
            return {
                "period": f"{year}-{label}(누적)",
                "revenue": rev,
                "op_income": op,
                "op_margin": _margin(op, rev),
                "net_income": net,
                "net_margin": _margin(net, rev),
                "fs_div": fs,
            }
    return None


def resolve_targets(args) -> list:
    """(code, name) 목록 결정."""
    if args.codes:
        return [(c.strip(), c.strip()) for c in args.codes.split(",") if c.strip()]
    if args.universe:
        d = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
        return [(s["code"], s.get("name", s["code"])) for s in d.get("passed", [])]
    # 기본: Top 10
    d = json.loads(SCREEN_PATH.read_text(encoding="utf-8"))
    return [(s["code"], s.get("name", s["code"])) for s in d.get("top", [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", help="쉼표구분 종목코드 (기본: Top 10)")
    ap.add_argument("--universe", action="store_true", help="universe 전체")
    ap.add_argument("--refresh-corpmap", action="store_true", help="corp_code 매핑 강제 갱신")
    args = ap.parse_args()

    load_env(ENV_PATH)
    key = os.environ.get("DART_API_KEY")
    if not key:
        sys.stderr.write("[ERROR] DART_API_KEY 미설정. .env 확인.\n")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    corpmap = load_or_build_corpmap(key, args.refresh_corpmap)
    targets = resolve_targets(args)
    this_year = datetime.now().year

    print(f"[financials] 대상 {len(targets)}종목 페치 시작")
    index, ok, skipped = [], 0, 0
    for i, (code, name) in enumerate(targets, 1):
        corp_code = corpmap.get(code)
        if not corp_code:
            print(f"  [{i}/{len(targets)}] {name}({code}) — corp_code 없음, 스킵")
            skipped += 1
            continue
        try:
            annual = fetch_annual_series(key, corp_code, this_year)
        except Exception as e:  # 네트워크/파싱 오류는 종목 스킵, 파이프라인 유지
            print(f"  [{i}/{len(targets)}] {name}({code}) — 오류 {e}, 스킵")
            skipped += 1
            continue
        if not annual:
            print(f"  [{i}/{len(targets)}] {name}({code}) — 재무 무데이터, 스킵")
            skipped += 1
            continue
        quarter = None
        try:
            quarter = fetch_latest_quarter(key, corp_code, this_year)
        except Exception:
            pass
        rec = {
            "code": code,
            "corp_code": corp_code,
            "source": "OpenDART",
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "unit": "원",
            "annual": annual,
            "latest_quarter": quarter,
        }
        (OUT_DIR / f"{code}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        yrs = f"{annual[0]['year']}~{annual[-1]['year']}"
        print(f"  [{i}/{len(targets)}] {name}({code}) — {len(annual)}개년({yrs}) 저장")
        index.append({"code": code, "years": len(annual)})
        ok += 1
        time.sleep(0.2)

    (OUT_DIR / "_index.json").write_text(
        json.dumps(
            {"generated_at": datetime.now().isoformat(timespec="seconds"), "items": index},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[financials] 완료. 성공 {ok} · 스킵 {skipped} → {OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
