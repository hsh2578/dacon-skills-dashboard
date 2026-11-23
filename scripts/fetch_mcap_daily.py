"""KRX 일별 시가총액(전 종목, 우선주 포함) → data/.cache/_krx_mcap_daily.json  {YYYYMMDD: {code: 시총(원)}}

PER = (보통주+우선주 시총) / TTM 지배순이익 에 쓴다. 지배순이익은 우선주 주주 몫까지 포함하므로
분자도 우선주를 더해야 한다 (삼성전자: 우선주가 보통주 시총의 약 11%).

    python scripts/fetch_mcap_daily.py            # 기본 66개월
이어받기. 최근 7일의 빈 날은 다시 조회한다(KRX는 당일 데이터를 다음 날 공개).
"""
import argparse, json, os, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from feeds import krx, short_code  # noqa: E402

PATH = ROOT / "data" / ".cache" / "_krx_mcap_daily.json"
CLOSE = ROOT / "data" / ".cache" / "_krx_close_daily.json"   # 원주가 종가 — 백테스트 수익률용 (같은 호출에서 함께 저장)


def _f(x):
    try:
        return float(x or 0)
    except ValueError:
        return 0.0


def one_day(ds):
    out, cl = {}, {}
    for svc in ("sto/stk_bydd_trd", "sto/ksq_bydd_trd"):
        for r in krx(svc, ds):          # 실패는 예외로 올린다 — 빈 날로 굳히지 않는다
            c = short_code(r["ISU_CD"])
            if _f(r.get("MKTCAP")) > 0:
                out[c] = _f(r.get("MKTCAP"))
            if _f(r.get("TDD_CLSPRC")) > 0:
                cl[c] = _f(r.get("TDD_CLSPRC"))
    return ds, out, cl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=66)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    raw = json.load(open(PATH, encoding="utf-8")) if PATH.exists() else {}
    closes = json.load(open(CLOSE, encoding="utf-8")) if CLOSE.exists() else {}
    end = datetime.now()
    day = (end - timedelta(days=31 * a.months)).replace(day=1)
    todo = []
    while day <= end:
        ds = day.strftime("%Y%m%d")
        if day.weekday() < 5 and (ds not in raw or (raw[ds] and ds not in closes)
                                  or (not raw[ds] and (end - day).days < 7)):
            todo.append(ds)
        day += timedelta(days=1)
    print(f"[mcap] 수집 {len(todo)}일 (보유 {len(raw)}일)")
    fails = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(one_day, ds): ds for ds in todo}
        for i, f in enumerate(futs, 1):
            try:
                ds, c, cl = f.result()
                raw[ds], closes[ds] = c, cl
            except Exception as e:
                fails.append((futs[f], repr(e)[:80]))
            if i % 100 == 0 or i == len(todo):
                print(f"  [{i}/{len(todo)}] 실패 {len(fails)}", flush=True)
                PATH.write_text(json.dumps(raw), encoding="utf-8")
    PATH.write_text(json.dumps(raw), encoding="utf-8")
    CLOSE.write_text(json.dumps(closes), encoding="utf-8")
    if fails:
        sys.exit(f"[ERROR] {len(fails)}일 실패 (다시 실행하면 이어받음): {fails[:3]}")
    print("DONE")


if __name__ == "__main__":
    main()
