"""
Scatter plot: ad-slot count vs RPM, with quadratic fit overlay.

Saves PNG to analysis/report/slots_vs_rpm.png.
"""

from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _jp_font import setup_japanese_font  # noqa: E402
setup_japanese_font()

ROOT = Path(__file__).resolve().parent.parent
PV = ROOT / "analysis" / "report" / "ad_slots_per_video.csv"
OUT_DIR = ROOT / "analysis" / "report"

df = pd.read_csv(PV).dropna(subset=["effective_slots", "rpm_jpy"])
df = df[df["rpm_jpy"] > 0]

x = df["effective_slots"].to_numpy(dtype=float)
y = df["rpm_jpy"].to_numpy(dtype=float)

# Quadratic fit y = a*x^2 + b*x + c
coef = np.polyfit(x, y, 2)
xs = np.linspace(x.min() - 0.5, x.max() + 0.5, 200)
ys = np.polyval(coef, xs)

# Vertex (optimum) of quadratic
a, b, c = coef
vertex_x = -b / (2 * a) if a != 0 else None
vertex_y = np.polyval(coef, vertex_x) if vertex_x is not None else None

# Linear fit for reference
lin = np.polyfit(x, y, 1)
ys_lin = np.polyval(lin, xs)

# Correlations
spearman = df[["effective_slots", "rpm_jpy"]].corr(method="spearman").iloc[0, 1]
pearson = df[["effective_slots", "rpm_jpy"]].corr(method="pearson").iloc[0, 1]

# R^2 of quadratic
ss_res = np.sum((y - np.polyval(coef, x)) ** 2)
ss_tot = np.sum((y - y.mean()) ** 2)
r2_quad = 1 - ss_res / ss_tot

ss_res_lin = np.sum((y - np.polyval(lin, x)) ** 2)
r2_lin = 1 - ss_res_lin / ss_tot

# Color by inserted_by
colors = df["inserted_by"].map({"manual": "#1f77b4", "auto": "#ff7f0e"})

fig, ax = plt.subplots(figsize=(9, 6))
ax.scatter(x, y, c=colors, s=80, edgecolor="black", linewidth=0.6, zorder=3,
           alpha=0.9)

# Annotate each point with video_id
for _, row in df.iterrows():
    ax.annotate(row["video_id"], (row["effective_slots"], row["rpm_jpy"]),
                xytext=(4, 4), textcoords="offset points",
                fontsize=7, color="#444")

ax.plot(xs, ys, "-", color="#d62728", linewidth=2,
        label=f"二次フィット  R²={r2_quad:.2f}")
ax.plot(xs, ys_lin, "--", color="#7f7f7f", linewidth=1.2,
        label=f"線形フィット  R²={r2_lin:.2f}")

if vertex_x is not None and a < 0 and x.min() <= vertex_x <= x.max():
    ax.axvline(vertex_x, color="#d62728", linestyle=":", alpha=0.5)
    ax.annotate(f"二次関数のピーク\nslots={vertex_x:.1f}, RPM={vertex_y:.0f}",
                xy=(vertex_x, vertex_y), xytext=(vertex_x + 0.5, vertex_y + 50),
                fontsize=9, color="#d62728")

# Legend for color
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#1f77b4",
           markersize=10, label="manual", markeredgecolor="black"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#ff7f0e",
           markersize=10, label="auto", markeredgecolor="black"),
]
fit_legend = ax.legend(loc="upper right", fontsize=9)
ax.add_artist(fit_legend)
ax.legend(handles=legend_elements, loc="lower left", fontsize=9, title="挿入方式")

ax.set_xlabel("動画あたりの有効広告スロット数")
ax.set_ylabel("RPM（円）")
ax.set_title(f"広告スロット数 vs RPM   (n={len(df)},  "
             f"Spearman={spearman:.2f}, Pearson={pearson:.2f})")
ax.grid(True, alpha=0.3)

out = OUT_DIR / "slots_vs_rpm.png"
plt.tight_layout()
plt.savefig(out, dpi=140)
print(f"Wrote: {out}")
print(f"Quadratic coef: a={a:.3f}, b={b:.3f}, c={c:.3f}")
print(f"Quadratic peak at slots={vertex_x:.2f}, RPM={vertex_y:.1f}" if a < 0 else "Quadratic is concave-up (no peak)")
print(f"R^2 quadratic={r2_quad:.3f}, R^2 linear={r2_lin:.3f}")
print(f"Spearman={spearman:.3f}, Pearson={pearson:.3f}")
