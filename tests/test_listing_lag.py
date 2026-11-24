"""권리락~신주 상장 사이 시총 과소 계상 보정 (build_valuation.fix_listing_lag)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from build_valuation import fix_listing_lag  # noqa: E402

SH = 100.0


def test_상장된_무상증자는_상장후_주식수로_메운다():
    cl = [300, 300, 200, 200, 200, 200]
    sh = [SH, SH, SH, SH, 150, 150]                 # 권리락 i=2, 신주 상장 i=4
    out = fix_listing_lag([c * s for c, s in zip(cl, sh)], cl)
    assert out == [30000, 30000, 30000, 30000, 30000, 30000]


def test_아직_미상장이면_가격비율로_추정한다():
    cl = [300, 300, 200, 200]
    out = fix_listing_lag([c * SH for c in cl], cl)
    assert out[2:] == [30000, 30000]


def test_보통_하락과_장기_불변은_건드리지_않는다():
    cl = [300, 250, 240]                            # −17%: 가격제한폭 안
    mc = [c * SH for c in cl]
    assert fix_listing_lag(mc, cl) == mc
    cl = [300] + [200] * 50                         # 40일 넘게 주식수 그대로 → 권리락 아님
    mc = [c * SH for c in cl]
    assert fix_listing_lag(mc, cl) == mc


def test_주식수_증가가_가격과_안_맞으면_건드리지_않는다():
    cl = [300, 200, 200, 200]
    sh = [SH, SH, SH, 400]                          # 1.5배 하락인데 주식수 4배 — 다른 사건
    mc = [c * s for c, s in zip(cl, sh)]
    assert fix_listing_lag(mc, cl) == mc
