"""매수 매력 순위 = (평소 주주이익 수익률 + 재평가 여지) × 확실성 — 논리 규칙 검증."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from rank_ai import certainty, score  # noqa: E402


def _ai(gap="TOO_PESSIMISTIC", verdict="EARLY_SIGNS", trap=None, flags=()):
    a = {"resolution": {"expectation_gap": gap, "verdict": verdict, "confidence": "HIGH"}}
    if trap:
        a["buy_check"] = {"trap": {"level": trap, "flags": list(flags)}}
    return a


def _fund(cur=0.10, med=0.10, rev_억=1000, net_fc_억=0, ctrl=1.0, checks=(True,) * 6):
    return {"rev": rev_억 * 1e8, "med_margin": med, "cur_margin": cur, "net_fc": net_fc_억 * 1e8, "ctrl": ctrl,
            "checks": list(checks), "check_vals": [None] * 6}


Q = {"market_cap_억": 500}


def test_정점_마진은_믿지_않는다():
    peak = score(_ai(), Q, _fund(cur=0.30, med=0.10))[1]["owner_yield"]
    normal = score(_ai(), Q, _fund(cur=0.10, med=0.10))[1]["owner_yield"]
    assert peak == normal


def test_근거_없이_회복을_가정하지_않는다():
    with_ev = score(_ai(verdict="EARLY_SIGNS"), Q, _fund(cur=0.05, med=0.10))[1]["owner_yield"]
    no_ev = score(_ai(verdict="NO_EVIDENCE"), Q, _fund(cur=0.05, med=0.10))[1]["owner_yield"]
    assert with_ev > no_ev


def test_빚과_비지배지분은_빼고_계산한다():
    base = score(_ai(), Q, _fund())[1]["owner_yield"]
    assert score(_ai(), Q, _fund(net_fc_억=50))[1]["owner_yield"] < base
    assert abs(score(_ai(), Q, _fund(ctrl=0.4))[1]["owner_yield"] - base * 0.4) < 1e-4


def test_확인된_함정과_나쁜_사업은_확실성을_깎는다():
    assert certainty(_fund(), _ai())[0] == 1.0
    assert certainty(_fund(), _ai(trap="SEVERE", flags=["ACCOUNTING"]))[0] == 0.3
    assert certainty(_fund(checks=(False, False, False, True, True, True)), _ai())[0] == 0.6
    assert certainty(_fund(checks=(None,) * 6), _ai())[0] == 1.0          # 자료 없음은 감점하지 않는다
