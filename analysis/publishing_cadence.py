"""
Publishing cadence (投稿間隔) optimization analysis.

Tests whether the time-since-previous-release affects each video's
performance, and recommends an optimal posting cadence for Phase 1
(half-pro period).
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
an["length_min"] = an["length_sec"] / 60
an["views_per_day"] = an["views"] / an["age_days"]
an["rev_per_day"] = an["est_revenue_jpy"] / an["age_days"]

# Performance index (from #6)
mask_long = an["format"] == "Long"
x_log = np.log(an.loc[mask_long, "age_days"].values)
y_log = np.log(an.loc[mask_long, "views"].clip(lower=1).values)
k, a_ = np.polyfit(x_log, y_log, 1)
c = np.exp(a_)
an["expected_views"] = c * (an["age_days"] ** k)
an["performance_index"] = an["views"] / an["expected_views"]

from _exclusions import EXCLUDED_VIDEO_IDS as EXC
df = an[(an["format"] == "Long") & (an["views"] > 0)].copy()
df = df[~df["video_id"].isin(EXC)].sort_values("published_at").reset_index(drop=True)


# ---- Compute interval between consecutive uploads ------------------
df["gap_from_prev_days"] = df["published_at"].diff().dt.days
df["gap_to_next_days"] = -df["published_at"].diff(-1).dt.days

# Recent-window cadence: count of uploads in past 90 days at each release
for i in range(len(df)):
    pub = df.loc[i, "published_at"]
    df.loc[i, "uploads_prev_90d"] = (
        (df["published_at"] >= pub - pd.Timedelta(days=90)) &
        (df["published_at"] < pub)
    ).sum()
    df.loc[i, "uploads_prev_180d"] = (
        (df["published_at"] >= pub - pd.Timedelta(days=180)) &
        (df["published_at"] < pub)
    ).sum()


# ---- Channel-wide cadence over time --------------------------------
print("=" * 90)
print("チャネル全体の投稿ペース推移")
print("=" * 90)
df["pub_year"] = df["published_at"].dt.year
df["pub_year_month"] = df["published_at"].dt.to_period("M").astype(str)

yearly = df.groupby("pub_year").agg(
    n=("video_id", "count"),
    median_perf=("performance_index", "median"),
    avg_gap_days=("gap_from_prev_days", "median"),
    total_revenue=("est_revenue_jpy", "sum"),
).reset_index()
print(yearly.to_string(index=False))


# ---- Interval bucket analysis --------------------------------------
print("\n" + "=" * 90)
print("前回投稿からの経過日数 vs パフォーマンス指数")
print("=" * 90)
df_with_gap = df.dropna(subset=["gap_from_prev_days"]).copy()
df_with_gap["gap_bin"] = pd.cut(df_with_gap["gap_from_prev_days"],
    bins=[0, 7, 14, 30, 60, 120, 365, 1000],
    labels=["1週以内","8-14日","15-30日","31-60日","61-120日","121-365日","365日超"])
g = df_with_gap.groupby("gap_bin", observed=True).agg(
    n=("video_id", "count"),
    median_perf=("performance_index", "median"),
    median_views_per_day=("views_per_day", "median"),
    median_rev_per_day=("rev_per_day", "median"),
).reset_index()
print(g.to_string(index=False))


# ---- 90-day rolling cadence vs performance --------------------------
print("\n" + "=" * 90)
print("過去 90 日の投稿本数 vs 当該動画パフォーマンス指数")
print("=" * 90)
df_with_cadence = df.dropna(subset=["uploads_prev_90d"]).copy()
df_with_cadence["cadence_bin"] = pd.cut(df_with_cadence["uploads_prev_90d"],
    bins=[-1, 0, 1, 2, 3, 5, 100],
    labels=["0本（ブランク）","1本","2本","3本","4-5本","6本以上"])
g2 = df_with_cadence.groupby("cadence_bin", observed=True).agg(
    n=("video_id", "count"),
    median_perf=("performance_index", "median"),
    median_views=("views", "median"),
).reset_index()
print(g2.to_string(index=False))


# ---- Spearman correlations -----------------------------------------
print("\n" + "=" * 90)
print("相関分析")
print("=" * 90)
sub = df.dropna(subset=["gap_from_prev_days"])
for col in ["gap_from_prev_days", "uploads_prev_90d", "uploads_prev_180d"]:
    rho = sub[[col, "performance_index"]].corr(method="spearman").iloc[0, 1]
    print(f"  {col:<28s} vs performance_index : ρ = {rho:+.2f}")


# ---- Active periods identification ----------------------------------
print("\n" + "=" * 90)
print("アクティブ期間 vs ブランク期間の識別")
print("=" * 90)
# Identify "long gaps" (>90 days)
df["is_long_gap"] = df["gap_from_prev_days"] > 90
long_gaps = df[df["is_long_gap"]][["video_id", "published_at",
    "gap_from_prev_days", "performance_index"]]
print(f"90 日超のブランク後の投稿 = {len(long_gaps)} 件")
print(long_gaps.to_string(index=False))


# ---- Save -----------------------------------------------------------
df.to_csv(OUT_DIR / "publishing_cadence.csv", index=False)
g.to_csv(OUT_DIR / "cadence_gap_buckets.csv", index=False)
g2.to_csv(OUT_DIR / "cadence_window_buckets.csv", index=False)


# ---- Plot -----------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Panel 1: Annual cadence + perf
ax = axes[0, 0]
ax2 = ax.twinx()
ax.bar(yearly["pub_year"].astype(str), yearly["n"],
    color="#1f77b4", edgecolor="black", linewidth=0.5, alpha=0.7,
    label="動画本数")
ax2.plot(yearly["pub_year"].astype(str), yearly["median_perf"],
    color="#d62728", marker="o", linewidth=2, label="中央パフォーマンス指数")
ax.set_xlabel("公開年")
ax.set_ylabel("年間動画数", color="#1f77b4")
ax2.set_ylabel("中央パフォーマンス指数", color="#d62728")
ax.set_title("年別投稿数とパフォーマンス推移")
ax.grid(True, alpha=0.3)
for i, row in yearly.iterrows():
    ax2.text(i, row["median_perf"], f"{row['median_perf']:.1f}",
            ha="center", va="bottom", fontsize=9, color="#d62728")

# Panel 2: gap interval bucket
ax = axes[0, 1]
ax.bar(g["gap_bin"].astype(str), g["median_perf"],
    color="#1f77b4", edgecolor="black", linewidth=0.5)
for i, row in g.iterrows():
    ax.text(i, row["median_perf"], f"n={row['n']}\n{row['median_perf']:.2f}",
        ha="center", va="bottom", fontsize=8, color="#444")
ax.axhline(1.0, color="black", linestyle="--", linewidth=1)
ax.set_xlabel("前回投稿からの経過日数")
ax.set_ylabel("中央パフォーマンス指数")
ax.set_title("投稿間隔別 パフォーマンス指数")
ax.grid(True, alpha=0.3, axis="y")
plt.setp(ax.get_xticklabels(), rotation=20, ha="right")

# Panel 3: 90-day window cadence
ax = axes[1, 0]
ax.bar(g2["cadence_bin"].astype(str), g2["median_perf"],
    color="#1f77b4", edgecolor="black", linewidth=0.5)
for i, row in g2.iterrows():
    ax.text(i, row["median_perf"], f"n={row['n']}\n{row['median_perf']:.2f}",
        ha="center", va="bottom", fontsize=8, color="#444")
ax.axhline(1.0, color="black", linestyle="--", linewidth=1)
ax.set_xlabel("過去 90 日の投稿本数（当該動画公開時点）")
ax.set_ylabel("中央パフォーマンス指数")
ax.set_title("90 日累積ペース vs パフォーマンス指数")
ax.grid(True, alpha=0.3, axis="y")
plt.setp(ax.get_xticklabels(), rotation=20, ha="right")

# Panel 4: timeline view
ax = axes[1, 1]
ax.scatter(df["published_at"], df["performance_index"],
    s=df["est_revenue_jpy"].fillna(0)/1500 + 30,
    c=df["performance_index"], cmap="RdYlGn", vmin=0, vmax=10,
    alpha=0.7, edgecolor="black", linewidth=0.5)
ax.axhline(1.0, color="black", linestyle="--", linewidth=1, alpha=0.5)
ax.set_xlabel("公開日")
ax.set_ylabel("パフォーマンス指数")
ax.set_title("時系列: 公開日 × パフォーマンス（バブル=収益）")
ax.grid(True, alpha=0.3)

plt.suptitle("投稿間隔・ペース最適化分析", fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "publishing_cadence.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'publishing_cadence.csv'}")
