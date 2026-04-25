"""
Top vs Bottom performer comparison.

Filters out videos that were quickly removed/restricted after publication
(re-upload failures, duplicate-content videos with near-zero views) and
videos still in the early-discovery phase (< 180 days old). Then contrasts
top 5 vs bottom 5 by revenue across the same metrics used in the top-only
fingerprint analysis.
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
an["subs_per_1k"] = an["subs_gained"] / an["views"] * 1000
an["impressions_per_day"] = an["impressions"] / an["age_days"]


# ---- Apply exclusions ----------------------------------------------
EXCLUDED = {
    "7FyovEYud1A": "再アップ失敗（subs=-1, 925 views, 重複タイトル）",
    "cbEDMw-fPWc": "公開後に非公開化と推定（5 views / 337 日, 重複タイトル）",
}

df = an[(an["format"] == "Long") & (an["views"] > 0)].copy()
df = df[~df["video_id"].isin(EXCLUDED.keys())]

# Also require mature age and non-null revenue for fair comparison
mature = df[(df["age_days"] >= 180) & df["est_revenue_jpy"].notna()].copy()

print("=" * 100)
print("除外動画")
print("=" * 100)
for vid, reason in EXCLUDED.items():
    print(f"  {vid}: {reason}")

print(f"\n対象: 公開 180 日経過 & 収益データあり Long-form 動画 = {len(mature)} 本")
print(f"  (元の Long-form 28 本から、若い動画と異常値を除外)")


# ---- Top 5 and Bottom 5 ---------------------------------------------
top5 = mature.nlargest(5, "est_revenue_jpy").copy()
bot5 = mature.nsmallest(5, "est_revenue_jpy").copy()

print("\n" + "=" * 100)
print("Top 5 (収益)")
print("=" * 100)
disp = top5[["video_id", "title", "length_min", "age_days", "views",
             "est_revenue_jpy", "rpm_jpy", "impression_ctr", "avg_view_pct"]].copy()
disp["title"] = disp["title"].str.slice(0, 35)
print(disp.to_string(index=False))

print("\n" + "=" * 100)
print("Bottom 5 (収益)")
print("=" * 100)
disp = bot5[["video_id", "title", "length_min", "age_days", "views",
             "est_revenue_jpy", "rpm_jpy", "impression_ctr", "avg_view_pct"]].copy()
disp["title"] = disp["title"].str.slice(0, 35)
print(disp.to_string(index=False))


# ---- Side-by-side comparison ---------------------------------------
print("\n" + "=" * 100)
print("Top 5 中央値 vs Bottom 5 中央値 比較")
print("=" * 100)

metrics = [
    ("length_min", "動画長(分)"),
    ("age_days", "経過日数"),
    ("views_per_day", "視聴/日"),
    ("rev_per_day", "収益/日"),
    ("rpm_jpy", "RPM(円)"),
    ("impression_ctr", "CTR(%)"),
    ("avg_view_pct", "平均視聴率(%)"),
    ("avg_watch_sec", "平均視聴秒"),
    ("subs_per_1k", "登録/1k視聴"),
    ("endscreen_ctr", "終了画面CTR(%)"),
    ("impressions_per_day", "インプレッション/日"),
    ("impression_ctr", "再掲CTR(%)"),
]
seen = set()
unique_metrics = []
for col, jp in metrics:
    if col not in seen:
        unique_metrics.append((col, jp))
        seen.add(col)

print(f"\n{'metric':<22s} | {'top5':>14s} | {'bot5':>14s} | {'top/bot':>10s}")
print("-" * 80)
rows = []
for col, jp in unique_metrics:
    t = top5[col].median()
    b = bot5[col].median()
    if pd.isna(t) or pd.isna(b) or b == 0:
        ratio = np.nan
    else:
        ratio = t / b
    print(f"{jp:<22s} | {t:>14,.1f} | {b:>14,.1f} | "
          f"{(str(round(ratio,2))+'x') if pd.notna(ratio) else '   n/a':>10s}")
    rows.append({"metric": jp, "top5_median": t, "bot5_median": b,
                 "ratio_top_over_bot": ratio})

comp_df = pd.DataFrame(rows)
comp_df.to_csv(OUT_DIR / "top_vs_bottom.csv", index=False)


# ---- Identify the biggest divergence drivers ------------------------
print("\n" + "=" * 100)
print("最大の分岐要因 (Top/Bot 比率の絶対値順)")
print("=" * 100)
comp_df["log_ratio"] = comp_df["ratio_top_over_bot"].map(
    lambda r: np.log10(r) if pd.notna(r) and r > 0 else np.nan
)
comp_df_sorted = comp_df.dropna(subset=["log_ratio"]).copy()
comp_df_sorted["abs_log"] = comp_df_sorted["log_ratio"].abs()
comp_df_sorted = comp_df_sorted.sort_values("abs_log", ascending=False)
print(comp_df_sorted[["metric", "top5_median", "bot5_median", "ratio_top_over_bot"]].to_string(index=False))


# ---- Plot -----------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Panel 1: side-by-side bars (log scale for comparable visualization)
ax = axes[0]
plot_metrics = ["視聴/日", "収益/日", "インプレッション/日"]
plot_data = comp_df[comp_df["metric"].isin(plot_metrics)].copy()
x = np.arange(len(plot_data))
width = 0.35
ax.bar(x - width/2, plot_data["top5_median"], width, label="Top 5", color="#2ca02c",
       edgecolor="black", linewidth=0.5)
ax.bar(x + width/2, plot_data["bot5_median"], width, label="Bottom 5", color="#d62728",
       edgecolor="black", linewidth=0.5)
ax.set_xticks(x)
ax.set_xticklabels(plot_data["metric"], rotation=15, ha="right")
ax.set_yscale("log")
ax.set_ylabel("中央値（対数軸）")
ax.set_title("流量指標 Top 5 vs Bottom 5（対数軸）")
ax.legend()
ax.grid(True, alpha=0.3, axis="y")
for i, row in plot_data.reset_index().iterrows():
    ax.text(i, max(row["top5_median"], row["bot5_median"]) * 1.5,
            f"{row['ratio_top_over_bot']:.0f}x",
            ha="center", fontsize=10, color="#444", fontweight="bold")

# Panel 2: ratio bar chart
ax = axes[1]
quality_metrics = ["RPM(円)", "CTR(%)", "平均視聴率(%)", "登録/1k視聴", "終了画面CTR(%)", "動画長(分)"]
qd = comp_df[comp_df["metric"].isin(quality_metrics)].copy()
ax.barh(qd["metric"], qd["ratio_top_over_bot"],
        color=["#2ca02c" if r > 1 else "#d62728" for r in qd["ratio_top_over_bot"]],
        edgecolor="black", linewidth=0.5)
ax.axvline(1.0, color="black", linewidth=0.7, linestyle="--", label="同水準")
for i, row in qd.iterrows():
    pos = list(qd.index).index(i)
    ax.text(row["ratio_top_over_bot"] + 0.05, pos,
            f"{row['top5_median']:.1f} / {row['bot5_median']:.1f}",
            va="center", fontsize=8, color="#444")
ax.set_xlabel("Top 5 / Bottom 5 倍率")
ax.set_title("品質指標 Top vs Bottom 倍率")
ax.legend()
ax.grid(True, alpha=0.3, axis="x")

plt.suptitle(f"Top 5 vs Bottom 5 比較（成熟動画 n={len(mature)}, 異常値除外）",
             fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "top_vs_bottom.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'top_vs_bottom.csv'}")
