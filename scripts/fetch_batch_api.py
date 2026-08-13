"""Top N 종목 일별 풀 데이터 → data/stocks/{code}.json (pykrx 대체)

기존 `fetch_batch.py`는 종목마다 pykrx로 일별 시세·재무비율을 받았다(종목당 2~3콜,
data.krx.co.kr 스크래핑). 이 스크립트는 **새 API 호출을 거의 하지 않는다** —
fetch_matrix_kis.py가 이미 만들어 둔 캐시를 재사용한다:

    data/.cache/_krx_close_daily.json      전 종목 일별 종가 (원주가)
    data/.cache/_krx_shares_monthly.json   월별 상장주식수
    data/.cache/_kis_ratio_q_real.json     KIS 분기 EPS/BPS

네이버 컨센서스(forward/consensus 블록)만 종목당 1회 호출한다.

출력 스키마는 기존 fetch_batch.py와 동일하다 (stock.js가 그대로 읽는다).

값 정의
    close        수정주가. 액면분할 지점에서 차트가 끊기지 않도록 보정한 값
                 (네이버 차트와 같은 방식). 원주가는 분할 시 계단이 생긴다.
    market_cap   원주가 x 상장주식수 = 실제 시가총액. 시총은 분할과 무관하게
                 연속이므로 보정하지 않는다.
    per / pbr    수정주가 / TTM EPS, 수정주가 / BPS — 매트릭스와 같은 기준
    div_yield    전부 null. KRX·KIS가 일별 배당수익률을 주지 않는다.
                 stock.js는 이미 매트릭스 폴백 경로에서 null을 처리한다(stock.js:314).

기간은 캐시가 보유한 범위(약 5년)다. 기존 스크립트는 10년을 받았지만 매트릭스가
5년 기준이므로 일관성을 위해 캐시 범위를 따른다.
"""
import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "stocks"
CACHE_DIR = ROOT / "data" / ".cache"
SCREENS = ROOT / "data" / "screens"
UNIVERSE = ROOT / "data" / "universe.json"

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# TTM/공시시차 로직은 fetch_matrix_kis.py 것을 그대로 재사용 (중복 정의 방지)
_spec = importlib.util.spec_from_file_location(
    "_fmk", Path(__file__).resolve().parent / "fetch_matrix_kis.py")
_fmk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fmk)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from naver_consensus import fetch_naver_data  # noqa: E402


def _load(name):
    p = CACHE_DIR / name
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_caches():
    daily = _load("_krx_close_daily.json")
    if not daily:
        sys.exit("[ERROR] _krx_close_daily.json 없음. "
                 "fetch_matrix_kis.py --daily 를 먼저 실행하세요.")
    shares = _load("_krx_shares_monthly.json") or {}
    ratios = (_load("_kis_ratio_q_real.json") or _load("_kis_ratio_q_paper.json")
              or _load("_kis_ratio_q.json") or {})
    # 월별 주식수를 YYYYMM 키로 정규화
    shares_by_ym = {}
    for ds, m in shares.items():
        shares_by_ym[ds[:6]] = m
    return daily, shares_by_ym, ratios


def build_one(code, name, daily, shares_by_ym, ratios):
    dates = sorted(d for d in daily if daily[d].get(code))
    if not dates:
        return None
    series = ratios.get(code) or {}

    latest_ym = max(shares_by_ym) if shares_by_ym else None
    n_latest = (shares_by_ym.get(latest_ym) or {}).get(code) if latest_ym else None

    out_dates, out_close, out_cap, out_per, out_pbr = [], [], [], [], []
    for ds in dates:
        px = daily[ds][code]
        n_t = (shares_by_ym.get(ds[:6]) or {}).get(code)
        factor = (n_t / n_latest) if (n_t and n_latest and n_latest > 0) else 1.0
        px_adj = px * factor

        out_dates.append(f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}")
        out_close.append(int(round(px_adj)))
        out_cap.append(int(round(px * n_t / 100_000_000)) if n_t else None)

        stac = _fmk.pick_stac(series, ds) if series else None
        eps = _fmk.ttm_eps(series, stac) if stac else None
        bps = _fmk._amt((series.get(stac) or {}).get("bps")) if stac else None
        out_per.append(round(px_adj / eps, 2) if (eps and eps > 0) else None)
        out_pbr.append(round(px_adj / bps, 2) if (bps and bps > 0) else None)

    try:
        naver = fetch_naver_data(code) or {}
    except Exception as e:
        print(f"      [WARN] 컨센서스 실패: {str(e)[:80]}", file=sys.stderr)
        naver = {}

    return {
        "name": name,
        "ticker": code,
        "market": "KR",
        "frequency": "daily",
        "dates": out_dates,
        "per": out_per,
        "pbr": out_pbr,
        "div_yield": [None] * len(out_dates),
        "close": out_close,
        "market_cap": out_cap,
        "market_cap_unit": "억원",
        "price_unit": "원",
        "per_basis": "TTM (종가/최근4분기 EPS, 수정주가 기준)",
        "forward": naver.get("forward", {}),
        "consensus": naver.get("consensus", {"summary": {}, "brokers": []}),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def regenerate_manifest():
    items = []
    for p in sorted(DATA_DIR.glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        items.append({"code": d.get("ticker") or p.stem, "name": d.get("name"),
                      "updated_at": d.get("updated_at"),
                      "points": len(d.get("dates") or [])})
    (DATA_DIR / "_index.json").write_text(
        json.dumps({"count": len(items), "items": items,
                    "generated_at": datetime.now().isoformat(timespec="seconds")},
                   ensure_ascii=False), encoding="utf-8")
    return len(items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-screen", default="triple_cross")
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--codes", default=None, help="쉼표구분 종목코드 직접 지정")
    args = ap.parse_args()

    if args.codes:
        uni = json.loads(UNIVERSE.read_text(encoding="utf-8"))
        nm = {s["code"]: s["name"] for s in (uni.get("passed") or uni.get("stocks") or [])}
        stocks = [{"code": c.strip(), "name": nm.get(c.strip(), c.strip())}
                  for c in args.codes.split(",") if c.strip()]
    else:
        sp = SCREENS / f"{args.from_screen}.json"
        if not sp.exists():
            sys.exit(f"[ERROR] {sp} 없음. apply_triple_cross.py 를 먼저 실행하세요.")
        screen = json.loads(sp.read_text(encoding="utf-8"))
        ranked = screen.get("top") or screen.get("all_ranked") or []
        stocks = [{"code": r["code"], "name": r["name"]} for r in ranked[:args.top_n]]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    daily, shares_by_ym, ratios = load_caches()
    print(f"[batch-api] 캐시 일별 {len(daily)}일 · 주식수 {len(shares_by_ym)}개월 "
          f"· KIS {len(ratios)}종목")
    print(f"[batch-api] 대상 {len(stocks)}종목\n")

    ok, fail = 0, []
    for i, s in enumerate(stocks):
        code, name = s["code"], s["name"]
        print(f"  [{i+1:>2}/{len(stocks)}] {name} ({code})", flush=True)
        try:
            doc = build_one(code, name, daily, shares_by_ym, ratios)
            if not doc:
                fail.append((code, name, "일별 종가 없음"))
                continue
            (DATA_DIR / f"{code}.json").write_text(
                json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            per_ok = sum(1 for v in doc["per"] if v is not None)
            print(f"       {len(doc['dates'])}일 · PER 유효 {per_ok}")
            ok += 1
        except Exception as e:
            fail.append((code, name, str(e)[:150]))
            print(f"       실패: {str(e)[:120]}", file=sys.stderr)
        time.sleep(0.3)   # 네이버 호출 간격

    n = regenerate_manifest()
    print(f"\n[batch-api] 성공 {ok}/{len(stocks)} · manifest {n}종목")
    if fail:
        for c, nme, e in fail:
            print(f"  실패: {nme}({c}) — {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
