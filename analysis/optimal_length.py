"""
Find the optimal video length by looking at the relationship
between length and multiple performance signals.

Hypothesis to test (user's intuition):
  - performance grows with length up to a knee
  - after the knee, returns flatten

Approach:
  - normalize views by age (views_per_day) to remove the "older
    videos have more time" confound
  - plot length vs (views_per_day, watch_hours, revenue, impressions)
  - fit log/power/piecewise curves to estimate the knee
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
ANALYTICS = ROOT / "analysis" / "report" / "cleaned.csv"
OUT_DIR = ROOT / "analysis" / "report"

an = pd.read_csv(ANALYTICS, parse_dates=["published_at"])
asof = pd.Timestamp("2026-04-25")
an["age_days"] = (asof - an["published_at"]).dt.days.clip(lower=1)
an["views_per_day"] = an["views"] / an["age_days"]
an["watch_hours_per_day"] = an["watch_hours"] / an["age_days"]
an["impressions_per_day"] = an["impressions"] / an["age_days"]
an["rev_per_day"] = an["est_revenue_jpy"] / an["age_days"]

long_df = an[(an["format"] == "Long") & (an["length_sec"] > 60)].copy()
long_df["length_min"] = long_df["length_sec"] / 60
long_df["avg_watch_min"] = long_df["avg_watch_sec"] / 60

print(f"n = {len(long_df)} long-form videos\n")


# ---- Spearman correlations -----------------------------------------
print("Spearman correlation of length_min with:")
for metric in ["views", "views_per_day", "watch_hours_per_day",
               "impressions_per_day", "rev_per_day", "avg_view_pct",
               "avg_watch_min", "rpm_jpy", "impression_ctr",
               "subs_gained"]:
    rho = long_df[["length_min", metric]].corr(method="spearman").iloc[0, 1]
    print(f"  {metric:<25s} : {rho:+.2f}")


# ---- Knee-point detection via piecewise linear fit ------------------
def piecewise_fit(x, y, breakpoint):
    """Two linear segments meeting at breakpoint."""
    mask = x <= breakpoint
    if mask.sum() < 2 or (~mask).sum() < 2:
        return None
    x1, y1 = x[mask], y[mask]
    x2, y2 = x[~mask], y[~mask]
    s1, i1 = np.polyfit(x1, y1, 1)
    s2, i2 = np.polyfit(x2, y2, 1)
    pred = np.where(x <= breakpoint, s1*x + i1, s2*x + i2)
    ss_res = np.sum((y - pred) ** 2)
    return ss_res, s1, s2


def find_knee(x, y, candidates):
    best = None
    for bp in candidates:
        r = piecewise_fit(x, y, bp)
        if r is None:
            continue
        ss, s1, s2 = r
        if best is None or ss < best["ss"]:
            best = {"bp": bp, "ss": ss, "s1": s1, "s2": s2}
    return best


# Use log-transformed metrics where appropriate
candidates = np.arange(15, 70, 1.0)

print("\n\nKnee detection (best break-point that minimizes SS):")
for metric in ["views_per_day", "watch_hours_per_day", "impressions_per_day",
               "rev_per_day"]:
    sub = long_df[long_df[metric] > 0].copy()
    x = sub["length_min"].values
    y = np.log(sub[metric].values)
    knee = find_knee(x, y, candidates)
    if knee:
        s1_pct = (np.exp(knee["s1"]) - 1) * 100  # % change per minute, segment 1
        s2_pct = (np.exp(knee["s2"]) - 1) * 100  # % change per minute, segment 2
        print(f"  log({metric:<22s}): knee at {knee['bp']:.0f}min  "
              f"slope_pre  {s1_pct:+5.1f}%/min  "
              f"slope_post {s2_pct:+5.1f}%/min")


# ---- Plot -----------------------------------------------------------
fig, axes = plt.subplots(2, 3, figsize=(16, 10))
metrics_to_plot = [
    ("views_per_day", "視聴回数/日", True),
    ("watch_hours_per_day", "再生時間/日（時間）", True),
    ("impressions_per_day", "インプレッション/日", True),
    ("rev_per_day", "収益/日（円）", True),
    ("avg_view_pct", "平均視聴維持率（%）", False),
    ("rpm_jpy", "RPM（円）", False),
]


def plot_with_fit(ax, x, y, label, log_y, knee_bp=None):
    ax.scatter(x, y, s=60, alpha=0.7, color="#1f77b4", edgecolor="black",
               linewidth=0.5)
    if log_y:
        ax.set_yscale("log")
    # Smooth log fit
    if log_y and (y > 0).all():
        coef = np.polyfit(x, np.log(y), 1)
        xs = np.linspace(x.min(), x.max(), 100)
        ax.plot(xs, np.exp(coef[1] + coef[0]*xs), "--", color="#7f7f7f",
                linewidth=1, label=f"対数線形フィット")
    elif not log_y:
        coef = np.polyfit(x, y, 1)
        xs = np.linspace(x.min(), x.max(), 100)
        ax.plot(xs, coef[0]*xs + coef[1], "--", color="#7f7f7f",
                linewidth=1, label="線形フィット")
    if knee_bp is not None:
        ax.axvline(knee_bp, color="#d62728", linestyle=":", linewidth=1.5,
                   label=f"屈曲点 {knee_bp:.0f}分")
    rho = pd.DataFrame({"a": list(x), "b": list(y)}).corr(method="spearman").iloc[0, 1]
    ax.set_title(f"{label}  ρ={rho:+.2f}")
    ax.set_xlabel("動画の長さ（分）")
    ax.set_ylabel(label)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)


# Find knees per metric for the plot
knees = {}
for m in ["views_per_day", "watch_hours_per_day", "impressions_per_day",
          "rev_per_day"]:
    sub = long_df[long_df[m] > 0]
    knee = find_knee(sub["length_min"].values, np.log(sub[m].values),
                     np.arange(15, 70, 1.0))
    knees[m] = knee["bp"] if knee else None

for ax, (col, label, logy) in zip(axes.flatten(), metrics_to_plot):
    sub = long_df[long_df[col] > 0]
    plot_with_fit(ax, sub["length_min"].values, sub[col].values, label, logy,
                  knees.get(col))

plt.suptitle(f"動画長 vs パフォーマンス指標  (n={len(long_df)} 本のロングフォーム動画)",
             fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "optimal_length_signals.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")

# ---- Save the per-video table ---------------------------------------
out_cols = ["video_id", "title", "published_at", "length_min", "avg_watch_min",
            "age_days", "views", "views_per_day", "watch_hours_per_day",
            "impressions_per_day", "rev_per_day", "rpm_jpy", "avg_view_pct"]
out = long_df[out_cols].copy().sort_values("length_min")
out["title"] = out["title"].str.slice(0, 30)
out.to_csv(OUT_DIR / "length_performance.csv", index=False)
print(f"Wrote: {OUT_DIR / 'length_performance.csv'}")

# Summary by length bucket
print("\n\nMedian metrics by length bucket:")
long_df["length_bin"] = pd.cut(long_df["length_min"],
                                bins=[0, 15, 25, 35, 50, 65, 80],
                                labels=["<15", "15-25", "25-35", "35-50",
                                        "50-65", "65+"])
summary = long_df.groupby("length_bin", observed=True).agg(
    n=("video_id", "count"),
    median_views_per_day=("views_per_day", "median"),
    median_watch_hpd=("watch_hours_per_day", "median"),
    median_rev_per_day=("rev_per_day", "median"),
    median_rpm=("rpm_jpy", "median"),
    median_impressions_pd=("impressions_per_day", "median"),
).round(2)
print(summary.to_string())
