"""data/stocks/ 의 종목 데이터를 검증해서 universe.json 의 passed/excluded 분리.

유니버스 조건 (CLAUDE.md):
  1. 시가총액 ≥ 2,000억  (fetch_universe.py 단계에서 이미 적용)
  2. 5년 PER 데이터에서 적자 분기 ≤ 4분기 (= 5년 중 1년 이하 적자 허용)

KRX 가 적자 분기 PER 을 0/null 로 표기하므로 PER 시계열만으로 판별 가능.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = PROJECT / "scripts"
STOCKS_DIR = PROJECT / "data" / "stocks"
UNIVERSE = PROJECT / "data" / "universe.json"

sys.path.insert(0, str(SCRIPT_DIR))
from incremental import regenerate_stocks_manifest  # noqa: E402

TRADING_DAYS_PER_YEAR = 252
LOOKBACK_5Y = TRADING_DAYS_PER_YEAR * 5
LOOKBACK_6M = TRADING_DAYS_PER_YEAR // 2
DAYS_PER_QUARTER = 60
MAX_ADVERSE_QUARTERS = 4
MIN_VALID_5Y = 60       # 5년 데이터 중 흑자 분기 PER 최소 60일
MIN_VALID_6M = 30       # 6개월 데이터 중 30일 이상


def _count_adverse_quarters(per_series, lookback):
    sliced = per_series[-lookback:] if len(per_series) >= lookback else per_series
    total = len(sliced)
    adverse_days = sum(1 for v in sliced if v is None or v <= 0)
    valid_days = total - adverse_days
    adverse_quarters = round(adverse_days / DAYS_PER_QUARTER, 1)
    valid_ratio = valid_days / total if total else 0
    return adverse_quarters, valid_days, valid_ratio


def validate_stock(stock_data: dict) -> dict:
    per = stock_data.get("per") or []
    if not per:
        return {"reason": "NO_PER_DATA", "passed": False}

    fwd = (stock_data.get("forward") or {}).get("per_forward")
    has_forward = fwd is not None and fwd > 0

    # 5년 / 6개월 적자 분기 카운트
    adv_5y, valid_5y, ratio_5y = _count_adverse_quarters(per, LOOKBACK_5Y)
    _, valid_6m, _ = _count_adverse_quarters(per, LOOKBACK_6M)

    info = {
        "adverse_quarters_5y": adv_5y,
        "valid_days_5y": valid_5y,
        "valid_days_6m": valid_6m,
        "valid_ratio_5y": round(ratio_5y, 3),
        "has_forward": has_forward,
        "forward_per": round(fwd, 2) if has_forward else None,
    }

    # 검증
    if adv_5y > MAX_ADVERSE_QUARTERS:
        info["passed"] = False
        info["reason"] = f"ADVERSE_QUARTERS_{adv_5y}"
        return info
    if valid_5y < MIN_VALID_5Y or valid_6m < MIN_VALID_6M:
        info["passed"] = False
        info["reason"] = "INSUFFICIENT_PER_DATA"
        return info
    if not has_forward:
        info["passed"] = False
        info["reason"] = "NO_FORWARD_PER"
        return info

    info["passed"] = True
    return info


def main():
    if not UNIVERSE.exists():
        print(f"[ERROR] {UNIVERSE} 없음. fetch_universe.py 먼저 실행.", file=sys.stderr)
        sys.exit(2)

    base = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    base_stocks = base.get("stocks") or []
    print(f"[validate] 기준 유니버스 {len(base_stocks)}개 검증 (시총 {base.get('meta',{}).get('min_market_cap_억')}억+)")

    passed, excluded = [], []
    for s in base_stocks:
        code = s["code"]
        p = STOCKS_DIR / f"{code}.json"
        if not p.exists():
            excluded.append({**s, "passed": False, "reason": "NOT_FETCHED"})
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            excluded.append({**s, "passed": False, "reason": "PARSE_ERROR"})
            continue

        v = validate_stock(d)
        merged = {**s, **v}
        if v["passed"]:
            passed.append(merged)
        else:
            excluded.append(merged)

    out = {
        "meta": {
            **(base.get("meta") or {}),
            "filters": {
                "min_market_cap_억": base.get("meta", {}).get("min_market_cap_억", 2000),
                "max_adverse_quarters_5y": MAX_ADVERSE_QUARTERS,
                "min_valid_days_5y": MIN_VALID_5Y,
                "min_valid_days_6m": MIN_VALID_6M,
                "require_forward_per": True,
            },
            "passed_count": len(passed),
            "excluded_count": len(excluded),
            "validated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "passed": passed,
        "excluded": excluded,
        "stocks": passed,  # 기존 호환성
    }
    UNIVERSE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 매니페스트도 갱신 (passed 종목만 카드 스트립에 보이게)
    # data/stocks/_index.json 은 모든 JSON 스캔하므로 그대로 두고,
    # 차후 메인 페이지에서 universe.json passed 기준으로 필터.
    n = regenerate_stocks_manifest(STOCKS_DIR)

    print(f"\n  통과 {len(passed)}개 / 제외 {len(excluded)}개 (매니페스트 {n}개)")
    print(f"\n  === 통과 종목 ===")
    for s in passed[:15]:
        adv = s.get("adverse_quarters_5y", 0)
        adv_lbl = "5년 연속 흑자" if adv == 0 else f"적자 {adv}Q"
        print(f"  {s['name']:<14} {s['code']}  {s['market_cap_억']:>9,}억  [{adv_lbl}]")
    if len(passed) > 15:
        print(f"  ... 외 {len(passed) - 15}개")

    print(f"\n  === 제외 종목 ===")
    for s in excluded:
        reason = s.get("reason", "?")
        adv = s.get("adverse_quarters_5y", "-")
        print(f"  {s['name']:<14} {s['code']}  사유: {reason}  (적자 {adv}Q)")


if __name__ == "__main__":
    main()
