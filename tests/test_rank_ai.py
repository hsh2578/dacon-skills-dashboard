"""AI 재순위 점수 — 같은 판정이면 같은 점수, 중복 계산 없음."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from rank_ai import earnings_pts, score  # noqa: E402


def _ai(gap="TOO_PESSIMISTIC", verdict="EARLY_SIGNS", conf="MEDIUM", window="1-2Q", ev=3, ce=2, risk="HIGH"):
    return {"risk_level": risk, "resolution": {"expectation_gap": gap, "verdict": verdict, "confidence": conf,
            "expected_window": window, "evidence": [{}] * ev, "counter_evidence": [{}] * ce}}


def test_실적은_발표된_숫자로만():
    assert earnings_pts(0.4, 1, 1) == 1.5 and earnings_pts(0.15, 1, 1) == 0.75
    assert earnings_pts(0.05, 1, 1) == 0 and earnings_pts(-0.2, 1, 1) == -1.5
    assert earnings_pts(None, 5, -1) == 1.5 and earnings_pts(None, -1, 5) == -1.5


def test_이익정점은_가격판정이_비관적이지_않을때만_가점_제외():
    q = {"cyclical_flag": True, "midcycle_vs_ttm": 0.5}
    assert score(_ai(gap="FAIR"), q, (0.5, 2, 1))[1]["3_earnings"] == 0
    assert score(_ai(gap="TOO_PESSIMISTIC"), q, (0.5, 2, 1))[1]["3_earnings"] == 1.5


def test_가격판정이_1순위():
    q = {}
    hi = score(_ai(gap="TOO_PESSIMISTIC", verdict="EARLY_SIGNS"), q, (0.0, 1, 1))[0]
    lo = score(_ai(gap="FAIR", verdict="RESOLVING"), q, (0.4, 1, 1))[0]
    assert hi > lo


def test_반증이_근거_이상이면_감점_그리고_악화엔_시점가점_없음():
    q = {}
    assert score(_ai(ev=3, ce=3), q, (0, 1, 1))[1]["2_resolution"] == 1.0      # 1 + .5 − .5
    assert score(_ai(verdict="WORSENING", window="1-2Q"), q, (0, 1, 1))[1]["2_resolution"] == -2.5
