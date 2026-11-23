"""기대 역산 필드 — 삼성전자형(이익 정점) 종목이 cyclical_flag·implied_fade 로 드러나는지."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from apply_triple_cross import expectations  # noqa: E402


def _ser(opms):
    """연간 매출 100 고정, 영업이익률 opms 의 12월 결산 시계열 (TTM = 연간)."""
    return {f"{2010 + i}12": {"rev": 100.0, "oi": 100.0 * m} for i, m in enumerate(opms)}


def test_peak_earnings_flagged():
    ser = _ser([0.10] * 9 + [0.40])                       # 평소 10% → 지금 40%
    e = expectations(ser, "201912", mcap=1000, med_per=10, cur_per=4, fwd_ni=500)
    assert e["cyclical_flag"]
    assert e["implied_fade"] == 100 / 500                  # 평소 PER 이면 이익 100 — 컨센서스 500의 0.2배
    assert e["implied_vs_ttm"] == 100 / 250
    assert abs(e["midcycle_vs_ttm"] - 0.25) < 1e-9          # 평소 마진이면 지금 이익의 1/4


def test_stable_business_not_flagged():
    e = expectations(_ser([0.10, 0.11, 0.09, 0.10, 0.12, 0.10, 0.11, 0.10]), "201712",
                     mcap=1000, med_per=10, cur_per=10, fwd_ni=None)
    assert not e["cyclical_flag"]
    assert e["implied_fade"] != e["implied_fade"]          # NaN — Forward 없음
