"""데이터 페치 결과 sanity 검증.

/update-data 워크플로우의 마지막 단계로 호출되어, 사용자가 사이트에서 stale·누락
데이터를 보지 않도록 미리 차단한다. 임계값을 넘는 경고는 stderr로 출력하고
exit code 1로 종료해서 후속 commit/push가 자동으로 멈추도록 한다.

검증 항목:
1. 시장 지수 (kospi/kosdaq/sp500) — 마지막 날짜가 N일 이내, non-null 비율 ≥ 80%
2. universe.json — close 0/None 비율 ≤ 5%, price_reference_date가 N일 이내
3. matrix/{per,pbr}_monthly.json — 마지막 거래일에 non-null 종목 ≥ 70%
4. screens/triple_cross.json — top 10 모두 current_price > 0
5. screens/ai_notes.json — items 길이 ≥ 8 (Top 10에 가까운지)
6. financials/{code}.json — Top 10 중 ≥ 80%가 annual ≥ 3개년 (DART 재무)
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
DATA = ROOT / "data"

WARN_FRESH_DAYS = 7
WARN_NON_NULL_RATIO = 0.80
# 매트릭스는 적자 종목 등으로 자연 NaN이 많아 50% 정도가 정상
WARN_MATRIX_COVERAGE = 0.50
# S&P 500은 multpl yearly PBR 특성상 가끔 마지막 갱신이 늦음
SP500_FRESH_DAYS_MAX = 90


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def check_market_index(name: str, path: Path, errors: list, warnings: list):
    d = load_json(path)
    if not d:
        errors.append(f"{name}: 파일 미존재 ({path})")
        return
    dates = d.get("dates") or []
    if not dates:
        errors.append(f"{name}: dates 비어 있음")
        return
    last = datetime.fromisoformat(dates[-1].replace("Z", ""))
    age_days = (datetime.now() - last).days
    fresh_max = SP500_FRESH_DAYS_MAX if name == "sp500" else WARN_FRESH_DAYS * 4
    if age_days > fresh_max:
        errors.append(f"{name}: 마지막 데이터 {dates[-1]} ({age_days}일 전) — 너무 오래됨")
    elif age_days > WARN_FRESH_DAYS:
        warnings.append(f"{name}: 마지막 데이터 {dates[-1]} ({age_days}일 전)")
    n = len(dates)
    for metric in ("per", "pbr", "div_yield", "close"):
        arr = d.get(metric)
        if arr is None:
            warnings.append(f"{name}.{metric}: 필드 미존재")
            continue
        cov = sum(1 for v in arr if v is not None) / max(n, 1)
        if cov < WARN_NON_NULL_RATIO:
            errors.append(f"{name}.{metric}: non-null {cov:.0%} < {WARN_NON_NULL_RATIO:.0%}")


def check_universe(errors: list, warnings: list):
    d = load_json(DATA / "universe.json")
    if not d:
        errors.append("universe.json: 미존재")
        return
    passed = d.get("passed") or []
    if not passed:
        errors.append("universe.json: passed 배열 비어 있음")
        return
    bad_close = sum(1 for s in passed if not s.get("close") or s["close"] <= 0)
    ratio = bad_close / len(passed)
    if ratio > 0.05:
        errors.append(
            f"universe.passed.close: 무효(0/None) 비율 {ratio:.1%} ({bad_close}/{len(passed)}) — refresh_universe_prices.py 실행 필요"
        )
    ref = d.get("meta", {}).get("price_reference_date")
    if ref:
        ref_dt = datetime.strptime(ref, "%Y%m%d")
        age = (datetime.now() - ref_dt).days
        if age > WARN_FRESH_DAYS:
            warnings.append(f"universe.price_reference_date: {ref} ({age}일 전)")
    else:
        warnings.append("universe.meta.price_reference_date 미기록")


def check_matrix(errors: list, warnings: list):
    for kind in ("per", "pbr"):
        path = DATA / "matrix" / f"{kind}_monthly.json"
        d = load_json(path)
        if not d or not d.get("matrix"):
            errors.append(f"matrix/{kind}_monthly.json: 미존재 또는 빈 matrix")
            continue
        matrix = d["matrix"]
        # 마지막 거래일에 non-null 종목 비율
        last_dates = set()
        for code, vals in matrix.items():
            if vals:
                last_dates.add(max(vals.keys()))
        if not last_dates:
            errors.append(f"matrix/{kind}: 데이터 없음")
            continue
        last = max(last_dates)
        nonnull = sum(1 for c, v in matrix.items() if last in v and v[last] and v[last] > 0)
        ratio = nonnull / len(matrix)
        if ratio < WARN_MATRIX_COVERAGE:
            errors.append(
                f"matrix/{kind} 마지막 {last}: non-null {ratio:.1%} ({nonnull}/{len(matrix)}) < {WARN_MATRIX_COVERAGE:.0%}"
            )


def check_screens(errors: list, warnings: list):
    tc = load_json(DATA / "screens" / "triple_cross.json")
    if not tc:
        errors.append("screens/triple_cross.json: 미존재")
    else:
        top = tc.get("top") or []
        bad = [t for t in top if not t.get("current_price") or t["current_price"] <= 0]
        if bad:
            names = ", ".join(t.get("name", t.get("code", "?")) for t in bad)
            errors.append(f"top 10에 current_price 무효 종목: {names}")

    ai = load_json(DATA / "screens" / "ai_notes.json")
    if ai:
        items = ai.get("items") or []
        if len(items) < 8:
            warnings.append(f"ai_notes.items: {len(items)}개 (Top 10에 비해 부족)")
    else:
        warnings.append("ai_notes.json: 미존재 (--skip-ai 모드라면 정상)")


def check_financials(errors: list, warnings: list):
    """DART 재무: Top 10 중 ≥ 80%가 annual ≥ 3개년이어야 함 (적자·금융사 자연 결측 허용)."""
    tc = load_json(DATA / "screens" / "triple_cross.json")
    if not tc:
        return  # triple_cross 자체 오류는 check_screens가 처리
    top = tc.get("top") or []
    if not top:
        return
    fin_dir = DATA / "financials"
    ok = 0
    missing = []
    for t in top:
        code = t.get("code")
        d = load_json(fin_dir / f"{code}.json")
        if d and len(d.get("annual") or []) >= 3:
            ok += 1
        else:
            missing.append(t.get("name", code))
    ratio = ok / len(top)
    if ratio < 0.80:
        errors.append(
            f"financials: Top 10 중 {ok}/{len(top)}만 재무 보유 (< 80%) — 누락: {', '.join(missing)}"
        )
    elif missing:
        warnings.append(f"financials: 일부 종목 재무 부족/누락 — {', '.join(missing)}")


def main():
    errors, warnings = [], []
    print("[verify-data] 검증 시작")

    check_market_index("kospi", DATA / "kospi.json", errors, warnings)
    check_market_index("kosdaq", DATA / "kosdaq.json", errors, warnings)
    check_market_index("sp500", DATA / "sp500.json", errors, warnings)
    check_universe(errors, warnings)
    check_matrix(errors, warnings)
    check_screens(errors, warnings)
    check_financials(errors, warnings)

    if warnings:
        print("\n[verify-data] 경고 (계속 진행):")
        for w in warnings:
            print(f"  ! {w}")
    if errors:
        print("\n[verify-data] 오류 (commit 자동 차단):", file=sys.stderr)
        for e in errors:
            print(f"  X {e}", file=sys.stderr)
        sys.exit(1)
    print("\n[verify-data] OK — 모든 검증 통과")


if __name__ == "__main__":
    main()
