"""
Premium revenue analysis.

Decomposes channel revenue into Premium vs ad streams and looks
at how Premium engagement varies by content type, length, and
audience profile. Premium revenue is a hidden 'subscriber-loyalty'
signal that doesn't show up in standard ad metrics.
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

from _exclusions import EXCLUDED_VIDEO_IDS as EXC
df = an[(an["format"] == "Long") & (an["views"] > 0)].copy()
df = df[~df["video_id"].isin(EXC)]
df = df.dropna(subset=["premium_jpy", "premium_views", "est_revenue_jpy"])

df["premium_views_share"] = df["premium_views"] / df["views"] * 100
df["premium_rev_share"] = df["premium_jpy"] / df["est_revenue_jpy"] * 100
df["ad_rev_share"] = (df["est_revenue_jpy"] - df["premium_jpy"]) / df["est_revenue_jpy"] * 100
# Per-Premium-view earning rate
df["jpy_per_premium_view"] = df["premium_jpy"] / df["premium_views"]
# Per-non-Premium-view ad earning rate
df["non_premium_views"] = df["views"] - df["premium_views"]
df["jpy_per_ad_view"] = (df["est_revenue_jpy"] - df["premium_jpy"]) / df["non_premium_views"]


# ---- Channel totals -------------------------------------------------
print("=" * 90)
print("チャネル全体 Premium 収益サマリー (Long-form n={})".format(len(df)))
print("=" * 90)
total_views = df["views"].sum()
total_premium_views = df["premium_views"].sum()
total_premium_rev = df["premium_jpy"].sum()
total_est_rev = df["est_revenue_jpy"].sum()
total_premium_hours = df["premium_watch_hours"].sum()
total_watch_hours = df["watch_hours"].sum()

print(f"  総視聴回数         : {total_views:>14,.0f}")
print(f"  うち Premium 視聴   : {total_premium_views:>14,.0f}  "
      f"({total_premium_views/total_views*100:.1f}%)")
print()
print(f"  総推定収益         : ¥{total_est_rev:>13,.0f}")
print(f"  うち Premium 収益   : ¥{total_premium_rev:>13,.0f}  "
      f"({total_premium_rev/total_est_rev*100:.1f}%)")
print(f"  うち 広告収益       : ¥{total_est_rev-total_premium_rev:>13,.0f}  "
      f"({(total_est_rev-total_premium_rev)/total_est_rev*100:.1f}%)")
print()
print(f"  総再生時間 (時間)   : {total_watch_hours:>14,.0f}")
print(f"  うち Premium 再生時間: {total_premium_hours:>14,.0f}  "
      f"({total_premium_hours/total_watch_hours*100:.1f}%)")
print()
print(f"  Premium 1視聴あたり収益: ¥{total_premium_rev/total_premium_views:.2f}")
print(f"  非Premium 1視聴あたり広告収益: "
      f"¥{(total_est_rev-total_premium_rev)/(total_views-total_premium_views):.2f}")


# ---- Per-video distribution ----------------------------------------
print("\n" + "=" * 90)
print("動画別 Premium 視聴シェア・収益シェア 分布")
print("=" * 90)
print(f"  Premium 視聴シェア (中央値): {df['premium_views_share'].median():.1f}%  "
      f"(範囲 {df['premium_views_share'].min():.1f}-{df['premium_views_share'].max():.1f}%)")
print(f"  Premium 収益シェア (中央値): {df['premium_rev_share'].median():.1f}%  "
      f"(範囲 {df['premium_rev_share'].min():.1f}-{df['premium_rev_share'].max():.1f}%)")


# ---- Top videos by Premium dependency ------------------------------
print("\n" + "=" * 90)
print("Premium 依存度の高い動画 Top 7 (収益のうち Premium が占める割合)")
print("=" * 90)
top_dep = df.nlargest(7, "premium_rev_share")[["video_id","title","length_min",
    "views","premium_views","premium_views_share","premium_rev_share","est_revenue_jpy"]]
top_dep["title"] = top_dep["title"].str.slice(0,35)
print(top_dep.to_string(index=False))

print("\n" + "=" * 90)
print("Premium 依存度の低い動画 Bottom 5")
print("=" * 90)
bot_dep = df.nsmallest(5, "premium_rev_share")[["video_id","title","length_min",
    "views","premium_views","premium_views_share","premium_rev_share","est_revenue_jpy"]]
bot_dep["title"] = bot_dep["title"].str.slice(0,35)
print(bot_dep.to_string(index=False))


# ---- By length bucket ----------------------------------------------
print("\n" + "=" * 90)
print("動画長別 Premium 指標")
print("=" * 90)
df["length_bin"] = pd.cut(df["length_min"], bins=[0,15,25,35,50,80],
    labels=["<15分","15-25分","25-35分","35-50分","50-80分"])
g = df.groupby("length_bin", observed=True).agg(
    n=("video_id","count"),
    med_premium_views_share=("premium_views_share","median"),
    med_premium_rev_share=("premium_rev_share","median"),
    total_premium_rev=("premium_jpy","sum"),
    total_views=("views","sum"),
    total_premium_views=("premium_views","sum"),
).reset_index()
g["weighted_premium_views_share"] = (g["total_premium_views"]/g["total_views"]*100).round(1)
print(g.to_string(index=False))


# ---- Tag-based -----------------------------------------------------
def tag(t):
    t = str(t)
    tags = []
    if re.search(r"ガチャ|爆速|累計", t): tags.append("ガチャ系")
    if re.search(r"てえてえ|てぇてぇ", t): tags.append("てえてえ")
    if "初コラボ" in t: tags.append("初コラボ")
    if re.search(r"総集編|総まとめ|劇場版", t): tags.append("総集編/劇場版")
    if "①" in t: tags.append("①マーカー")
    if "②" in t: tags.append("②マーカー")
    return tags
df["tags"] = df["title"].map(tag)

print("\n" + "=" * 90)
print("コンテンツタイプ別 Premium 視聴シェア")
print("=" * 90)
for t in ["①マーカー","②マーカー","てえてえ","初コラボ","総集編/劇場版","ガチャ系"]:
    matched = df[df["tags"].map(lambda lst: t in lst)]
    if len(matched) == 0: continue
    weighted = matched["premium_views"].sum() / matched["views"].sum() * 100
    print(f"  {t:<14s}  n={len(matched):>2d}  "
          f"Premium視聴シェア (加重) {weighted:.1f}%  "
          f"中央 {matched['premium_views_share'].median():.1f}%  "
          f"Premium収益 ¥{matched['premium_jpy'].sum():>10,.0f}")


# ---- Correlation with audience characteristics ----------------------
print("\n" + "=" * 90)
print("Premium 視聴シェアの相関")
print("=" * 90)
df["subs_per_1k"] = df["subs_gained"]/df["views"]*1000
for col in ["length_min","avg_view_pct","avg_watch_sec","subs_per_1k","views","est_revenue_jpy"]:
    rho = df[["premium_views_share",col]].corr(method="spearman").iloc[0,1]
    print(f"  Premium視聴シェア vs {col:<22s}  ρ = {rho:+.2f}")


# ---- Save ---
df.to_csv(OUT_DIR / "premium_analysis.csv", index=False)
g.to_csv(OUT_DIR / "premium_by_length.csv", index=False)


# ---- Plot ---
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Panel 1: revenue split (channel-level)
ax = axes[0, 0]
labels = ["広告 (¥%.0fk)" % ((total_est_rev-total_premium_rev)/1000),
         "Premium (¥%.0fk)" % (total_premium_rev/1000)]
sizes = [total_est_rev-total_premium_rev, total_premium_rev]
colors_p = ["#1f77b4", "#ff7f0e"]
ax.pie(sizes, labels=labels, colors=colors_p, autopct="%1.1f%%",
       startangle=90, textprops={"fontsize":11})
ax.set_title("チャネル収益: 広告 vs Premium")

# Panel 2: per-video Premium share scatter
ax = axes[0, 1]
ax.scatter(df["length_min"], df["premium_views_share"],
           s=df["views"]/3000, alpha=0.6, color="#ff7f0e",
           edgecolor="black", linewidth=0.5)
for _, r in df.iterrows():
    ax.annotate(r["video_id"], (r["length_min"], r["premium_views_share"]),
                xytext=(3,3), textcoords="offset points",
                fontsize=6, color="#444")
ax.set_xlabel("動画の長さ (分)")
ax.set_ylabel("Premium 視聴シェア (%)")
ax.set_title("動画長 vs Premium 視聴シェア (バブル=視聴回数)")
ax.grid(True, alpha=0.3)

# Panel 3: by length bucket
ax = axes[1, 0]
ax.bar(g["length_bin"].astype(str), g["weighted_premium_views_share"],
       color="#ff7f0e", edgecolor="black", linewidth=0.5)
for i, row in g.iterrows():
    ax.text(i, row["weighted_premium_views_share"]+0.5,
            f"n={row['n']}\n¥{row['total_premium_rev']:,.0f}",
            ha="center", va="bottom", fontsize=9, color="#444")
ax.set_xlabel("動画の長さ")
ax.set_ylabel("Premium 視聴シェア (加重平均, %)")
ax.set_title("動画長別 Premium 視聴の集中度")
ax.grid(True, alpha=0.3, axis="y")

# Panel 4: rate per Premium view vs rate per ad view
ax = axes[1, 1]
mature = df[df["age_days"]>=180].copy()
ax.scatter(mature["jpy_per_ad_view"], mature["jpy_per_premium_view"],
           s=80, alpha=0.7, color="#1f77b4", edgecolor="black", linewidth=0.5)
ax.plot([0,1.5],[0,1.5], "--", color="#7f7f7f", alpha=0.5, label="同水準")
for _, r in mature.iterrows():
    ax.annotate(r["video_id"], (r["jpy_per_ad_view"], r["jpy_per_premium_view"]),
                xytext=(3,3), textcoords="offset points",
                fontsize=6, color="#444")
ax.set_xlabel("¥ / 非Premium視聴 (広告)")
ax.set_ylabel("¥ / Premium視聴")
ax.set_title("単価比較: 広告視聴 vs Premium視聴 (成熟動画)")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

plt.suptitle("Premium 収益分析 — 隠れたファンロイヤルティ指標", fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "premium.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'premium_analysis.csv'}")
