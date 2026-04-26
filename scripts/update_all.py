"""4개 지수 + 종목 데이터 일괄 갱신.

기본: 증분 갱신 (KR 일별 데이터). 미국 월별은 항상 풀 fetch.
--full: 모든 데이터 풀 재수집.
--with-stocks: data/stocks/*.json 에 있는 모든 종목도 함께 갱신.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
STOCKS_DIR = PROJECT / "data" / "stocks"


def run(args: list) -> bool:
    label = f"{Path(args[0]).name} {' '.join(args[1:])}".strip()
    print(f"\n=== {label} ===")
    r = subprocess.run([sys.executable] + args)
    if r.returncode != 0:
        print(f"[FAIL] {label}", file=sys.stderr)
        return False
    return True


def list_stock_codes() -> list:
    if not STOCKS_DIR.exists():
        return []
    codes = []
    for p in STOCKS_DIR.glob("*.json"):
        codes.append(p.stem)
    return sorted(codes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="증분 무시하고 풀 재수집")
    ap.add_argument("--with-stocks", action="store_true",
                    help="data/stocks/*.json 의 모든 종목도 함께 갱신")
    args = ap.parse_args()

    extra = ["--full"] if args.full else []

    ok = True
    ok &= run([str(ROOT / "fetch_kr.py"), *extra])
    ok &= run([str(ROOT / "fetch_us.py")])

    if args.with_stocks:
        codes = list_stock_codes()
        if not codes:
            print("\n[stocks] data/stocks/ 비어있음. 건너뜀.")
        else:
            print(f"\n[stocks] {len(codes)}개 종목 갱신: {', '.join(codes)}")
            for code in codes:
                ok &= run([str(ROOT / "fetch_stock_kr.py"), code, *extra])
                ok &= run([str(ROOT / "render_stock.py"), code])

    print("\n" + ("=" * 40))
    print("DONE" if ok else "PARTIAL FAIL", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
