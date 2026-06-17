"""
Plot marginal revenue per minute of video length.

Shows:
  1. Raw scatter of length vs rev/day with smoothed fit
  2. Smoothed log(rev/day) curve with breakpoint candidates
  3. Marginal revenue (d rev/day / d length) — the "limit" curve
  4. Same for views/day

Filters out videos < 180 days old to avoid discovery-boost artifacts.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _jp_font import setup_japanese_font  # noqa: E402
setup_japanese_font()

ROOT = Path(__file__).resolve().parent.parent
ANALYTICS = ROOT / "analysis" / "report" / "cleaned.csv"
OUT_DIR = ROOT / "analysis" / "report"

an = pd.read_csv(ANALYTICS, parse_dates=["published_at"])
asof = pd.Timestamp("2026-04-25")
an["age_days"] = (asof - an["published_at"]).dt.days.clip(lower=1)
an["length_min"] = an["length_sec"] / 60
an["rev_per_day"] = an["est_revenue_jpy"] / an["age_days"]
an["views_per_day"] = an["views"] / an["age_days"]

long_df = an[(an["format"] == "Long") & (an["length_sec"] > 60)].copy()
print(f"Total long-form videos: {len(long_df)}")

# Mature videos only (age >= 180 days) to filter discovery boost
mature = long_df[(long_df["age_days"] >= 180) &
                 long_df["rev_per_day"].notna() &
                 (long_df["rev_per_day"] > 0)].copy()
recent = long_df[long_df["age_days"] < 180].copy()
print(f"Mature (>=180d, rev>0): {len(mature)}, Recent (<180d): {len(recent)}")


def loess_smooth(x, y, span=0.5):
    """Simple LOWESS-style local polynomial smoothing without scipy."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    order = np.argsort(x)
    x, y = x[order], y[order]
    n = len(x)
    k = max(3, int(n * span))
    xs = np.linspace(x.min(), x.max(), 100)
    ys = np.zeros_like(xs)
    for i, xi in enumerate(xs):
        # k nearest neighbors by x
        d = np.abs(x - xi)
        idx = np.argsort(d)[:k]
        xn, yn = x[idx], y[idx]
        wn = np.maximum(0, 1 - (d[idx] / d[idx].max()) ** 3) ** 3
        # Weighted linear fit
        wsum = wn.sum()
        if wsum == 0:
            ys[i] = yn.mean()
            continue
        wx = np.sum(wn * xn) / wsum
        wy = np.sum(wn * yn) / wsum
        wxx = np.sum(wn * (xn - wx) ** 2)
        wxy = np.sum(wn * (xn - wx) * (yn - wy))
        slope = wxy / wxx if wxx > 0 else 0
        ys[i] = wy + slope * (xi - wx)
    return xs, ys


def numerical_derivative(xs, ys):
    """First derivative of a smooth curve."""
    return xs[:-1] + np.diff(xs) / 2, np.diff(ys) / np.diff(xs)


# ---- Compute smoothed curves on log scale (revenue grows roughly log-linear) ----
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Panel 1: rev_per_day vs length, mature only, smoothed
x_m = mature["length_min"].values
y_m = mature["rev_per_day"].values
y_log = np.log(np.maximum(y_m, 0.1))
xs_m, ys_log = loess_smooth(x_m, y_log, span=0.6)
ys_m = np.exp(ys_log)

ax = axes[0, 0]
ax.scatter(mature["length_min"], mature["rev_per_day"],
           color="#1f77b4", s=60, alpha=0.7, edgecolor="black",
           linewidth=0.5, label=f"成熟動画 (n={len(mature)})")
ax.scatter(recent["length_min"], recent["rev_per_day"],
           color="#ff7f0e", s=60, alpha=0.5, edgecolor="black",
           linewidth=0.5, marker="^", label=f"新作 <180日 (n={len(recent)}・除外)")
ax.plot(xs_m, ys_m, "-", color="#d62728", linewidth=2.5,
        label="平滑化曲線 (成熟動画)")
for _, r in mature.iterrows():
    ax.annotate(r["video_id"], (r["length_min"], r["rev_per_day"]),
                xytext=(3, 3), textcoords="offset points",
                fontsize=6, color="#444")
ax.set_yscale("log")
ax.set_xlabel("動画の長さ（分）")
ax.set_ylabel("収益/日（円・対数軸）")
ax.set_title("動画長 vs 1日あたり収益（成熟動画のみ）")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# Panel 2: marginal revenue (d rev/d length) — the limit curve
ax = axes[0, 1]
xd, dy = numerical_derivative(xs_m, ys_m)
ax.plot(xd, dy, "-", color="#2ca02c", linewidth=2.5,
        label="限界収益（傾き）")
ax.fill_between(xd, 0, dy, where=(dy > 0), alpha=0.2, color="#2ca02c",
                label="プラス領域（伸ばすほど儲かる）")
ax.fill_between(xd, 0, dy, where=(dy <= 0), alpha=0.2, color="#d62728",
                label="マイナス領域（伸ばすと損）")
ax.axhline(0, color="black", linewidth=0.7)
peak_idx = np.argmax(ys_m)
ax.axvline(xs_m[peak_idx], color="black", linestyle=":",
           label=f"収益ピーク {xs_m[peak_idx]:.0f}分")
ax.set_xlabel("動画の長さ（分）")
ax.set_ylabel("1分追加あたりの収益増減（円/日）")
ax.set_title("1分追加で得られる限界収益")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# Panel 3: same for views_per_day
y_v = mature["views_per_day"].values
y_v_log = np.log(np.maximum(y_v, 1))
xs_v, ys_v_log = loess_smooth(x_m, y_v_log, span=0.6)
ys_v = np.exp(ys_v_log)
ax = axes[1, 0]
ax.scatter(mature["length_min"], mature["views_per_day"],
           color="#1f77b4", s=60, alpha=0.7, edgecolor="black",
           linewidth=0.5, label="成熟動画")
ax.plot(xs_v, ys_v, "-", color="#d62728", linewidth=2.5,
        label="平滑化曲線")
ax.set_yscale("log")
ax.set_xlabel("動画の長さ（分）")
ax.set_ylabel("視聴回数/日（対数軸）")
ax.set_title("動画長 vs 1日あたり視聴回数（成熟動画のみ）")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# Panel 4: marginal views
ax = axes[1, 1]
xd_v, dy_v = numerical_derivative(xs_v, ys_v)
ax.plot(xd_v, dy_v, "-", color="#2ca02c", linewidth=2.5,
        label="限界視聴増（傾き）")
ax.fill_between(xd_v, 0, dy_v, where=(dy_v > 0), alpha=0.2, color="#2ca02c")
ax.fill_between(xd_v, 0, dy_v, where=(dy_v <= 0), alpha=0.2, color="#d62728")
ax.axhline(0, color="black", linewidth=0.7)
peak_idx_v = np.argmax(ys_v)
ax.axvline(xs_v[peak_idx_v], color="black", linestyle=":",
           label=f"視聴ピーク {xs_v[peak_idx_v]:.0f}分")
ax.set_xlabel("動画の長さ（分）")
ax.set_ylabel("1分追加あたりの視聴回数増減（views/日）")
ax.set_title("1分追加で得られる限界視聴回数")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

plt.suptitle(f"動画長の限界収益・限界視聴 分析  "
             f"(成熟動画 n={len(mature)}・新作除外)",
             fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "marginal_length.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")

# ---- Print numeric summary at common length points ----------------
print("\n=== Marginal revenue at key length points ===")
print(f"{'length':>10s}  {'rev/day':>12s}  {'+1min Δrev':>14s}")
for L in [20, 25, 30, 35, 40, 45, 50, 60, 70]:
    if L < xs_m.min() or L > xs_m.max():
        continue
    i = np.argmin(np.abs(xs_m - L))
    rev = ys_m[i]
    if i < len(xd):
        dr = dy[i] if i < len(dy) else 0
    else:
        dr = 0
    print(f"  {L:>5d}min  ¥{rev:>10.0f}/day  ¥{dr:>+12.1f}/day per +1min")

# Save smoothed curves
out_csv = pd.DataFrame({
    "length_min": xs_m,
    "smooth_rev_per_day": ys_m,
})
out_csv["marginal_rev"] = np.append(np.diff(ys_m) / np.diff(xs_m), np.nan)
out_csv.to_csv(OUT_DIR / "marginal_length_curve.csv", index=False)
print(f"Wrote: {OUT_DIR / 'marginal_length_curve.csv'}")
