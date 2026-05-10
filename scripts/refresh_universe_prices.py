"""universe.json의 close 필드만 직전 거래일 종가로 빠르게 갱신.

`/update-data` 기본 모드에서 universe.json은 갱신되지 않으나, 그 안의 close 필드를
apply_triple_cross.py가 사용하므로 stale되면 Top 10의 current_price와 upside가
옛 가격 기준으로 산출되는 버그를 막기 위한 보조 스크립트.

시장 일괄 호출 2회(KOSPI/KOSDAQ)로 약 30초 소요.
fetch_universe.py 전체 재실행(약 15분)을 대체한다.
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
UNIVERSE_PATH = ROOT / "data" / "universe.json"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def find_latest_business_day(stock_module, max_lookback: int = 10) -> str:
    """오늘부터 거꾸로 거슬러 가장 최근 거래일을 찾는다."""
    today = datetime.today()
    for i in range(max_lookback):
        d = (today - timedelta(days=i)).strftime("%Y%m%d")
        df = stock_module.get_market_ohlcv_by_ticker(d, market="KOSPI")
        if not df.empty and df["종가"].sum() > 0:
            return d
    raise RuntimeError(f"최근 {max_lookback}일 내 거래일을 찾지 못했습니다.")


def fetch_market_close_prices(stock_module, date: str) -> dict:
    """KOSPI + KOSDAQ 전체 종목의 종가를 한 번에 페치."""
    prices = {}
    for market in ("KOSPI", "KOSDAQ"):
        df = stock_module.get_market_ohlcv_by_ticker(date, market=market)
        for code, row in df.iterrows():
            close = int(row["종가"])
            if close > 0:
                prices[code] = close
    return prices


def main():
    load_env(ENV_PATH)
    if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
        sys.stderr.write("[ERROR] KRX_ID / KRX_PW 미설정. .env 확인.\n")
        sys.exit(1)

    if not UNIVERSE_PATH.exists():
        sys.stderr.write(f"[ERROR] {UNIVERSE_PATH} 미존재. 먼저 fetch_universe.py 실행.\n")
        sys.exit(1)

    from pykrx import stock

    # 1. 최근 거래일 탐색
    target_date = find_latest_business_day(stock)
    print(f"[refresh-prices] 기준 거래일: {target_date}")

    # 2. 시장 일괄 종가 페치
    prices = fetch_market_close_prices(stock, target_date)
    print(f"[refresh-prices] 유효 종가 페치: {len(prices)}종목")

    # 3. universe.json의 passed 배열 close 갱신
    with UNIVERSE_PATH.open(encoding="utf-8") as f:
        universe = json.load(f)

    passed = universe.get("passed", [])
    updated, missing = 0, 0
    for s in passed:
        code = s["code"]
        if code in prices:
            old = s.get("close")
            new = prices[code]
            s["close"] = new
            if old != new:
                updated += 1
        else:
            missing += 1

    universe.setdefault("meta", {})["price_updated_at"] = (
        datetime.now().isoformat(timespec="seconds")
    )
    universe["meta"]["price_reference_date"] = target_date

    with UNIVERSE_PATH.open("w", encoding="utf-8") as f:
        json.dump(universe, f, ensure_ascii=False, indent=2)

    print(
        f"[refresh-prices] 갱신: {updated}건 변경 / {len(passed) - missing}건 매칭 / "
        f"{missing}건 누락"
    )
    print(f"[refresh-prices] → {UNIVERSE_PATH.relative_to(ROOT)} (price_reference_date={target_date})")


if __name__ == "__main__":
    main()
