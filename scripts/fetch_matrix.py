"""월별 PER + PBR 매트릭스 일괄 페치 → data/matrix/{per,pbr}_monthly.json

universe 검증과 점수 계산에 공통 사용.
60개월 × 2시장 = 120번 호출 (~2분/메트릭)
"""
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
MATRIX_DIR = PROJECT / "data" / "matrix"
MATRIX_DIR.mkdir(parents=True, exist_ok=True)

_load_env(PROJECT / ".env")
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
    sys.stderr.write("[ERROR] KRX_ID / KRX_PW 미설정.\n")
    sys.exit(2)

import pandas as pd
from pykrx import stock

LOOKBACK_MONTHS = 60


def _resolve_business_date(d: datetime, max_back: int = 7) -> str:
    for _ in range(max_back):
        ds = d.strftime("%Y%m%d")
        try:
            df = stock.get_market_fundamental_by_ticker(ds, market="KOSPI")
            if df is not None and not df.empty and (df["PER"] != 0).any():
                return ds
        except Exception:
            pass
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def fetch(months: int = LOOKBACK_MONTHS):
    """PER + PBR 매트릭스 동시 페치 (한 번 호출에 둘 다 받음)"""
    end_dt = datetime.now()
    sample_dates = []
    for i in range(months):
        target = end_dt - timedelta(days=30 * i)
        target = target.replace(day=15)
        sample_dates.append(target)
    sample_dates.reverse()

    per_matrix = {}  # {ticker: {date: per}}
    pbr_matrix = {}
    t0 = time.time()
    for i, target in enumerate(sample_dates):
        ds = _resolve_business_date(target)
        for market in ("KOSPI", "KOSDAQ"):
            try:
                df = stock.get_market_fundamental_by_ticker(ds, market=market)
                if df is None or df.empty:
                    continue
                for ticker, row in df.iterrows():
                    per_matrix.setdefault(ticker, {})[ds] = row["PER"]
                    pbr_matrix.setdefault(ticker, {})[ds] = row["PBR"]
            except Exception as e:
                print(f"    [WARN] {ds} {market} 실패: {e}", file=sys.stderr)

        elapsed = time.time() - t0
        eta = (elapsed / (i + 1)) * (months - i - 1)
        print(f"  [{i+1:>2}/{months}] {ds}  경과 {elapsed:.0f}s · ETA {eta:.0f}s",
              flush=True)
    return per_matrix, pbr_matrix


def main():
    print(f"[matrix] PER + PBR 월별 매트릭스 페치 ({LOOKBACK_MONTHS}개월 × 2시장)\n")

    per_matrix, pbr_matrix = fetch()

    print(f"\n  PER 매트릭스: {len(per_matrix)}개 종목")
    print(f"  PBR 매트릭스: {len(pbr_matrix)}개 종목")

    out = {
        "meta": {
            "months": LOOKBACK_MONTHS,
            "ticker_count": len(per_matrix),
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        },
        "matrix": per_matrix,
    }
    (MATRIX_DIR / "per_monthly.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")

    out["matrix"] = pbr_matrix
    out["meta"]["ticker_count"] = len(pbr_matrix)
    (MATRIX_DIR / "pbr_monthly.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")

    print(f"\n  → data/matrix/per_monthly.json")
    print(f"  → data/matrix/pbr_monthly.json")


if __name__ == "__main__":
    main()
