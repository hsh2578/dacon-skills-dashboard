"""4팩터 점수 계산 → data/screens/triple_cross.json

알고리즘 (multi_factor.py 패턴, Winsorize 제외):
  1. 각 팩터별 Rank 변환 (큰 값이 좋음)
  2. 각 팩터별 Rank의 Z-Score (평균 0, 표준편차 1)
  3. 그룹별 Z-Score 합산 (Value, Growth)
  4. Re-Z (그룹 합산값 다시 Z-Score → 그룹 간 분포 일치)
  5. 가중 합산 (Value 60% / Growth 40%)
  6. 정렬 → Top 10

팩터 (4개):
  Value 그룹 (저평가):
    s1_per = (avg_5y_per - cur_per) / avg_5y_per       [큰 값 = 5Y 평균 대비 PER 저평가]
    s1_pbr = (avg_5y_pbr - cur_pbr) / avg_5y_pbr       [큰 값 = 5Y 평균 대비 PBR 저평가]
  Growth 그룹 (미래 안전):
    s3_per = (cur_per - fwd_per) / cur_per             [큰 값 = Cur 대비 Fwd PER 개선]
    upside = (avg_target - cur_close) / cur_close      [큰 값 = 목표가 상승여력]
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import zscore

PROJECT = Path(__file__).resolve().parent.parent
UNIVERSE = PROJECT / "data" / "universe.json"
PER_MATRIX = PROJECT / "data" / "matrix" / "per_monthly.json"
PBR_MATRIX = PROJECT / "data" / "matrix" / "pbr_monthly.json"
SCREENS_DIR = PROJECT / "data" / "screens"
SCREENS_DIR.mkdir(parents=True, exist_ok=True)
OUT = SCREENS_DIR / "triple_cross.json"

WEIGHTS = {"value": 0.60, "growth": 0.40}
LOOKBACK_6M_MONTHS = 6


def _safe_zscore(series: pd.Series) -> pd.Series:
    """NaN 제외하고 Z-Score 계산 (NaN 위치는 NaN 유지)."""
    out = pd.Series(np.nan, index=series.index)
    mask = series.notna()
    if mask.sum() < 2:
        return out
    valid = series[mask]
    std = valid.std()
    if std == 0 or pd.isna(std):
        out.loc[mask] = 0
    else:
        out.loc[mask] = (valid - valid.mean()) / std
    return out


def _calc_avg_and_cur(matrix_data: dict, code: str) -> tuple:
    """월별 매트릭스에서 5Y avg + 가장 최근 값 (적자=0/null 제외)."""
    series = matrix_data.get(code) or {}
    if not series:
        return None, None

    sorted_dates = sorted(series.keys())
    valid_values = [series[d] for d in sorted_dates if series[d] is not None and series[d] > 0]

    if len(valid_values) < 6:
        return None, None

    # 가장 최근 양수 값
    cur = None
    for d in reversed(sorted_dates):
        if series[d] is not None and series[d] > 0:
            cur = series[d]
            break

    avg = sum(valid_values) / len(valid_values)
    return round(avg, 4), round(cur, 4) if cur else None


def main():
    # 1. 데이터 로드
    print("[apply_triple_cross] 데이터 로드 중...")
    universe_doc = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    universe = universe_doc.get("passed") or universe_doc.get("stocks") or []
    print(f"  universe: {len(universe)}개")

    per_doc = json.loads(PER_MATRIX.read_text(encoding="utf-8"))
    pbr_doc = json.loads(PBR_MATRIX.read_text(encoding="utf-8"))
    per_matrix = per_doc["matrix"]
    pbr_matrix = pbr_doc["matrix"]
    print(f"  PER 매트릭스: {len(per_matrix)}개 종목")
    print(f"  PBR 매트릭스: {len(pbr_matrix)}개 종목")

    # 2. 종목별 시그널 계산
    print("\n[1/5] 시그널 raw 값 계산...")
    rows = []
    for s in universe:
        code = s["code"]
        # PER
        avg_per, cur_per = _calc_avg_and_cur(per_matrix, code)
        # PBR
        avg_pbr, cur_pbr = _calc_avg_and_cur(pbr_matrix, code)
        # Forward, target, price
        fwd_per = s.get("forward_per")
        target = s.get("avg_target_price")
        close = s.get("close")

        # 시그널 raw
        s1_per = (avg_per - cur_per) / avg_per if avg_per and cur_per else np.nan
        s1_pbr = (avg_pbr - cur_pbr) / avg_pbr if avg_pbr and cur_pbr else np.nan
        s3_per = (cur_per - fwd_per) / cur_per if cur_per and fwd_per else np.nan
        upside = (target - close) / close if target and close else np.nan

        rows.append({
            "code": code,
            "name": s.get("name"),
            "market": s.get("market"),
            "market_cap_억": s.get("market_cap_억"),
            "close": close,
            "avg_5y_per": avg_per,
            "cur_per": cur_per,
            "avg_5y_pbr": avg_pbr,
            "cur_pbr": cur_pbr,
            "fwd_per": fwd_per,
            "fwd_year": s.get("fwd_year"),
            "avg_target": target,
            "broker_count": s.get("broker_count"),
            "s1_per": s1_per,
            "s1_pbr": s1_pbr,
            "s3_per": s3_per,
            "upside": upside,
        })

    df = pd.DataFrame(rows)
    print(f"  종목 {len(df)}개")

    # 3. Rank 변환 (각 팩터별, ascending=True = 큰 값이 큰 등수)
    print("\n[2/5] Rank 변환...")
    factors = ["s1_per", "s1_pbr", "s3_per", "upside"]
    for col in factors:
        df[f"{col}_rank"] = df[col].rank(ascending=True, na_option="keep")

    # 4. Rank의 Z-Score
    print("[3/5] Rank Z-Score 정규화...")
    for col in factors:
        df[f"{col}_z"] = _safe_zscore(df[f"{col}_rank"])

    # 5. 그룹별 합산
    print("[4/5] 그룹별 합산 → Re-Z...")
    df["value_raw"] = df[["s1_per_z", "s1_pbr_z"]].sum(axis=1, skipna=True, min_count=1)
    df["growth_raw"] = df[["s3_per_z", "upside_z"]].sum(axis=1, skipna=True, min_count=1)

    # 6. Re-Z
    df["value_score"] = _safe_zscore(df["value_raw"])
    df["growth_score"] = _safe_zscore(df["growth_raw"])

    # 7. 가중 합산
    print("[5/5] 가중 합산 (Value 60% / Growth 40%)...")
    df["total_score"] = (
        df["value_score"].fillna(0) * WEIGHTS["value"]
        + df["growth_score"].fillna(0) * WEIGHTS["growth"]
    )

    # 8. 정렬
    df = df.sort_values("total_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    # 9. 출력
    def _round(v, n=4):
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), n)

    out_records = []
    for _, r in df.iterrows():
        # 시그널 통과 (Z > 0 = universe 평균보다 좋음)
        s1_pass = (r["s1_per_z"] is not None and r["s1_per_z"] > 0
                   and r["s1_pbr_z"] is not None and r["s1_pbr_z"] > 0)
        s3_pass = r["s3_per_z"] is not None and r["s3_per_z"] > 0
        upside_pass = r["upside_z"] is not None and r["upside_z"] > 0
        pass_count = int(s1_pass) + int(s3_pass) + int(upside_pass)

        # 티어 (Z-score 분포 기준)
        total = r["total_score"]
        if pd.isna(total):
            tier = "MISS"
        elif total >= 1.65:
            tier = "HIDDEN_GEM"      # 상위 5%
        elif total >= 0.84:
            tier = "STRONG_BUY"      # 상위 20%
        elif total >= 0.0:
            tier = "BUY"
        elif total >= -0.5:
            tier = "WATCH"
        else:
            tier = "WEAK"

        out_records.append({
            "rank": int(r["rank"]),
            "code": r["code"],
            "name": r["name"],
            "market": r["market"],
            "market_cap_억": r["market_cap_억"],

            # === 호환 필드 (UI에서 사용) ===
            "current_price": int(r["close"]) if pd.notna(r["close"]) else None,
            "current_per": _round(r["cur_per"], 2),
            "avg_5y_per": _round(r["avg_5y_per"], 2),
            "forward_per": _round(r["fwd_per"], 2),
            "fwd_year": r["fwd_year"],
            "min_6m_per": None,  # S2 제거로 더 이상 사용 안 함
            "s1_historical_value": s1_pass,
            "s2_recovery_momentum": upside_pass,  # 자리만 채움 (UI 호환)
            "s3_forward_growth": s3_pass,
            "pass_count": pass_count,
            "triple_cross": pass_count == 3,
            "is_value_trap": False,
            "tier": tier,
            "adverse_quarters": 0,  # universe 검증 통과 종목은 모두 ≤4Q

            # === 새 알고리즘 데이터 ===
            "cur_pbr": _round(r["cur_pbr"], 2),
            "avg_5y_pbr": _round(r["avg_5y_pbr"], 2),
            "avg_target": int(r["avg_target"]) if pd.notna(r["avg_target"]) else None,
            "broker_count": r["broker_count"],

            # 시그널 raw
            "score_s1": _round(r["s1_per"]),  # UI 호환 (이전 필드명)
            "score_s2": _round(r["upside"]),  # 자리만
            "score_s3": _round(r["s3_per"]),
            "s1_per_raw": _round(r["s1_per"]),
            "s1_pbr_raw": _round(r["s1_pbr"]),
            "s3_per_raw": _round(r["s3_per"]),
            "upside_raw": _round(r["upside"]),

            # 정규화
            "s1_per_z": _round(r["s1_per_z"], 3),
            "s1_pbr_z": _round(r["s1_pbr_z"], 3),
            "s3_per_z": _round(r["s3_per_z"], 3),
            "upside_z": _round(r["upside_z"], 3),

            # 그룹/총점
            "value_score": _round(r["value_score"], 3),
            "growth_score": _round(r["growth_score"], 3),
            "total_score": _round(r["total_score"], 3),
        })

    triple_count = sum(1 for r in out_records if r["triple_cross"])
    out = {
        "meta": {
            "rule": "Triple Cross v5 — 4팩터 (Value 2 + Growth 2), Rank → Z → Re-Z → 가중합 (60:40)",
            "universe_size": len(universe),
            "factors": ["s1_per", "s1_pbr", "s3_per", "upside"],
            "weights": WEIGHTS,
            "winsorize": False,
            # UI 호환 필드
            "total_analyzed": len(universe),
            "ranked_count": len(out_records),
            "triple_cross_pass": triple_count,
            "avoid_count": 0,
            "excluded_count": 0,  # universe 단계에서 모두 처리됨
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "top": out_records[:10],
        "all_ranked": out_records,
        "avoid": [],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n  → {OUT.relative_to(PROJECT)}")
    print(f"\n  === Top 10 ===")
    print(f"  {'#':<3} {'종목':<14} {'CurPER':>7} {'5YPER':>7} {'FwdPER':>7} "
          f"{'CurPBR':>7} {'5YPBR':>7} {'Up%':>6} {'Total':>7}")
    for r in out_records[:10]:
        up_pct = (r["upside_raw"] * 100) if r["upside_raw"] is not None else 0
        print(f"  {r['rank']:<3} {r['name']:<14} {r['tier']:<11} "
              f"{(r['current_per'] or 0):>7.2f} {(r['avg_5y_per'] or 0):>7.2f} {(r['forward_per'] or 0):>7.2f} "
              f"{(r['cur_pbr'] or 0):>7.2f} {(r['avg_5y_pbr'] or 0):>7.2f} "
              f"{up_pct:>6.1f} {r['total_score']:>7.3f}")


if __name__ == "__main__":
    main()
