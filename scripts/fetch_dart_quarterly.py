"""DART 분기·연간 보고서 → 지배주주 순이익(누적)·지배주주 자본·기본EPS(누적) 시계열.

왜 필요한가 (2026-11-23):
  KIS 재무비율 API(financial-ratio)가 404로 바뀌어 EPS/BPS 갱신이 끊겼다.
  또 주당 값(EPS/BPS)은 액면분할 때 회사마다 소급 수정 여부가 달라 이어 붙이면 틀린다
  (나이스정보통신: 1Q 누적 1,656 → 반기 누적 751). 그래서 **금액**으로 받고
  PER = 시가총액 / TTM 지배순이익, PBR = 시가총액 / 지배자본 으로 계산한다.

출력: data/financials_q/{code}.json
  {code, corp_code, series: {stac: {ni, eq, eps, fs, status}}}
  stac = KIS와 같은 결산연월 6자리 (202609 = 3분기 누적). ni·eps 는 **당해 누적**이다.

    python scripts/fetch_dart_quarterly.py                       # universe passed
    python scripts/fetch_dart_quarterly.py --codes-file X.json   # {"passed":[...]} 형식
원천: dartlab 미러(HuggingFace) 우선, 없는 보고서만 DART API.
이어받기: 이미 받은 보고서는 건너뛴다. 공시 기한 전 보고서는 요청하지 않는다.
"""
import argparse, json, os, sys
from datetime import date
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import feeds  # noqa: E402
import ttm    # noqa: E402

OUT = ROOT / "data" / "financials_q"
CORPMAP = ROOT / "data" / "financials" / "_dart_corpmap.json"
REPORTS = {"03": "11013", "06": "11012", "09": "11014", "12": "11011"}
START_YEAR = 2015   # 2026-11-24: 2020→2015 — 한국 수출 경기순환(조선·화학·반도체)은 10년 단위라 5년으로는 '평소 이익'을 못 잡는다. 미러에 2015~ 있음

NI_IDS = {"CFS": ["ifrs-full_ProfitLossAttributableToOwnersOfParent"],
          "OFS": ["ifrs-full_ProfitLoss"]}
EQ_IDS = {"CFS": ["ifrs-full_EquityAttributableToOwnersOfParent"],
          "OFS": ["ifrs-full_Equity"]}
EPS_IDS = ["ifrs-full_BasicEarningsLossPerShare"]


def _amt(s):
    s = str(s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _pick(rows, ids, field, sj=None):
    # 2019년 이전 공시는 옛 택소노미 접두사(ifrs_)를 쓴다 — 같은 계정을 둘 다 받는다 (2026-11-24, 2015~ 확장 때 발견)
    ids = list(ids) + [i.replace("ifrs-full_", "ifrs_") for i in ids if i.startswith("ifrs-full_")]
    for r in rows:
        if r.get("account_id") in ids and (sj is None or r.get("sj_div") in sj):
            v = _amt(r.get(field))
            if v is not None:
                return v
    return None


def extract(rows, fs, annual):
    """보고서 rows → 금액 dict. 손익·현금흐름은 **당해 누적**(분기보고서는 thstrm_add_amount).

    지배 태그를 안 쓰는 회사가 있다(유한양행: 자본총계·비지배지분만 공시) →
      eq = 지배자본 태그, 없으면 자본총계 − 비지배지분
      ni = 지배순이익 태그, 없으면 당기순이익 − 비지배순이익
    rev·oi·ocf·assets·fc 는 퀄리티 필터용 (매출·영업이익·영업현금흐름·자산·금융비용).
    """
    IS = ("IS", "CIS")

    def flow(ids, sj=IS):
        f = "thstrm_amount" if annual else "thstrm_add_amount"
        v = _pick(rows, ids, f, sj)
        if v is None and not annual:     # 1분기는 add_amount 를 비워두는 회사가 있다
            v = _pick(rows, ids, "thstrm_amount", sj)
        return v

    stock = lambda ids: _pick(rows, ids, "thstrm_amount", ("BS",))
    ni = flow(NI_IDS[fs])
    if ni is None and fs == "CFS":
        tot, nci = flow(["ifrs-full_ProfitLoss"]), flow(["ifrs-full_ProfitLossAttributableToNoncontrollingInterests"])
        ni = None if tot is None else tot - (nci or 0)
    eq = stock(EQ_IDS[fs])
    if eq is None and fs == "CFS":
        tot, nci = stock(["ifrs-full_Equity"]), stock(["ifrs-full_NoncontrollingInterests"])
        eq = None if tot is None else tot - (nci or 0)
    # 현금흐름표는 분기보고서도 thstrm_amount 가 누적이다 (add_amount 를 안 쓴다)
    ocf = _pick(rows, ["ifrs-full_CashFlowsFromUsedInOperatingActivities"], "thstrm_amount", ("CF",))
    # 두산밥캣(USD)·GRT(CNY)처럼 원화가 아닌 통화로 공시하는 회사가 있다 — 원화 시총과 나누면 PBR 930배가 된다.
    cur = next((r.get("currency") for r in rows if r.get("currency")), "KRW")
    return {"ni": ni, "eq": eq, "eps": flow(EPS_IDS),
            "rev": flow(["ifrs-full_Revenue"]) if flow(["ifrs-full_Revenue"]) is not None else flow(["ifrs-full_RevenueFromContractsWithCustomers"]), "oi": flow(["dart_OperatingIncomeLoss"]),
            "ocf": ocf, "assets": stock(["ifrs-full_Assets"]), "fc": flow(["ifrs-full_FinanceCosts"]),
            # 2026-11-24 매수 매력 순위용: 전체 순이익(→ 지배주주 몫 비율 — 지주회사 연결 이익 과대 방지) · 설비투자(→ FCF)
            "ni_tot": flow(["ifrs-full_ProfitLoss"]),
            "fi": flow(["ifrs-full_FinanceIncome"]),
            # 주주환원 (코리아 디스카운트의 핵심) — 현금흐름표 누적, 지급액은 양수로 공시되는 경우가 대부분
            "div": _pick(rows, ["ifrs-full_DividendsPaidClassifiedAsFinancingActivities", "ifrs-full_DividendsPaidClassifiedAsOperatingActivities"], "thstrm_amount", ("CF",)),
            "buyback": _pick(rows, ["dart_AcquisitionOfTreasuryShares"], "thstrm_amount", ("CF",)),   # 금융수익 — 금융비용의 외환·파생 손실과 상계해 순금융비용을 본다
            "capex": _pick(rows, ["ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"], "thstrm_amount", ("CF",)),
            "currency": cur}


DARTLAB_URL = "https://huggingface.co/datasets/eddmpython/dartlab-data/resolve/main/dart/finance/{code}.parquet"
DARTLAB_CACHE = ROOT / "data" / ".cache" / "dartlab"


def dartlab_reports(code):
    """dartlab(HuggingFace, CC-BY-4.0) 미러 — DART fnlttSinglAcntAll 원본 행을 종목별로 모은 파일.
    2026-11-23 실측: 삼성전자·나이스정보통신 각 27개 보고서의 지배순이익·지배자본이 직접 호출과 100% 일치.
    {(bsns_year, reprt_code, fs_div): rows}. 실패하면 {} — 호출부가 DART API로 메운다."""
    import time
    import urllib.request
    import pandas as pd
    DARTLAB_CACHE.mkdir(parents=True, exist_ok=True)
    p = DARTLAB_CACHE / f"{code}.parquet"
    if not p.exists() or time.time() - p.stat().st_mtime > 86400:
        try:
            urllib.request.urlretrieve(DARTLAB_URL.format(code=code), p)
        except Exception as e:
            print(f"    [dartlab] {code} 다운로드 실패: {e}", file=sys.stderr)
            return {}
    try:
        raw = pd.read_parquet(p)
    except Exception as e:
        print(f"    [dartlab] {code} 읽기 실패: {e}", file=sys.stderr)
        return {}
    if not {"fs_div", "reprt_code", "bsns_year"} <= set(raw.columns):   # 재무 없는 회사는 스키마가 다르다
        return {}
    df = raw.dropna(subset=["fs_div", "reprt_code"])
    out = {k: g.to_dict("records") for k, g in df.groupby(["bsns_year", "reprt_code", "fs_div"])}
    # 미러가 '없음'을 확인해 준 범위 — 이 보고서들은 DART에 다시 묻지 않는다 (상장 전 기간 등).
    # 2026-11-23: 이걸 안 하니 비유니버스 종목에서 종목당 DART 호출이 ~5건 나가 한도에 근접했다.
    rev = {v: k for k, v in REPORTS.items()}
    have = sorted(f"{y}{rev[r]}" for y, r, _ in out if r in rev)
    out["_first"] = have[0] if have else None
    out["_nodata"] = {f"{y}{rev[r]}" for y, r in
                      raw[raw.get("collect_status") == "no_data"][["bsns_year", "reprt_code"]].dropna().itertuples(index=False)
                      if r in rev} if "collect_status" in raw else set()
    return out


def from_dartlab(reports, stac):
    """미러에서 추출. 미러가 '없음'을 보증하면 status 013 을 돌려 DART 호출을 생략한다."""
    if stac in reports.get("_nodata", ()) or (reports.get("_first") and stac < reports["_first"]):
        return {"status": "013", "src": "dartlab"}
    y, m = stac[:4], stac[4:]
    for fs in ("CFS", "OFS"):
        rows = reports.get((y, REPORTS[m], fs))
        if rows:
            v = extract(rows, fs, m == "12")
            if v["ni"] is not None or v["eq"] is not None:
                return {**v, "fs": fs, "status": "000", "src": "dartlab"}
    return None


def fetch(corp, stac):
    y, m = int(stac[:4]), stac[4:]
    last = {}
    for fs in ("CFS", "OFS"):
        j = feeds.dart_json("fnlttSinglAcntAll.json", corp_code=corp, bsns_year=y,
                            reprt_code=REPORTS[m], fs_div=fs)
        st = j.get("status")
        if st == "020":                       # 사용한도 초과 — 계속 돌면 차단된다
            sys.exit(f"[ERROR] DART 사용한도 초과(020): {j.get('message')}")
        if st == "000" and j.get("list"):
            return {**extract(j["list"], fs, m == "12"), "fs": fs, "status": st}
        last = {"status": st}
    return last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes-file", default=str(ROOT / "data" / "universe.json"))
    ap.add_argument("--no-api", action="store_true",
                    help="미러 추출만 (DART 호출 안 함) — 여러 프로세스로 병렬 실행할 때. 빈 곳은 나중에 API 모드로 한 번 더")
    ap.add_argument("--shard", default="0/1", help="i/n — 종목을 n등분한 i번째만 (병렬 실행용)")
    ap.add_argument("--reextract", action="store_true",
                    help="받아 둔 dartlab 파일에서 전 보고서를 다시 추출 (추출 규칙을 바꿨을 때, 네트워크 거의 없음)")
    args = ap.parse_args()
    doc_in = json.load(open(args.codes_file, encoding="utf-8"))
    stocks = doc_in.get("stage1") or doc_in.get("stocks") or doc_in["passed"]   # 1단계 전체를 받는다 (검증이 이 데이터를 쓴다)
    cmap = json.load(open(CORPMAP, encoding="utf-8"))
    si, sn = map(int, args.shard.split("/"))
    stocks = stocks[si::sn]
    OUT.mkdir(parents=True, exist_ok=True)

    today = date.today()
    due = ttm.latest_due_stac(today)
    stacs = [f"{y}{m}" for y in range(START_YEAR, today.year + 1) for m in REPORTS
             if f"{y}{m}" <= due]
    print(f"[dart-q] {len(stocks)}종목 × 최대 {len(stacs)}개 보고서 ({stacs[0]}~{due})")

    calls = 0
    for i, s in enumerate(stocks):
        code = s["code"]
        corp = cmap.get(code)
        p = OUT / f"{code}.json"
        doc = json.load(open(p, encoding="utf-8")) if p.exists() else \
            {"code": code, "name": s.get("name"), "corp_code": corp, "series": {}}
        if not corp:
            doc["error"] = "corp_code 없음"
            p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            continue
        ser = doc["series"]
        need = stacs if args.reextract else [
            st for st in stacs
            # 받았으면 건너뜀. 단 '없음(013)'이 최근 분기면 늦은 공시일 수 있어 다시 본다.
            if not (ser.get(st) and (ser[st].get("status") == "000" or st < due))]
        reports = dartlab_reports(code) if need else {}
        for st in need:
            got = from_dartlab(reports, st)
            if got:
                ser[st] = got
                continue
            if (args.reextract or args.no_api) and ser.get(st):   # 미러에 없고 이미 받은 값이 있으면 유지
                continue
            if args.no_api:
                continue
            ser[st] = fetch(corp, st)        # 미러에 없는 보고서만 DART 직접 호출
            calls += 1
        p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        if (i + 1) % 20 == 0 or i + 1 == len(stocks):
            print(f"  [{i+1:>3}/{len(stocks)}] {code} {s.get('name')} · 누적 호출 {calls}", flush=True)
    print(f"DONE · 호출 {calls}")


if __name__ == "__main__":
    main()
