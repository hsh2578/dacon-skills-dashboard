"""퀄리티 필터 지표 — 백테스트(backtest_value.py)와 점수(apply_triple_cross.py)가 같은 정의를 쓰도록 한 곳에 둔다.

역할: 점수가 아니라 **함정 필터**. 저평가 후보 중 하위 Q_CUT 를 탈락시킨다.
  (가치와 퀄리티는 음의 상관이라 점수로 섞으면 '덜 싼 우량주' 쪽으로 끌려간다 — QMJ·Novy-Marx.
   Piotroski·Gray&Carlisle 처럼 저평가 집합 안에서 두 번째 체로 쓴다.)

  trend  TTM 영업이익률 − 자기 과거(최근 20개 분기) TTM 영업이익률 중앙값   — 사업이 망가지는 중인가
  accr   (TTM 영업현금흐름 − TTM 지배순이익) / 자산                         — 이익이 현금으로 들어오는가
  icr    TTM 영업이익 / TTM 금융비용                                       — 이자를 감당하는가
값이 없으면(금융업은 매출·영업이익 태그가 없다 등) 그 지표는 판단 보류.
"""
import numpy as np

import ttm

Q_CUT = 0.20


def margins(ser: dict) -> dict:
    out = {}
    for st in ttm.stacs(ser):
        r, o = ttm.ttm_eps(ser, st, "rev"), ttm.ttm_eps(ser, st, "oi")
        if r and o is not None and r > 0:
            out[st] = o / r
    return out


def metrics(ser: dict, st: str, mg: dict = None):
    """결산기 st 기준 (trend, accr, icr). ser 는 status 000·원화 보고서만."""
    mg = margins(ser) if mg is None else mg
    past = [m for k, m in sorted(mg.items()) if k < st][-20:]
    trend = mg[st] - float(np.median(past)) if st in mg and len(past) >= 8 else np.nan
    T = lambda f: ttm.ttm_eps(ser, st, f)
    ocf, ni, assets = T("ocf"), T("ni"), ttm.amount((ser.get(st) or {}).get("assets"))
    accr = (ocf - ni) / assets if (ocf is not None and ni is not None and assets) else np.nan
    oi, fc = T("oi"), T("fc")
    icr = (oi / fc if fc and fc > 0 else np.nan) if oi is not None else np.nan
    return trend, accr, icr


def passes(q):
    """q: DataFrame[trend, accr, icr] (행=종목). 지표 순위 평균 하위 Q_CUT 탈락. 지표가 하나도 없으면 통과."""
    has = q.notna().any(axis=1)
    score = q.rank(pct=True).mean(axis=1, skipna=True)
    cut = score[has].quantile(Q_CUT) if has.any() else -1
    return ~has | (score > cut), score
