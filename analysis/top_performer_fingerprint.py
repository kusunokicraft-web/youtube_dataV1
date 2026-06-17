"""
Top performer reverse-engineering.

For the top revenue / view videos, compares each metric against
channel median to identify the distinctive "fingerprint" of
winning content. Then validates by checking whether other videos
sharing those traits also tend to win.
"""

from pathlib import Path
import re
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


# Filter long-form videos for fair comparison
df = an[(an["format"] == "Long") & (an["views"] > 0)].copy()

# Take top 5 by total revenue
top5 = df.nlargest(5, "est_revenue_jpy").copy()
print("=" * 100)
print("Top 5 videos by total revenue")
print("=" * 100)
disp_cols = ["video_id", "title", "length_min", "views", "est_revenue_jpy",
             "rpm_jpy", "impression_ctr", "avg_view_pct", "subs_per_1k"]
disp = top5[disp_cols].copy()
disp["title"] = disp["title"].str.slice(0, 35)
print(disp.to_string(index=False))


# ---- Compare top 5 against channel median (z-score in robust units) -
print("\n" + "=" * 100)
print("Top 5 vs channel median — distinctive metrics")
print("=" * 100)

metrics = [
    ("length_min", "動画長(分)"),
    ("avg_view_pct", "平均視聴率(%)"),
    ("avg_watch_sec", "平均視聴秒数"),
    ("impression_ctr", "インプレッションCTR(%)"),
    ("rpm_jpy", "RPM(円)"),
    ("subs_per_1k", "登録/1k視聴"),
    ("endscreen_ctr", "終了画面CTR(%)"),
    ("impressions_per_day", "インプレッション/日"),
    ("views_per_day", "視聴/日"),
    ("rev_per_day", "収益/日"),
]

print(f"\n{'metric':<22s} | {'channel':<10s}",
      end="")
for _, r in top5.iterrows():
    print(f" | {r['video_id'][:11]:>11s}", end="")
print()
print("-" * 100)

z_data = []
for col, jp in metrics:
    ch_med = df[col].median()
    ch_q25 = df[col].quantile(0.25)
    ch_q75 = df[col].quantile(0.75)
    iqr = ch_q75 - ch_q25 if ch_q75 > ch_q25 else 1
    print(f"{jp:<22s} | {ch_med:>10,.1f}", end="")
    row_z = {"metric": jp}
    for _, r in top5.iterrows():
        val = r[col]
        z = (val - ch_med) / iqr if pd.notna(val) else np.nan
        row_z[r["video_id"]] = z
        marker = "↑↑" if z > 1 else "↑" if z > 0.5 else "↓↓" if z < -1 else "↓" if z < -0.5 else " "
        if pd.isna(val):
            print(f" |       n/a   ", end="")
        else:
            print(f" | {val:>9,.1f}{marker}", end="")
    print()
    z_data.append(row_z)
z_df = pd.DataFrame(z_data)


# ---- Common "winning" patterns ----
print("\n" + "=" * 100)
print("Common patterns: what makes top 5 distinctive (median z >= +0.5)")
print("=" * 100)
for col, jp in metrics:
    ch_med = df[col].median()
    ch_q25 = df[col].quantile(0.25)
    ch_q75 = df[col].quantile(0.75)
    iqr = ch_q75 - ch_q25 if ch_q75 > ch_q25 else 1
    z_vals = [(r[col] - ch_med) / iqr for _, r in top5.iterrows() if pd.notna(r[col])]
    if not z_vals:
        continue
    med_z = np.median(z_vals)
    if abs(med_z) < 0.5:
        continue
    direction = "高い" if med_z > 0 else "低い"
    print(f"  {jp:<22s} : 中央 z = {med_z:+.2f} ({direction})  "
          f"トップ5中央値 = {np.median([r[col] for _, r in top5.iterrows() if pd.notna(r[col])]):,.1f}, "
          f"チャネル中央値 = {ch_med:,.1f}")


# ---- Specific deep-dive on bv2iwq17LVY (top 1) ---
print("\n" + "=" * 100)
print("ディープダイブ: bv2iwq17LVY (フレンとこ①, ¥775k = 全 Long-form 収益の 27%)")
print("=" * 100)
b = top5.iloc[0]
print(f"  公開日: {b['published_at'].date()} ({b['age_days']} 日経過)")
print(f"  動画長: {b['length_min']:.1f} 分（チャネル中央 {df['length_min'].median():.1f} 分）")
print(f"  視聴回数: {b['views']:,.0f}（チャネル中央 {df['views'].median():,.0f}）")
print(f"  推定収益: ¥{b['est_revenue_jpy']:,.0f}（チャネル中央 ¥{df['est_revenue_jpy'].median():,.0f}）")
print(f"  視聴/日 : {b['views_per_day']:,.1f}（チャネル中央 {df['views_per_day'].median():,.1f}）")
print(f"  収益/日 : ¥{b['rev_per_day']:,.1f}")
print(f"  RPM     : ¥{b['rpm_jpy']:.0f}（チャネル中央 ¥{df['rpm_jpy'].median():.0f}）")
print(f"  CTR     : {b['impression_ctr']:.2f}%（チャネル中央 {df['impression_ctr'].median():.2f}%）")
print(f"  平均視聴率: {b['avg_view_pct']:.1f}%（チャネル中央 {df['avg_view_pct'].median():.1f}%）")
print(f"  登録/1k : {b['subs_per_1k']:.2f}（チャネル中央 {df['subs_per_1k'].median():.2f}）")
print(f"  インプレッション: {b['impressions']:,.0f}（チャネル中央 {df['impressions'].median():,.0f}）")
print(f"  終了画面CTR: {b['endscreen_ctr']:.2f}%")


# ---- Validation: do videos sharing the "winning fingerprint" tend to win? ---
print("\n" + "=" * 100)
print("検証: 「勝つ要素」を持つ他の動画も実際に勝っているか？")
print("=" * 100)

# Define winning traits based on what was distinctive
def has_winning_traits(row):
    score = 0
    if row["length_min"] >= 45: score += 1  # long format
    if row["impressions_per_day"] >= df["impressions_per_day"].quantile(0.6): score += 1
    if pd.notna(row["impression_ctr"]) and row["impression_ctr"] >= 3.5: score += 1
    if pd.notna(row["subs_per_1k"]) and row["subs_per_1k"] >= 1.0: score += 1
    return score


df["winning_score"] = df.apply(has_winning_traits, axis=1)
print(df.groupby("winning_score").agg(
    n=("video_id", "count"),
    median_views=("views", "median"),
    median_revenue=("est_revenue_jpy", "median"),
).round(0).to_string())


# ---- Save ----
top5.to_csv(OUT_DIR / "top_performers.csv", index=False)
z_df.to_csv(OUT_DIR / "top_performers_z.csv", index=False)


# ---- Plot: radar chart-like comparison -----------------------------
fig, axes = plt.subplots(1, 2, figsize=(15, 6))

# Panel 1: heatmap of z-scores
ax = axes[0]
metric_labels = [m[1] for m in metrics]
top_ids = top5["video_id"].tolist()
heat_data = []
for col, jp in metrics:
    ch_med = df[col].median()
    ch_q25 = df[col].quantile(0.25)
    ch_q75 = df[col].quantile(0.75)
    iqr = ch_q75 - ch_q25 if ch_q75 > ch_q25 else 1
    row = []
    for _, r in top5.iterrows():
        val = r[col]
        if pd.isna(val):
            row.append(np.nan)
        else:
            row.append((val - ch_med) / iqr)
    heat_data.append(row)
heat = np.array(heat_data)
heat_clipped = np.clip(heat, -3, 3)
im = ax.imshow(heat_clipped, cmap="RdBu_r", aspect="auto", vmin=-3, vmax=3)
ax.set_xticks(range(len(top_ids)))
ax.set_xticklabels(top_ids, rotation=15, ha="right", fontsize=9)
ax.set_yticks(range(len(metric_labels)))
ax.set_yticklabels(metric_labels, fontsize=9)
ax.set_title("Top 5 動画の指標 z-score（チャネル中央比 / 単位: IQR）")
for i in range(len(metric_labels)):
    for j in range(len(top_ids)):
        if not np.isnan(heat[i, j]):
            ax.text(j, i, f"{heat[i, j]:+.1f}", ha="center", va="center",
                    fontsize=8,
                    color="white" if abs(heat_clipped[i, j]) > 1.5 else "black")
plt.colorbar(im, ax=ax, label="z-score (IQR units)")

# Panel 2: validation - winning_score vs revenue
ax = axes[1]
import numpy as np
score_buckets = df.groupby("winning_score").agg(
    n=("video_id", "count"),
    median_revenue=("est_revenue_jpy", "median"),
    median_views=("views", "median"),
).reset_index()
ax.bar(score_buckets["winning_score"].astype(str), score_buckets["median_revenue"],
       color="#1f77b4", edgecolor="black", linewidth=0.5)
for i, row in score_buckets.iterrows():
    ax.text(i, row["median_revenue"], f"n={row['n']}\n¥{row['median_revenue']:,.0f}",
            ha="center", va="bottom", fontsize=9, color="#444")
ax.set_xlabel("勝ち要素のスコア (0=なし, 4=全部)")
ax.set_ylabel("中央値収益 (円)")
ax.set_title("勝ち要素スコア別の中央収益（仮説検証）")
ax.grid(True, alpha=0.3, axis="y")

plt.suptitle(f"Top パフォーマー リバースエンジニアリング", fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "top_performers.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'top_performers.csv'}")
