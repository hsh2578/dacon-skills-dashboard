"""AI 재순위 — 점수는 코드가 계산한다 (2026-11-24, ranker 에이전트 대체).

왜: 같은 판정을 넣어도 ranker 에이전트가 돌 때마다 규칙을 다르게 해석해 순위가 몇 칸씩 흔들렸다
    (에스티팜 1→5위, HD현대 10→16위 — 판정은 그대로). 또 옛 §4.6 보조 점수는 정량 점수(evidence_strength)와
    이미 센 판정(verdict 문구 = gap × risk)을 한 번 더 세는 중복이었다.
AI 는 종목별 판정(expectation_gap·verdict·confidence·risk_level)만 내리고, 합산은 여기서 한다.

  1 가격 판정 (1순위 — "싼 게 미래가 나빠서인가, 시장이 과하게 비관한 건가")
      TOO_PESSIMISTIC +4 · FAIR 0 · NOT_PESSIMISTIC_ENOUGH −4, × confidence(HIGH 1 · MEDIUM .75 · LOW .5)
  2 해소 근거  RESOLVING +2 · EARLY_SIGNS +1 · NO_EVIDENCE −1.5 · WORSENING −2.5
      (+만) 1-2Q +.5 · 1년+/불명 −.5 · 반증 수 ≥ 근거 수 −.5
  3 실적 = DART 지배 TTM 영업이익 전년 대비 (예상치가 아니라 발표된 숫자)
      ≥+30% +1.5 · +10~30% +.75 · ±10% 0 · ≤−10% −1.5 · 적자→흑자 +1.5 · 적자 −1.5
  4 퀄리티 점수(유니버스 순위 0~1) → (q−.5)×3 = ±1.5   ┐ 백테스트로 확인된 두 가지 (backtest_signals.py)
  5 영업이익률 ÷ 자기 5년 중앙  ≥1.2 +.75 · ≤0.8 −.75   ┘ (옛 '이익 정점이면 가점 제외'는 데이터와 반대라 삭제)
  6 함정 점검 (buy-check 에이전트 trap.level)  SEVERE −3 · WATCH −.75
  7 risk_level  LOW +.5 · HIGH −.5
  동점 → 정량 순위

    python scripts/rank_ai.py      # ai_notes.json + triple_cross.json + financials_q → data/screens/_ranking.json
"""
import json, os, sys
from datetime import date
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ttm  # noqa: E402

SC = ROOT / "data" / "screens"
GAP = {"TOO_PESSIMISTIC": 4, "FAIR": 0, "NOT_PESSIMISTIC_ENOUGH": -4}   # 한 단계(×.75=3)가 나머지 차이(해소 1 + 실적 1.5)보다 크게 — 1순위 보장
CONF = {"HIGH": 1, "MEDIUM": 0.75, "LOW": 0.5}
VERDICT = {"RESOLVING": 2, "EARLY_SIGNS": 1, "NO_EVIDENCE": -1.5, "WORSENING": -2.5}
RISK = {"LOW": 0.5, "MEDIUM": 0, "HIGH": -0.5}
TRAP = {"SEVERE": -3, "WATCH": -0.75, "NONE": 0}
TRAP_KR = {"ONE_OFF_EARNINGS": "일회성 이익", "ACCOUNTING": "회계", "STRUCTURAL_BREAK": "구조 변화",
           "GOVERNANCE": "지배구조", "BALANCE_SHEET": "재무 체력"}
GAP_KR = {"TOO_PESSIMISTIC": "가격이 과도하게 비관", "FAIR": "가격이 전망 반영", "NOT_PESSIMISTIC_ENOUGH": "함정 경계"}
VERDICT_KR = {"RESOLVING": "해소 진행", "EARLY_SIGNS": "해소 초기 신호", "NO_EVIDENCE": "해소 근거 없음", "WORSENING": "원인 악화"}


def oi_yoy(code):
    """(TTM 영업이익 전년 대비 증감률, 지금 TTM, 1년 전 TTM). 데이터 없으면 (None, None, None)."""
    p = ROOT / "data" / "financials_q" / f"{code}.json"
    if not p.exists():
        return None, None, None
    s = {k: v for k, v in json.load(open(p, encoding="utf-8"))["series"].items()
         if v.get("status") == "000" and v.get("currency", "KRW") == "KRW"}
    st = ttm.disclosed_stac(s, date.today().strftime("%Y%m%d"))
    if not st:
        return None, None, None
    now, prev = ttm.ttm_eps(s, st, "oi"), ttm.ttm_eps(s, f"{int(st[:4]) - 1}{st[4:]}", "oi")
    if now is None or prev is None:
        return None, now, prev
    return (now / prev - 1 if prev > 0 else None), now, prev


def earnings_pts(yoy, now, prev):
    if now is None or prev is None:
        return 0.0
    if now <= 0:
        return -1.5
    if prev <= 0:
        return 1.5
    return 1.5 if yoy >= 0.3 else 0.75 if yoy >= 0.1 else -1.5 if yoy <= -0.1 else 0.0


def score(ai, q, oi):
    """ai = ai_notes, q = triple_cross top 항목, oi = oi_yoy() 결과. (총점, 내역, 이유 문구)."""
    r = ai.get("resolution") or {}
    gap, v = r.get("expectation_gap"), r.get("verdict")
    b = {"1_gap": GAP.get(gap, 0) * CONF.get(r.get("confidence"), 0.75)}
    res = VERDICT.get(v, 0)
    if res > 0:
        w = r.get("expected_window") or "불명"
        res += 0.5 if w == "1-2Q" else -0.5 if (w.startswith("1년") or w == "불명") else 0
        if len(r.get("counter_evidence") or []) >= len(r.get("evidence") or []):
            res -= 0.5
    b["2_resolution"] = res
    b["3_earnings"] = earnings_pts(*oi)
    # 백테스트(backtest_signals.py, 싼 종목 안 43개월): 퀄리티 IC +0.054(t 3.9) · 이익률/자기 중앙 +0.034(t 2.8).
    # 그래서 옛 '이익 정점이면 실적 가점 제외'는 뺐다 — 과거엔 이익률이 평소보다 높은 싼 종목이 오히려 더 올랐다.
    qs = q.get("quality_score")
    b["4_quality"] = round((qs - 0.5) * 3, 2) if qs is not None else 0.0
    ot, om = q.get("opm_ttm"), q.get("opm_med5y")
    ratio = ot / om if (ot is not None and om and om > 0) else None
    b["5_margin"] = 0.75 if (ratio and ratio >= 1.2) else -0.75 if (ratio is not None and ratio <= 0.8) else 0.0
    trap = ((ai.get("buy_check") or {}).get("trap") or {})
    b["6_trap"] = TRAP.get(trap.get("level"), 0)
    b["7_risk"] = RISK.get(ai.get("risk_level"), 0)
    total = round(sum(b.values()), 2)
    yoy = oi[0]
    parts = [GAP_KR.get(gap, "판정 없음"), VERDICT_KR.get(v, "해소 판정 없음") + (f"({r.get('expected_window')})" if res > 0 and r.get("expected_window") else ""),
             "영업이익(4분기 합) " + (f"{yoy:+.0%}" if yoy is not None else ("적자" if (oi[1] or 0) <= 0 and oi[1] is not None else "흑자전환" if oi[1] else "자료 없음")) + " [출처: DART]"]
    if qs is not None:
        parts.append(f"퀄리티 상위 {100 - round(qs * 100)}%" if qs >= 0.5 else f"퀄리티 하위 {round(qs * 100)}%")
    if trap.get("level") in ("SEVERE", "WATCH"):
        parts.append(("함정 확인" if trap["level"] == "SEVERE" else "함정 주의") + "(" + ",".join(TRAP_KR.get(f, f) for f in trap.get("flags") or []) + ")")
    return total, b, " · ".join(parts)


def main():
    notes = json.load(open(SC / "ai_notes.json", encoding="utf-8"))["items"]
    top = {x["code"]: x for x in json.load(open(SC / "triple_cross.json", encoding="utf-8"))["top"]}
    rows = []
    for it in notes:
        c = it["code"]
        if c not in top:
            sys.exit(f"[ERROR] {c} 가 triple_cross top 에 없다 — ai_stage merge 부터")
        t, b, why = score(it["ai_notes"], top[c], oi_yoy(c))
        rows.append({"code": c, "quant_rank": top[c]["rank"], "rerank_score": t, "score_breakdown": b, "rerank_reason": why})
    rows.sort(key=lambda x: (-x["rerank_score"], x["quant_rank"]))
    for i, x in enumerate(rows, 1):
        x["ai_rank"] = i
    out = {"ranking": rows, "ranked_at": date.today().isoformat(),
           "basis": "매수 매력 순위 — scripts/rank_ai.py: 가격 판정(×확신도) · 해소 근거 · DART TTM 영업이익 YoY · 퀄리티 · 이익률 수준 · 함정 점검 · 리스크. AI 는 판정만, 합산은 코드"}
    (SC / "_ranking.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    names = {i["code"]: i["name"] for i in notes}
    for x in rows:
        print(f"{x['ai_rank']:>2} {names[x['code']]:<12} {x['rerank_score']:>5}  {x['rerank_reason']}")


if __name__ == "__main__":
    main()
