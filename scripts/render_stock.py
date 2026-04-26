"""data/stocks/{code}.json → static_charts/{code}.png (4분할 차트)"""
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter

plt.rcParams["font.family"] = ["Malgun Gothic", "AppleGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "stocks"
OUT_DIR = ROOT / "static_charts"
OUT_DIR.mkdir(exist_ok=True)

COLOR = "#2563eb"


def _plot_metric(ax, dates, series, title, value_fmt="{:.2f}", forward_value=None, forward_label=""):
    if series is None or all(v is None for v in series):
        ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center",
                transform=ax.transAxes, color="#9ca3af", fontsize=11)
        ax.set_title(title, fontsize=11, fontweight="bold", loc="left")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.spines[["top", "right", "bottom", "left"]].set_visible(False)
        return

    pairs = [(d, v) for d, v in zip(dates, series) if v is not None]
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    ax.plot(xs, ys, color=COLOR, linewidth=1.5)

    if len(ys) >= 2:
        mean = statistics.mean(ys)
        sd = statistics.stdev(ys)
        if sd > 0:
            ax.axhspan(mean - sd, mean + sd, color=COLOR, alpha=0.08)
        ax.axhline(mean, color=COLOR, linestyle="--", linewidth=1, alpha=0.5)
        cur = ys[-1]
        z = (cur - mean) / sd if sd > 0 else 0
        sign = "+" if z >= 0 else ""
        subtitle = f"현재 {value_fmt.format(cur)}  ·  평균 {value_fmt.format(mean)}  ·  {sign}{z:.2f}σ"
    else:
        subtitle = f"현재 {value_fmt.format(ys[-1])}"

    if forward_value is not None:
        ax.axhline(forward_value, color="#dc2626", linestyle=":", linewidth=1.8, alpha=0.85)
        ax.annotate(f"Forward {value_fmt.format(forward_value)} ({forward_label})",
                    xy=(xs[-1], forward_value), xytext=(-6, 6),
                    textcoords="offset points", color="#dc2626",
                    fontsize=9, fontweight="bold", ha="right")
        subtitle += f"  ·  Forward {value_fmt.format(forward_value)}"

    ax.set_title(f"{title}\n{subtitle}", fontsize=10, fontweight="bold", loc="left",
                 color="#1c1f24")
    ax.grid(True, alpha=0.2, linestyle="-", linewidth=0.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#d1d5db")
    ax.tick_params(colors="#6b7280", labelsize=9)
    ax.xaxis.set_major_formatter(DateFormatter("%Y"))


def render(code: str) -> Path:
    p = DATA_DIR / f"{code}.json"
    if not p.exists():
        raise FileNotFoundError(p)
    d = json.loads(p.read_text(encoding="utf-8"))
    dates = [datetime.strptime(s, "%Y-%m-%d") for s in d["dates"]]

    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    fig.patch.set_facecolor("white")
    fig.suptitle(f"{d['name']} ({d['ticker']}) · {d['market']} · 10년 시계열",
                 fontsize=14, fontweight="bold", x=0.05, ha="left", y=0.98)

    fwd = d.get("forward") or {}
    fwd_year = fwd.get("year_estimate", "Forward")
    _plot_metric(axes[0, 0], dates, d.get("per"), "PER (주가수익비율)",
                 forward_value=fwd.get("per_forward"), forward_label=fwd_year)
    _plot_metric(axes[0, 1], dates, d.get("pbr"), "PBR (주가순자산비율)",
                 forward_value=fwd.get("pbr_forward"), forward_label=fwd_year)

    cap_unit = d.get("market_cap_unit", "")
    _plot_metric(axes[1, 0], dates, d.get("market_cap"),
                 f"시가총액 ({cap_unit})", "{:,.0f}")

    price_unit = d.get("price_unit", "")
    _plot_metric(axes[1, 1], dates, d.get("close"),
                 f"종가 ({price_unit})", "{:,.0f}")

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = OUT_DIR / f"{code}.png"
    fig.savefig(out, dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main():
    if len(sys.argv) < 2:
        print("Usage: python render_stock.py <code>", file=sys.stderr)
        sys.exit(1)
    out = render(sys.argv[1])
    print(f"  → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
