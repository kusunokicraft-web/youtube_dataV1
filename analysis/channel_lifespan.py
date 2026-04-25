"""
Channel lifespan / future revenue projection.

Models:
  - Each existing video's daily revenue follows the channel-fit
    decay V'(t) ∝ age^(-0.21) (cumulative V(t) = c * age^0.79)
  - Projects each video's contribution forward 1, 3, 5, 10 years
  - Layers four scenarios:
      A. 完全停止 — no new releases (pure tail)
      B. 現状維持 — average historical pace continues
      C. V2 戦略 — placement fix + serial + new pair execution
      D. リスクシナリオ — talent retirement / algorithm shift
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

EXC = {"7FyovEYud1A", "cbEDMw-fPWc"}
df = an[(an["format"] == "Long") & (an["views"] > 0)].copy()
df = df[~df["video_id"].isin(EXC)].dropna(subset=["est_revenue_jpy"])

# Fit decay (from #6)
x_log = np.log(df["age_days"].values)
y_log = np.log(df["views"].clip(lower=1).values)
k, a_ = np.polyfit(x_log, y_log, 1)
c_global = np.exp(a_)
print(f"Decay model: views = {c_global:.1f} × age^{k:.2f}")
print(f"  daily views ∝ age^{k-1:.2f}")
print(f"  Per-day revenue follows the same decay shape")

# Estimate each video's "scale" parameter c_i so that
# c_i * age_now^k = current_views (i.e. scale to actual cumulative)
df["scale_c"] = df["views"] / (df["age_days"] ** k)
df["rev_per_view"] = df["est_revenue_jpy"] / df["views"]


def daily_revenue(scale_c: float, rpv: float, age: float) -> float:
    """Revenue per day at the given age, using the scale and per-view rate."""
    if age <= 0:
        return 0
    daily_views = scale_c * k * (age ** (k - 1))
    return daily_views * rpv


# ---- Scenario A: 完全停止 (no new releases) -------------------
print("\n" + "=" * 90)
print("シナリオ A: 完全停止（新作なし、既存 26 動画の長尾のみ）")
print("=" * 90)

horizons = [0, 90, 180, 365, 365*3, 365*5, 365*10]
print(f"{'経過':>10s} {'年/日':>8s} {'チャネル合計 ¥/日':>18s} {'年率換算':>15s}")
for d in horizons:
    total_per_day = 0
    for _, r in df.iterrows():
        future_age = r["age_days"] + d
        total_per_day += daily_revenue(r["scale_c"], r["rev_per_view"], future_age)
    annual = total_per_day * 365
    label = "現在" if d == 0 else f"{d/365:.1f}年後" if d >= 365 else f"{d}日後"
    print(f"{label:>10s} {d:>5d}日 ¥{total_per_day:>15,.0f}/日 ¥{annual:>13,.0f}/年")


# Cumulative future revenue (no new content)
print("\n累積将来収益（新作ゼロ前提）:")
for end in [1, 3, 5, 10, 20]:
    total_future = 0
    for _, r in df.iterrows():
        # ∫_age_now^(age_now + 365*end) c_i * k * t^(k-1) dt = c_i * t^k from age_now to (age_now + 365*end)
        a0 = r["age_days"]
        a1 = r["age_days"] + 365 * end
        future_views = r["scale_c"] * (a1**k - a0**k)
        total_future += future_views * r["rev_per_view"]
    print(f"  今後{end:>2d}年間の累計収益: ¥{total_future:>12,.0f}")


# ---- Scenario B: 現状維持 (1 video / 2 months at avg perf) -----
print("\n" + "=" * 90)
print("シナリオ B: 現状維持（年 6 本 × 平均的な動画品質）")
print("=" * 90)

# Average new-video parameters from 2024-2025 baseline
typical_views_2yr = df[df["age_days"].between(180, 730)]["views"].median()
typical_rpv = df[df["age_days"].between(180, 730)]["rev_per_view"].median()
print(f"  典型的な動画パラメータ (180-730日コホート):")
print(f"    視聴回数 (2 年想定): {typical_views_2yr:,.0f}")
print(f"    1 視聴あたり収益: ¥{typical_rpv:.2f}")


def project_with_new_releases(years: int, new_per_year: int, video_views_2yr: float, rpv: float) -> float:
    """Project total revenue over 'years' years with continuous new releases."""
    daily_views_new_at_age = lambda age: (
        video_views_2yr / (730 ** k) * k * (age ** (k - 1)) if age > 0 else 0
    )
    # For each future day, sum revenue from existing videos + all new ones released by that day
    total_revenue = 0
    interval = 365 / new_per_year  # days between releases
    end_day = years * 365
    # Existing tail: integrate
    for _, r in df.iterrows():
        a0 = r["age_days"]
        a1 = r["age_days"] + end_day
        future_views = r["scale_c"] * (a1**k - a0**k)
        total_revenue += future_views * r["rev_per_view"]
    # New releases: each video released at day τ contributes views from age 0 to age (end_day-τ)
    tau = 0
    while tau < end_day:
        age_at_end = end_day - tau
        new_video_total_views = video_views_2yr / (730 ** k) * (age_at_end ** k)
        total_revenue += new_video_total_views * rpv
        tau += interval
    return total_revenue


for end in [1, 3, 5, 10]:
    pace_6 = project_with_new_releases(end, 6, typical_views_2yr, typical_rpv)
    print(f"  今後{end:>2d}年間 (年 6 本ペース): ¥{pace_6:>12,.0f}")


# ---- Scenario C: V2 戦略 (1.5x revenue uplift on new + フレンとこ②) -----
print("\n" + "=" * 90)
print("シナリオ C: V2 戦略（新作の RPM 1.5x + フレンとこ② 1 本投入）")
print("=" * 90)

# V2: new videos use better placement (RPM up 30%) + 35-50min sweet spot
# + better titles → views up 15%
v2_views = typical_views_2yr * 1.15
v2_rpv = typical_rpv * 1.30  # placement-driven RPM uplift

# フレンとこ② contribution: estimated lifetime ~¥800k-1.2M (single contribution)
furen2_lifetime_5y = 1_000_000  # midpoint

for end in [1, 3, 5, 10]:
    base = project_with_new_releases(end, 6, v2_views, v2_rpv)
    # フレンとこ② is one big single shot during the period
    furen2 = min(furen2_lifetime_5y * (end/5), furen2_lifetime_5y * 1.5)
    total = base + furen2
    print(f"  今後{end:>2d}年間 (V2): ¥{total:>12,.0f}")


# ---- Scenario D: リスクシナリオ ---------------------------------
print("\n" + "=" * 90)
print("シナリオ D: リスクシナリオ（タレント引退・チャネル休止）")
print("=" * 90)

# If アンジュ retires or channel pauses publishing for X years
# Existing tail continues but no new uploads
# After 2-year pause, return likely impossible (algorithm would deprioritize)
print("D-1: 1 年間休止 → 再開（既存タール + 1 年遅れて再開）")
for end in [3, 5, 10]:
    # Existing tail
    total = 0
    for _, r in df.iterrows():
        a0 = r["age_days"]
        a1 = r["age_days"] + 365 * end
        future_views = r["scale_c"] * (a1**k - a0**k)
        total += future_views * r["rev_per_view"]
    # Resume after 1 year, half pace, lower performance
    if end > 1:
        resume_years = end - 1
        # Assume 50% recovery (algorithm penalty)
        resume_revenue = project_with_new_releases(resume_years, 4, typical_views_2yr * 0.5,
                                                     typical_rpv) - sum(
            r["scale_c"] * ((r["age_days"]+365*resume_years)**k - r["age_days"]**k) * r["rev_per_view"]
            for _, r in df.iterrows()
        )
        total += resume_revenue
    print(f"  今後{end:>2d}年間: ¥{total:>12,.0f}")

print("\nD-2: 完全終了（タレント引退・素材枯渇）")
for end in [3, 5, 10, 20]:
    total = 0
    for _, r in df.iterrows():
        a0 = r["age_days"]
        a1 = r["age_days"] + 365 * end
        future_views = r["scale_c"] * (a1**k - a0**k)
        total += future_views * r["rev_per_view"]
    print(f"  今後{end:>2d}年間 (新作ゼロ・既存だけ): ¥{total:>12,.0f}")


# ---- Half-life and decay timeline ---------------------------------
print("\n" + "=" * 90)
print("チャネル収益の半減期推定（新作ゼロ前提）")
print("=" * 90)
# Compute total daily revenue forward
days_grid = np.arange(0, 365*15, 30)
rev_curve = []
for d in days_grid:
    total = 0
    for _, r in df.iterrows():
        future_age = r["age_days"] + d
        total += daily_revenue(r["scale_c"], r["rev_per_view"], future_age)
    rev_curve.append(total)
rev_curve = np.array(rev_curve)
peak = rev_curve[0]
half = peak / 2
crossing = np.where(rev_curve <= half)[0]
if len(crossing) > 0:
    half_day = days_grid[crossing[0]]
    print(f"  現在の日次収益: ¥{peak:,.0f}/日")
    print(f"  半減 (¥{half:,.0f}/日 以下) になる経過日数: {half_day} 日 = {half_day/365:.1f} 年")
quarter = peak / 4
crossing_q = np.where(rev_curve <= quarter)[0]
if len(crossing_q) > 0:
    print(f"  4分の1 (¥{quarter:,.0f}/日) になる経過日数: {days_grid[crossing_q[0]]} 日 = {days_grid[crossing_q[0]]/365:.1f} 年")


# ---- Plot --------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Panel 1: daily revenue projection
ax = axes[0, 0]
ax.plot(days_grid/365, rev_curve, "-", color="#d62728", linewidth=2,
        label="新作ゼロ（既存26動画のみ）")
ax.axhline(peak/2, color="#7f7f7f", linestyle="--", label="現在の半分")
ax.axhline(peak/4, color="#7f7f7f", linestyle=":", label="現在の4分の1")
ax.set_xlabel("今後の経過年数")
ax.set_ylabel("チャネル合計 ¥/日")
ax.set_title("シナリオ A: 完全停止時の日次収益減衰")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# Panel 2: cumulative future revenue per scenario
ax = axes[0, 1]
years_grid = [1, 3, 5, 10, 20]
A_vals = []
for end in years_grid:
    total = 0
    for _, r in df.iterrows():
        a0 = r["age_days"]
        a1 = r["age_days"] + 365 * end
        future_views = r["scale_c"] * (a1**k - a0**k)
        total += future_views * r["rev_per_view"]
    A_vals.append(total)
B_vals = [project_with_new_releases(end, 6, typical_views_2yr, typical_rpv) for end in years_grid]
C_vals = []
for end in years_grid:
    base = project_with_new_releases(end, 6, v2_views, v2_rpv)
    furen2 = min(furen2_lifetime_5y * (end/5), furen2_lifetime_5y * 1.5)
    C_vals.append(base + furen2)
x = np.arange(len(years_grid))
width = 0.25
ax.bar(x - width, A_vals, width, label="A: 完全停止", color="#d62728")
ax.bar(x,         B_vals, width, label="B: 現状維持", color="#1f77b4")
ax.bar(x + width, C_vals, width, label="C: V2 戦略", color="#2ca02c")
ax.set_xticks(x)
ax.set_xticklabels([f"{y}年" for y in years_grid])
ax.set_xlabel("将来期間")
ax.set_ylabel("累積収益 (円)")
ax.set_title("シナリオ別 累積収益予測")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3, axis="y")

# Panel 3: per-video contribution ranking (top 10)
ax = axes[1, 0]
df_sorted = df.copy()
df_sorted["rev_5y_remaining"] = df_sorted.apply(
    lambda r: r["scale_c"] * ((r["age_days"]+365*5)**k - r["age_days"]**k) * r["rev_per_view"],
    axis=1)
top10 = df_sorted.nlargest(10, "rev_5y_remaining")
ax.barh(top10["video_id"], top10["rev_5y_remaining"],
        color="#1f77b4", edgecolor="black", linewidth=0.5)
for i, (_, r) in enumerate(top10.iterrows()):
    ax.text(r["rev_5y_remaining"], i, f"  ¥{r['rev_5y_remaining']:,.0f}",
            va="center", fontsize=8, color="#444")
ax.set_xlabel("今後 5 年の予測収益 (円)")
ax.set_title("既存動画の今後 5 年寄与 Top 10")
ax.invert_yaxis()
ax.grid(True, alpha=0.3, axis="x")

# Panel 4: cohort age distribution
ax = axes[1, 1]
cohorts = pd.cut(df["age_days"],
    bins=[0, 180, 365, 730, 1100, 5000],
    labels=["0-180日","180-365日","1-2年","2-3年","3年+"])
cohort_count = cohorts.value_counts().sort_index()
ax.bar(cohort_count.index.astype(str), cohort_count.values,
       color="#1f77b4", edgecolor="black", linewidth=0.5)
for i, v in enumerate(cohort_count.values):
    ax.text(i, v+0.2, str(v), ha="center", fontsize=10, color="#444")
ax.set_xlabel("動画の年代")
ax.set_ylabel("動画本数")
ax.set_title("動画在庫の年代分布")
ax.grid(True, alpha=0.3, axis="y")

plt.suptitle("チャネル寿命分析 — 既存資産の減衰と将来投影", fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "lifespan.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
