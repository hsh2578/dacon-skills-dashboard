"""저평가 점수 → data/screens/triple_cross.json   (v6, 2026-11-23)

목적: 자기 과거 대비 싼 종목을 찾되, 싼 이유가 '미래 이익 악화'·'사업 훼손'인 함정은 거른다.

  가치   s1_per = 1 - 현재PER / 5년 PER 중앙값      s1_pbr = 1 - 현재PBR / 5년 PBR 중앙값
  전망   outlook = 1 - ForwardPER / 5년 PER 중앙값   — 미래 이익으로 봐도 평소보다 싼가
           ForwardPER = 시총 / (FY0 지배순이익 × g),  g = 컨센서스 FwdEPS / FY0 EPS (같은 FnGuide 잣대)
           FwdEPS = (내년E+내후년E)/2, 내후년E 없으면 내년E   (fetch_consensus.forward_eps)
  점수   total = ⅓·Z(PER할인) + ⅓·Z(PBR할인) + ⅓·Z(전망)   — 가중 민감도 백테스트상 차이 없음 → 동일 비중
  필터   퀄리티(quality.py) 하위 20% 는 Top N 자격 없음 — 점수에는 섞지 않는다
  제외   목표가 괴리(upside)는 점수에서 뺐다 (Bradshaw 2013 등: 과대·예측력 약함). 표시용으로만 남김.

PER/PBR 은 시총(보통주+우선주) / DART 지배순이익·지배자본 (build_valuation.py). 중앙값은 이상치(이익 바닥 해의
PER 100배 등)에 끌려가지 않게 하려고 평균 대신 쓴다.
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

# 정량 후보 수. 이 숫자만큼 AI 정성 분석·재순위(ranker)가 돌아간다.
# 2026-08-13 10 → 20으로 확대 (ranker가 고를 수 있는 폭을 넓힘).
# 바꾸면 fetch_batch_api / fetch_financials / AI 분석 대상이 함께 따라온다
# (셋 다 triple_cross.json의 top 배열을 읽는다).
TOP_N = 30   # 2026-11-24 20 → 30: 백테스트상 싼 종목 안의 정량 순서는 잡음 → AI 가 더 넓은 후보에서 거른다
PER_MATRIX = PROJECT / "data" / "matrix" / "per_monthly.json"
PBR_MATRIX = PROJECT / "data" / "matrix" / "pbr_monthly.json"
SCREENS_DIR = PROJECT / "data" / "screens"
SCREENS_DIR.mkdir(parents=True, exist_ok=True)
OUT = SCREENS_DIR / "triple_cross.json"

WEIGHTS = {"per": 1 / 3, "pbr": 1 / 3, "outlook": 1 / 3}
FQ = PROJECT / "data" / "financials_q"
DAILY = PROJECT / "data" / ".cache" / "daily"
PUBLISH = PROJECT / "data" / "daily"   # 사이트 종목 상세 일별 차트 — Top N 만
sys.path.insert(0, str(PROJECT / "scripts"))
import quality  # noqa: E402
import ttm  # noqa: E402
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
    """월별 매트릭스에서 최근 60개월 **중앙값** + 가장 최근 값 (적자=0/null 제외). 필드명 avg_* 는 UI 호환용."""
    series = matrix_data.get(code) or {}
    if not series:
        return None, None

    sorted_dates = sorted(series.keys())[-60:]
    valid_values = [series[d] for d in sorted_dates if series[d] is not None and series[d] > 0]

    if len(valid_values) < 24:   # 백테스트(backtest_value.MIN_HIST)와 같은 기준 — 2년 미만 이력은 '평소'가 없다
        return None, None

    # 가장 최근 양수 값
    cur = None
    for d in reversed(sorted_dates):
        if series[d] is not None and series[d] > 0:
            cur = series[d]
            break

    return round(float(np.median(valid_values)), 4), round(cur, 4) if cur else None


def _clean(o):
    """NaN → None (JSON 표준·브라우저는 NaN 을 못 읽는다)."""
    if isinstance(o, float) and o != o:
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


def expectations(ser, st, mcap, med_per, cur_per, fwd_ni):
    """가격이 깔고 있는 기대 — Mauboussin 역산·Damodaran 정상화의 단순판.

      implied_ni      = 시총 / 5년 PER 중앙값          (평소 PER을 받으려면 필요한 이익)
      implied_fade    = implied_ni / Forward 이익       (<1: 시장이 컨센서스보다 이익이 줄어든다고 가격을 매김)
      implied_vs_ttm  = implied_ni / TTM 이익
      midcycle_vs_ttm = (5년 영업이익률 중앙값 × TTM 매출) / TTM 영업이익   (<1: 지금 마진이 평소보다 높다)
      cyclical_flag   = 최근 20분기 TTM 영업이익률이 적자를 오갔거나, 최고/최저 ≥ 3배, 또는 현재가 중앙값의 2배 이상
    """
    out = {"implied_fade": np.nan, "implied_vs_ttm": np.nan, "midcycle_vs_ttm": np.nan,
           "opm_ttm": np.nan, "opm_med5y": np.nan, "cyclical_flag": False}
    if not (mcap and med_per):
        return out
    implied = mcap / med_per
    if fwd_ni and fwd_ni > 0:
        out["implied_fade"] = implied / fwd_ni
    if cur_per:
        out["implied_vs_ttm"] = implied / (mcap / cur_per)
    if not st:
        return out
    mg = [m for _, m in sorted(quality.margins(ser).items())][-20:]
    if len(mg) >= 8:
        cur, med = mg[-1], float(np.median(mg))
        out["opm_ttm"], out["opm_med5y"] = cur, med
        pos = [m for m in mg if m > 0]
        out["cyclical_flag"] = bool(min(mg) <= 0 < max(mg)
                                    or (pos and min(pos) > 0 and max(pos) / min(pos) >= 3)
                                    or (med > 0 and cur >= 2 * med))
        if cur > 0:
            out["midcycle_vs_ttm"] = med / cur
    return out


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
        target = s.get("avg_target_price")
        close = s.get("close")

        ser, mcap = {}, None
        fq = FQ / f"{code}.json"
        if fq.exists():
            ser = {k: v for k, v in json.loads(fq.read_text(encoding="utf-8"))["series"].items()
                   if v.get("status") == "000" and v.get("currency", "KRW") == "KRW"}
        dp = DAILY / f"{code}.json"
        if dp.exists():
            dd = json.loads(dp.read_text(encoding="utf-8"))
            mcap = dd["mcap_억"][-1] * 1e8 if dd["mcap_억"] else None

        # 전망: FY0(직전 결산) 지배순이익 × 컨센서스 성장배수 → 시총 기준 Forward PER
        fy0_eps, fwd_eps = s.get("fy0_eps"), s.get("fwd_eps")
        fy0_stac = f"{datetime.now().year - 1}12"
        ni_fy0 = ttm.amount((ser.get(fy0_stac) or {}).get("ni"))
        if ni_fy0 is None and ser:
            # 1~3월엔 직전 연도 사업보고서가 아직 없다 → 최근 4분기 합(TTM)으로 대신.
            # 안 하면 매년 1분기에 전 종목 전망 팩터가 비어 점수 ⅓이 조용히 0이 된다 (2026-11-24 grill 발견)
            ni_fy0 = ttm.ttm_eps(ser, max(ser), "ni")
        g = fwd_eps / fy0_eps if (fwd_eps and fy0_eps and fy0_eps > 0) else None
        fwd_per = mcap / (ni_fy0 * g) if (mcap and ni_fy0 and ni_fy0 > 0 and g and g > 0) else None

        s1_per = (avg_per - cur_per) / avg_per if avg_per and cur_per else np.nan
        s1_pbr = (avg_pbr - cur_pbr) / avg_pbr if avg_pbr and cur_pbr else np.nan
        outlook = 1 - fwd_per / avg_per if (fwd_per and avg_per) else np.nan
        upside = (target - close) / close if target and close else np.nan   # 표시용

        st = max(ser) if ser else None
        q = quality.metrics(ser, st) if st else (np.nan,) * 3
        exp = expectations(ser, st, mcap, avg_per, cur_per, ni_fy0 * g if (ni_fy0 and g) else None)
        annual_eps = fy0_eps
        base_per = None
        s3_per = outlook

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
            "base_per": base_per,          # s3_per 기준선 (직전 결산 PER)
            "annual_eps": annual_eps,
            "fwd_year": s.get("fwd_basis"),
            "fwd_eps": fwd_eps,
            "avg_target": target,
            "broker_count": s.get("broker_count"),
            "s1_per": s1_per,
            "s1_pbr": s1_pbr,
            "s3_per": s3_per,
            "upside": upside,
            "q_trend": q[0], "q_accr": q[1], "q_icr": q[2],
            **exp,
        })

    df = pd.DataFrame(rows)
    print(f"  종목 {len(df)}개")

    print("\n[2/4] Rank → Z ...")
    for col in ["s1_per", "s1_pbr", "s3_per"]:
        df[f"{col}_z"] = _safe_zscore(df[col].rank(ascending=True, na_option="keep"))
    df["upside_z"] = np.nan                       # 점수 미사용 (UI 호환 필드)
    df["value_score"] = _safe_zscore(df[["s1_per_z", "s1_pbr_z"]].sum(axis=1, skipna=True, min_count=1))
    df["growth_score"] = df["s3_per_z"]           # = 전망(outlook). 필드명은 UI 호환
    # 2026-11-24 ⅓씩: 가치50/전망50 이면 PER 계열(PER할인·전망, 상관 0.56)이 실효 75%를 차지했다.
    # 백테스트(40개월)에서 PER:PBR 가중을 1:0~0:1 로 바꿔도 IC 0.034~0.040 — 최적화할 근거가 없어 동일 비중.
    print("[3/4] 동일 비중 합산 (PER할인 ⅓ · PBR할인 ⅓ · 전망 ⅓)...")
    df["total_score"] = (df["s1_per_z"].fillna(0) * WEIGHTS["per"] + df["s1_pbr_z"].fillna(0) * WEIGHTS["pbr"]
                         + df["s3_per_z"].fillna(0) * WEIGHTS["outlook"])
    print("[4/4] 퀄리티 필터 (하위 20% → Top N 자격 없음)...")
    df["quality_pass"], df["quality_score"] = quality.passes(df[["q_trend", "q_accr", "q_icr"]])

    # 8. 정렬
    # 퀄리티 통과 종목을 앞에 — Top N 은 통과 종목에서만 뽑힌다. 탈락 종목도 all_ranked 에는 남긴다.
    df = df.sort_values(["quality_pass", "total_score"], ascending=[False, False]).reset_index(drop=True)
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

        # 티어 — 전 종목 STRONG_BUY로 통일.
        # (메인 순위는 ranker의 ai_rank(저평가 해소 가능성)이며,
        #  정량 Z-score 기반 티어 세분(HIDDEN_GEM/BUY/WATCH 등)은
        #  순위 축과 달라 혼란을 주므로 미사용)
        total = r["total_score"]
        tier = "MISS" if pd.isna(total) else "STRONG_BUY"

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
            "outlook_raw": _round(r["s3_per"]),
            "quality_pass": bool(r["quality_pass"]),
            "quality_score": _round(r["quality_score"], 3),
            "q_trend": _round(r["q_trend"]), "q_accr": _round(r["q_accr"]), "q_icr": _round(r["q_icr"], 2),
            # 기대 역산 [정량] — 에이전트가 '가격이 깐 가정 vs 증거'를 판정하는 입력 (계산은 여기서만)
            "implied_fade": _round(r["implied_fade"], 3),
            "implied_vs_ttm": _round(r["implied_vs_ttm"], 3),
            "midcycle_vs_ttm": _round(r["midcycle_vs_ttm"], 3),
            "opm_ttm": _round(r["opm_ttm"]), "opm_med5y": _round(r["opm_med5y"]),
            "cyclical_flag": bool(r["cyclical_flag"]),
        })

    triple_count = sum(1 for r in out_records if r["triple_cross"])
    out = {
        "meta": {
            "rule": "v6 — PER할인·PBR할인·전망(Forward PER vs 5년 중앙값) 동일 비중, 퀄리티 하위 20% Top N 제외",
            "universe_size": len(universe),
            "factors": ["s1_per", "s1_pbr", "outlook(s3_per 필드)"],
            "quality_filter": {"metrics": ["q_trend", "q_accr", "q_icr"], "cut": quality.Q_CUT},
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
        "top": out_records[:TOP_N],
        "all_ranked": out_records,
        "avoid": [],
    }
    # NaN 은 파이썬은 읽지만 JSON 표준·브라우저는 못 읽는다 → 사이트 Top 목록이 통째로 사라진다 (2026-11-24 발견:
    # 목표가 없는 종목을 유니버스에 남기면서 broker_count 가 NaN 이 됨). null 로 바꾸고 allow_nan=False 로 막는다.
    OUT.write_text(json.dumps(_clean(out), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    # AI 에이전트 입력 (/update-data 2단계) — 정량 필드만 추려 둔다
    ctx = [{"name": r["name"], "code": r["code"], "rank": r["rank"], "market_cap_억": r["market_cap_억"],
            "valuation": {k: r.get(k) for k in ("current_price", "current_per", "avg_5y_per", "cur_pbr", "avg_5y_pbr",
                                                 "forward_per", "fwd_year", "avg_target", "broker_count")},
            "factors": {k: r.get(k) for k in ("s1_per_raw", "s1_per_z", "s1_pbr_raw", "s1_pbr_z", "outlook_raw", "s3_per_z")},
            "scores": {k: r.get(k) for k in ("value_score", "growth_score", "total_score")},
            "expectations": {k: r.get(k) for k in ("implied_fade", "implied_vs_ttm", "midcycle_vs_ttm",
                                                    "opm_ttm", "opm_med5y", "cyclical_flag")},
            "quality": {k: r.get(k) for k in ("quality_score", "q_trend", "q_accr", "q_icr")},
            "note": "avg_5y_* 는 5년 중앙값. forward_per = 시총/(FY0 지배순이익×컨센서스 성장배수). 목표가는 점수 미사용."}
           for r in out_records[:TOP_N]]
    (SCREENS_DIR / "_top_context.json").write_text(json.dumps(_clean(ctx), ensure_ascii=False, indent=1,
                                                              allow_nan=False), encoding="utf-8")

    # ── 검색 대상(시총 2,000억+ 보통주 전체) — Top N 밖 종목도 일별 차트·PER·재무를 볼 수 있게 (2026-11-24) ──
    # 점수·AI 는 universe 안만. 여기서는 이미 받은 데이터로 '보여 주기'만 채운다 (추가 API 호출 없음).
    import shutil
    ex = universe_doc.get("excluded") or {}
    pool, seen = [], set()
    for s_ in (universe_doc.get("stage1") or []) + universe + sum((ex.get(k) or [] for k in
               ("validation_adverse", "validation_short", "validation_nodata", "no_fy1_eps")), []):
        if s_.get("code") and s_["code"] not in seen:
            seen.add(s_["code"]); pool.append(s_)
    ranked = {r["code"]: r for r in out_records}
    index = []
    for s_ in pool:
        c = s_["code"]
        med_per, cur_per = _calc_avg_and_cur(per_matrix, c)
        med_pbr, cur_pbr = _calc_avg_and_cur(pbr_matrix, c)
        r = ranked.get(c) or {}
        index.append({"code": c, "name": s_.get("name"), "market": s_.get("market"),
                      "market_cap_억": s_.get("market_cap_억"), "close": s_.get("close"),
                      "cur_per": cur_per, "med_per": med_per, "cur_pbr": cur_pbr, "med_pbr": med_pbr,
                      "rank": r.get("rank"), "total_score": r.get("total_score"),
                      "forward_per": r.get("forward_per"), "avg_target": r.get("avg_target"),
                      "in_universe": c in ranked, "reason": s_.get("reason")})
    (SCREENS_DIR / "search_index.json").write_text(
        json.dumps({"count": len(index), "items": _clean(index)}, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    PUBLISH.mkdir(parents=True, exist_ok=True)
    for f in PUBLISH.glob("*.json"):
        f.unlink()
    for s_ in pool:
        src = DAILY / f"{s_['code']}.json"
        if src.exists():
            shutil.copy(src, PUBLISH / src.name)

    # 재무 추이 파일이 없는 검색 대상은 DART 분기 데이터(financials_q)에서 연간을 파생 — 호출 없음
    fin_dir = PROJECT / "data" / "financials"
    for s_ in pool:
        out_f = fin_dir / f"{s_['code']}.json"
        q = FQ / f"{s_['code']}.json"
        if out_f.exists() or not q.exists():
            continue
        ser = {k: v for k, v in json.loads(q.read_text(encoding="utf-8"))["series"].items()
               if v.get("status") == "000" and v.get("currency", "KRW") == "KRW"}
        ann = []
        for st in sorted(k for k in ser if k.endswith("12"))[-6:]:
            v = ser[st]
            rev, oi, ni = v.get("rev"), v.get("oi"), v.get("ni")
            ann.append({"year": int(st[:4]), "revenue": rev, "op_income": oi,
                        "op_margin": round(oi / rev, 4) if rev and oi is not None else None,
                        "net_income": ni, "net_margin": round(ni / rev, 4) if rev and ni is not None else None,
                        "fs_div": v.get("fs")})
        lq = max(ser) if ser else None
        latest = None
        if lq and not lq.endswith("12"):
            v = ser[lq]; rev, oi, ni = v.get("rev"), v.get("oi"), v.get("ni")
            latest = {"period": f"{lq[:4]}-{int(lq[4:]) // 3}Q(누적)", "revenue": rev, "op_income": oi,
                      "op_margin": round(oi / rev, 4) if rev and oi is not None else None,
                      "net_income": ni, "net_margin": round(ni / rev, 4) if rev and ni is not None else None,
                      "fs_div": v.get("fs")}
        if ann:
            out_f.write_text(json.dumps(_clean({"code": s_["code"], "source": "DART 분기 파생 (financials_q)",
                                               "unit": "원", "annual": ann, "latest_quarter": latest}),
                                        ensure_ascii=False, allow_nan=False), encoding="utf-8")

    print(f"\n  → {OUT.relative_to(PROJECT)}")
    print(f"\n  === Top 10 ===")
    print(f"  {'#':<3} {'종목':<14} {'CurPER':>7} {'5YPER':>7} {'FwdPER':>7} "
          f"{'CurPBR':>7} {'5YPBR':>7} {'Up%':>6} {'Total':>7}")
    for r in out_records[:TOP_N]:
        up_pct = (r["upside_raw"] * 100) if r["upside_raw"] is not None else 0
        print(f"  {r['rank']:<3} {r['name']:<14} {r['tier']:<11} "
              f"{(r['current_per'] or 0):>7.2f} {(r['avg_5y_per'] or 0):>7.2f} {(r['forward_per'] or 0):>7.2f} "
              f"{(r['cur_pbr'] or 0):>7.2f} {(r['avg_5y_pbr'] or 0):>7.2f} "
              f"{up_pct:>6.1f} {r['total_score']:>7.3f}")


if __name__ == "__main__":
    main()
