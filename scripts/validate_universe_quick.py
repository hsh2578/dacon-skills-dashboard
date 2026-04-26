"""universe.json 의 종목들을 월별 PER 일괄 페치로 검증 (forward 안 받음).

pykrx 일괄 API 활용:
  stock.get_market_fundamental_by_ticker(date, market) → 시장 전체 한 번에

5년 × 12개월 × 2시장 = 120번 호출, 호출당 1-2초 → ~3-5분

검증 조건:
  1. 5년 PER 시계열 충분 (60개월 중 흑자 PER ≥ MIN_VALID_MONTHS)
  2. 5년 적자 분기 ≤ 4Q (= 적자 월 ≤ 12)
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
UNIVERSE = PROJECT / "data" / "universe.json"

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

LOOKBACK_MONTHS = 60                # 5년
MAX_ADVERSE_MONTHS = 12             # 적자 4분기 = 12개월
MIN_VALID_MONTHS = 24               # 흑자 PER 24개월 이상 (= 2년)
MAX_NULL_RATIO = 0.20               # 데이터 결손 ≤ 20%


def _resolve_business_date(d: datetime, max_back: int = 7) -> str:
    """주어진 날짜 또는 그 이전의 가장 가까운 영업일 (YYYYMMDD)."""
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


def fetch_per_matrix(months: int = LOOKBACK_MONTHS):
    """매월 15일 (또는 인접 영업일)의 시장 전체 PER → {ticker: {date: per}}"""
    end_dt = datetime.now()
    sample_dates = []
    for i in range(months):
        # i개월 전의 15일
        target = end_dt - timedelta(days=30 * i)
        target = target.replace(day=15)
        sample_dates.append(target)
    sample_dates.reverse()  # 오래된 순으로

    matrix = {}
    t0 = time.time()
    for i, target in enumerate(sample_dates):
        ds = _resolve_business_date(target)
        for market in ("KOSPI", "KOSDAQ"):
            try:
                df = stock.get_market_fundamental_by_ticker(ds, market=market)
                if df is None or df.empty:
                    continue
                for ticker, per in df["PER"].items():
                    matrix.setdefault(ticker, {})[ds] = per
            except Exception as e:
                print(f"    [WARN] {ds} {market} 실패: {e}", file=sys.stderr)

        elapsed = time.time() - t0
        eta = (elapsed / (i + 1)) * (months - i - 1)
        print(f"  [{i+1:>2}/{months}] {ds}  경과 {elapsed:.0f}s · ETA {eta:.0f}s",
              flush=True)
    return matrix


def validate(matrix: dict, universe_codes: list) -> dict:
    passed = []
    excluded_no_data = []
    excluded_adverse = []
    excluded_short = []

    for code in universe_codes:
        series = matrix.get(code, {})
        total = len(series)
        if total == 0:
            excluded_no_data.append({"code": code, "reason": "NO_DATA"})
            continue

        valid_months = sum(1 for v in series.values() if v is not None and v > 0)
        adverse_months = sum(1 for v in series.values() if v is None or v <= 0)

        # 데이터 결손 (= 60개월 중 받은 데이터 부족) — 신규 상장 등
        if total < LOOKBACK_MONTHS * (1 - MAX_NULL_RATIO):
            excluded_short.append({
                "code": code, "reason": "INSUFFICIENT_HISTORY",
                "data_months": total, "needed": int(LOOKBACK_MONTHS * (1 - MAX_NULL_RATIO))
            })
            continue

        if valid_months < MIN_VALID_MONTHS:
            excluded_no_data.append({
                "code": code, "reason": "INSUFFICIENT_VALID_PER",
                "valid_months": valid_months, "needed": MIN_VALID_MONTHS
            })
            continue

        if adverse_months > MAX_ADVERSE_MONTHS:
            adv_q = round(adverse_months / 3, 1)
            excluded_adverse.append({
                "code": code, "reason": f"ADVERSE_QUARTERS_{adv_q}",
                "adverse_months": adverse_months, "adverse_quarters": adv_q,
            })
            continue

        passed.append({
            "code": code,
            "valid_months": valid_months,
            "adverse_months": adverse_months,
            "adverse_quarters": round(adverse_months / 3, 1),
            "data_months": total,
        })

    return {
        "passed": passed,
        "excluded_no_data": excluded_no_data,
        "excluded_short": excluded_short,
        "excluded_adverse": excluded_adverse,
    }


def main():
    base = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    base_stocks = base.get("stocks") or []
    universe_codes = [s["code"] for s in base_stocks]
    print(f"[validate-quick] 기준 universe {len(universe_codes)}개 (시총 "
          f"{base.get('meta',{}).get('min_market_cap_억')}억+ 보통주)")
    print(f"  월별 PER 일괄 페치 시작 ({LOOKBACK_MONTHS}개월 × 2시장 = "
          f"{LOOKBACK_MONTHS*2}번 호출)\n")

    matrix = fetch_per_matrix()

    print(f"\n  매트릭스 종목 수: {len(matrix)} (시장 전체)")
    result = validate(matrix, universe_codes)

    code_to_meta = {s["code"]: s for s in base_stocks}
    passed_full = []
    for p in result["passed"]:
        meta = code_to_meta.get(p["code"], {})
        passed_full.append({**meta, **p})

    out = {
        "meta": {
            **(base.get("meta") or {}),
            "validation": {
                "method": "monthly_batch_per",
                "months": LOOKBACK_MONTHS,
                "max_adverse_months": MAX_ADVERSE_MONTHS,
                "min_valid_months": MIN_VALID_MONTHS,
                "max_null_ratio": MAX_NULL_RATIO,
            },
            "input_count": len(universe_codes),
            "passed_count": len(result["passed"]),
            "excluded_short": len(result["excluded_short"]),
            "excluded_no_data": len(result["excluded_no_data"]),
            "excluded_adverse": len(result["excluded_adverse"]),
            "validated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "stocks": passed_full,
        "passed": passed_full,
        "excluded": {
            "short_history": result["excluded_short"],
            "no_data": result["excluded_no_data"],
            "adverse": result["excluded_adverse"],
            **base.get("excluded_types", {}),
        },
    }
    UNIVERSE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n  === 검증 결과 ===")
    print(f"  입력 universe (시총 + 보통주):       {len(universe_codes):>5}개")
    print(f"  ├─ 상장 5년 미만 (이력 부족):         {len(result['excluded_short']):>5}개")
    print(f"  ├─ 흑자 PER 부족 (월 < {MIN_VALID_MONTHS}):           {len(result['excluded_no_data']):>5}개")
    print(f"  ├─ 적자 분기 > 4Q (적자 월 > 12):     {len(result['excluded_adverse']):>5}개")
    print(f"  └─ 통과 (PER 차트 가능):              {len(result['passed']):>5}개")


if __name__ == "__main__":
    main()
