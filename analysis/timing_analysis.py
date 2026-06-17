"""
Publishing-timing analysis (day-of-week, month, year).

Tests whether the channel's revenue/views/subs gain depends on
when content is released. Sample is small (n=28 long-form), so
all conclusions are accompanied by sample-size flags.

Hour-of-day is NOT available — published_at is date-only.
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

# Performance index from #6
x_log = np.log(an["age_days"].values)
y_log = np.log(an["views"].clip(lower=1).values)
mask_long = an["format"] == "Long"
k, a_ = np.polyfit(x_log[mask_long], y_log[mask_long], 1)
c = np.exp(a_)
an["expected_views"] = c * (an["age_days"] ** k)
an["performance_index"] = an["views"] / an["expected_views"]

from _exclusions import EXCLUDED_VIDEO_IDS as EXC
df = an[(an["format"] == "Long") & (an["views"] > 0)].copy()
df = df[~df["video_id"].isin(EXC)]

# Extract calendar features
df["dow"] = df["published_at"].dt.dayofweek  # 0=Mon
df["dow_name"] = df["published_at"].dt.day_name()
df["dow_jp"] = df["dow"].map({0: "月", 1: "火", 2: "水", 3: "木",
                               4: "金", 5: "土", 6: "日"})
df["month"] = df["published_at"].dt.month
df["year"] = df["published_at"].dt.year
df["quarter"] = df["published_at"].dt.quarter
df["day_of_month"] = df["published_at"].dt.day


# ---- Day of week ----
print("=" * 80)
print("曜日別パフォーマンス (n={})".format(len(df)))
print("=" * 80)
dow_stats = df.groupby(["dow", "dow_jp"], observed=True).agg(
    n=("video_id", "count"),
    median_views_per_day=("views_per_day", "median"),
    median_rev_per_day=("rev_per_day", "median"),
    median_perf_idx=("performance_index", "median"),
    median_subs_gained=("subs_gained", "median"),
    total_revenue=("est_revenue_jpy", "sum"),
).reset_index().sort_values("dow")
print(dow_stats[["dow_jp", "n", "median_views_per_day", "median_rev_per_day",
                  "median_perf_idx", "median_subs_gained"]].to_string(index=False))


# ---- Weekday vs Weekend ----
print("\n" + "=" * 80)
print("平日 (月-金) vs 週末 (土日)")
print("=" * 80)
df["is_weekend"] = df["dow"] >= 5
wd = df.groupby("is_weekend").agg(
    n=("video_id", "count"),
    median_perf_idx=("performance_index", "median"),
    mean_perf_idx=("performance_index", "mean"),
    median_views_per_day=("views_per_day", "median"),
    median_rev_per_day=("rev_per_day", "median"),
).reset_index()
wd["label"] = wd["is_weekend"].map({False: "平日", True: "週末"})
print(wd[["label", "n", "median_perf_idx", "median_views_per_day", "median_rev_per_day"]].to_string(index=False))


# ---- Month ----
print("\n" + "=" * 80)
print("月別パフォーマンス（季節性）")
print("=" * 80)
month_stats = df.groupby("month").agg(
    n=("video_id", "count"),
    median_perf_idx=("performance_index", "median"),
    median_views_per_day=("views_per_day", "median"),
).reset_index()
month_stats["month_label"] = month_stats["month"].astype(str) + "月"
print(month_stats[["month_label", "n", "median_perf_idx", "median_views_per_day"]].to_string(index=False))


# ---- Year (channel growth phase) ----
print("\n" + "=" * 80)
print("年別パフォーマンス（チャネル成長期）")
print("=" * 80)
year_stats = df.groupby("year").agg(
    n=("video_id", "count"),
    total_revenue=("est_revenue_jpy", "sum"),
    median_views_per_day=("views_per_day", "median"),
    median_perf_idx=("performance_index", "median"),
).reset_index()
print(year_stats.to_string(index=False))


# ---- Day of month (early/mid/late) ----
print("\n" + "=" * 80)
print("月内タイミング (上旬/中旬/下旬)")
print("=" * 80)
df["dom_period"] = pd.cut(df["day_of_month"],
    bins=[0, 10, 20, 31], labels=["上旬(1-10)", "中旬(11-20)", "下旬(21-31)"])
dom = df.groupby("dom_period", observed=True).agg(
    n=("video_id", "count"),
    median_perf_idx=("performance_index", "median"),
    median_views_per_day=("views_per_day", "median"),
).reset_index()
print(dom.to_string(index=False))


# ---- Statistical caveats ----
print("\n" + "=" * 80)
print("注意点（小サンプル）")
print("=" * 80)
print(f"  曜日中央値の最小サンプル: {dow_stats['n'].min()} 本")
print(f"  曜日中央値の最大サンプル: {dow_stats['n'].max()} 本")
print(f"  → 各曜日 4-5 本の差は偶発的なばらつきの可能性が高い")


# ---- Save ----
df.to_csv(OUT_DIR / "timing_analysis.csv", index=False)
dow_stats.to_csv(OUT_DIR / "timing_dow.csv", index=False)


# ---- Plot ----
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Panel 1: dow median performance index
ax = axes[0, 0]
colors = ["#1f77b4" if not we else "#ff7f0e" for we in (dow_stats["dow"]>=5)]
ax.bar(dow_stats["dow_jp"], dow_stats["median_perf_idx"],
       color=colors, edgecolor="black", linewidth=0.5)
ax.axhline(1.0, color="black", linestyle="--", linewidth=1, label="軌道どおり")
for i, row in dow_stats.iterrows():
    ax.text(list(dow_stats["dow_jp"]).index(row["dow_jp"]),
            row["median_perf_idx"] + 0.1,
            f"n={row['n']}", ha="center", va="bottom",
            fontsize=9, color="#444")
ax.set_xlabel("公開曜日")
ax.set_ylabel("パフォーマンス指数 中央値")
ax.set_title("曜日別パフォーマンス（青=平日, 橙=週末）")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3, axis="y")

# Panel 2: dow median views_per_day
ax = axes[0, 1]
ax.bar(dow_stats["dow_jp"], dow_stats["median_views_per_day"],
       color=colors, edgecolor="black", linewidth=0.5)
for i, row in dow_stats.iterrows():
    ax.text(list(dow_stats["dow_jp"]).index(row["dow_jp"]),
            row["median_views_per_day"],
            f"{row['median_views_per_day']:.0f}",
            ha="center", va="bottom", fontsize=9, color="#444")
ax.set_xlabel("公開曜日")
ax.set_ylabel("中央値 視聴/日")
ax.set_title("曜日別 視聴/日 中央値")
ax.grid(True, alpha=0.3, axis="y")

# Panel 3: month
ax = axes[1, 0]
month_full = pd.DataFrame({"month": range(1, 13)})
month_full = month_full.merge(month_stats, on="month", how="left").fillna(0)
month_full["label"] = month_full["month"].astype(str) + "月"
bars = ax.bar(month_full["label"], month_full["median_perf_idx"],
              color="#1f77b4", edgecolor="black", linewidth=0.5)
for i, row in month_full.iterrows():
    if row["n"] > 0:
        ax.text(i, row["median_perf_idx"]+0.05, f"n={int(row['n'])}",
                ha="center", va="bottom", fontsize=8, color="#444")
ax.axhline(1.0, color="black", linestyle="--", linewidth=1)
ax.set_xlabel("公開月")
ax.set_ylabel("パフォーマンス指数 中央値")
ax.set_title("月別パフォーマンス（季節性）")
ax.grid(True, alpha=0.3, axis="y")

# Panel 4: year (channel growth)
ax = axes[1, 1]
ax.bar(year_stats["year"].astype(str), year_stats["total_revenue"],
       color="#1f77b4", edgecolor="black", linewidth=0.5)
for i, row in year_stats.iterrows():
    ax.text(i, row["total_revenue"]+10000,
            f"n={int(row['n'])}\n¥{row['total_revenue']:,.0f}",
            ha="center", va="bottom", fontsize=9, color="#444")
ax.set_xlabel("公開年")
ax.set_ylabel("年内に公開した動画の総収益 (円)")
ax.set_title("年別の制作リターン（チャネル成長期）")
ax.grid(True, alpha=0.3, axis="y")

plt.suptitle("公開タイミング分析 — 曜日・月・年", fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "timing.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'timing_analysis.csv'}")
