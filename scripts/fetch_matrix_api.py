"""KRX 공식 OpenAPI + DART로 월별 PER/PBR 매트릭스 산출 (pykrx 대체 경로)

pykrx는 data.krx.co.kr을 스크랩하는 방식이라 KRX 약관 제10조 제2호(자동화 수단
정보 무단 수집) 대상이고, 2026-08-13 실제로 IP가 1일 차단됐다. 이 스크립트는
KRX가 차단 안내에서 직접 제시한 공식 경로(openapi.krx.co.kr)만 사용한다.

KRX OpenAPI는 PER/PBR을 제공하지 않으므로 시가총액 + DART 재무로 역산한다.
정의는 2026-08-13 실측으로 확정했다 (Top 10 종목 KRX 실제값 대조):

    PER = 시가총액 / 지배주주 직전결산 순이익     중앙 오차 1.7% (최대 10.6%)
    PBR = 시가총액 / 지배주주 직전결산 자본       중앙 오차 4.9% (최대 12.0%)

KRX PER/PBR은 TTM이 아니라 **직전 확정 결산** 기준이며 사업보고서 공시 후
연 1회 갱신된다. 따라서 기준 사업연도는 4월을 경계로 한다:
    월 >= 4월  →  FY(연도 - 1)      예: 2026-06 → FY2025 (검증됨)
    월 <  4월  →  FY(연도 - 2)      예: 2023-01 → FY2021

주의: 이 방식으로 만든 값과 기존 pykrx 매트릭스 값을 **한 시계열에 섞으면 안 된다.**
종목별 수 % 편차가 계단으로 나타나 4팩터의 "5년평균 대비 현재" 비율을 오염시킨다.
교체할 거면 60개월 전량을 이 방식으로 다시 계산해야 한다.

출력은 기존 파일을 덮지 않고 별도 경로에 쓴다 (--replace 로만 정식 경로에 기록).

사용:
    python scripts/fetch_matrix_api.py              # universe 종목, 검증 리포트 포함
    python scripts/fetch_matrix_api.py --all        # KRX 전 종목 (느림)
    python scripts/fetch_matrix_api.py --months 24  # 기간 축소 (빠른 확인용)
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX_DIR = ROOT / "data" / "matrix"
CORPMAP_PATH = ROOT / "data" / "financials" / "_dart_corpmap.json"
UNIVERSE_PATH = ROOT / "data" / "universe.json"

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env(ROOT / ".env")

KRX_KEY = os.environ.get("KRX_API_KEY")
DART_KEY = os.environ.get("DART_API_KEY")
if not KRX_KEY or not DART_KEY:
    sys.stderr.write("[ERROR] KRX_API_KEY / DART_API_KEY 미설정. .env 확인.\n")
    sys.exit(2)

KRX_BASE = "http://data-dbg.krx.co.kr/svc/apis/"
DART_BASE = "https://opendart.fss.or.kr/api"
KRX_SLEEP = 0.3
DART_SLEEP = 0.15
DART_WORKERS = 8   # 실측: 1/4/8/12 워커 모두 실패 0건, 12가 순차 대비 10배. 여유 두고 8.
LOOKBACK_MONTHS = 60

# 지배주주 기준 우선, 없으면 전체로 폴백 (실측상 지배주주가 KRX와 일치)
NET_IDS = ["ifrs-full_ProfitLossAttributableToOwnersOfParent", "ifrs-full_ProfitLoss"]
EQ_IDS = ["ifrs-full_EquityAttributableToOwnersOfParent", "ifrs-full_Equity"]
NET_NAMES = ["지배기업의 소유주에게 귀속되는 당기순이익(손실)", "지배기업 소유주지분 당기순이익",
             "당기순이익", "당기순이익(손실)"]
EQ_NAMES = ["지배기업의 소유주에게 귀속되는 자본", "지배기업 소유주지분", "자본총계"]

# EPS — KRX PER의 실제 분모. PER = 주가 / 기본주당이익(직전결산) 이 KRX 정의이고,
# 실측(12종목)에서 11개가 소수점까지 일치했다(HD건설기계·더존비즈온은 시총÷순이익
# 방식에서 175%·137% 틀렸는데 여기선 0.0%). 시총÷순이익은 주식수·우선주·비지배지분이
# 전부 맞아야 성립하는 근사라, EPS가 있으면 무조건 EPS를 쓴다.
EPS_IDS = ["ifrs-full_BasicEarningsLossPerShare",
           "ifrs-full_BasicEarningsLossPerShareFromContinuingOperations"]
EPS_NAMES = ["기본주당이익(손실)", "기본주당이익", "기본주당순이익", "주당이익"]


# ---------------------------------------------------------------- helpers

def _amt(s):
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s in ("", "-"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def krx_get(svc: str, bas_dd: str, retry: int = 3):
    url = f"{KRX_BASE}{svc}?basDd={bas_dd}"
    last = None
    for attempt in range(retry):
        try:
            req = urllib.request.Request(url, headers={"AUTH_KEY": KRX_KEY})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8")
            return json.loads(body).get("OutBlock_1") or []
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError(f"{svc}: 미승인 서비스(401)") from e
            last = e
        except Exception as e:
            last = e
        time.sleep(KRX_SLEEP * (attempt + 2))
    raise last


def dart_get(path: str, retry: int = 3, **params):
    """DART 호출 + 백오프 재시도.

    재시도가 없으면 일시적 오류 하나로 그 종목이 통째로 누락된다. 실제로 60개월
    런(최대 1,212콜)에서 61종목이 이렇게 날아갔다 — 6개월 런(303콜)은 전량 성공.
    """
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{DART_BASE}/{path}?crtfc_key={DART_KEY}&{q}"
    last = None
    for attempt in range(retry):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            last = e
            time.sleep(DART_SLEEP * (attempt + 1) * 4)
    raise last


def short_code(isu_cd: str) -> str:
    """KR7095570008 → 095570"""
    return isu_cd[3:9] if len(isu_cd) > 9 else isu_cd


# ------------------------------------------------------- KRX 시가총액 수집

def resolve_trading_day(d: datetime, max_back: int = 10) -> str | None:
    """해당 날짜(또는 그 이전 최근 거래일)의 basDd 반환. 못 찾으면 None."""
    for _ in range(max_back):
        ds = d.strftime("%Y%m%d")
        try:
            if krx_get("sto/stk_bydd_trd", ds):
                return ds
        except Exception as e:
            print(f"    [WARN] {ds} 조회 실패: {e}", file=sys.stderr)
        d -= timedelta(days=1)
        time.sleep(KRX_SLEEP)
    return None


def _merge_preferred(month_cap: dict) -> dict:
    """우선주 시총을 보통주에 합산.

    KRX 시가총액은 상장 종목(주식 종류) 단위다. 반면 DART 자본·순이익은 회사 전체
    기준이라, 우선주가 있는 회사는 분자(보통주 시총)만 작아져 PBR/PER이 구조적으로
    과소 산출된다(SK케미칼 -10%). 종목코드 앞 5자리가 같고 끝자리가 0이면 보통주,
    5/7/9면 같은 회사의 우선주라는 KRX 규칙을 이용해 합산한다.
    """
    merged = dict(month_cap)
    for code, cap in month_cap.items():
        if code[-1] in "579":
            base = code[:5] + "0"
            if base in merged:
                merged[base] += cap
    return merged


def fetch_marketcaps(months: int):
    """{basDd: {code: mktcap}} + 날짜 목록 (오래된 순). 우선주는 보통주에 합산됨."""
    end_dt = datetime.now()
    targets = [(end_dt - timedelta(days=30 * i)).replace(day=15) for i in range(months)]
    targets.reverse()

    caps, dates, names = {}, [], {}
    t0 = time.time()
    for i, target in enumerate(targets):
        ds = resolve_trading_day(target)
        if ds is None or ds in caps:
            print(f"  [{i+1:>2}/{months}] {target:%Y-%m} 거래일 없음 · 건너뜀", flush=True)
            continue
        month_cap = {}
        for svc in ("sto/stk_bydd_trd", "sto/ksq_bydd_trd"):
            try:
                for r in krx_get(svc, ds):
                    code = short_code(r["ISU_CD"])
                    mc = _amt(r.get("MKTCAP"))
                    if mc:
                        month_cap[code] = mc
                        names.setdefault(code, r.get("ISU_NM", ""))
            except Exception as e:
                print(f"    [WARN] {ds} {svc} 실패: {e}", file=sys.stderr)
            time.sleep(KRX_SLEEP)
        if month_cap:
            caps[ds] = _merge_preferred(month_cap)
            dates.append(ds)
        elapsed = time.time() - t0
        eta = (elapsed / (i + 1)) * (months - i - 1)
        print(f"  [{i+1:>2}/{months}] {ds} · {len(month_cap)}종목 "
              f"· 경과 {elapsed:.0f}s · ETA {eta:.0f}s", flush=True)
    return caps, dates, names


# --------------------------------------------------------- DART 결산 재무

def _pick(rows, ids, names, field, sj=None):
    """account_id 우선, 없으면 account_nm으로 금액 추출.

    sj로 재무제표 구분을 반드시 좁힌다. 같은 account_id가 자본변동표(SCE)에도
    여러 번 등장하는데 거기 값은 자본의 '구성 항목/증감분'이라 총계가 아니다.
    이걸 안 거르면 롯데렌탈처럼 PBR이 0.87 대신 134로 나온다(154배 오류).
    """
    cand = [r for r in rows if r.get("sj_div") in sj] if sj else rows
    for tag in ids:
        for r in cand:
            if r.get("account_id") == tag:
                v = _amt(r.get(field))
                if v is not None:
                    return v
    for nm in names:
        for r in cand:
            if (r.get("account_nm") or "").strip() == nm:
                v = _amt(r.get(field))
                if v is not None:
                    return v
    return None


SJ_BS = ("BS",)          # 재무상태표 — 자본
SJ_IS = ("IS", "CIS")    # 손익계산서 / 포괄손익계산서 — 순이익


def fetch_annual_report(corp_code: str, year: int):
    """사업보고서 전체재무제표. CFS(연결) 우선, 없으면 OFS(별도).

    반환: (rows, hard_fail). hard_fail=True면 통신 실패(재시도 소진)라
    '해당 연도 공시 없음(status 013)'과 구분된다.
    """
    hard_fail = False
    for fs in ("CFS", "OFS"):
        try:
            d = dart_get("fnlttSinglAcntAll.json", corp_code=corp_code,
                         bsns_year=year, reprt_code="11011", fs_div=fs)
        except Exception:
            hard_fail = True
            continue
        if d.get("status") == "000" and d.get("list"):
            return d["list"], False
        time.sleep(DART_SLEEP)
    return None, hard_fail


# 한 보고서에서 당기/전기 2개년만 쓴다.
# 전전기(bfefrmtrm)는 재무상태표에서 자주 비고 값도 덜 안정적이라, 이걸 쓰면 가장
# 오래된 구간의 오차가 커진다(FY2020 구간 PER 중앙 5.8% vs 나머지 2~3%).
# 앵커를 2년 간격으로 촘촘히 두는 대신 전전기를 버린다 — 호출은 1.5배, 품질은 개선.
PERIOD_FIELDS = [("thstrm_amount", 0), ("frmtrm_amount", 1)]
ANCHOR_STEP = 2


def _one_stock(corp: str, anchors, fy_min: int, fy_max: int):
    """한 종목의 {fy: {ni, eq}} + 통신실패 여부."""
    per_fy = {}
    hard = False
    for anchor in anchors:
        rows, hard_fail = fetch_annual_report(corp, anchor)
        hard = hard or hard_fail
        if not rows:
            continue
        for field, back in PERIOD_FIELDS:
            fy = anchor - back
            if fy < fy_min or fy > fy_max or fy in per_fy:
                continue
            ni = _pick(rows, NET_IDS, NET_NAMES, field, sj=SJ_IS)
            eq = _pick(rows, EQ_IDS, EQ_NAMES, field, sj=SJ_BS)
            if ni is not None or eq is not None:
                per_fy[fy] = {"ni": ni, "eq": eq}
    return per_fy, hard


def fetch_fundamentals(codes, corpmap, fy_min: int, fy_max: int, workers: int = DART_WORKERS):
    """{code: {fy: {"ni": 순이익, "eq": 자본}}}

    종목 단위로 병렬 처리한다. DART는 동시 호출을 잘 받는다 — 실측(40종목 1콜씩)에서
    1/4/8/12 워커 모두 실패 0건이었고 12워커가 순차 대비 10배였다. 일일 한도(20,000콜)만
    지키면 되므로 여유를 두고 8을 기본값으로 쓴다.
    """
    anchors = []
    y = fy_max
    while y >= fy_min:
        anchors.append(y)
        y -= ANCHOR_STEP
    print(f"  DART 앵커 연도: {anchors}  (보고서당 당기·전기 2개년) · 워커 {workers}")

    targets = [(c, corpmap[c]) for c in codes if corpmap.get(c)]
    out, failed = {}, []
    total = len(targets)
    t0 = time.time()
    done = 0
    lock = threading.Lock()

    def work(item):
        nonlocal done
        code, corp = item
        try:
            per_fy, hard = _one_stock(corp, anchors, fy_min, fy_max)
        except Exception:
            per_fy, hard = {}, True
        with lock:
            done += 1
            if per_fy:
                out[code] = per_fy
            elif hard:
                failed.append(code)
            if done % 100 == 0 or done == total:
                elapsed = time.time() - t0
                eta = (elapsed / done) * (total - done)
                print(f"  [{done:>4}/{total}] DART · 경과 {elapsed:.0f}s · ETA {eta:.0f}s",
                      flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, targets))

    if failed:
        print(f"  [WARN] 통신 실패로 누락된 종목 {len(failed)}개: "
              f"{', '.join(failed[:15])}{' ...' if len(failed) > 15 else ''}",
              file=sys.stderr)
    return out


SWITCH_MONTH = 5  # KRX가 신규 결산을 반영하는 달 (실측: 4월은 아직 전전 FY, 5월부터 직전 FY)


def base_fy(bas_dd: str) -> int:
    """기준 사업연도 — SWITCH_MONTH 이후면 직전 FY, 이전이면 전전 FY.

    사업보고서는 3월 말 공시되지만 KRX 반영은 그보다 늦다. 2026-04는 여전히 FY2024
    기준이었고(오차 중앙 30.6%), 2026-05부터 FY2025로 전환됐다(오차 2.2%).
    """
    y, m = int(bas_dd[:4]), int(bas_dd[4:6])
    return y - 1 if m >= SWITCH_MONTH else y - 2


def unit_scale(mc: int, eq) -> int:
    """DART 보고 단위 보정 계수.

    fnlttSinglAcntAll은 보고서에 적힌 단위를 그대로 준다. 대부분 원이지만 일부
    기업은 천원/백만원으로 보고한다(예: 두산밥캣 FY2025 자본 = 5,011,583,000 천원).
    자본 대비 시총 비율이 현실적인 PBR 범위를 크게 벗어나면 단위 불일치로 보고
    1,000배 / 1,000,000배를 적용한다. 계수는 같은 보고서의 순이익에도 함께 쓴다.
    """
    if not eq or eq <= 0:
        return 1
    ratio = mc / eq
    if ratio > 200_000:
        return 1_000_000
    if ratio > 200:
        return 1_000
    return 1


# ------------------------------------------------------------- 매트릭스 조립

def build_matrices(caps, dates, fundamentals):
    per_matrix, pbr_matrix = {}, {}
    scaled = 0
    for ds in dates:
        fy = base_fy(ds)
        for code, mc in caps[ds].items():
            fin = (fundamentals.get(code) or {}).get(fy)
            if not fin:
                continue
            ni, eq = fin.get("ni"), fin.get("eq")
            k = unit_scale(mc, eq)
            if k > 1:
                scaled += 1
                eq = eq * k
                ni = ni * k if ni is not None else None
            # 적자면 PER 미산출 (KRX도 0으로 표기) — 여기선 0으로 맞춘다
            if ni is not None:
                per_matrix.setdefault(code, {})[ds] = (
                    round(mc / ni, 2) if ni > 0 else 0.0)
            if eq and eq > 0:
                pbr_matrix.setdefault(code, {})[ds] = round(mc / eq, 2)
    if scaled:
        print(f"  단위 보정 적용: {scaled}건 (천원/백만원 보고 기업)")
    return per_matrix, pbr_matrix


# ----------------------------------------------------------------- 검증

def validate(new_matrix, truth_path: Path, label: str):
    """기존 pykrx 매트릭스와 겹치는 (종목, 날짜)에서 오차 분포를 낸다."""
    if not truth_path.exists():
        print(f"  [{label}] 정답지 없음 — 검증 생략")
        return
    truth = json.loads(truth_path.read_text(encoding="utf-8")).get("matrix", {})
    errs, pairs = [], 0
    for code, dd in new_matrix.items():
        t = truth.get(code)
        if not t:
            continue
        for ds, v in dd.items():
            k = t.get(ds)
            if k in (None, 0) or not v:
                continue
            pairs += 1
            errs.append(abs((v - k) / k * 100))
    if not errs:
        print(f"  [{label}] 비교 가능한 쌍 없음")
        return
    errs.sort()
    n = len(errs)
    within = lambda p: sum(1 for e in errs if e <= p) / n * 100
    print(f"  [{label}] 비교쌍 {pairs:,}개 · 중앙 {errs[n//2]:.1f}% · "
          f"p90 {errs[int(n*0.9)]:.1f}% · 최대 {errs[-1]:.1f}%")
    print(f"           오차 5% 이내 {within(5):.0f}% · 10% 이내 {within(10):.0f}% · "
          f"20% 이내 {within(20):.0f}%")


# -------------------------------------------------------------------- main

def resolve_codes(args, caps_codes):
    if args.all:
        return sorted(caps_codes)
    if UNIVERSE_PATH.exists():
        u = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
        items = u.get("items") or u.get("stocks") or []
        codes = [it.get("code") for it in items
                 if isinstance(it, dict) and it.get("code")
                 and it.get("passed", True)]
        codes = [c for c in codes if c in caps_codes]
        if codes:
            return sorted(set(codes))
    print("  [WARN] universe 코드 추출 실패 → 전 종목으로 진행", file=sys.stderr)
    return sorted(caps_codes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="KRX 전 종목 (기본: universe)")
    ap.add_argument("--months", type=int, default=LOOKBACK_MONTHS)
    ap.add_argument("--replace", action="store_true",
                    help="정식 경로(per_monthly.json)에 기록. 기본은 *_api.json")
    ap.add_argument("--workers", type=int, default=DART_WORKERS,
                    help=f"DART 동시 호출 수 (기본 {DART_WORKERS})")
    args = ap.parse_args()

    print(f"[matrix-api] KRX OpenAPI + DART → PER/PBR ({args.months}개월)")
    print(f"             PER = 시총 / 지배주주 직전결산 순이익")
    print(f"             PBR = 시총 / 지배주주 직전결산 자본\n")

    print("[1/4] KRX OpenAPI 월별 시가총액 수집")
    caps, dates, names = fetch_marketcaps(args.months)
    if not dates:
        sys.stderr.write("[ERROR] 시가총액을 하나도 못 받았습니다.\n")
        sys.exit(1)
    all_codes = {c for m in caps.values() for c in m}
    print(f"  → {len(dates)}개월 · 누적 {len(all_codes)}종목\n")

    print("[2/4] 대상 종목 확정")
    codes = resolve_codes(args, all_codes)
    corpmap = json.loads(CORPMAP_PATH.read_text(encoding="utf-8")) if CORPMAP_PATH.exists() else {}
    if not corpmap:
        sys.stderr.write("[ERROR] _dart_corpmap.json 없음. fetch_financials.py 먼저 실행.\n")
        sys.exit(1)
    codes = [c for c in codes if c in corpmap]
    print(f"  → {len(codes)}종목 (corp_code 보유)\n")

    fy_min, fy_max = base_fy(dates[0]), base_fy(dates[-1])
    print(f"[3/4] DART 결산 재무 수집 (FY{fy_min}~FY{fy_max})")
    fundamentals = fetch_fundamentals(codes, corpmap, fy_min, fy_max, workers=args.workers)
    print(f"  → {len(fundamentals)}종목 재무 확보\n")

    print("[4/4] 매트릭스 조립 + 기존 pykrx 값과 대조")
    per_matrix, pbr_matrix = build_matrices(caps, dates, fundamentals)
    print(f"  PER {len(per_matrix)}종목 · PBR {len(pbr_matrix)}종목\n")

    validate(per_matrix, MATRIX_DIR / "per_monthly.json", "PER")
    validate(pbr_matrix, MATRIX_DIR / "pbr_monthly.json", "PBR")

    suffix = "" if args.replace else "_api"
    meta = {
        "months": args.months,
        "source": "KRX OpenAPI(시가총액) + DART(지배주주 직전결산 순이익/자본)",
        "per_formula": "시가총액 / 지배주주 직전결산 순이익",
        "pbr_formula": "시가총액 / 지배주주 직전결산 자본",
        "fy_rule": "월>=4월 → FY(연-1), 월<4월 → FY(연-2)",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    for name, mat in (("per", per_matrix), ("pbr", pbr_matrix)):
        path = MATRIX_DIR / f"{name}_monthly{suffix}.json"
        path.write_text(json.dumps(
            {"meta": {**meta, "ticker_count": len(mat)}, "matrix": mat},
            ensure_ascii=False), encoding="utf-8")
        print(f"\n  → {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
