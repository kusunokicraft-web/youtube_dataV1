"""
Subscriber acquisition efficiency analysis.

Identifies which videos / content types best convert viewers into
channel subscribers (the long-term growth signal). Distinguishes
"growth videos" (high subs per view) from "monetization videos"
(high revenue per view) — different strategic uses.
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
an["subs_per_1k_views"] = an["subs_gained"] / an["views"] * 1000
an["rev_per_1k_views"] = an["est_revenue_jpy"] / an["views"] * 1000  # ≒ RPM


# Tag content type from title
def tag(title: str) -> list[str]:
    t = str(title)
    tags = []
    if re.search(r"ガチャ|爆速|累計", t):
        tags.append("ガチャ系")
    if re.search(r"てえてえ|てぇてぇ", t):
        tags.append("てえてえ")
    if "初コラボ" in t:
        tags.append("初コラボ")
    if re.search(r"総集編|総まとめ|劇場版", t):
        tags.append("総集編/劇場版")
    if "10分でわかる" in t:
        tags.append("10分でわかる")
    if re.search(r"注意|爆笑|ガチ照れ", t):
        tags.append("感情ワード")
    if "①" in t or "その１" in t or "その1" in t:
        tags.append("①マーカー")
    if "②" in t or "その２" in t or "その2" in t:
        tags.append("②マーカー")
    return tags


an["tags"] = an["title"].map(tag)
df = an[(an["format"] == "Long") & (an["views"] > 0)].copy()
df = df.dropna(subset=["subs_gained"])
df = df[df["subs_gained"] >= 0]  # exclude reupload negative case

# ---- Channel-level baseline ----------------------------------------
print("=" * 80)
print("Channel-level subscriber acquisition baseline")
print("=" * 80)
print(f"  Total subs gained (Long-form, n={len(df)})    : "
      f"{df['subs_gained'].sum():,.0f}")
print(f"  Total views                                    : "
      f"{df['views'].sum():,.0f}")
print(f"  Channel-wide subs per 1k views (weighted)      : "
      f"{df['subs_gained'].sum() / df['views'].sum() * 1000:.2f}")
print(f"  Per-video subs per 1k views (median)           : "
      f"{df['subs_per_1k_views'].median():.2f}")
print(f"  Per-video subs per 1k views (mean)             : "
      f"{df['subs_per_1k_views'].mean():.2f}")

# ---- Top / bottom subscriber-efficiency videos ---------------------
print("\n" + "=" * 80)
print("Top 10: subscriber efficiency (subs per 1k views, views>=10k)")
print("=" * 80)
sub = df[df["views"] >= 10_000].copy()
top = sub.nlargest(10, "subs_per_1k_views")[["video_id", "title", "views",
                                              "subs_gained", "subs_per_1k_views",
                                              "rpm_jpy"]]
top["title"] = top["title"].str.slice(0, 40)
print(top.to_string(index=False))

print("\n" + "=" * 80)
print("Bottom 10: subscriber efficiency")
print("=" * 80)
bot = sub.nsmallest(10, "subs_per_1k_views")[["video_id", "title", "views",
                                                "subs_gained", "subs_per_1k_views",
                                                "rpm_jpy"]]
bot["title"] = bot["title"].str.slice(0, 40)
print(bot.to_string(index=False))


# ---- Per-tag subscriber efficiency ---------------------------------
print("\n" + "=" * 80)
print("Subscriber efficiency by content tag")
print("=" * 80)
tag_rows = []
for tag_name in ["ガチャ系", "てえてえ", "初コラボ", "総集編/劇場版",
                 "10分でわかる", "感情ワード", "①マーカー", "②マーカー"]:
    matched = df[df["tags"].map(lambda lst: tag_name in lst)]
    if len(matched) == 0:
        continue
    tag_rows.append({
        "tag": tag_name,
        "n": len(matched),
        "med_subs_per_1k_views": round(matched["subs_per_1k_views"].median(), 2),
        "med_rpm_jpy": round(matched["rpm_jpy"].median(), 0)
            if matched["rpm_jpy"].notna().any() else np.nan,
        "total_subs": int(matched["subs_gained"].sum()),
        "total_views": int(matched["views"].sum()),
        "subs_per_1k_weighted": round(matched["subs_gained"].sum() / matched["views"].sum() * 1000, 2),
    })
tag_df = pd.DataFrame(tag_rows).sort_values("med_subs_per_1k_views", ascending=False)
print(tag_df.to_string(index=False))


# ---- Length bucket ----------------------------------------------------
print("\n" + "=" * 80)
print("Subscriber efficiency by video length")
print("=" * 80)
df["length_bin"] = pd.cut(df["length_min"], bins=[0,15,25,35,50,80],
                           labels=["<15分","15-25分","25-35分","35-50分","50-80分"])
len_df = df.groupby("length_bin", observed=True).agg(
    n=("video_id","count"),
    med_subs_per_1k=("subs_per_1k_views","median"),
    med_rpm=("rpm_jpy","median"),
    total_subs=("subs_gained","sum"),
    total_views=("views","sum"),
).reset_index()
len_df["subs_per_1k_weighted"] = (len_df["total_subs"] / len_df["total_views"] * 1000).round(2)
print(len_df.to_string(index=False))


# ---- Growth vs monetization quadrant -------------------------------
print("\n" + "=" * 80)
print("Growth vs Monetization quadrant (median splits)")
print("=" * 80)
med_subs = df["subs_per_1k_views"].median()
med_rev = df["rev_per_1k_views"].median()
df["quadrant"] = "?"
df.loc[(df["subs_per_1k_views"] >= med_subs) & (df["rev_per_1k_views"] >= med_rev), "quadrant"] = "Q1: 両得"
df.loc[(df["subs_per_1k_views"] >= med_subs) & (df["rev_per_1k_views"] < med_rev), "quadrant"] = "Q2: 成長型"
df.loc[(df["subs_per_1k_views"] < med_subs) & (df["rev_per_1k_views"] >= med_rev), "quadrant"] = "Q3: 収益型"
df.loc[(df["subs_per_1k_views"] < med_subs) & (df["rev_per_1k_views"] < med_rev), "quadrant"] = "Q4: 不振"
print(f"\n  median subs/1k = {med_subs:.2f},  median rev/1k = ¥{med_rev:.1f}")
print(df.groupby("quadrant").agg(n=("video_id","count")).to_string())

# Save
df.to_csv(OUT_DIR / "subs_efficiency.csv", index=False)
tag_df.to_csv(OUT_DIR / "subs_by_tag.csv", index=False)


# ---- Plot -----------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Panel 1: subs/1k vs rev/1k scatter (the two-axis growth-vs-revenue)
ax = axes[0, 0]
quadrant_colors = {
    "Q1: 両得": "#2ca02c",
    "Q2: 成長型": "#1f77b4",
    "Q3: 収益型": "#ff7f0e",
    "Q4: 不振": "#d62728",
}
for q, color in quadrant_colors.items():
    sub_q = df[df["quadrant"] == q]
    ax.scatter(sub_q["subs_per_1k_views"], sub_q["rev_per_1k_views"],
               s=80, alpha=0.85, color=color, edgecolor="black",
               linewidth=0.5, label=f"{q} (n={len(sub_q)})")
    for _, r in sub_q.iterrows():
        ax.annotate(r["video_id"], (r["subs_per_1k_views"], r["rev_per_1k_views"]),
                    xytext=(3, 3), textcoords="offset points",
                    fontsize=6, color="#444")
ax.axvline(med_subs, color="#7f7f7f", linestyle="--", alpha=0.5)
ax.axhline(med_rev, color="#7f7f7f", linestyle="--", alpha=0.5)
ax.set_xlabel("登録者獲得効率（人/1k視聴）")
ax.set_ylabel("収益効率（円/1k視聴 ≒ RPM）")
ax.set_title("成長 vs 収益マトリクス")
ax.legend(fontsize=8, loc="lower right")
ax.grid(True, alpha=0.3)

# Panel 2: by tag - bar chart
ax = axes[0, 1]
tag_plot = tag_df.copy()
ax.barh(tag_plot["tag"], tag_plot["med_subs_per_1k_views"],
        color="#1f77b4", edgecolor="black", linewidth=0.5)
ax.axvline(df["subs_per_1k_views"].median(), color="#d62728",
           linestyle="--", label=f"全体中央値 {df['subs_per_1k_views'].median():.2f}")
for i, row in tag_plot.iterrows():
    ax.text(row["med_subs_per_1k_views"] + 0.05, list(tag_plot.index).index(i),
            f"n={row['n']}", va="center", fontsize=8, color="#444")
ax.set_xlabel("登録者/1k視聴 中央値")
ax.set_title("コンテンツタイプ別 登録者獲得効率")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3, axis="x")

# Panel 3: by length bucket
ax = axes[1, 0]
ax.bar(len_df["length_bin"].astype(str), len_df["med_subs_per_1k"],
       color="#1f77b4", edgecolor="black", linewidth=0.5)
for i, row in len_df.iterrows():
    ax.text(i, row["med_subs_per_1k"] + 0.05,
            f"n={row['n']}\n¥{row['med_rpm']:.0f} RPM" if pd.notna(row['med_rpm']) else f"n={row['n']}",
            ha="center", va="bottom", fontsize=8, color="#444")
ax.set_xlabel("動画の長さ")
ax.set_ylabel("登録者/1k視聴 中央値")
ax.set_title("動画長別 登録者獲得効率")
ax.grid(True, alpha=0.3, axis="y")

# Panel 4: distribution of subs_per_1k
ax = axes[1, 1]
vals = df["subs_per_1k_views"].dropna()
ax.hist(vals, bins=15, color="#1f77b4", edgecolor="black", alpha=0.85)
ax.axvline(vals.median(), color="#d62728", linestyle="-",
           label=f"中央値 {vals.median():.2f}")
ax.axvline(vals.mean(), color="#2ca02c", linestyle="--",
           label=f"平均 {vals.mean():.2f}")
ax.set_xlabel("登録者/1k視聴")
ax.set_ylabel("動画本数")
ax.set_title(f"登録者獲得効率の分布 (n={len(vals)})")
ax.legend()
ax.grid(True, alpha=0.3)

plt.suptitle(f"登録者獲得効率分析 — チャネル成長の要因", fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "subs_efficiency.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'subs_efficiency.csv'}")
print(f"Wrote: {OUT_DIR / 'subs_by_tag.csv'}")
