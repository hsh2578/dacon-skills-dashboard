"""매수 매력 순위 — '확실성 조정 기대수익률' 순 (2026-11-24). 점수는 코드가 계산한다.

참고: xbtlin/ai-berkshire (버핏·멍거·돤융핑·리루 방법론, MIT) 의 investment-checklist·quality-screen 과
      '확실성 조정 후 수익률' 비교 방식. 그대로 쓰지 않고 우리 데이터(DART 분기 원본)로 계산 가능한 것만 옮겼다.

    점수 = (평소 주주이익 수익률 + 재평가 여지) × 확실성

  평소 주주이익 수익률 (안전마진, 코드) — 이익률은 보수적으로: 지금 > 평소면 평소, 지금 < 평소면 회복 근거(AI)가 있을 때만 평소
      = [ 최근 4분기 매출 × 자기 20분기 중앙 영업이익률 − 최근 4분기 순금융비용(금융비용 − 금융수익) ] × (1 − 22%) × 지배주주 몫 ÷ 시가총액
      · 중앙 이익률 → 정점 마진에 속지 않는다.   · 영업이익 기준 → 자산 매각·평가이익 같은 영업 밖 일회성이 빠진다.
      · 금융비용 차감 → 빚 많은 회사가 싸 보이지 않는다.   · 지배주주 몫(지배 순이익 ÷ 전체 순이익) → 지주회사 과대 방지.
      ponytail: 순금융수익(이자수익 > 비용)은 0으로 둔다 — 순현금 회사는 보수적으로(덜 싸게) 나온다.
  재평가 여지 (AI 판정, %p)
      시장이 과하게 비관(TOO_PESSIMISTIC) +3 · 함정 경계(NOT_…) −3, × 확신도  /  해소 진행 +1.5 · 초기 신호 +.75 · 근거 없음 −1 · 악화 −2
  확실성 (0~1)
      좋은 사업 6관문 (코드, quality-screen 참고 — 5년 · 연간 보고서)
        ① ROE 평균 ≥ 8%  ② 영업현금흐름 ÷ 순이익 ≥ 0.7  ③ 이자보상배율 ≥ 2  ④ 순이익률 평균 ≥ 5%
        ⑤ 누적 FCF(영업현금 − 설비투자) > 0  ⑥ 주식 수 증가 ≤ 20%
        통과 수 6 → 1.0 · 5 → .9 · 4 → .75 · 3 → .6 · ≤2 → .45   (자료 없는 관문은 통과로 본다 — 모름 ≠ 나쁨)
      AI 함정 점검: 확인(SEVERE) ×0.3 — 사실상 탈락 · 구조 변화 ×0.85 · 지배구조 ×0.9 · 기타 주의 ×0.95
      자료가 적은 종목(정보량 C) ×0.9
  동점 → 정량 순위

    python scripts/rank_ai.py      # ai_notes.json + triple_cross.json + financials_q + daily → data/screens/_ranking.json
"""
import json, os, sys
from datetime import date
from pathlib import Path

import numpy as np

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import quality  # noqa: E402
import ttm  # noqa: E402

SC = ROOT / "data" / "screens"
TAX = 0.22
GAP = {"TOO_PESSIMISTIC": 0.03, "FAIR": 0, "NOT_PESSIMISTIC_ENOUGH": -0.03}
CONF = {"HIGH": 1, "MEDIUM": 0.75, "LOW": 0.5}
VERDICT = {"RESOLVING": 0.015, "EARLY_SIGNS": 0.0075, "NO_EVIDENCE": -0.01, "WORSENING": -0.02}
PASS_CERT = {6: 1.0, 5: 0.9, 4: 0.75, 3: 0.6}
GAP_KR = {"TOO_PESSIMISTIC": "시장이 과하게 비관", "FAIR": "가격이 전망 반영", "NOT_PESSIMISTIC_ENOUGH": "함정 경계"}
VERDICT_KR = {"RESOLVING": "해소 진행", "EARLY_SIGNS": "해소 초기 신호", "NO_EVIDENCE": "해소 근거 없음", "WORSENING": "원인 악화"}
TRAP_KR = {"ONE_OFF_EARNINGS": "일회성 이익", "ACCOUNTING": "회계", "STRUCTURAL_BREAK": "구조 변화",
           "GOVERNANCE": "지배구조", "BALANCE_SHEET": "재무 체력"}
CHECKS = ["ROE 평균 ≥8%", "현금흐름/순이익 ≥0.7", "이자보상 ≥2배", "순이익률 평균 ≥5%", "누적 FCF > 0", "주식 수 증가 ≤20%"]


def _series(code):
    p = ROOT / "data" / "financials_q" / f"{code}.json"
    if not p.exists():
        return None
    return {k: v for k, v in json.load(open(p, encoding="utf-8"))["series"].items()
            if v.get("status") == "000" and v.get("currency", "KRW") == "KRW"}


def fundamentals(code):
    """코드로 계산하는 사실들. 없는 값은 None."""
    s = _series(code)
    if not s:
        return None
    st = ttm.disclosed_stac(s, date.today().strftime("%Y%m%d"))
    if not st:
        return None
    T = lambda f: ttm.ttm_eps(s, st, f)
    rev, fc, ni, ni_tot, fi = T("rev"), T("fc"), T("ni"), T("ni_tot"), T("fi")
    # 금융비용에는 이자 말고 외환·파생 손실이 섞인다(HD현대 9개월 4.8조) — 같은 줄의 이익은 금융수익에 있으니 상계한 순금융비용을 쓴다
    net_fc = max((fc or 0) - (fi or 0), 0.0)
    mg = [m for k, m in sorted(quality.margins(s).items()) if k <= st][-20:]
    med = float(np.median(mg)) if len(mg) >= 8 else None
    ctrl = min(max(ni / ni_tot, 0.0), 1.0) if (ni and ni_tot and ni_tot > 0 and ni > 0) else 1.0

    # 좋은 사업 6관문 — 최근 5개 연간 보고서
    yrs = sorted(k for k in s if k.endswith("12") and k <= st)[-5:]
    A = lambda f: [ttm.amount(s[y].get(f)) for y in yrs]
    nis, eqs, revs, ocfs, capex = A("ni"), A("eq"), A("rev"), A("ocf"), A("capex")
    ok = lambda xs: [x for x in xs if x is not None]
    roe = [n / e for n, e in zip(nis, eqs) if n is not None and e and e > 0]
    nm = [n / r for n, r in zip(nis, revs) if n is not None and r and r > 0]
    ocf_ni = sum(ok(ocfs)) / sum(ok(nis)) if (ok(ocfs) and ok(nis) and sum(ok(nis)) > 0) else None
    fcf = sum(o - c for o, c in zip(ocfs, capex) if o is not None and c is not None) if any(c is not None for c in capex) else None
    oi_t = T("oi")
    icr = (oi_t / net_fc if net_fc > 0 else 99.0) if oi_t is not None else None   # 순금융비용 0 이하 = 이자 부담 없음
    dil = dilution(code)
    vals = [np.mean(roe) if len(roe) >= 3 else None, ocf_ni, icr, np.mean(nm) if len(nm) >= 3 else None, fcf, dil]
    rule = [lambda v: v >= 0.08, lambda v: v >= 0.7, lambda v: v >= 2, lambda v: v >= 0.05, lambda v: v > 0, lambda v: v <= 0.2]
    checks = [None if v is None else bool(f(v)) for v, f in zip(vals, rule)]
    return {"net_fc": net_fc, "rev": rev, "med_margin": med, "cur_margin": mg[-1] if mg else None, "fc": fc,
            "ctrl": ctrl, "checks": checks, "check_vals": [None if v is None else float(v) for v in vals]}


def dilution(code):
    """약 5년(1,250거래일) 전 대비 주식 수 증가율. 주식 수 = 시총 ÷ 종가.
    분할·무상증자는 주주 가치가 그대로라 빼야 한다 — 그날 주식 수가 r배 되면서 종가가 1/r 로 떨어진 날이 그것
    (유상증자·전환은 종가가 그만큼 안 떨어진다 → 희석으로 남는다)."""
    p = ROOT / "data" / ".cache" / "daily" / f"{code}.json"
    if not p.exists():
        return None
    d = json.load(open(p, encoding="utf-8"))
    pts = [(m / c, c) for m, c in zip(d["mcap_억"], d.get("close") or []) if m and c]
    if len(pts) < 1000:
        return None
    f, adj = 1.0, [pts[0][0]]
    for (s0, c0), (s1, c1) in zip(pts, pts[1:]):
        r = s1 / s0
        if abs(r - 1) > 0.05 and 0.85 < r * (c1 / c0) < 1.15:
            f *= r
        adj.append(s1 / f)
    base = adj[-1250] if len(adj) >= 1250 else adj[0]
    return adj[-1] / base - 1


def certainty(fund, ai):
    trap = (ai.get("buy_check") or {}).get("trap") or {}
    flags = set(trap.get("flags") or [])
    checks = fund["checks"] if fund else [None] * 6
    passes = sum(1 for c in checks if c is not False)          # 모름(None)은 통과 — 자료 부족 ≠ 나쁜 사업
    c = PASS_CERT.get(passes, 0.45)
    if trap.get("level") == "SEVERE":
        c *= 0.3
    elif trap.get("level") == "WATCH":
        c *= 0.85 if "STRUCTURAL_BREAK" in flags else 0.9 if "GOVERNANCE" in flags else 0.95
    grade = ai.get("info_grade") or (ai.get("resolution") or {}).get("info_grade")
    if grade == "C":
        c *= 0.9
    return round(c, 3), passes


def score(ai, q, fund):
    r = ai.get("resolution") or {}
    gap, v = r.get("expectation_gap"), r.get("verdict")
    mcap = (q.get("market_cap_억") or 0) * 1e8
    # 쓰는 이익률 = 보수적으로. 지금이 평소보다 높으면 평소(정점을 믿지 않는다),
    # 지금이 평소보다 낮으면 회복 근거(해소 진행·초기 신호)가 있을 때만 평소로 — 근거 없이 회복을 가정하지 않는다
    y, used = None, None
    if fund and fund["rev"] and fund["med_margin"] is not None and mcap:
        cur, med = fund["cur_margin"], fund["med_margin"]
        used = med if (cur is None or cur >= med or v in ("RESOLVING", "EARLY_SIGNS")) else cur
        y = (fund["rev"] * used - fund["net_fc"]) * (1 - TAX) * fund["ctrl"] / mcap
    rerate = GAP.get(gap, 0) * CONF.get(r.get("confidence"), 0.75) + VERDICT.get(v, 0)
    cert, passes = certainty(fund, ai)
    total = round(((y if y is not None else 0) + rerate) * cert * 100, 2)      # %p 단위
    b = {"owner_yield": None if y is None else round(y, 4), "rerate": round(rerate, 4), "certainty": cert,
         "good_business": f"{passes}/6", "checks": fund["checks"] if fund else None,
         "check_vals": fund["check_vals"] if fund else None}
    parts = []
    if y is not None:
        parts.append(f"평소 주주이익 수익률 {y:.1%}(≈PER {1 / y:.1f})" if y > 0 else "평소 이익으로는 이자도 못 냄")
        if fund["cur_margin"] and fund["med_margin"] and fund["cur_margin"] > fund["med_margin"] * 1.3:
            parts.append(f"지금 이익률 {fund['cur_margin']:.0%} → 평소 {fund['med_margin']:.0%}로 계산")
        elif used is not None and fund["cur_margin"] is not None and used == fund["cur_margin"] < fund["med_margin"]:
            parts.append(f"이익률 {fund['cur_margin']:.0%}(평소 {fund['med_margin']:.0%}) — 회복 근거가 없어 지금 이익률로 계산")
        if fund["ctrl"] < 0.9:
            parts.append(f"지배주주 몫 {fund['ctrl']:.0%}만 반영")
    else:
        parts.append("평소 이익 산출 불가(자료 부족)")
    parts.append(f"좋은 사업 {passes}/6")
    trap = (ai.get("buy_check") or {}).get("trap") or {}
    if trap.get("level") in ("SEVERE", "WATCH"):
        parts.append(("함정 확인" if trap["level"] == "SEVERE" else "함정 주의") + "(" +
                     ",".join(TRAP_KR.get(f, f) for f in trap.get("flags") or []) + ")")
    parts.append(GAP_KR.get(gap, "판정 없음") + " · " + VERDICT_KR.get(v, "해소 판정 없음"))
    return total, b, " · ".join(parts) + " [정량·AI]"


def main():
    notes = json.load(open(SC / "ai_notes.json", encoding="utf-8"))["items"]
    top = {x["code"]: x for x in json.load(open(SC / "triple_cross.json", encoding="utf-8"))["top"]}
    rows = []
    for it in notes:
        c = it["code"]
        if c not in top:
            sys.exit(f"[ERROR] {c} 가 triple_cross top 에 없다 — ai_stage merge 부터")
        t, b, why = score(it["ai_notes"], top[c], fundamentals(c))
        rows.append({"code": c, "quant_rank": top[c]["rank"], "rerank_score": t, "score_breakdown": b, "rerank_reason": why})
    rows.sort(key=lambda x: (-x["rerank_score"], x["quant_rank"]))
    for i, x in enumerate(rows, 1):
        x["ai_rank"] = i
    out = {"ranking": rows, "ranked_at": date.today().isoformat(), "checks": CHECKS,
           "basis": "매수 매력 순위 = (평소 주주이익 수익률 + 재평가 여지) × 확실성 — scripts/rank_ai.py (ai-berkshire 체크리스트 참고)"}
    (SC / "_ranking.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    names = {i["code"]: i["name"] for i in notes}
    for x in rows:
        b = x["score_breakdown"]
        print(f"{x['ai_rank']:>2} {names[x['code']]:<12} {x['rerank_score']:>6}  수익률 {b['owner_yield']} 재평가 {b['rerate']:+.3f} 확실성 {b['certainty']} ({b['good_business']})")


if __name__ == "__main__":
    main()
