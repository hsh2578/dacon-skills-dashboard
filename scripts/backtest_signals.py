"""싼 종목 안에서 '무엇이 다음 수익률을 갈랐나' — 순위 신호 후보 검증 (연구용, 2026-11-24).

    python scripts/backtest_signals.py

backtest_value.py 와 같은 데이터·같은 point-in-time 규칙(공시 시차·상장폐지 수익률)을 쓴다.
매월 말: 시총 2,000억+ · 자기 5년 대비 가치점수 상위 40% (= '싼 종목') 안에서
  후보 신호별 순위 IC (다음 1개월 / 3개월 수익률) 와 상위 1/3 − 싼 종목 평균 초과수익을 본다.

후보 (전부 그 시점에 알 수 있던 값만)
  value     가치점수 자체 (더 쌀수록)
  oi_yoy    DART TTM 영업이익 전년 대비
  peak      TTM 영업이익률 ÷ 자기 20분기 중앙 (높을수록 정점 의심 — 부호 반대로 기대)
  quality   퀄리티 점수 (quality.passes 의 순위 평균)
  mom12_1   12개월 수익률(최근 1개월 제외)
  mom6_1    6개월 수익률(최근 1개월 제외)
  drawdown  1년 고점 대비 (많이 빠졌을수록 — 반등 가설)
  rev1      최근 1개월 수익률 (단기 반전 가설 — 부호 반대 기대)
검증 못 하는 것: Forward EPS 전망·AI 판정 (과거 시점 자료 없음).
기간이 약 40개월이라 t 값 2 근처는 '방향 참고'일 뿐이다.
"""
import json, os, sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import backtest_value as bv  # noqa: E402
import quality  # noqa: E402
import ttm  # noqa: E402

CHEAP = 0.40


def fin_panel(codes, dates):
    """{(date, code): (oi_yoy, peak, trend, accr, icr)}"""
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
            now, prev = ttm.ttm_eps(ser, st, "oi"), ttm.ttm_eps(ser, f"{int(st[:4]) - 1}{st[4:]}", "oi")
            yoy = now / prev - 1 if (now is not None and prev and prev > 0) else np.nan
            past = [m for k, m in sorted(mg.items()) if k < st][-20:]
            peak = mg[st] / np.median(past) if (st in mg and len(past) >= 8 and np.median(past) > 0) else np.nan
            out[(d, c)] = (yoy, peak, *quality.metrics(ser, st, mg))
    return out


def main():
    mcap, close, last = bv.load()
    dates, codes = list(mcap.index), list(mcap.columns)
    per, pbr = bv.monthly_valuation(codes, dates)
    shares = mcap / close
    jump = (shares.shift(-1) / shares - 1).abs() > 0.2
    fwd = (close.shift(-1) / close - 1).where(~jump, mcap.shift(-1) / mcap - 1)
    for i, d in enumerate(dates[:-1]):                      # 상장폐지 수익률 (backtest_value 와 동일)
        nxt = dates[i + 1]
        for c in mcap.columns[mcap.loc[d].notna() & mcap.loc[nxt].isna()]:
            ld, lv = last.get(c, (None, None))
            if ld and d < ld <= nxt:
                fwd.loc[d, c] = lv / mcap.loc[d, c] - 1
    # 가격 신호는 시총 기준 (분할에 안전)
    px = mcap
    fp = fin_panel(per.columns, dates)
    print(f"[bt] 재무 패널 {len(fp)}건")

    sig_names = ["value", "oi_yoy", "peak", "quality", "mom12_1", "mom6_1", "drawdown", "rev1"]
    rows = []
    for i, d in enumerate(dates[:-1]):
        if i < max(bv.MIN_HIST, 13):
            continue
        uni = mcap.loc[d][mcap.loc[d] >= bv.MIN_CAP].index.intersection(per.columns)
        hp, hb = per.iloc[max(0, i - bv.LOOKBACK):i][uni], pbr.iloc[max(0, i - bv.LOOKBACK):i][uni]
        ok = (hp.notna().sum() >= bv.MIN_HIST) & (hb.notna().sum() >= bv.MIN_HIST)
        uni = ok[ok].index
        df = pd.DataFrame({"v_per": 1 - per.loc[d, uni] / hp[uni].median(),
                           "v_pbr": 1 - pbr.loc[d, uni] / hb[uni].median(),
                           "ret": fwd.loc[d, uni]})
        df["ret3"] = (1 + fwd.iloc[i:i + 3][uni]).prod(min_count=3) - 1 if i + 3 < len(dates) else np.nan
        df = df.dropna(subset=["v_per", "v_pbr", "ret"])
        if len(df) < 50:
            continue
        df["value"] = bv.rz(df.v_per) + bv.rz(df.v_pbr)
        f = pd.DataFrame([fp.get((d, c), (np.nan,) * 5) for c in df.index], index=df.index,
                         columns=["oi_yoy", "peak", "trend", "accr", "icr"])
        df["oi_yoy"], df["peak"] = f.oi_yoy, f.peak
        _, df["quality"] = quality.passes(f[["trend", "accr", "icr"]])
        p0, p1, p6, p12 = px.loc[d, df.index], px.iloc[i - 1][df.index], px.iloc[i - 6][df.index], px.iloc[i - 12][df.index]
        df["mom12_1"], df["mom6_1"], df["rev1"] = p1 / p12 - 1, p1 / p6 - 1, p0 / p1 - 1
        df["drawdown"] = -(p0 / px.iloc[i - 12:i + 1][df.index].max() - 1)
        cheap = df[df.value >= df.value.quantile(1 - CHEAP)]
        row = {"date": d, "n": len(cheap), "cheap_ret": cheap.ret.mean(), "all_ret": df.ret.mean(),
               "cheap_ret3": cheap.ret3.mean()}
        for s in sig_names:
            x = cheap.dropna(subset=[s])
            if len(x) < 20:
                continue
            row[f"ic_{s}"] = x[s].corr(x.ret, method="spearman")
            row[f"ic3_{s}"] = x[s].corr(x.ret3, method="spearman") if x.ret3.notna().sum() > 20 else np.nan
            top = x[x[s] >= x[s].quantile(2 / 3)]
            bot = x[x[s] <= x[s].quantile(1 / 3)]
            row[f"ls_{s}"] = top.ret.mean() - bot.ret.mean()
        # Top 30 포트폴리오 비교 — 지금 방식(가치 순) vs 싼 종목 안에서 퀄리티·이익률 순
        z = lambda col: bv.rz(cheap[col].fillna(cheap[col].median()))
        strat = {"A_value_top30": df.value,
                 "B_cheap_quality": cheap.quality,
                 "C_cheap_q+peak+oi": z("quality") + z("peak") + z("oi_yoy"),
                 "D_cheap_q+peak+oi-dd": z("quality") + z("peak") + z("oi_yoy") - z("drawdown")}
        for k, sc in strat.items():
            pick = sc.dropna().sort_values(ascending=False).index[:30]
            row[f"p_{k}"] = df.loc[pick, "ret"].mean()
            row[f"p3_{k}"] = df.loc[pick, "ret3"].mean()
        rows.append(row)
    res = pd.DataFrame(rows).set_index("date")
    t = lambda x: x.mean() / x.std() * np.sqrt(x.notna().sum()) if x.std() else np.nan
    print(f"\n기간 {res.index[0]} ~ {res.index[-1]} · {len(res)}개월 · 싼 종목 월평균 {res.n.mean():.0f}개")
    print(f"싼 40% 월평균 {res.cheap_ret.mean():+.2%} vs 전체 {res.all_ret.mean():+.2%}\n")
    print(f"{'신호':<10}{'IC 1개월':>10}{'t':>7}{'IC 3개월':>10}{'상위⅓−하위⅓/월':>16}{'t':>7}")
    out = {}
    for s in sig_names:
        ic, ic3, ls = res.get(f"ic_{s}"), res.get(f"ic3_{s}"), res.get(f"ls_{s}")
        if ic is None:
            continue
        print(f"{s:<10}{ic.mean():>+10.3f}{t(ic):>7.2f}{ic3.mean():>+10.3f}{ls.mean():>+16.2%}{t(ls):>7.2f}")
        out[s] = {"ic1": ic.mean(), "t_ic1": t(ic), "ic3": ic3.mean(), "ls": ls.mean(), "t_ls": t(ls)}
    print()
    print(f"Top 30 포트폴리오 (월 리밸런싱, 동일비중) — 전체 유니버스 평균 {res.all_ret.mean():+.2%}/월")
    for k in [c[2:] for c in res.columns if c.startswith("p_")]:
        ex = res[f"p_{k}"] - res.all_ret
        cum = (1 + res[f"p_{k}"]).prod() - 1
        print(f"  {k:<22} 월 {res[f'p_{k}'].mean():+.2%} · 초과 {ex.mean():+.2%} (t={t(ex):.2f}) · 누적 {cum:+.0%} · 3개월 보유 {res[f'p3_{k}'].mean():+.2%}")
        out[k] = {"m": res[f"p_{k}"].mean(), "ex": ex.mean(), "t": t(ex), "cum": cum}
    (ROOT / "data/backtest").mkdir(parents=True, exist_ok=True)
    (ROOT / "data/backtest/signals_in_cheap.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
