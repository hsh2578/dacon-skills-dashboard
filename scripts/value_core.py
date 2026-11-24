"""매수 매력 점수의 정량 핵심 — 1차 선별(apply_triple_cross)과 최종 순위(rank_ai)가 같은 정의를 쓴다 (2026-11-24).

사용자의 중심 논리: "높은 밸류를 받던 종목은 이유가 있다. 그 이유가 사라지지 않으면 과거 밸류로 회복한다."
설계 문서: docs/superpowers/specs/2026-11-24-buy-ranking-design.md (grill-me 비평 반영)

  기대 수익(연) = 주주이익 수익률 + 재평가 수익
  ─ 믿을 수 있는 이익 (주주이익)
      이익률: AI 가 '이익률 상승이 구조적'이라 하면 최근 8분기 중앙 · 아니면 지금 > 평소일 때 평소(정점 불신)
              · 지금 < 평소일 때 회복 근거(해소 진행·초기 신호)가 있어야 평소, 없으면 지금
              (평소 = 자기 최대 40분기 TTM 영업이익률 중앙 — 한국 수출 경기순환 한 바퀴)
      매출: 경기순환 표시 + 구조적 아님 → min(지금, 최근 3년 TTM 매출 평균)  (사이클 정점 매출 불신)
      이익 = min( 매출 × 이익률 × (1−22%) × 이익 전환율 × 지배주주 몫 ,  지배 순이익 TTM × 이익률 비율 × 매출 비율 )
             이익 전환율 = 전체 순이익 ÷ 세후 영업이익 (이자·영업외), 지배주주 몫 — 둘 다 최근 8개 결산기 누적의 중앙
             앞쪽은 영업 밖 일회성(자산 매각·평가이익)을, 뒤쪽은 실제 순이익을 반영 → 둘 중 작은 쪽(보수적)
  ─ 재평가 수익 = (목표 시총 ÷ 시총)^(1/n) − 1, 상한·하한 ±30%/년
      목표 PER = 자기 '상대 PER' 이력 중앙 × 지금 시장 PER       (상대 PER = 종목 PER ÷ 같은 날 유니버스 중앙 PER)
               → 시장 전체가 싸진 효과를 빼고 '그 종목이 시장 대비 받던 프리미엄'만 본다 (grill 결함 1)
               → 매달의 상대 PER 을 (그 달 이익률 ÷ 지금 쓰는 이익률)로 환산 — 저마진기 PER 의 분모 착시 제거 (grill 3차)
      프리미엄 생존(AI): 살아 있음 = 과거 상대 PER · 약해짐 = 과거와 시장의 기하평균 · 사라짐 = 시장 평균(1.0)
               할인 종목(상대 < 1)은 '사라짐'이 확인될 때만 시장 수준으로. 비교 이력이 없으면 시장 배수. 일회성 이익 표시면 보수적 이익 기준
               (AI 전 1차 선별은 '약해짐'으로 가정)
      회복 기간 n: 해소 진행·초기 신호 3년 · 근거 없음 5년 · 악화 = 사라짐 취급
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

import quality
import ttm

ROOT = Path(__file__).resolve().parent.parent
TAX = 0.22
MARGIN_Q = 40
CLAMP = 0.30


def series(code):
    p = ROOT / "data" / "financials_q" / f"{code}.json"
    if not p.exists():
        return None
    s = {k: v for k, v in json.load(open(p, encoding="utf-8"))["series"].items()
         if v.get("status") == "000" and v.get("currency", "KRW") == "KRW"}
    return s or None


@lru_cache(maxsize=1)
def _per_matrix():
    return json.load(open(ROOT / "data/matrix/per_monthly.json", encoding="utf-8"))["matrix"]


@lru_cache(maxsize=1)
def market_median():
    """{월말키: 유니버스(시총 2,000억+ 1단계) PER 중앙} — 적자(PER 없음) 제외."""
    u = json.load(open(ROOT / "data/universe.json", encoding="utf-8"))
    codes = {s["code"] for s in (u.get("stage1") or u.get("stocks") or [])}
    m = _per_matrix()
    by = {}
    for c in codes:
        for k, v in (m.get(c) or {}).items():
            if v and v > 0:
                by.setdefault(k, []).append(v)
    return {k: float(np.median(v)) for k, v in by.items() if len(v) >= 50}


def relative_history(code, s):
    """최근 60개월 상대 PER — (단순 중앙, 개월 수, [(상대 PER, 그 달 TTM 이익률)]). 이익률 보정은 expected() 가 한다."""
    mm, per = market_median(), (_per_matrix().get(code) or {})
    mg = quality.margins(s)
    rows = []
    for k in sorted(per)[-61:-1]:                     # 마지막 달은 '지금'이라 뺀다
        v, st = per[k], ttm.disclosed_stac(s, k)
        if v and v > 0 and k in mm:
            rows.append((v / mm[k], mg.get(st)))        # 이익률을 모르는 달(옛 공시에 매출·영업이익 태그 없음)도 PER 이력은 쓴다
    if len(rows) < 24:
        return None, len(rows), rows
    return float(np.median([r for r, _ in rows])), len(rows), rows


def facts(code, today):
    """AI 와 무관한 사실들 (rank_ai 가 AI 판정과 합친다)."""
    s = series(code)
    if not s:
        return None
    st = ttm.disclosed_stac(s, today)
    if not st:
        return None
    mg = quality.margins(s)
    past = [m for k, m in sorted(mg.items()) if k <= st]
    T = lambda f, x=st: ttm.ttm_eps(s, x, f)
    rev = T("rev")
    if not rev or rev <= 0 or len(past) < 8:
        return None
    ni, ni_tot = T("ni"), T("ni_tot")
    # 지배주주 몫·이익 전환율(전체 순이익 ÷ 세후 영업이익 — 이자·영업외 손익)을 최근 8개 결산기 누적값의 중앙으로.
    # 한 분기의 대규모 손상(CJ제일제당 4Q25)이 TTM 을 적자로 만들어도 흔들리지 않게 한다.
    ctrls, convs = [], []
    for k in [k for k in sorted(s) if k <= st][-8:]:
        v = s[k]
        n, nt, o = ttm.amount(v.get("ni")), ttm.amount(v.get("ni_tot")), ttm.amount(v.get("oi"))
        if n and nt and n > 0 and nt > 0:
            ctrls.append(min(n / nt, 1.0))
        if nt and o and nt > 0 and o > 0:
            convs.append(min(nt / (o * (1 - TAX)), 1.0))
    stacs = [k for k in sorted(s) if k <= st][-12:]
    revs3 = [r for r in (T("rev", k) for k in stacs) if r]
    rel, n_rel, rel_rows = relative_history(code, s)
    mm = market_median()
    return {"rev": rev, "rev_3y": float(np.mean(revs3)) if len(revs3) >= 8 else rev,
            "med": float(np.median(past[-MARGIN_Q:])), "recent8": float(np.median(past[-8:])), "cur": past[-1],
            "ni": ni, "ctrl": float(np.median(ctrls)) if ctrls else 1.0, "conv": float(np.median(convs)) if convs else 0.5,
            "rel_hist": rel, "rel_months": n_rel, "rel_rows": rel_rows, "mkt_per": mm[max(mm)] if mm else None, "stac": st}


def expected(f, mcap, ai=None, cyclical=False):
    """기대 수익(연)과 구성. ai = {'premium', 'reason_type', 'durable', 'verdict', 'flags'} (없으면 1차 선별 가정).
    grill 2차(2026-11-24) 반영: 재평가는 과거 PER 과 같은 기준(순이익)으로 · 이익률 규칙 연속화 · 음수 재평가 5년 ·
    할인 종목은 근거 없이 오르지 않음 · 이력 없으면 시장 배수."""
    ai = ai or {}
    verdict, flags = ai.get("verdict"), set(ai.get("flags") or [])
    # AI 판정끼리 모순이면 보수적인 쪽 — 구조 변화·일회성 이익 함정이 있는데 '이익률이 구조적'일 수 없다
    durable = bool(ai.get("durable")) and not (flags & {"STRUCTURAL_BREAK", "ONE_OFF_EARNINGS"})
    # 이익률 (먼저 정한다 — 과거 상대 PER 을 같은 이익률 기준으로 환산하는 데 쓴다)
    med3 = float(np.median([f["med"], f["recent8"], f["cur"]]))
    if durable:
        margin, m_note = f["recent8"], "구조적 개선 인정(최근 8분기)"
    elif f["cur"] >= f["med"]:
        margin, m_note = (f["med"] + med3) / 2, "정점 불신(10년 평소와 최근의 중간)"
    elif verdict in ("RESOLVING", "EARLY_SIGNS"):
        margin, m_note = f["med"], "회복 근거 있음(10년 평소)"
    else:
        margin, m_note = med3, "회복 근거 없음(10년 평소·최근 2년·지금의 중앙)"
    # 과거 상대 PER 을 지금 쓰는 이익률 기준으로 환산 — 과거 PER 은 그때의 이익률 위에서 매겨졌다.
    # 저마진기에 받은 높은 PER 을 고마진 이익에 그대로 곱하면 프리미엄이 부풀려진다 (grill 3차: 세진중공업 1.86→0.92)
    rows = f.get("rel_rows") or []
    adj = [r * (float(np.clip(m / margin, 1 / 3, 3)) if (m is not None and m > 0 and margin > 0) else 1.0) for r, m in rows]
    rel_hist = float(np.median(adj)) if len(adj) >= 24 else f.get("rel_hist")
    is_premium = (rel_hist or 1.0) > 1
    premium = ai.get("premium") or "WEAKENED"
    if premium == "INTACT" and ai.get("reason_type") in ("CYCLE", "THEME") and is_premium:
        premium = "WEAKENED"      # 경기 호황·테마 프리미엄은 회복 대상이 아니다 (해자와 구분)
    if verdict == "WORSENING" and is_premium:
        premium = "GONE"          # 원인 악화 → 프리미엄 상실 (할인 종목에선 GONE 이 '시장 수준 재평가'라 적용 안 함)

    rev = min(f["rev"], f["rev_3y"]) if (cyclical and not durable) else f["rev"]
    e_oi = rev * margin * (1 - TAX) * f["conv"] * f["ctrl"]
    e_ni = f["ni"] * (margin / f["cur"]) * (rev / f["rev"]) if (f["ni"] and f["ni"] > 0 and f["cur"] > 0) else None
    owner = min(e_oi, e_ni) if e_ni is not None else e_oi          # 수익률은 보수적으로 (둘 중 작은 쪽)
    y = owner / mcap

    # 재평가 — 과거 PER(순이익 기준)과 같은 기준의 이익: 순이익을 위 이익률로 정상화한 값 (이중 차감 방지)
    e_rev = e_ni if e_ni is not None else e_oi
    if "ONE_OFF_EARNINGS" in flags:
        e_rev = owner              # 일회성 이익이 확인되면 순이익 기준을 믿지 않는다 (grill 3차: HD현대·대웅제약)
    rer, target_per, rel = 0.0, None, None
    if f["mkt_per"] and e_rev > 0:
        if rel_hist is None:
            rel, premium = 1.0, "NO_HISTORY"                     # 비교할 과거가 없으면 시장 배수 (프리미엄 근거 없음)
        elif not is_premium:
            rel = 1.0 if premium == "GONE" else rel_hist         # 할인은 이유가 '사라졌다'고 확인돼야 시장 수준으로
        else:
            rel = {"INTACT": rel_hist, "WEAKENED": float(np.sqrt(rel_hist)), "GONE": 1.0}[premium]   # 약해짐 = 과거와 시장의 기하평균
        target_per = rel * f["mkt_per"]
        ratio = target_per * e_rev / mcap
        n = 3 if (ratio > 1 and verdict in ("RESOLVING", "EARLY_SIGNS")) else 5   # 내려갈 땐 좋은 판정이 하락을 서두르지 않게
        rer = float(np.clip(ratio ** (1 / n) - 1, -CLAMP, CLAMP))
    return {"er": y + rer, "yield": y, "rerate": rer, "owner": owner, "margin": margin, "margin_note": m_note,
            "rev_used": rev, "target_per": target_per, "rel_used": rel, "rel_hist_adj": rel_hist, "premium": premium,
            "cur_per_owner": mcap / owner if owner > 0 else None, "cur_per_reval": mcap / e_rev if e_rev > 0 else None}


# ── 확실성 (코드 부분) — 좋은 사업 6관문 + 주주환원. AI 함정 점검은 rank_ai 가 곱한다 ──
GATES = ["ROE 평균 ≥8%", "현금흐름/순이익 ≥0.7", "이자보상 ≥2배", "순이익률 평균 ≥5%", "FCF 적자 연도 ≤2 (5년)", "주식 수 증가 ≤20%"]
PASS_CERT = {6: 1.0, 5: 0.9, 4: 0.75, 3: 0.6}


def gates(code, s, st):
    """최근 5개 연간 보고서 기준 6관문 — '지금의 사업'이 좋은가. 사이클은 이익률 정상화가 따로 다룬다.
    (10년으로 보면 사업을 바꾼 회사가 옛 적자로 탈락한다 — 감성코퍼레이션 2019~21 충전기 사업.) (통과, 값, 배당성향)"""
    yrs = sorted(k for k in s if k.endswith("12") and k <= st)[-5:]
    A = lambda f: [ttm.amount(s[y].get(f)) for y in yrs]
    nis, eqs, revs, ocfs, capex, div = A("ni"), A("eq"), A("rev"), A("ocf"), A("capex"), A("div")
    ok = lambda xs: [x for x in xs if x is not None]
    roe = [n / e for n, e in zip(nis, eqs) if n is not None and e and e > 0]
    nm = [n / r for n, r in zip(nis, revs) if n is not None and r and r > 0]
    ocf_ni = sum(ok(ocfs)) / sum(ok(nis)) if (ok(ocfs) and ok(nis) and sum(ok(nis)) > 0) else None
    # FCF: 누적 합은 한 해의 큰 흑자가 여러 해 적자를 가린다 → 최근 5년 중 FCF 음수인 해의 수 (≤2 통과)
    f5 = [o - c for o, c in list(zip(ocfs, capex))[-5:] if o is not None and c is not None]
    fcf = float(sum(1 for x in f5 if x < 0)) if len(f5) >= 3 else None
    T = lambda f: ttm.ttm_eps(s, st, f)
    oi, fc, fi = T("oi"), T("fc"), T("fi")
    net_fc = max((fc or 0) - (fi or 0), 0.0)
    icr = (oi / net_fc if net_fc > 0 else 99.0) if oi is not None else None
    vals = [np.mean(roe) if len(roe) >= 3 else None, ocf_ni, icr, np.mean(nm) if len(nm) >= 3 else None, fcf, dilution(code)]
    rule = [lambda v: v >= 0.08, lambda v: v >= 0.7, lambda v: v >= 2, lambda v: v >= 0.05, lambda v: v <= 2, lambda v: v <= 0.2]
    checks = [None if v is None else bool(fn(v)) for v, fn in zip(vals, rule)]
    # 주주환원 — 배당만 센다 (자사주 '매입'은 소각이 아니면 교환사채 재원으로 재매각되기도 한다 — 오킨스전자 2026-01)
    # 현금흐름표(영업현금흐름)는 있는데 배당 줄이 비었으면 배당을 안 한 것 — 0 으로 본다 (빈 값이 감점을 피하지 않게)
    div = [d if d is not None else (0.0 if o is not None else None) for d, o in zip(div, ocfs)]
    d5, n5 = ok(div[-5:]), ok(nis[-5:])
    payout = abs(sum(d5)) / sum(n5) if (d5 and n5 and sum(n5) > 0) else None
    return checks, [None if v is None else float(v) for v in vals], payout


def dilution(code):
    """약 5년(1,250거래일) 전 대비 주식 수 증가율. 분할·무상증자(그날 주식 수 r배 + 종가 1/r)는 뺀다."""
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


def certainty_code(checks, payout):
    passes = sum(1 for c in checks if c is not False)          # 모름(None) = 통과: 자료 부족 ≠ 나쁜 사업
    c = PASS_CERT.get(passes, 0.45)
    if payout is not None and payout < 0.10:                   # 번 돈을 주주에게 거의 안 돌려준다 — 코리아 디스카운트가 안 풀릴 위험
        c *= 0.9
    return c, passes


def signed(er, cert):
    """기대 수익이 음수면 확실성으로 '덜 나쁘게' 만들지 않는다 (grill 결함 3)."""
    return er * cert if er > 0 else er * (2 - cert)


def screen_score(code, mcap, cyclical, today):
    """AI 전 1차 선별 점수 — 프리미엄 '살아 있음+구조적'과 '약해짐' 두 시나리오 평균 (프리미엄 종목을 미리 밀어내지 않게)."""
    s = series(code)
    f = facts(code, today) if s else None
    if not f or not mcap:
        return None
    best = expected(f, mcap, {"premium": "INTACT", "durable": True, "verdict": "EARLY_SIGNS"}, cyclical)
    base = expected(f, mcap, {"premium": "WEAKENED", "durable": False, "verdict": "NO_EVIDENCE"}, cyclical)   # 기본은 회복 근거 없음 — 보수적
    checks, vals, payout = gates(code, s, f["stac"])
    cert, _ = certainty_code(checks, payout)
    return {"score": signed((best["er"] + base["er"]) / 2, cert), "best": signed(best["er"], cert),
            "base": signed(base["er"], cert), "cert": cert}


SCREEN_VALUE, SCREEN_PREMIUM = 20, 10


def select(rows):
    """rows = [(code, screen dict)] → Top N 코드 목록 (순서 = 표시 순서).
    20개는 두 시나리오 평균 순(확실한 저평가), 10개는 남은 것 중 '프리미엄 유지' 시나리오 순(프리미엄 회복 후보 —
    사용자 논리: 이유가 살아 있으면 과거 밸류로 회복. 살아 있는지는 AI 가 판정하므로 여기서 미리 떨어뜨리지 않는다)."""
    rows = [(c, d) for c, d in rows if d]
    by_avg = sorted(rows, key=lambda x: -x[1]["score"])
    value = [c for c, _ in by_avg[:SCREEN_VALUE]]
    rest = sorted((x for x in rows if x[0] not in value), key=lambda x: -x[1]["best"])
    return value, [c for c, _ in rest[:SCREEN_PREMIUM]]


def buy_inputs(code, cur_per, today):
    """AI(buy-check)에게 넘기는 정량 입력 — 판정할 대상이 되는 숫자들."""
    f = facts(code, today)
    if not f:
        return None
    mm = f["mkt_per"]
    r = lambda v, n=3: None if v is None else round(float(v), n)
    return {"rel_hist": r(f["rel_hist"], 2), "rel_months": f["rel_months"],
            "rel_now": r(cur_per / mm, 2) if (cur_per and mm) else None, "market_per_now": r(mm, 1),
            "margin_now": r(f["cur"]), "margin_normal": r(f["med"]), "margin_recent8": r(f["recent8"]),
            "rev_ttm_억": round(f["rev"] / 1e8), "rev_3y_avg_억": round(f["rev_3y"] / 1e8),
            "ctrl_share": r(f["ctrl"], 2), "note": "rel = 종목 PER ÷ 같은 날 유니버스 중앙 PER. rel_hist 는 이익이 꺼진 달 제외 5년 중앙."}
