"""
Slot count vs total watch time / per-viewer watch time scatter.

Tests whether more slots correlate non-monotonically (inverted-U)
with retention metrics. Plots three views:
  - slot count vs total watch hours (raw)
  - slot count vs avg_watch_sec (per-viewer)
  - slots/min vs avg_watch_sec (density)

Length is a strong confound (longer videos -> more total watch),
so length-controlled residual scatters are also produced.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PV = ROOT / "analysis" / "report" / "ad_slots_per_video.csv"
ANALYTICS = ROOT / "analysis" / "report" / "cleaned.csv"
OUT_DIR = ROOT / "analysis" / "report"

pv = pd.read_csv(PV)
an = pd.read_csv(ANALYTICS)
df = pv.merge(an[["video_id", "watch_hours"]], on="video_id")
df["slots_per_min"] = df["effective_slots"] / df["length_min"]
df["watch_hours_per_view"] = df["watch_hours"] / df["views"] * 60  # min/view


def fit_quadratic(x, y):
    if len(x) < 3:
        return None, None, None
    coef = np.polyfit(x, y, 2)
    a, b, c = coef
    vertex = -b / (2 * a) if a != 0 else None
    ss_res = np.sum((y - np.polyval(coef, x)) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot
    return coef, vertex, r2


def spearman(x, y):
    return pd.DataFrame({"a": list(x), "b": list(y)}).corr(method="spearman").iloc[0, 1]


fig, axes = plt.subplots(2, 2, figsize=(13, 10))


def plot_panel(ax, x, y, xlabel, ylabel, df_ref):
    colors = df_ref["inserted_by"].map({"manual": "#1f77b4", "auto": "#ff7f0e"})
    ax.scatter(x, y, c=colors, s=80, edgecolor="black", linewidth=0.5, alpha=0.85)
    for _, r in df_ref.iterrows():
        ax.annotate(r["video_id"], (r[x.name], r[y.name]),
                    xytext=(3, 3), textcoords="offset points",
                    fontsize=7, color="#444")

    coef, vertex, r2 = fit_quadratic(x.values, y.values)
    if coef is not None:
        xs = np.linspace(x.min() - 0.5, x.max() + 0.5, 100)
        ax.plot(xs, np.polyval(coef, xs), "-", color="#d62728", linewidth=2,
                label=f"quadratic R^2={r2:.2f}")
        if coef[0] < 0 and x.min() <= vertex <= x.max():
            ax.axvline(vertex, color="#d62728", linestyle=":", alpha=0.5)
            ax.annotate(f"peak x={vertex:.2f}",
                        xy=(vertex, np.polyval(coef, vertex)),
                        xytext=(8, -10), textcoords="offset points",
                        color="#d62728", fontsize=9)

    rho = spearman(x, y)
    ax.set_title(f"{xlabel} vs {ylabel}   ρ={rho:+.2f}")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)


# Panel 1: slot count vs total watch hours
plot_panel(axes[0, 0],
           df["effective_slots"], df["watch_hours"],
           "Effective slot count", "Total watch hours", df)

# Panel 2: slot count vs avg_watch_min (per-viewer)
plot_panel(axes[0, 1],
           df["effective_slots"], df["avg_watch_min"],
           "Effective slot count", "Avg watch (minutes per viewer)", df)

# Panel 3: slots/min vs avg_watch_min
plot_panel(axes[1, 0],
           df["slots_per_min"], df["avg_watch_min"],
           "Slots / min (density)", "Avg watch (minutes per viewer)", df)

# Panel 4: length-controlled (residualize avg_watch_min on length)
slope, intercept = np.polyfit(df["length_min"], df["avg_watch_min"], 1)
df["avg_watch_resid"] = df["avg_watch_min"] - (slope * df["length_min"] + intercept)
plot_panel(axes[1, 1],
           df["effective_slots"], df["avg_watch_resid"],
           "Effective slot count",
           "Avg watch residual (length-controlled, min)", df)
axes[1, 1].axhline(0, color="black", linewidth=0.6)

plt.suptitle("Slot count vs watch-time metrics  (n=19)", fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "slots_vs_watchtime.png"
plt.savefig(out_png, dpi=140)
print(f"Wrote: {out_png}")

# Print summary
print("\nSpearman correlations:")
print(f"  slots vs total_watch_hours        : {spearman(df['effective_slots'], df['watch_hours']):+.2f}")
print(f"  slots vs avg_watch_min            : {spearman(df['effective_slots'], df['avg_watch_min']):+.2f}")
print(f"  slots/min vs avg_watch_min        : {spearman(df['slots_per_min'], df['avg_watch_min']):+.2f}")
print(f"  slots vs avg_watch_resid          : {spearman(df['effective_slots'], df['avg_watch_resid']):+.2f}")

print("\nQuadratic fits (R^2 / peak-x if concave-down):")
for x_col, y_col, label in [
    ("effective_slots", "watch_hours", "slots vs watch_hours"),
    ("effective_slots", "avg_watch_min", "slots vs avg_watch_min"),
    ("slots_per_min", "avg_watch_min", "slots/min vs avg_watch_min"),
    ("effective_slots", "avg_watch_resid", "slots vs avg_watch_resid"),
]:
    coef, vertex, r2 = fit_quadratic(df[x_col].values, df[y_col].values)
    a = coef[0]
    shape = "concave-down (peak)" if a < 0 else "concave-up (no peak)"
    print(f"  {label:36s}  R²={r2:.2f}  a={a:+.3f} {shape}  vertex_x={vertex:.2f}")
