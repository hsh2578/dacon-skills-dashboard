"""한국 종목 일별 PER/PBR/시가총액/종가 + 컨센서스 → data/stocks/{code}.json

기본은 증분 갱신. --full 옵션 시 풀 10년 재수집.
"""
import argparse
import json
import os
import sys
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


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_load_env(_PROJECT_ROOT / ".env")

if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
    sys.stderr.write("[ERROR] KRX_ID / KRX_PW 미설정. .env 확인.\n")
    sys.exit(2)

import pandas as pd
from pykrx import stock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from naver_consensus import fetch_naver_data  # noqa: E402
from incremental import (read_existing, get_incremental_start,  # noqa: E402
                          merge_timeseries, diff_summary,
                          regenerate_stocks_manifest)

try:
    import FinanceDataReader as fdr
    _HAS_FDR = True
except ImportError:
    _HAS_FDR = False

DATA_DIR = _PROJECT_ROOT / "data" / "stocks"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SERIES_FIELDS = ["per", "pbr", "div_yield", "close", "market_cap"]


def _to_list(s, ndigits=2):
    return [None if pd.isna(v) else round(float(v), ndigits) for v in s]


def _to_int_list(s):
    return [None if pd.isna(v) else int(round(float(v))) for v in s]


def fetch_kr_stock(code: str, start: str, end: str) -> dict:

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

    print("  네이버 Wisereport 컨센서스 ...", flush=True)
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
    ap.add_argument("code", help="6자리 KR 종목코드")
    ap.add_argument("--full", action="store_true",
                    help="기존 데이터 무시하고 10년 풀 재수집")
    args = ap.parse_args()

    end_dt = datetime.now()
    end = end_dt.strftime("%Y%m%d")
    out = DATA_DIR / f"{args.code}.json"
    existing = None if args.full else read_existing(out)
    start = get_incremental_start(out) if not args.full else \
        (end_dt - timedelta(days=365 * 10 + 30)).strftime("%Y%m%d")

    mode = "FULL" if args.full or existing is None else "INCR"
    print(f"[KR/{args.code}/{mode}] {start}~{end} fetching...", flush=True)
    new = fetch_kr_stock(args.code, start, end)
    merged = merge_timeseries(existing, new, SERIES_FIELDS)
    out.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
    s = diff_summary(existing, merged)
    print(f"  → {out.relative_to(_PROJECT_ROOT)} ({s['new_count']}건, "
          f"+{s['added']} added, last {s['new_last']}, {merged.get('name')})")

    n = regenerate_stocks_manifest(DATA_DIR)
    print(f"  → data/stocks/_index.json ({n}개 종목 매니페스트)")


if __name__ == "__main__":
    main()
