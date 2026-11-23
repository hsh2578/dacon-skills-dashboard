"""universe 2단계 — 5년 실적 검증 (DART 분기 지배순이익 기반)

2026-11-23: KIS 재무비율 API 404 → DART 금액(data/financials_q, fetch_dart_quarterly.py)으로 전환.
TTM EPS 대신 TTM 지배순이익의 부호를 본다 — 적자 판정은 주당이든 금액이든 같다.

기존 `validate_universe_quick.py`는 pykrx 월별 PER 매트릭스의 NaN/0 패턴으로
적자분기를 *추정*했다. 이제 KIS에서 분기 EPS를 직접 받으므로 추정할 필요가 없다.

검증 룰 (기존과 동일 의미)
    최근 5년(20개 분기) 중 TTM EPS <= 0 인 분기가 MAX_ADVERSE_Q 이하
    유효 분기 수가 MIN_VALID_Q 이상 (데이터 부족 종목 제외)

TTM EPS를 쓰는 이유: 단일 분기 EPS는 계절성으로 자주 음수가 되지만, 4개 분기를
합치면 사업의 실제 손익 상태를 본다. "적자 기업"을 거르는 취지에 맞다.

입력  data/universe.json (1단계 통과 종목) + data/financials_q/{code}.json
출력  data/universe.json 갱신 (passed / excluded_validation / meta.validation)
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ttm import recent_stacs, ttm_eps  # noqa: E402

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


def load_ratios(codes):
    """{code: {stac: {ni, eq}}} — status 000 인 보고서만. 파일이 없으면 그 종목은 '데이터 없음'."""
    fq = DATA_DIR / "financials_q"
    out = {}
    for c in codes:
        p = fq / f"{c}.json"
        if p.exists():
            ser = json.loads(p.read_text(encoding="utf-8")).get("series", {})
            out[c] = {k: v for k, v in ser.items() if v.get("status") == "000"}
    print(f"  DART 분기: {len(out)}/{len(codes)}종목 (fetch_dart_quarterly.py)")
    if len(out) < len(codes) * 0.9:
        sys.exit("[ERROR] DART 분기 데이터가 10% 넘게 없습니다 — fetch_dart_quarterly.py 를 먼저 실행하세요.")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-adverse", type=int, default=MAX_ADVERSE_Q)
    ap.add_argument("--min-valid", type=int, default=MIN_VALID_Q)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    uni = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    stocks = uni.get("stage1") or uni.get("stocks") or []   # 단계 키 (2026-11-24): stage1 = 1단계 · validated = 실적 검증 · final(=passed=stocks) = 최종. 각 단계는 자기 키에만 쓴다 — 재실행이 이미 줄어든 목록을 다시 검증하지 않게.
    print(f"[validate] 1단계 통과 {len(stocks)}종목 · 최근 {LOOKBACK_Q}분기 검증")
    print(f"  룰: 적자(TTM 지배순이익<=0) 분기 <= {args.max_adverse} · 유효분기 >= {args.min_valid}\n")

    ratios = load_ratios([s["code"] for s in stocks])

    passed, ex_short, ex_nodata, ex_adverse = [], [], [], []
    for s in stocks:
        code = s["code"]
        series = ratios.get(code)
        if not series:
            ex_nodata.append(s)
            continue
        # 여기서는 공시 시차(ttm.disclosed_stac)를 적용하지 않는다 — 의도적이다.
        # 시차는 "과거 시점에 아직 몰랐을 실적"을 막는 장치인데, 이 검증은 과거
        # 시계열이 아니라 **지금 시점의 스크리닝**이다. 캐시에 들어 있다는 건 이미
        # 공시됐다는 뜻이므로 최신 분기를 그대로 쓰는 것이 맞다.
        vals = [ttm_eps(series, st, "ni") for st in recent_stacs(series, LOOKBACK_Q)]
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

    uni["validated"] = passed
    uni["passed"] = passed
    uni["stocks"] = passed
    uni.setdefault("excluded", {})
    uni["excluded"]["validation_short"] = ex_short
    uni["excluded"]["validation_nodata"] = ex_nodata
    uni["excluded"]["validation_adverse"] = ex_adverse
    uni["meta"]["validation"] = {
        "method": "dart_quarterly_ttm_controlling_ni",
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
