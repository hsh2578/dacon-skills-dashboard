"""data/universe.json 의 종목들을 한 프로세스 안에서 일괄 페치.

subprocess 방식보다 빠름:
  - KRX 로그인 1회만
  - pykrx import 1회만
  - 종목당 ~4-7초 → ~3-5초로 단축
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


def _load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


PROJECT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = PROJECT / "scripts"
UNIVERSE = PROJECT / "data" / "universe.json"
DATA_DIR = PROJECT / "data" / "stocks"
DATA_DIR.mkdir(parents=True, exist_ok=True)

_load_env(PROJECT / ".env")
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
    sys.stderr.write("[ERROR] KRX_ID / KRX_PW 미설정. .env 확인.\n")
    sys.exit(2)

import pandas as pd
from pykrx import stock

sys.path.insert(0, str(SCRIPT_DIR))
from naver_consensus import fetch_naver_data  # noqa: E402
from incremental import (read_existing, get_incremental_start,  # noqa: E402
                          merge_timeseries, regenerate_stocks_manifest)

try:
    import FinanceDataReader as fdr
    _HAS_FDR = True
except ImportError:
    _HAS_FDR = False

SERIES_FIELDS = ["per", "pbr", "div_yield", "close", "market_cap"]
REQUEST_DELAY = 0.3


def _to_list(s, ndigits=2):
    return [None if pd.isna(v) else round(float(v), ndigits) for v in s]


def _to_int_list(s):
    return [None if pd.isna(v) else int(round(float(v))) for v in s]


def fetch_one(code: str, start: str, end: str, name_hint: str = None) -> dict:
    name = name_hint
    if not name:
        try:
            name = stock.get_market_ticker_name(code)
        except Exception:
            name = code

    fund = stock.get_market_fundamental_by_date(start, end, code)
    cap = stock.get_market_cap_by_date(start, end, code)
    df = fund.join(cap[["시가총액", "상장주식수"]], how="inner").reset_index()
    date_col = df.columns[0]
    df["date_dt"] = pd.to_datetime(df[date_col])
    df["date"] = df["date_dt"].dt.strftime("%Y-%m-%d")
    df["market_cap_억원"] = df["시가총액"] / 100_000_000

    if _HAS_FDR:
        try:
            px = fdr.DataReader(code, start, end)
            if not px.empty and "Close" in px.columns:
                px = px["Close"].copy()
                px.index = pd.to_datetime(px.index)
                df = df.set_index("date_dt").join(
                    px.rename("close_adj"), how="left"
                ).reset_index().drop(columns=["date_dt"])
                df["종가"] = df["close_adj"]
            else:
                df["종가"] = df["시가총액"] / df["상장주식수"]
        except Exception:
            df["종가"] = df["시가총액"] / df["상장주식수"]
    else:
        df["종가"] = df["시가총액"] / df["상장주식수"]

    naver = fetch_naver_data(code)

    return {
        "name": name,
        "ticker": code,
        "market": "KR",
        "frequency": "daily",
        "dates": df["date"].tolist(),
        "per": _to_list(df["PER"]),
        "pbr": _to_list(df["PBR"]),
        "div_yield": _to_list(df["DIV"]),
        "close": _to_int_list(df["종가"]),
        "market_cap": _to_int_list(df["market_cap_억원"]),
        "market_cap_unit": "억원",
        "price_unit": "원",
        "forward": naver.get("forward", {}),
        "consensus": naver.get("consensus", {"summary": {}, "brokers": []}),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--full", action="store_true",
                    help="기존 데이터 무시하고 풀 재수집")
    ap.add_argument("--from-screen", type=str, default=None,
                    help="data/screens/{name}.json의 Top N 종목 페치")
    ap.add_argument("--top-n", type=int, default=10,
                    help="--from-screen 사용 시 Top N (기본 10)")
    args = ap.parse_args()

    if args.from_screen:
        screen_path = PROJECT / "data" / "screens" / f"{args.from_screen}.json"
        if not screen_path.exists():
            sys.stderr.write(f"[ERROR] {screen_path} 없음\n")
            sys.exit(2)
        screen = json.loads(screen_path.read_text(encoding="utf-8"))
        ranked = screen.get("top") or screen.get("all_ranked") or []
        stocks = [{"code": r["code"], "name": r["name"]} for r in ranked[: args.top_n]]
    else:
        universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
        stocks = universe.get("stocks") or universe.get("passed") or []
        if args.limit:
            stocks = stocks[: args.limit]

    total = len(stocks)
    print(f"[batch-inline] {total}개 종목 페치 시작 (delay {REQUEST_DELAY}s)")

    end_dt = datetime.now()
    end = end_dt.strftime("%Y%m%d")
    full_start = (end_dt - timedelta(days=365 * 10 + 30)).strftime("%Y%m%d")

    success, failed = 0, []
    t0 = time.time()

    for i, s in enumerate(stocks):
        code, name = s["code"], s["name"]
        elapsed = time.time() - t0
        eta = (elapsed / max(i, 1)) * (total - i) if i > 0 else 0
        print(f"[{i+1:>3}/{total}] {name:<14} ({code})  "
              f"경과 {elapsed:.0f}s · ETA {eta:.0f}s", flush=True)

        out = DATA_DIR / f"{code}.json"
        existing = None if args.full else read_existing(out)
        start = get_incremental_start(out) if not args.full else full_start

        try:
            new = fetch_one(code, start, end, name_hint=name)
            merged = merge_timeseries(existing, new, SERIES_FIELDS)
            out.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
            success += 1
        except Exception as e:
            failed.append({"code": code, "name": name, "error": str(e)[:200]})
            print(f"      ❌ FAIL: {str(e)[:150]}")

        if i < total - 1:
            time.sleep(REQUEST_DELAY)

    n = regenerate_stocks_manifest(DATA_DIR)
    elapsed = time.time() - t0
    print(f"\n[batch-inline] 완료. 성공 {success}/{total} · 실패 {len(failed)} · "
          f"소요 {elapsed:.0f}s ({elapsed/60:.1f}분) · 매니페스트 {n}개")
    if failed:
        print("\n  실패 종목:")
        for f in failed[:10]:
            print(f"    {f['name']} ({f['code']}): {f['error'][:120]}")


if __name__ == "__main__":
    main()
