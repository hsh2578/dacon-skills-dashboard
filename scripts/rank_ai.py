"""매수 매력 순위 — 정량 Top 30 안에서 '(주주이익 수익률 + 재평가 수익) × 확실성' 순 (2026-11-24). 점수는 코드.

사용자의 중심 논리: "높은 밸류를 받던 종목은 이유가 있다. 그 이유가 사라지지 않으면 과거 밸류로 회복한다."
정량 계산은 scripts/value_core.py (설계: docs/superpowers/specs/2026-11-24-buy-ranking-design.md, grill-me 비평 반영).
AI(buy-check)는 판정만 한다 — premium.status · premium.reason_type · margin.durable · trap. 같은 판정이면 같은 순위.

  기대 수익(연) = 주주이익 수익률 + 재평가 수익                    (value_core.expected)
  확실성 = 좋은 사업 6관문 × 배당성향 (value_core.certainty_code) × 함정 × 정보량
      함정: 확인(SEVERE) ×0.3 · 구조 변화 ×0.85 · 지배구조·본업 무관 확장 ×0.9 · 기타 주의 ×0.95
      정보량 C(증권사 리포트 0~1건) ×0.9
  점수 = 기대 수익 × 확실성 (기대 수익이 음수면 × (2 − 확실성) — 불확실하다고 덜 나빠지지 않게)
  동점 → 정량 순위

    python scripts/rank_ai.py      # ai_notes.json + triple_cross.json + financials_q + daily + matrix → data/screens/_ranking.json
"""
import json, os, sys
from datetime import date
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import value_core as V  # noqa: E402

SC = ROOT / "data" / "screens"
PREM_KR = {"INTACT": "이유 유효", "WEAKENED": "이유 약해짐", "GONE": "이유 사라짐", "NO_HISTORY": "비교 이력 없음 → 시장 배수"}
TRAP_KR = {"ONE_OFF_EARNINGS": "일회성 이익", "ACCOUNTING": "회계", "STRUCTURAL_BREAK": "구조 변화",
           "GOVERNANCE": "지배구조", "BALANCE_SHEET": "재무 체력", "DIVERSIFICATION": "본업 무관 확장"}


FLAG_MULT = {"STRUCTURAL_BREAK": 0.85, "GOVERNANCE": 0.9, "DIVERSIFICATION": 0.9, "ACCOUNTING": 0.9,
             "BALANCE_SHEET": 0.95, "ONE_OFF_EARNINGS": 0.95}


def trap_mult(trap):
    """확인(SEVERE) ×0.3. 주의(WATCH)는 플래그마다 곱한다 — 3개 겹친 종목과 1개인 종목이 같지 않게. 하한 0.7."""
    if trap.get("level") == "SEVERE":
        return 0.3
    if trap.get("level") == "WATCH":
        m = 1.0
        for x in set(trap.get("flags") or []) or {"OTHER"}:
            m *= FLAG_MULT.get(x, 0.95)
        return max(m, 0.7)
    return 1.0


def score(ai, q, today):
    code = q["code"]
    bc = ai.get("buy_check") or {}
    prem, mg, trap = bc.get("premium") or {}, bc.get("margin") or {}, bc.get("trap") or {}
    r = ai.get("resolution") or {}
    f = V.facts(code, today)
    mcap = (q.get("market_cap_억") or 0) * 1e8
    if not f or not mcap:
        return -99.0, {"note": "계산 불가(자료 부족)"}, "평소 이익 산출 불가(자료 부족)"
    judg = {"premium": prem.get("status"), "reason_type": prem.get("reason_type"),
            "durable": mg.get("durable"), "verdict": r.get("verdict"), "flags": trap.get("flags")}
    e = V.expected(f, mcap, judg, bool(q.get("cyclical_flag")))
    s = V.series(code)
    checks, vals, payout = V.gates(code, s, f["stac"])
    cert_c, passes = V.certainty_code(checks, payout)
    grade = ai.get("info_grade") or r.get("info_grade")
    cert = round(cert_c * trap_mult(trap) * (0.9 if grade == "C" else 1.0), 3)
    total = round(V.signed(e["er"], cert) * 100, 2)
    b = {"er": round(e["er"], 4), "owner_yield": round(e["yield"], 4), "rerate": round(e["rerate"], 4),
         "target_per": None if e["target_per"] is None else round(e["target_per"], 1),
         "cur_per_reval": None if e["cur_per_reval"] is None else round(e["cur_per_reval"], 1),
         "rel_hist": None if e["rel_hist_adj"] is None else round(e["rel_hist_adj"], 2), "premium": e["premium"],
         "margin_used": round(e["margin"], 3), "margin_note": e["margin_note"],
         "certainty": cert, "good_business": f"{passes}/6", "checks": checks, "check_vals": vals,
         "payout": None if payout is None else round(payout, 3)}
    parts = [f"기대 수익 연 {e['er']:+.1%} = 주주이익 수익률 {e['yield']:.1%} + 재평가 {e['rerate']:+.1%}"]
    if e["target_per"] and e["cur_per_reval"]:
        parts.append(f"과거 밸류 {PREM_KR.get(e['premium'], '')} → 목표 PER {e['target_per']:.1f}(정상화 이익 기준 지금 {e['cur_per_reval']:.1f})")
    parts.append(f"이익률 {e['margin']:.0%} — {e['margin_note']}")
    parts.append(f"좋은 사업 {passes}/6")
    if trap.get("level") in ("SEVERE", "WATCH"):
        parts.append(("함정 확인" if trap["level"] == "SEVERE" else "함정 주의") + "(" +
                     ",".join(TRAP_KR.get(x, x) for x in trap.get("flags") or []) + ")")
    return total, b, " · ".join(parts) + " [정량·AI]"


def main():
    notes = json.load(open(SC / "ai_notes.json", encoding="utf-8"))["items"]
    top = {x["code"]: x for x in json.load(open(SC / "triple_cross.json", encoding="utf-8"))["top"]}
    today = date.today().strftime("%Y%m%d")
    rows = []
    for it in notes:
        c = it["code"]
        if c not in top:
            sys.exit(f"[ERROR] {c} 가 triple_cross top 에 없다 — ai_stage merge 부터")
        t, b, why = score(it["ai_notes"], top[c], today)
        rows.append({"code": c, "quant_rank": top[c]["rank"], "rerank_score": t, "score_breakdown": b, "rerank_reason": why})
    rows.sort(key=lambda x: (-x["rerank_score"], x["quant_rank"]))
    for i, x in enumerate(rows, 1):
        x["ai_rank"] = i
    out = {"ranking": rows, "ranked_at": date.today().isoformat(), "checks": V.GATES,
           "basis": "매수 매력 순위 = (주주이익 수익률 + 재평가 수익) × 확실성 — scripts/rank_ai.py · value_core.py"}
    (SC / "_ranking.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    names = {i["code"]: i["name"] for i in notes}
    for x in rows:
        print(f"{x['ai_rank']:>2} {names[x['code']]:<12} {x['rerank_score']:>6}  {x['rerank_reason'][:150]}")


if __name__ == "__main__":
    main()
