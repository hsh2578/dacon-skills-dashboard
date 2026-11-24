"""S&P 500 (multpl 월별 PER/PBR/배당 + 종가) → data/sp500.json

종가는 **FRED(공식 St. Louis Fed, `FRED_API_KEY`) 우선**, 실패/부재 시 yfinance ^GSPC 폴백.
PER/PBR/배당수익률은 FRED가 제공하지 않으므로 multpl 스크래핑 유지 (FRED는 가격선 robustness만).
meta.close_source에 실제 사용한 소스("FRED"/"yfinance") 기록.
이전 프로젝트(주식 per pbr차트/scripts/fetch_us.py)의 검증된 패턴 기반.
"""
import io
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

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
    """multpl 테이블을 BeautifulSoup으로 직접 파싱.
    pd.read_html이 rowspan/abbr 등을 잘못 해석하는 문제를 회피.
    """
    from bs4 import BeautifulSoup
    from dateutil import parser as _dateparser

    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    raw_rows = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) != 2:
            continue
        date_txt = tds[0].get_text(strip=True)
        val_txt = tds[1].get_text(strip=True)
        if not date_txt or not val_txt:
            continue
        # value: %, ,, † 제거 후 첫 숫자 추출
        clean = val_txt.replace("%", "").replace(",", "").replace("†", "").strip()
        num_m = re.search(r"-?\d+\.?\d+|-?\d+", clean)
        if not num_m:
            continue
        try:
            v = float(num_m.group(0))
        except ValueError:
            continue
        # date: dateutil로 안전 파싱
        try:
            dt = _dateparser.parse(date_txt)
        except (ValueError, TypeError):
            continue
        raw_rows.append((dt, v))

    if not raw_rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(raw_rows, columns=["date", "value"])
    return df.set_index("date")["value"].sort_index()


def _to_month_end(series: pd.Series) -> pd.Series:
    series = series.copy()
    series.index = series.index.to_period("M").to_timestamp("M")
    return series.groupby(series.index).last()


def _fetch_fred_sp500_monthly(api_key: str, years: int) -> pd.Series:
    """FRED SP500(공식 S&P 500 지수, 일별)을 월말 종가 시계열로. 약 10년 제공."""
    start = (datetime.now() - timedelta(days=years * 366 + 30)).strftime("%Y-%m-%d")
    url = (
        "https://api.stlouisfed.org/fred/series/observations?series_id=SP500"
        f"&api_key={api_key}&file_type=json&observation_start={start}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    obs = resp.json().get("observations", [])
    rows = [(o["date"], float(o["value"])) for o in obs
            if o.get("value") not in (".", "", None)]
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series([v for _, v in rows], index=pd.to_datetime([d for d, _ in rows]))
    s.index = s.index.to_period("M").to_timestamp("M")
    return s.groupby(s.index).last()


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

    # close: FRED(공식) 우선, 실패/부재 시 yfinance 폴백
    close = pd.Series(dtype=float)
    close_source = "yfinance"
    fred_key = os.environ.get("FRED_API_KEY")
    if fred_key:
        try:
            print("  FRED SP500", flush=True)
            close = _fetch_fred_sp500_monthly(fred_key, years)
            if not close.empty:
                close_source = "FRED"
        except Exception as e:
            print(f"  FRED 실패 → yfinance 폴백: {e}", flush=True)
    if close.empty:
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
        "close_source": close_source,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def main():
    load_env(ENV_PATH)
    print("[sp500]")
    sp500 = fetch_sp500_monthly(10)
    out = DATA_DIR / "sp500.json"
    out.write_text(json.dumps(sp500, ensure_ascii=False), encoding="utf-8")
    print(f"  → sp500.json ({len(sp500['dates'])}건)")


if __name__ == "__main__":
    main()
