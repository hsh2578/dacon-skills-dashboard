"""네이버 컨센서스가 비어서 돌아올 때 universe가 붕괴하지 않는지 검증.

네이버는 스로틀되면 요약표에 "최근3개월 이내에 제시된 의견이 없습니다"를 돌려준다.
`fetch_consensus.py`는 컨센서스 없는 종목을 universe에서 **제외**하고 결과를
무조건 덮어쓰므로, 스로틀 한 번에 모집단이 통째로 무너지고 그 축소된 집합으로
4팩터가 계산된다 — 오류도 경고도 없이.

네트워크를 타지 않는다 (fetch_naver_data를 대체하고 universe 경로를 임시 파일로 돌린다).

    python -m pytest tests/ -q
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_consensus as fc  # noqa: E402


def _stock(i, *, with_consensus=True, days_old=0):
    s = {"code": f"{i:06d}", "name": f"종목{i}", "market": "KOSPI",
         "market_cap_억": 5000, "close": 10000}
    if with_consensus:
        stamp = (datetime.now() - timedelta(days=days_old)).isoformat(timespec="seconds")
        s.update({"forward_per": 8.0, "forward_pbr": 0.9, "forward_eps": 1200,
                  "fwd_year": "2026/12", "avg_target_price": 15000,
                  "broker_count": 10, "consensus_score": 4.0,
                  "consensus_at": stamp})
    return s


def _write_universe(tmp_path, stocks):
    p = tmp_path / "universe.json"
    p.write_text(json.dumps({"passed": stocks, "stocks": stocks, "meta": {}},
                            ensure_ascii=False), encoding="utf-8")
    return p


def _patch(monkeypatch, tmp_path, stocks, naver_returns):
    p = _write_universe(tmp_path, stocks)
    monkeypatch.setattr(fc, "UNIVERSE", p)
    monkeypatch.setattr(fc, "fetch_naver_data", lambda code: naver_returns)
    monkeypatch.setattr(fc, "CONCURRENT_WORKERS", 1)
    monkeypatch.setattr(fc, "PER_THREAD_DELAY", 0)
    return p


EMPTY = {"forward": {}, "consensus": {"summary": {"avg_target_price": None,
                                                  "broker_count": None}, "brokers": []}}
GOOD = {"forward": {"per_forward": 7.5, "pbr_forward": 0.8, "eps_forward": 1300,
                    "year_estimate": "2026/12"},
        "consensus": {"summary": {"avg_target_price": 16000, "broker_count": 11,
                                  "consensus_score": 4.1}, "brokers": []}}


def test_전부_비어도_직전값이_있으면_승계된다(monkeypatch, tmp_path):
    stocks = [_stock(i) for i in range(30)]
    p = _patch(monkeypatch, tmp_path, stocks, EMPTY)
    fc.main()
    out = json.loads(p.read_text(encoding="utf-8"))
    assert len(out["passed"]) == 30                      # 아무도 안 빠졌다
    assert out["meta"]["carried_from_previous"] == 30
    assert all(s["avg_target_price"] == 15000 for s in out["passed"])
    assert all(s["consensus_carried"] for s in out["passed"])


def test_직전값이_없으면_붕괴하므로_기록을_거부한다(monkeypatch, tmp_path):
    """승계할 것이 없는 상태에서 페치가 전멸하면 universe.json을 건드리지 않는다."""
    stocks = [_stock(i) for i in range(30)]
    p = _patch(monkeypatch, tmp_path, stocks, EMPTY)
    # 직전 값 자체를 지워 승계 경로를 막는다
    monkeypatch.setattr(fc, "CARRY_MAX_DAYS", -1)
    before = p.read_text(encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        fc.main()
    assert "급감" in str(e.value)
    assert p.read_text(encoding="utf-8") == before        # 원본 그대로


def test_너무_낡은_값은_승계하지_않는다(monkeypatch, tmp_path):
    """목표주가는 upside 팩터로 들어간다 — 무한정 승계하면 안 된다."""
    stocks = [_stock(i, days_old=fc.CARRY_MAX_DAYS + 1) for i in range(30)]
    p = _patch(monkeypatch, tmp_path, stocks, EMPTY)
    before = p.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        fc.main()
    assert p.read_text(encoding="utf-8") == before


def test_정상_페치는_새_값으로_갱신된다(monkeypatch, tmp_path):
    stocks = [_stock(i) for i in range(30)]
    p = _patch(monkeypatch, tmp_path, stocks, GOOD)
    fc.main()
    out = json.loads(p.read_text(encoding="utf-8"))
    assert len(out["passed"]) == 30
    assert out["meta"]["carried_from_previous"] == 0
    assert all(s["avg_target_price"] == 16000 for s in out["passed"])
    assert not any(s["consensus_carried"] for s in out["passed"])


def test_일부만_실패하면_그_종목만_승계된다(monkeypatch, tmp_path):
    stocks = [_stock(i) for i in range(30)]
    p = _write_universe(tmp_path, stocks)
    monkeypatch.setattr(fc, "UNIVERSE", p)
    monkeypatch.setattr(fc, "CONCURRENT_WORKERS", 1)
    monkeypatch.setattr(fc, "PER_THREAD_DELAY", 0)
    # 코드가 짝수인 종목만 정상 응답
    monkeypatch.setattr(fc, "fetch_naver_data",
                        lambda code: GOOD if int(code) % 2 == 0 else EMPTY)
    fc.main()
    out = json.loads(p.read_text(encoding="utf-8"))
    assert len(out["passed"]) == 30
    assert out["meta"]["carried_from_previous"] == 15
    fresh = [s for s in out["passed"] if not s["consensus_carried"]]
    assert all(s["avg_target_price"] == 16000 for s in fresh)


def test_신규_종목은_컨센서스가_없으면_정상적으로_빠진다(monkeypatch, tmp_path):
    """가드가 '컨센서스 없는 종목 제외' 룰 자체를 무력화하면 안 된다."""
    stocks = [_stock(i) for i in range(28)] + [_stock(i, with_consensus=False)
                                               for i in (900, 901)]
    p = _patch(monkeypatch, tmp_path, stocks, EMPTY)
    fc.main()
    out = json.loads(p.read_text(encoding="utf-8"))
    codes = {s["code"] for s in out["passed"]}
    assert "000900" not in codes and "000901" not in codes
    assert len(out["passed"]) == 28
