"""universe 2단계 — 5년 실적 검증 (KIS 분기 EPS 기반, pykrx 대체)

기존 `validate_universe_quick.py`는 pykrx 월별 PER 매트릭스의 NaN/0 패턴으로
적자분기를 *추정*했다. 이제 KIS에서 분기 EPS를 직접 받으므로 추정할 필요가 없다.

검증 룰 (기존과 동일 의미)
    최근 5년(20개 분기) 중 TTM EPS <= 0 인 분기가 MAX_ADVERSE_Q 이하
    유효 분기 수가 MIN_VALID_Q 이상 (데이터 부족 종목 제외)

TTM EPS를 쓰는 이유: 단일 분기 EPS는 계절성으로 자주 음수가 되지만, 4개 분기를
합치면 사업의 실제 손익 상태를 본다. "적자 기업"을 거르는 취지에 맞다.

입력  data/universe.json (1단계 통과 종목) + data/.cache/_kis_ratio_q_*.json
출력  data/universe.json 갱신 (passed / excluded_validation / meta.validation)
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / ".cache"
UNIVERSE = DATA_DIR / "universe.json"

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

LOOKBACK_Q = 20      # 최근 5년 = 20분기
MAX_ADVERSE_Q = 4    # 적자 허용 분기 수
MIN_VALID_Q = 12     # 최소 유효 분기 (3년치)


def _amt(s):
    s = str(s if s is not None else "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _ref(series, stac):
    """KIS는 데이터 없는 기간을 0.0으로 채운다 → 정확히 0이면 결측 취급."""
    v = _amt((series.get(stac) or {}).get("eps"))
    return None if (v is None or v == 0) else v


def ttm_eps(series, stac):
    y, m = int(stac[:4]), int(stac[4:6])
    cur = _amt((series.get(stac) or {}).get("eps"))
    if cur is None:
        return None
    if m == 12:
        return cur
    a = _ref(series, f"{y-1}12")
    p = _ref(series, f"{y-1}{m:02d}")
    if a is None or p is None:
        return None
    return a - p + cur


def load_ratios():
    """실전 캐시 우선, 없으면 모의 캐시."""
    for nm in ("_kis_ratio_q_real.json", "_kis_ratio_q_paper.json", "_kis_ratio_q.json"):
        p = CACHE_DIR / nm
        if p.exists():
            print(f"  KIS 캐시: {nm}")
            return json.loads(p.read_text(encoding="utf-8"))
    sys.exit("[ERROR] KIS 캐시 없음. fetch_matrix_kis.py 를 먼저 실행하세요.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-adverse", type=int, default=MAX_ADVERSE_Q)
    ap.add_argument("--min-valid", type=int, default=MIN_VALID_Q)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    uni = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    stocks = uni.get("stocks") or []
    print(f"[validate] 1단계 통과 {len(stocks)}종목 · 최근 {LOOKBACK_Q}분기 검증")
    print(f"  룰: 적자(TTM EPS<=0) 분기 <= {args.max_adverse} · 유효분기 >= {args.min_valid}\n")

    ratios = load_ratios()

    passed, ex_short, ex_nodata, ex_adverse = [], [], [], []
    for s in stocks:
        code = s["code"]
        series = ratios.get(code)
        if not series:
            ex_nodata.append(s)
            continue
        stacs = sorted([k for k in series if len(str(k)) == 6], reverse=True)[:LOOKBACK_Q]
        vals = [ttm_eps(series, st) for st in stacs]
        valid = [v for v in vals if v is not None]
        if len(valid) < args.min_valid:
            (ex_short if valid else ex_nodata).append(s)
            continue
        adverse = sum(1 for v in valid if v <= 0)
        rec = {**s, "valid_quarters": len(valid), "adverse_quarters": adverse}
        if adverse > args.max_adverse:
            ex_adverse.append(rec)
        else:
            passed.append(rec)

    print(f"  통과            {len(passed):>4}")
    print(f"  데이터 없음      {len(ex_nodata):>4}")
    print(f"  유효분기 부족    {len(ex_short):>4}")
    print(f"  적자분기 초과    {len(ex_adverse):>4}")
    if ex_adverse:
        worst = sorted(ex_adverse, key=lambda x: -x["adverse_quarters"])[:8]
        print("    예: " + ", ".join(f"{x['name']}({x['adverse_quarters']}Q)" for x in worst))
    if ex_nodata:
        print("    데이터 없음 예: " + ", ".join(x["name"] for x in ex_nodata[:8]))

    if args.dry_run:
        print("\n  (--dry-run: 파일 미기록)")
        return

    uni["passed"] = passed
    uni["stocks"] = passed
    uni.setdefault("excluded", {})
    uni["excluded"]["validation_short"] = ex_short
    uni["excluded"]["validation_nodata"] = ex_nodata
    uni["excluded"]["validation_adverse"] = ex_adverse
    uni["meta"]["validation"] = {
        "method": "kis_quarterly_ttm_eps",
        "lookback_quarters": LOOKBACK_Q,
        "max_adverse_quarters": args.max_adverse,
        "min_valid_quarters": args.min_valid,
        "input_count": len(stocks),
        "passed_count": len(passed),
        "excluded_short": len(ex_short),
        "excluded_no_data": len(ex_nodata),
        "excluded_adverse": len(ex_adverse),
        "validated_at": datetime.now().isoformat(timespec="seconds"),
    }
    UNIVERSE.write_text(json.dumps(uni, ensure_ascii=False), encoding="utf-8")
    print(f"\n  → {UNIVERSE.relative_to(ROOT)}")
    print("  ※ 다음 단계: 컨센서스(Forward PER·목표주가)")


if __name__ == "__main__":
    main()
