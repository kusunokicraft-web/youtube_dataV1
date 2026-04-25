"""
Video lifecycle curve analysis.

Cross-sectional fit of cumulative-views vs age to estimate the
channel's decay shape. Used to:
  - characterize how view rate declines with age
  - identify early-warning underperformers (new videos below the
    expected trajectory at their age)
  - project 1-year/5-year cumulative views for new releases
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

EXC = {"7FyovEYud1A", "cbEDMw-fPWc"}
df = an[(an["format"] == "Long") & (an["views"] > 0)].copy()
df = df[~df["video_id"].isin(EXC)]


# ---- Fit cumulative-views vs age power law -------------------------
# log(views) = a + k * log(age) -> views = exp(a) * age^k
# views/day at age T = c*k*T^(k-1)
print("=" * 90)
print("動画ライフサイクル曲線フィット (Long-form n={})".format(len(df)))
print("=" * 90)

x_log = np.log(df["age_days"].values)
y_log = np.log(df["views"].values)
k, a = np.polyfit(x_log, y_log, 1)
c = np.exp(a)
print(f"  累積視聴フィット: views = {c:.1f} × age^{k:.2f}")
print(f"  R² (logスケール): "
      f"{1 - ((y_log - (a + k*x_log))**2).sum() / ((y_log - y_log.mean())**2).sum():.2f}")

# Decay implied
print(f"\n  累積指数 k = {k:.2f}")
if k < 1:
    # views/day = c*k*T^(k-1) — declining
    print(f"  → views/日 は age に対して減衰: dV/dT ∝ T^{k-1:.2f}")
    half_age_factor = (0.5)**(1/(k-1)) if k != 1 else None
    if half_age_factor:
        print(f"  → views/日 が半減するまで: 元の age を {half_age_factor:.2f} 倍した時点")
elif k > 1:
    print(f"  → 累積が加速成長 (異常、要確認)")


def expected_views(age_days: float) -> float:
    return c * (age_days ** k)


def expected_views_per_day(age_days: float) -> float:
    return c * k * (age_days ** (k - 1))


# ---- Per-video performance index --------------------------------
df["expected_views"] = df["age_days"].map(expected_views)
df["performance_index"] = df["views"] / df["expected_views"]
df["performance_pct"] = (df["performance_index"] - 1) * 100


# ---- Cohort analysis ---------------------------------------------
print("\n" + "=" * 90)
print("年代コホート別 視聴/日 分布")
print("=" * 90)
df["age_cohort"] = pd.cut(df["age_days"],
    bins=[0, 30, 90, 180, 365, 730, 10000],
    labels=["0-30日", "30-90日", "90-180日", "180-365日", "365-730日", "730日+"])
g = df.groupby("age_cohort", observed=True).agg(
    n=("video_id", "count"),
    median_views_per_day=("views_per_day", "median"),
    median_views_total=("views", "median"),
    median_age=("age_days", "median"),
).reset_index()
print(g.to_string(index=False))


# ---- "Half-life" estimation --------------------------------------
print("\n" + "=" * 90)
print("実効半減期推定（views/日 中央値が peak の半分以下になる経過日数）")
print("=" * 90)
# Peak views/day from earliest cohort
peak_vpd = df[df["age_days"] < 30]["views_per_day"].median()
# Find when median views/day drops to peak/2
half_threshold = peak_vpd / 2
print(f"  ピーク views/日 (0-30日): {peak_vpd:.1f}")
print(f"  半減閾値 (peak/2): {half_threshold:.1f}")
for _, row in g.iterrows():
    crossed = "✓" if row["median_views_per_day"] < half_threshold else " "
    print(f"  {row['age_cohort']:<14s} : {row['median_views_per_day']:>7.1f} views/日  {crossed}")


# ---- Early warning: underperforming new videos ------------------
print("\n" + "=" * 90)
print("早期警告: 公開後 180 日以内で軌道を下回る動画")
print("=" * 90)
young = df[df["age_days"] < 180].copy()
young = young.sort_values("age_days")
disp = young[["video_id", "title", "age_days", "views", "expected_views",
              "performance_index", "views_per_day", "est_revenue_jpy"]].copy()
disp["title"] = disp["title"].str.slice(0, 35)
disp["expected_views"] = disp["expected_views"].astype(int)
disp["performance_index"] = disp["performance_index"].round(2)
print(disp.to_string(index=False))


# ---- Mature video performance index ranking --------------------
print("\n" + "=" * 90)
print("成熟動画 (>=180日) のパフォーマンス指数 Top/Bottom")
print("=" * 90)
mature = df[df["age_days"] >= 180].copy().sort_values("performance_index", ascending=False)
disp = mature[["video_id", "title", "age_days", "views", "performance_index",
               "est_revenue_jpy"]].head(8).copy()
disp["title"] = disp["title"].str.slice(0, 35)
disp["performance_index"] = disp["performance_index"].round(2)
print("Top 5:")
print(disp.head(5).to_string(index=False))
print("\nBottom 5:")
disp = mature[["video_id", "title", "age_days", "views", "performance_index",
               "est_revenue_jpy"]].tail(5).copy()
disp["title"] = disp["title"].str.slice(0, 35)
disp["performance_index"] = disp["performance_index"].round(2)
print(disp.to_string(index=False))


# ---- Project 1y / 5y cumulative views from current new videos ---
print("\n" + "=" * 90)
print("新作の生涯予測 (公開後 180 日未満の動画)")
print("=" * 90)
print(f"{'video_id':<14s} {'age':>4s} {'now':>10s} {'1年後予測':>12s} {'5年後予測':>14s}")
for _, r in young.iterrows():
    if r["age_days"] >= 180: continue
    # If it tracks median trajectory: V(T) = V_now * (T/age_now)^k
    age_now = r["age_days"]
    v_now = r["views"]
    # Use the video's own performance_index to scale
    pi = r["performance_index"]
    v_1y = c * pi * (365 ** k)
    v_5y = c * pi * (1825 ** k)
    print(f"{r['video_id']:<14s} {age_now:>4.0f}日 {v_now:>10,.0f} "
          f"{v_1y:>12,.0f} {v_5y:>14,.0f}")


# ---- Save ---------------------------------------------------------
df.to_csv(OUT_DIR / "lifecycle_analysis.csv", index=False)


# ---- Plot ---------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Panel 1: cumulative views vs age (log-log) with fit
ax = axes[0, 0]
ax.scatter(df["age_days"], df["views"], s=80, alpha=0.7, color="#1f77b4",
           edgecolor="black", linewidth=0.5)
xs = np.logspace(np.log10(df["age_days"].min()), np.log10(df["age_days"].max()), 100)
ax.plot(xs, c * xs**k, "-", color="#d62728", linewidth=2, label=f"フィット曲線\nviews = {c:.0f} × age^{k:.2f}")
for _, r in df.iterrows():
    ax.annotate(r["video_id"], (r["age_days"], r["views"]),
                xytext=(3, 3), textcoords="offset points", fontsize=6, color="#444")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("公開からの経過日数（対数軸）")
ax.set_ylabel("累積視聴回数（対数軸）")
ax.set_title("累積視聴 vs 経過日数（チャネル全体の成長曲線）")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3, which="both")

# Panel 2: views_per_day vs age (log scale, declining)
ax = axes[0, 1]
ax.scatter(df["age_days"], df["views_per_day"], s=80, alpha=0.7,
           color="#1f77b4", edgecolor="black", linewidth=0.5)
xs = np.logspace(np.log10(df["age_days"].min()), np.log10(df["age_days"].max()), 100)
ax.plot(xs, c * k * xs**(k-1), "-", color="#d62728", linewidth=2,
        label=f"理論曲線 (微分) ∝ age^{k-1:.2f}")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("公開からの経過日数（対数軸）")
ax.set_ylabel("視聴/日（対数軸）")
ax.set_title("視聴/日 の経過日数による減衰")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3, which="both")

# Panel 3: performance index distribution
ax = axes[1, 0]
df_sorted = df.sort_values("performance_index")
colors = ["#d62728" if pi < 1 else "#2ca02c" for pi in df_sorted["performance_index"]]
ax.barh(range(len(df_sorted)), df_sorted["performance_index"],
        color=colors, edgecolor="black", linewidth=0.5)
ax.axvline(1.0, color="black", linestyle="--", linewidth=1, label="軌道どおり")
ax.set_yticks(range(len(df_sorted)))
ax.set_yticklabels(df_sorted["video_id"], fontsize=7)
ax.set_xlabel("パフォーマンス指数（実績 / 軌道予測）")
ax.set_title("動画別パフォーマンス指数（年代を補正後）")
ax.legend(fontsize=9, loc="lower right")
ax.grid(True, alpha=0.3, axis="x")

# Panel 4: cohort medians bar
ax = axes[1, 1]
g_plot = g.copy()
ax.bar(g_plot["age_cohort"].astype(str), g_plot["median_views_per_day"],
       color="#1f77b4", edgecolor="black", linewidth=0.5)
for i, row in g_plot.iterrows():
    ax.text(i, row["median_views_per_day"],
            f"n={row['n']}\n{row['median_views_per_day']:.0f}/日",
            ha="center", va="bottom", fontsize=9, color="#444")
ax.set_xlabel("年代コホート")
ax.set_ylabel("中央値 視聴/日")
ax.set_title("年代別 視聴/日 中央値（横断的減衰）")
ax.grid(True, alpha=0.3, axis="y")

plt.suptitle("動画ライフサイクル分析 — 減衰特性と早期警告", fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "lifecycle.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'lifecycle_analysis.csv'}")
