"""매수 매력 순위의 논리 규칙 (value_core.expected · signed · rank_ai.trap_mult)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from rank_ai import trap_mult  # noqa: E402
from value_core import expected, signed  # noqa: E402


def _f(cur=0.10, med=0.10, recent8=0.10, rev=1000e8, rev3=1000e8, ni=60e8, rel=2.0, mkt=10.0):
    return {"rev": rev, "rev_3y": rev3, "med": med, "recent8": recent8, "cur": cur, "ni": ni,
            "ctrl": 1.0, "conv": 1.0, "rel_hist": rel, "mkt_per": mkt}


M = 600e8


def test_정점_마진은_믿지_않고_구조적이면_인정한다():
    mid = _f(cur=0.20, med=0.10, recent8=0.15, ni=120e8)
    assert abs(expected(mid, M)["margin"] - 0.125) < 1e-9           # 평소와 (평소·최근·지금 중앙)의 중간
    peak = _f(cur=0.20, med=0.10, recent8=0.20, ni=120e8)
    assert expected(peak, M, {"durable": True})["margin"] == 0.20


def test_근거_없이_회복을_가정하지_않는다():
    low = _f(cur=0.05, med=0.10, recent8=0.05, ni=30e8)       # 최근 2년도 낮다 = 일시적 하락이 아니다
    assert expected(low, M, {"verdict": "NO_EVIDENCE"})["margin"] == 0.05
    assert expected(low, M, {"verdict": "EARLY_SIGNS"})["margin"] == 0.10


def test_프리미엄_이유가_살아있으면_과거_배수_사라지면_시장_배수():
    f = _f(rel=3.0)
    intact = expected(f, M, {"premium": "INTACT", "verdict": "EARLY_SIGNS"})
    gone = expected(f, M, {"premium": "GONE", "verdict": "EARLY_SIGNS"})
    assert intact["target_per"] == 30.0 and gone["target_per"] == 10.0 and intact["rerate"] > gone["rerate"]


def test_경기호황_테마_프리미엄은_회복으로_인정하지_않는다():
    f = _f(rel=3.0)
    assert expected(f, M, {"premium": "INTACT", "reason_type": "CYCLE"})["premium"] == "WEAKENED"
    assert expected(f, M, {"premium": "INTACT", "reason_type": "MOAT_COST"})["premium"] == "INTACT"


def test_할인의_이유가_사라지면_시장_수준으로_오른다_근거_없으면_그대로():
    f = _f(rel=0.5)
    assert expected(f, M, {"premium": "GONE"})["rerate"] > expected(f, M, {"premium": "INTACT"})["rerate"]
    assert expected(f, M, {"premium": "WEAKENED"})["rel_used"] == 0.5


def test_이력이_없으면_시장_배수():
    assert expected(_f(rel=None), M)["rel_used"] == 1.0


def test_이익률_규칙에_계단이_없다():
    a = expected(_f(cur=0.0999, med=0.10, recent8=0.12, ni=60e8), M, {"verdict": "EARLY_SIGNS"})["margin"]
    b = expected(_f(cur=0.1001, med=0.10, recent8=0.12, ni=60e8), M, {"verdict": "EARLY_SIGNS"})["margin"]
    assert abs(a - b) < 0.002


def test_음수_기대수익은_불확실성으로_덜_나빠지지_않는다():
    assert signed(-0.1, 0.5) < signed(-0.1, 1.0) < 0 < signed(0.1, 0.5) < signed(0.1, 1.0)


def test_함정_배수():
    assert trap_mult({"level": "SEVERE"}) == 0.3
    assert trap_mult({"level": "WATCH", "flags": ["DIVERSIFICATION"]}) == 0.9
    assert trap_mult({"level": "NONE"}) == 1.0


def test_과거_배수는_지금_이익률_기준으로_환산된다():
    f = _f(cur=0.20, med=0.20, recent8=0.20, ni=120e8, rel=3.0)
    f["rel_rows"] = [(3.0, 0.05)] * 30           # 이익률 5% 시절 상대 PER 3배 → 지금 20% 이익률 기준이면 1배
    assert abs(expected(f, M, {"premium": "INTACT"})["rel_hist_adj"] - 1.0) < 1e-9


def test_일회성_이익이면_재평가도_보수적_이익으로():
    f = _f(cur=0.10, med=0.10, recent8=0.10, ni=200e8)      # 순이익이 영업 기준보다 크다(일회성)
    a = expected(f, M, {"premium": "INTACT"})["rerate"]
    b = expected(f, M, {"premium": "INTACT", "flags": ["ONE_OFF_EARNINGS"]})["rerate"]
    assert b < a
