"""일별 PER·PBR (시가총액 / DART 금액) → data/.cache/daily/{code}.json + 월별 매트릭스.

    PER = (보통주+우선주 시총) / TTM 지배주주 순이익      (순이익 ≤ 0 이면 None)
    PBR = (보통주+우선주 시총) / 최근 공시 분기 지배주주 자본  (자본 ≤ 0 이면 None)

주당 값을 쓰지 않으므로 액면분할·무상증자·병합의 영향을 받지 않는다.
공시 시차·0=결측·연간 폴백 금지는 ttm.py 규칙을 그대로 쓴다.

입력: data/.cache/_krx_mcap_daily.json (fetch_mcap_daily.py), data/financials_q/ (fetch_dart_quarterly.py)
출력: data/.cache/daily/{code}.json {dates, mcap, per, pbr, stac}   — 전 종목 일별 (사이트엔 Top N 만 data/daily/ 로 복사)
      data/matrix/{per,pbr}_monthly.json  (정식 — 사이트·4팩터가 읽음)  {meta, matrix:{code:{YYYYMMDD(월말): 월평균}}}
"""
import json, os, sys
from datetime import date
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ttm  # noqa: E402

MCAP = ROOT / "data" / ".cache" / "_krx_mcap_daily.json"
FQ = ROOT / "data" / "financials_q"
DAILY = ROOT / "data" / ".cache" / "daily"   # 전 종목(~2,700, 130MB+) — 사이트용 Top N 사본은 apply_triple_cross 가 data/daily/ 로 복사
MATRIX = ROOT / "data" / "matrix"
PREF_SUFFIX = set("5789KLMN")   # 우선주 코드 끝자리 (보통주 = 0)


def pref_map(codes) -> dict:
    """{보통주코드: [같은 발행사 우선주 코드…]} — 한 번만 만든다 (매일 전 종목을 훑으면 10^10 연산).
    ponytail: 앞 5자리가 같은 코드를 같은 발행사로 본다 — 신형 영문 코드 체계에서 틀리면 종목명 매칭으로 바꿀 것."""
    out = {}
    for c in codes:
        if c[5] in PREF_SUFFIX:
            out.setdefault(c[:5] + "0", []).append(c)
    return out


def company_mcap(day: dict, code: str, prefs: dict = None):
    """보통주 + 같은 발행사 우선주 시총."""
    base = day.get(code)
    if not base:
        return None
    if prefs is None:
        prefs = pref_map(day)
    return base + sum(day.get(p, 0) for p in prefs.get(code, ()))


def valuation_series(series: dict, dates: list, mcaps: list):
    """일별 (per, pbr, stac). series = {stac: {ni, eq}} — status 000 만 넘길 것."""
    out = []
    cache = {}
    for ds, mc in zip(dates, mcaps):
        st = ttm.disclosed_stac(series, ds)
        if st not in cache:
            ni = ttm.ttm_eps(series, st, "ni") if st else None
            eq = ttm.amount((series.get(st) or {}).get("eq")) if st else None
            cache[st] = (ni, eq)
        ni, eq = cache[st]
        per = mc / ni if (mc and ni and ni > 0) else None
        pbr = mc / eq if (mc and eq and eq > 0) else None
        out.append((per, pbr, st))
    return out


def main():
    mc_all = json.load(open(MCAP, encoding="utf-8"))
    cl_path = ROOT / "data" / ".cache" / "_krx_close_daily.json"
    cl_all = json.load(open(cl_path, encoding="utf-8")) if cl_path.exists() else {}
    days = sorted(d for d, v in mc_all.items() if v)
    prefs = pref_map({c for d in days for c in mc_all[d]})
    DAILY.mkdir(parents=True, exist_ok=True)
    per_m, pbr_m = {}, {}
    n = 0
    for p in sorted(FQ.glob("*.json")):
        doc = json.load(open(p, encoding="utf-8"))
        code = doc["code"]
        # ponytail: 원화 외 통화(두산밥캣 USD·GRT CNY, 2026-11 기준 2종목) 보고서는 버린다 → PER/PBR 없음.
        # 늘어나면 FRED 환율(DEXKOUS 등)로 환산할 것.
        # 최신 보고서가 외화면 종목 전체 제외 — 옛 원화 보고서만 남기면 몇 년 전 실적으로 PER이 나온다.
        series = {k: v for k, v in doc.get("series", {}).items() if v.get("status") == "000"}
        if not series or series[max(series)].get("currency", "KRW") != "KRW":
            (DAILY / f"{code}.json").unlink(missing_ok=True)
            continue
        series = {k: v for k, v in series.items() if v.get("currency", "KRW") == "KRW"}
        dates, mcaps = [], []
        for d in days:
            m = company_mcap(mc_all[d], code, prefs)
            if m:
                dates.append(d)
                mcaps.append(m)
        vals = valuation_series(series, dates, mcaps)
        r = lambda x, k=2: None if x is None else round(x, k)
        (DAILY / f"{code}.json").write_text(json.dumps({
            "code": code, "name": doc.get("name"), "dates": dates,
            "mcap_억": [round(m / 1e8) for m in mcaps],
            "close": [(cl_all.get(d) or {}).get(code) for d in dates],   # 원주가 종가
            "per": [r(v[0]) for v in vals], "pbr": [r(v[1], 3) for v in vals],
            "stac": [v[2] for v in vals],
        }, ensure_ascii=False), encoding="utf-8")
        # 월평균 (최신 달은 최신 거래일 값 — fetch_matrix_kis 와 같은 규칙)
        by = {}
        for d, (per, pbr, _) in zip(dates, vals):
            by.setdefault(d[:6], []).append((d, per, pbr))
        last_ym = max(by) if by else None
        for ym, rows in by.items():
            key = max(x[0] for x in rows)
            for idx, mat in ((1, per_m), (2, pbr_m)):
                xs = [x[idx] for x in rows if x[idx] is not None]
                if ym == last_ym:
                    xs = [rows[-1][idx]] if rows[-1][idx] is not None else []
                mat.setdefault(code, {})[key] = round(sum(xs) / len(xs), 4) if xs else None
        n += 1
    meta = {"method": "mcap(common+pref) / DART TTM controlling NI · equity", "built_at": date.today().isoformat(),
            "count": n}
    for nm, mat in (("per", per_m), ("pbr", pbr_m)):
        (MATRIX / f"{nm}_monthly.json").write_text(
            json.dumps({"meta": meta, "matrix": mat}, ensure_ascii=False), encoding="utf-8")
    print(f"[valuation] {n}종목 → data/.cache/daily/, data/matrix/{{per,pbr}}_monthly.json")


if __name__ == "__main__":
    main()
