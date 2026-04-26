"""S&P 500 (multpl 월별 PER/PBR/배당 + yfinance ^GSPC 종가) → data/sp500.json

이전 프로젝트(주식 per pbr차트/scripts/fetch_us.py)의 검증된 패턴 그대로.
"""
import io
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

MULTPL_URLS = {
    "per": "https://www.multpl.com/s-p-500-pe-ratio/table/by-month",
    "pbr": "https://www.multpl.com/s-p-500-price-to-book/table/by-month",
    "div_yield": "https://www.multpl.com/s-p-500-dividend-yield/table/by-month",
}


def _fetch_multpl(url: str) -> pd.Series:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    df = pd.read_html(io.StringIO(resp.text))[0]
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = (
        df["value"].astype(str)
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("†", "", regex=False)
        .str.strip()
        .str.extract(r"(-?\d+\.?\d*)")[0]
    )
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().set_index("date")["value"].sort_index()


def _to_month_end(series: pd.Series) -> pd.Series:
    series = series.copy()
    series.index = series.index.to_period("M").to_timestamp("M")
    return series.groupby(series.index).last()


def _fetch_yf_close_monthly(ticker: str, years: int) -> pd.Series:
    end = datetime.now()
    start = end - timedelta(days=years * 366 + 30)
    px = yf.download(ticker, start=start, end=end, interval="1mo",
                     progress=False, auto_adjust=False)
    if px is None or px.empty:
        return pd.Series(dtype=float)
    if isinstance(px.columns, pd.MultiIndex):
        px.columns = [c[0] for c in px.columns]
    s = px["Close"].copy()
    s.index = pd.to_datetime(s.index).to_period("M").to_timestamp("M")
    return s


def _to_list(series, ndigits=2):
    return [None if pd.isna(v) else round(float(v), ndigits) for v in series]


def fetch_sp500_monthly(years: int = 10) -> dict:
    cutoff = pd.Timestamp(datetime.now() - timedelta(days=years * 366))

    metrics = {}
    for key, url in MULTPL_URLS.items():
        print(f"  multpl/{key}", flush=True)
        s = _fetch_multpl(url)
        s = _to_month_end(s[s.index >= cutoff])
        metrics[key] = s

    print("  yfinance ^GSPC", flush=True)
    close = _fetch_yf_close_monthly("^GSPC", years)

    df = pd.DataFrame(metrics)
    df["close"] = close
    df = df.sort_index().dropna(subset=["per", "pbr", "div_yield"], how="all")

    return {
        "name": "S&P 500",
        "ticker": "^GSPC",
        "frequency": "monthly",
        "dates": df.index.strftime("%Y-%m-%d").tolist(),
        "per": _to_list(df["per"]),
        "pbr": _to_list(df["pbr"]),
        "div_yield": _to_list(df["div_yield"]),
        "close": _to_list(df["close"]),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def main():
    print("[sp500]")
    sp500 = fetch_sp500_monthly(10)
    out = DATA_DIR / "sp500.json"
    out.write_text(json.dumps(sp500, ensure_ascii=False), encoding="utf-8")
    print(f"  → sp500.json ({len(sp500['dates'])}건)")


if __name__ == "__main__":
    main()
