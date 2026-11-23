"""가치(자기 과거 대비) 신호 + 퀄리티 필터 백테스트 — 연구용.

    python scripts/backtest_value.py            # 결과 표 출력 + data/backtest/value_quality.json

설계
  · 매월 말 리밸런싱. 그 시점 시총 2,000억+ 보통주 (point-in-time 유니버스)
  · value = 순위Z( 1 - PER/자기중앙값 ) + 순위Z( 1 - PBR/자기중앙값 ), 중앙값은 직전 최대 60개월(최소 24)
  · 퀄리티 필터 = 세 지표 순위 평균의 하위 20% 탈락 (값 없는 지표는 판단 보류 = 중립)
      q_trend  TTM 영업이익률 - 자기 과거 분기들의 TTM 영업이익률 중앙값
      q_accr   (TTM 영업현금흐름 - TTM 순이익) / 자산          (클수록 이익의 질 좋음)
      q_icr    TTM 영업이익 / TTM 금융비용                    (이자보상배율)
  · 재무값은 공시 시차(ttm.available_from) 이후만 사용 — look-ahead 없음
  · 수익률: 다음 달 말까지 종가 수익률. 주식수가 20% 넘게 바뀌면(분할·병합) 시총 수익률로 대체

한계 (결과를 읽을 때 반드시 함께 볼 것)
  · 상장폐지 종목: 수익률은 마지막 거래일(정리매매 포함)까지 반영. 재무는 fetch_dart_quarterly 로 받아야 신호가 생김
  · 기간이 짧다(약 40개월). 방향 확인용이지 확정 수치가 아니다
  · 미래전망(Forward PER) 팩터는 과거 추정치가 없어 검증 불가
  · 거래비용·배당 미반영
"""
import json, os, sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import quality  # noqa: E402
import ttm  # noqa: E402

MIN_CAP = 2000e8
LOOKBACK, MIN_HIST = 60, 24


def load():
    mc = json.load(open(ROOT / "data/.cache/_krx_mcap_daily.json", encoding="utf-8"))
    cl = json.load(open(ROOT / "data/.cache/_krx_close_daily.json", encoding="utf-8"))
    days = sorted(d for d in mc if mc[d] and cl.get(d))
    month_end = sorted({max(d for d in days if d[:6] == ym) for ym in {d[:6] for d in days}})
    mcap = pd.DataFrame({d: mc[d] for d in month_end}).T
    close = pd.DataFrame({d: cl[d] for d in month_end}).T
    cols = [c for c in mcap.columns if c.endswith("0")]
    # 마지막 거래일 시총 — 상장폐지 종목의 정리매매 폭락까지 수익률에 넣기 위해
    last = {}
    for d in days:
        for c, v in mc[d].items():
            last[c] = (d, v)
    return mcap[cols], close.reindex(columns=cols), last


def monthly_valuation(codes, dates):
    """실제 점수(apply_triple_cross)와 **같은** 월별 매트릭스를 읽는다 — 검증한 신호 = 쓰는 신호 (2026-11-24 정렬).
    매트릭스 키는 각 달 마지막 거래일이라 월말 날짜와 그대로 맞는다."""
    m = {k: json.load(open(ROOT / f"data/matrix/{k}_monthly.json", encoding="utf-8"))["matrix"] for k in ("per", "pbr")}
    per = pd.DataFrame({c: pd.Series(m["per"].get(c, {})) for c in codes if c in m["per"]}).reindex(dates)
    pbr = pd.DataFrame({c: pd.Series(m["pbr"].get(c, {})) for c in codes if c in m["pbr"]}).reindex(dates)
    return per.where(per > 0), pbr.where(pbr > 0)


def quality_panel(codes, dates):
    """월말 시점에 공시된 최신 분기 기준 세 지표. {(date, code): (trend, accr, icr)}"""
    out = {}
    for c in codes:
        p = ROOT / "data/financials_q" / f"{c}.json"
        if not p.exists():
            continue
        ser = {k: v for k, v in json.load(open(p, encoding="utf-8"))["series"].items()
               if v.get("status") == "000" and v.get("currency", "KRW") == "KRW"}
        if not ser:
            continue
        mg = quality.margins(ser)
        for d in dates:
            st = ttm.disclosed_stac(ser, d)
            if not st:
                continue
            trend, accr, icr = quality.metrics(ser, st, mg)
            out[(d, c)] = (trend, accr, icr)
    return out


def rz(s):
    r = s.rank(pct=True)
    return (r - r.mean()) / r.std()


def main():
    mcap, close, last = load()
    dates = list(mcap.index)
    codes = list(mcap.columns)
    per, pbr = monthly_valuation(codes, dates)
    print(f"[bt] 월말 {len(dates)}개 · 밸류 보유 {per.shape[1]}종목")
    qp = quality_panel(per.columns, dates)

    # 수익률: 종가 기준, 주식수 20% 넘게 변하면 시총 기준
    shares = mcap / close
    r_close = close.shift(-1) / close - 1
    r_mcap = mcap.shift(-1) / mcap - 1
    jump = (shares.shift(-1) / shares - 1).abs() > 0.2
    fwd = r_close.where(~jump, r_mcap)
    # 3개월 보유 (월간 수익률 복리 — 상장폐지 반영된 fwd 를 이어 붙인다)
    # 생존 편향: 다음 달 말에 없는 종목(상장폐지·합병)은 빼지 않고 마지막 거래일 시총까지의 수익률로 처리
    n_delist = 0
    for i, d in enumerate(dates[:-1]):
        nxt = dates[i + 1]
        for c in mcap.columns[mcap.loc[d].notna() & mcap.loc[nxt].isna()]:
            ld, lv = last.get(c, (None, None))
            if ld and d < ld <= nxt:
                fwd.loc[d, c] = lv / mcap.loc[d, c] - 1
                n_delist += 1
    print(f"[bt] 상장폐지·합병 수익률 반영 {n_delist}건")

    rows = []
    for i, d in enumerate(dates[:-1]):
        if i < MIN_HIST:
            continue
        uni = mcap.loc[d][mcap.loc[d] >= MIN_CAP].index.intersection(per.columns)
        hist_per = per.iloc[max(0, i - LOOKBACK):i][uni]
        hist_pbr = pbr.iloc[max(0, i - LOOKBACK):i][uni]
        ok = (hist_per.notna().sum() >= MIN_HIST) & (hist_pbr.notna().sum() >= MIN_HIST)
        uni = ok[ok].index
        cur_per, cur_pbr = per.loc[d, uni], pbr.loc[d, uni]
        v_per = 1 - cur_per / hist_per[uni].median()
        v_pbr = 1 - cur_pbr / hist_pbr[uni].median()
        r3 = (1 + fwd.iloc[i:i + 3][uni]).prod(min_count=3) - 1 if i + 3 < len(dates) else pd.Series(np.nan, index=uni)
        df = pd.DataFrame({"v_per": v_per, "v_pbr": v_pbr, "ret": fwd.loc[d, uni], "ret3": r3}).dropna(subset=["v_per", "v_pbr", "ret"])
        if len(df) < 50:
            continue
        df["value"] = rz(df.v_per) + rz(df.v_pbr)
        q = pd.DataFrame([qp.get((d, c), (np.nan,) * 3) for c in df.index],
                         index=df.index, columns=["trend", "accr", "icr"])
        df["qpass"], df["qscore"] = quality.passes(q)
        quint = pd.qcut(df.value.rank(method="first"), 5, labels=[1, 2, 3, 4, 5])   # 5 = 가장 쌈
        top = df[quint == 5]
        rows.append({
            "date": d, "n": len(df),
            "ic": df.value.corr(df.ret, method="spearman"),
            "ic_per": df.v_per.corr(df.ret, method="spearman"), "ic_pbr": df.v_pbr.corr(df.ret, method="spearman"),
            "ic3": df.value.corr(df.ret3, method="spearman"),
            "q5_3m": top.ret3.mean(), "mkt_3m": df.ret3.mean(), "q5q_3m": top[top.qpass].ret3.mean(),
            "q5": top.ret.mean(), "q1": df[quint == 1].ret.mean(), "mkt": df.ret.mean(),
            "q5_qpass": top[top.qpass].ret.mean(), "q5_qfail": top[~top.qpass].ret.mean(),
            "n_q5_fail": int((~top.qpass).sum()),
            **{f"Q{k}": df[quint == k].ret.mean() for k in range(1, 6)},
        })
    res = pd.DataFrame(rows).set_index("date")
    n = len(res)
    t = lambda x: x.mean() / x.std() * np.sqrt(len(x.dropna())) if x.std() else np.nan
    print(f"\n기간 {res.index[0]} ~ {res.index[-1]} · {n}개월 · 월평균 유니버스 {res.n.mean():.0f}종목")
    print(f"  IC(가치점수 vs 다음달 수익률) 평균 {res.ic.mean():+.3f} · t={t(res.ic):.2f} · 양(+)인 달 {(res.ic > 0).mean():.0%}")
    ex = res.q5 - res.mkt
    print(f"  가장 싼 20%  월평균 {res.q5.mean():+.2%}  (전체 대비 {ex.mean():+.2%}, t={t(ex):.2f})")
    print(f"  가장 비싼 20% 월평균 {res.q1.mean():+.2%}")
    qe = res.q5_qpass - res.q5
    print(f"  가장 싼 20% + 퀄리티 통과 {res.q5_qpass.mean():+.2%}  (필터 효과 {qe.mean():+.2%}/월, t={t(qe):.2f})")
    print(f"  └ 퀄리티 탈락분 {res.q5_qfail.mean():+.2%}  (월평균 {res.n_q5_fail.mean():.1f}종목 탈락)")
    print(f"  팩터별 IC: PER 할인 {res.ic_per.mean():+.3f} (t={t(res.ic_per):.2f}) · PBR 할인 {res.ic_pbr.mean():+.3f} (t={t(res.ic_pbr):.2f})")
    print("  5분위 월평균 (1=가장 비쌈 … 5=가장 쌈): " + " · ".join(f"Q{k} {res[f'Q{k}'].mean():+.2%}" for k in range(1, 6)))
    r3 = res.dropna(subset=["ic3"])
    print(f"  3개월 보유: IC {r3.ic3.mean():+.3f} (t={t(r3.ic3):.2f}, 겹치는 구간이라 t 과대) · 싼 20% {r3.q5_3m.mean():+.2%} vs 전체 {r3.mkt_3m.mean():+.2%} · +퀄리티 {r3.q5q_3m.mean():+.2%}")
    out = ROOT / "data/backtest"
    out.mkdir(parents=True, exist_ok=True)
    res.to_json(out / "value_quality.json", orient="index", indent=1)
    print(f"\n  월별 상세 → {out / 'value_quality.json'}")


if __name__ == "__main__":
    main()
