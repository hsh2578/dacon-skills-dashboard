"""시장 지수(KOSPI·KOSDAQ·S&P 500)만 갱신하는 최소 러너.

기본: 증분 갱신 (KR 일별 데이터). 미국 월별은 항상 풀 fetch.
--full: 풀 재수집.

종목 단위 갱신(`--with-stocks`)은 제거됐다 — pykrx 기반 `fetch_stock_kr.py`가
2026-08-13 KRX IP 차단으로 폐기됐기 때문. Top N 일별 풀 데이터는
`scripts/fetch_batch_api.py --top-n 20`이 담당한다.
전체 파이프라인은 `/update-data` 슬래시 커맨드를 쓸 것.
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(args: list) -> bool:
    label = f"{Path(args[0]).name} {' '.join(args[1:])}".strip()
    print(f"\n=== {label} ===")
    r = subprocess.run([sys.executable] + args)
    if r.returncode != 0:
        print(f"[FAIL] {label}", file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="증분 무시하고 풀 재수집")
    args = ap.parse_args()

    extra = ["--full"] if args.full else []

    ok = True
    ok &= run([str(ROOT / "fetch_kr.py"), *extra])
    ok &= run([str(ROOT / "fetch_us.py")])

    print("\n" + ("=" * 40))
    print("DONE" if ok else "PARTIAL FAIL", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
