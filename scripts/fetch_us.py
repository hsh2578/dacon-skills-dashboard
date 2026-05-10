"""S&P 500 (multpl 월별 PER/PBR/배당 + yfinance ^GSPC 종가) → data/sp500.json

이전 프로젝트(주식 per pbr차트/scripts/fetch_us.py)의 검증된 패턴 그대로.
"""
import io
import json
import re
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
    # PBR은 multpl이 by-month를 사실상 제공 안 함 → by-year로 받아 월 단위로 forward fill
    "pbr": "https://www.multpl.com/s-p-500-price-to-book/table/by-year",
    "div_yield": "https://www.multpl.com/s-p-500-dividend-yield/table/by-month",
}


def _fetch_multpl(url: str) -> pd.Series:
    """multpl 테이블을 직접 파싱. pd.read_html은 multpl의 rowspan 구조를 잘못 해석함."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    # 모든 <tr>의 첫 td(date)와 두 번째 td(value, 내부에 <abbr> 등 포함 가능) 추출
    row_pattern = re.compile(
        r"<tr[^>]*>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>",
        re.IGNORECASE | re.DOTALL,
    )
    raw_rows = []
    for m in row_pattern.finditer(resp.text):
        date_txt = m.group(1).strip()
        val_txt = m.group(2).strip()
        if not date_txt or not val_txt:
            continue
        # value 정리 (%, ,, †, 공백 제거 후 숫자만 추출)
        clean = val_txt.replace("%", "").replace(",", "").replace("†", "").strip()
        num_m = re.search(r"-?\d+\.?\d*", clean)
        if not num_m:
            continue
        try:
            v = float(num_m.group(0))
        except ValueError:
            continue
        raw_rows.append((date_txt, v))
    if not raw_rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(raw_rows, columns=["date", "value"])
    # pandas to_datetime이 'Apr 1, 2026' 같은 single-day 형식을 못 잡으므로 dateutil 사용
    from dateutil import parser as _dateparser
    def _parse(s):
        try:
            return _dateparser.parse(s)
        except (ValueError, TypeError):
            return pd.NaT
    df["date"] = df["date"].apply(_parse)
    df = df.dropna(subset=["date"])
    return df.set_index("date")["value"].sort_index()


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

    # PER, div_yield는 월별. PBR은 연 1회. close는 월별.
    # 월 인덱스로 통일하고, PBR은 forward fill로 매월 채움.
    df = pd.DataFrame({"per": metrics["per"], "div_yield": metrics["div_yield"]})
    df["close"] = close
    df = df.sort_index().dropna(subset=["per", "div_yield"], how="all")
    pbr_yearly = metrics["pbr"].sort_index()
    df["pbr"] = pbr_yearly.reindex(df.index, method="ffill")

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
