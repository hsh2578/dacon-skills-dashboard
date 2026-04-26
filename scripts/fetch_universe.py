"""시총 상위 N개 종목 마스터 → data/universe.json

KOSPI + KOSDAQ 시가총액 기준 상위 종목. CLAUDE.md 룰: 시총 2,000억 이상.
초기 MVP는 시연 위해 상위 50개부터 (실제 운영은 1,000+ 가능).
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

SPAC_PATTERN = re.compile(r'스팩|SPAC|기업인수목적', re.IGNORECASE)
REIT_PATTERN = re.compile(r'리츠|REIT|부동산투자', re.IGNORECASE)


def is_common_stock(code: str) -> bool:
    """보통주 = 코드 끝자리 0 (우선주는 5/7/9)"""
    return bool(code) and len(code) >= 6 and code[-1] == '0'


def is_spac(name: str) -> bool:
    return bool(SPAC_PATTERN.search(str(name or '')))


def is_reit(name: str) -> bool:
    return bool(REIT_PATTERN.search(str(name or '')))


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

# pykrx 한글 컬럼 처리를 위해 강제 utf-8
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

DATA_DIR = _PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
OUT = DATA_DIR / "universe.json"

MIN_MARKET_CAP_억 = 2000  # 2,000억 이상


def _resolve_business_date() -> str:
    """가장 최근 영업일 (휴장일이면 거꾸로 찾음).

    pykrx는 휴장일에도 빈 DataFrame이 아닌 시총=0 채워진 DataFrame을 반환할 수 있어
    시총 합산값으로 판정한다.
    """
    d = datetime.now()
    for _ in range(10):
        ds = d.strftime("%Y%m%d")
        df = stock.get_market_cap_by_ticker(ds, market="KOSPI")
        if df is not None and not df.empty and df["시가총액"].sum() > 0:
            return ds
        d -= timedelta(days=1)
    return datetime.now().strftime("%Y%m%d")


def get_universe(top_n=None, min_cap: int = MIN_MARKET_CAP_억) -> dict:
    business_date = _resolve_business_date()
    print(f"  기준일: {business_date}", flush=True)

    rows = []
    for market in ("KOSPI", "KOSDAQ"):
        cap_df = stock.get_market_cap_by_ticker(business_date, market=market)
        cap_df = cap_df.reset_index()  # 티커 컬럼화
        cap_df["시가총액_억"] = cap_df["시가총액"] / 100_000_000
        cap_df = cap_df[cap_df["시가총액_억"] >= min_cap].copy()
        cap_df["market"] = market
        rows.append(cap_df[["티커", "시가총액_억", "종가", "market"]])

    df = pd.concat(rows, ignore_index=True)
    df = df.sort_values("시가총액_억", ascending=False).reset_index(drop=True)

    universe = []
    excluded_pref, excluded_reit, excluded_spac = [], [], []
    for _, r in df.iterrows():
        code = r["티커"]
        try:
            name = stock.get_market_ticker_name(code)
        except Exception:
            name = code

        record = {
            "code": code,
            "name": name,
            "market": r["market"],
            "market_cap_억": int(round(float(r["시가총액_억"]))),
            "close": int(round(float(r["종가"]))),
        }

        # 종목 유형 분류
        if is_spac(name):
            excluded_spac.append(record)
            continue
        if is_reit(name):
            excluded_reit.append(record)
            continue
        if not is_common_stock(code):
            excluded_pref.append(record)
            continue

        universe.append(record)

    if top_n is not None:
        universe = universe[:top_n]

    return {
        "universe": universe,
        "excluded": {
            "preferred": excluded_pref,
            "reit": excluded_reit,
            "spac": excluded_spac,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=None,
                    help="상위 N개 (기본: 제한 없음 = 시총 조건 통과 전체)")
    ap.add_argument("--min-cap", type=int, default=MIN_MARKET_CAP_억,
                    help="최소 시가총액(억원, 기본 2000)")
    args = ap.parse_args()

    top_label = f"상위 {args.top}개" if args.top else "전체"
    print(f"[universe] 시총 {args.min_cap}억+ {top_label} 수집...", flush=True)
    result = get_universe(top_n=args.top, min_cap=args.min_cap)
    universe = result["universe"]
    ex = result["excluded"]

    out_data = {
        "meta": {
            "min_market_cap_억": args.min_cap,
            "filter_excluded": {
                "preferred": len(ex["preferred"]),
                "reit": len(ex["reit"]),
                "spac": len(ex["spac"]),
            },
            "count": len(universe),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "stocks": universe,
        "excluded_types": ex,
    }
    OUT.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")

    total_pre_filter = len(universe) + len(ex["preferred"]) + len(ex["reit"]) + len(ex["spac"])
    print(f"\n  시총 {args.min_cap}억+ 통과 (필터 전): {total_pre_filter}개")
    print(f"    - 우선주 제외:  {len(ex['preferred']):>4}개")
    print(f"    - 리츠 제외:    {len(ex['reit']):>4}개")
    print(f"    - 스팩 제외:    {len(ex['spac']):>4}개")
    print(f"  → 보통주 universe: {len(universe)}개")
    print(f"  → {OUT.relative_to(_PROJECT_ROOT)}")
    for i, s in enumerate(universe[:10]):
        print(f"  {i+1:>2}. {s['name']} ({s['code']}) {s['market']}  {s['market_cap_억']:>9,}억")
    if len(universe) > 10:
        print(f"  ... 외 {len(universe) - 10}개")


if __name__ == "__main__":
    main()
