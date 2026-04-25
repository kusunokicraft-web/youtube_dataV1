"""
Ad-slot placement vs viewer retention analysis.

Tests whether slot count, density, and pre-roll gap correlate
with avg_view_pct and avg_watch_sec across the 19 ingested
videos. Length is a strong confound (longer videos -> lower
view %), so length-controlled (residualized) views are also
computed.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PV = ROOT / "analysis" / "report" / "ad_slots_per_video.csv"
GAPS = ROOT / "analysis" / "report" / "slot_gaps_per_video.csv"
ANALYTICS = ROOT / "analysis" / "report" / "cleaned.csv"
OUT_DIR = ROOT / "analysis" / "report"

pv = pd.read_csv(PV)
gp = pd.read_csv(GAPS)
an = pd.read_csv(ANALYTICS)

df = pv.merge(gp[["video_id", "pre_gap_min", "median_inter_min", "max_inter_min",
                  "n_wide_gt10min", "n_sub30s"]], on="video_id")
df = df.merge(an[["video_id", "avg_view_pct"]], on="video_id")
df["slots_per_min"] = df["effective_slots"] / df["length_min"]

# Residualize: regress avg_view_pct ~ length_min, take residuals
slope, intercept = np.polyfit(df["length_min"], df["avg_view_pct"], 1)
df["avg_view_pct_pred"] = slope * df["length_min"] + intercept
df["avg_view_pct_resid"] = df["avg_view_pct"] - df["avg_view_pct_pred"]

# Same for avg_watch_min
slope2, intercept2 = np.polyfit(df["length_min"], df["avg_watch_min"], 1)
df["avg_watch_min_pred"] = slope2 * df["length_min"] + intercept2
df["avg_watch_min_resid"] = df["avg_watch_min"] - df["avg_watch_min_pred"]

# ---- Correlation matrix --------------------------------------------
metrics = ["effective_slots", "slots_per_min", "pre_gap_min",
           "median_inter_min", "max_inter_min", "n_wide_gt10min",
           "slots_in_golden_zone", "first_slot_pct_of_avg"]
target_cols = ["avg_view_pct", "avg_view_pct_resid",
               "avg_watch_min", "avg_watch_min_resid"]

print("=" * 78)
print("Spearman correlation: slot metric  vs  retention metric")
print("=" * 78)
print(f"{'metric':<28s} | " + " | ".join(f"{t:<22s}" for t in target_cols))
print("-" * 78)
for m in metrics:
    row = []
    for t in target_cols:
        rho = df[[m, t]].corr(method="spearman").iloc[0, 1]
        row.append(f"{rho:+.2f}")
    print(f"{m:<28s} | " + " | ".join(f"{v:<22s}" for v in row))

# ---- Auto vs manual retention --------------------------------------
print("\n" + "=" * 78)
print("Retention by inserted_by")
print("=" * 78)
for tag in ["manual", "auto"]:
    sub = df[df["inserted_by"] == tag]
    if len(sub) == 0:
        continue
    print(f"  {tag} (n={len(sub)}): "
          f"avg_view_pct median={sub['avg_view_pct'].median():.1f}%  "
          f"residualized={sub['avg_view_pct_resid'].median():+.1f}pp  "
          f"avg_watch_min={sub['avg_watch_min'].median():.1f}")

# ---- Plot ----------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(13, 10))

def scatter_with_fit(ax, x, y, label_x, label_y, color="#1f77b4", colors=None):
    if colors is None:
        ax.scatter(x, y, color=color, s=70, edgecolor="black", linewidth=0.5,
                   alpha=0.85)
    else:
        ax.scatter(x, y, c=colors, s=70, edgecolor="black", linewidth=0.5,
                   alpha=0.85)
    if len(x) > 2:
        slope, intercept = np.polyfit(x, y, 1)
        xs = np.linspace(x.min(), x.max(), 100)
        ax.plot(xs, slope*xs + intercept, "--", color="#7f7f7f", linewidth=1)
        rho = pd.DataFrame({"a": list(x), "b": list(y)}).corr(method="spearman").iloc[0, 1]
        ax.set_title(f"{label_x} vs {label_y}   ρ={rho:+.2f}")
    ax.set_xlabel(label_x)
    ax.set_ylabel(label_y)
    ax.grid(True, alpha=0.3)

colors = df["inserted_by"].map({"manual": "#1f77b4", "auto": "#ff7f0e"}).tolist()

scatter_with_fit(axes[0, 0], df["effective_slots"], df["avg_view_pct"],
                 "Slot count", "avg_view_pct (%)", colors=colors)

scatter_with_fit(axes[0, 1], df["slots_per_min"], df["avg_view_pct_resid"],
                 "Slots / min", "avg_view_pct residual (length-controlled)",
                 colors=colors)
axes[0, 1].axhline(0, color="black", linewidth=0.6)

scatter_with_fit(axes[1, 0], df["pre_gap_min"], df["avg_view_pct"],
                 "Pre-roll-to-first-slot gap (min)", "avg_view_pct (%)",
                 colors=colors)

scatter_with_fit(axes[1, 1], df["slots_in_golden_zone"], df["avg_view_pct_resid"],
                 "Slots in golden zone", "avg_view_pct residual",
                 colors=colors)
axes[1, 1].axhline(0, color="black", linewidth=0.6)

# Annotate each point with video_id
for ax, x_col, y_col in [(axes[0, 0], "effective_slots", "avg_view_pct"),
                          (axes[0, 1], "slots_per_min", "avg_view_pct_resid"),
                          (axes[1, 0], "pre_gap_min", "avg_view_pct"),
                          (axes[1, 1], "slots_in_golden_zone", "avg_view_pct_resid")]:
    for _, row in df.iterrows():
        ax.annotate(row["video_id"], (row[x_col], row[y_col]),
                    xytext=(3, 3), textcoords="offset points",
                    fontsize=6, color="#444")

# Single legend (top-left)
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#1f77b4",
           markersize=9, label="manual", markeredgecolor="black"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#ff7f0e",
           markersize=9, label="auto", markeredgecolor="black"),
]
axes[0, 0].legend(handles=legend_elements, loc="upper right", fontsize=8)

plt.suptitle("Ad-slot placement vs viewer retention  (n=19)", fontsize=12, y=1.00)
plt.tight_layout()
out_png = OUT_DIR / "slots_vs_retention.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")

# Save the merged dataset for further drilling
df_out = df[["video_id", "title", "length_min", "avg_watch_min",
             "effective_slots", "slots_per_min", "pre_gap_min",
             "slots_in_golden_zone", "inserted_by",
             "avg_view_pct", "avg_view_pct_resid",
             "avg_watch_min_resid", "rpm_jpy", "est_revenue_jpy"]]
df_out.to_csv(OUT_DIR / "slots_vs_retention.csv", index=False)
print(f"Wrote: {OUT_DIR / 'slots_vs_retention.csv'}")
