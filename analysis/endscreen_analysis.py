"""
End-screen engagement analysis.

End-screen CTR is YouTube's signal for "session continuation" — viewers who
clicked through to the next video extend their session. This is heavily
weighted by the recommendation algorithm but underused by most creators.

Tests whether the channel is leaving end-screen value on the table:
  - distribution of end-screen CTR
  - which content types convert best to next-video clicks
  - estimated total clicks lost vs the channel's best performers
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

EXC = {"7FyovEYud1A", "cbEDMw-fPWc"}
df = an[(an["format"] == "Long") & (an["views"] > 0) & (an["age_days"] >= 180)].copy()
df = df[~df["video_id"].isin(EXC)]
df = df.dropna(subset=["endscreen_ctr", "endscreen_impressions",
                       "endscreen_clicks"])

# Tag content type
def tag(t):
    t = str(t)
    tags = []
    if re.search(r"ガチャ|爆速|累計", t): tags.append("ガチャ系")
    if re.search(r"てえてえ|てぇてぇ", t): tags.append("てえてえ")
    if "初コラボ" in t: tags.append("初コラボ")
    if re.search(r"総集編|総まとめ|劇場版", t): tags.append("総集編/劇場版")
    if "10分でわかる" in t: tags.append("10分でわかる")
    if "①" in t or "その１" in t: tags.append("①マーカー")
    if "②" in t or "その２" in t: tags.append("②マーカー")
    return tags
df["tags"] = df["title"].map(tag)

# ---- Channel baseline -----------------------------------------------
print("=" * 90)
print("End-screen 指標 チャネルベースライン")
print("=" * 90)
print(f"  対象: 公開 180 日経過 Long-form n = {len(df)}")
print(f"  終了画面 CTR 中央値    : {df['endscreen_ctr'].median():.2f}%")
print(f"  終了画面 CTR 平均      : {df['endscreen_ctr'].mean():.2f}%")
print(f"  終了画面 CTR 範囲      : {df['endscreen_ctr'].min():.2f}% 〜 {df['endscreen_ctr'].max():.2f}%")
print(f"  チャネル合計 終了画面クリック: {df['endscreen_clicks'].sum():,.0f} クリック")
print(f"  チャネル合計 終了画面表示  : {df['endscreen_impressions'].sum():,.0f}")


# ---- Top / bottom by end-screen CTR --------------------------------
print("\n" + "=" * 90)
print("終了画面 CTR Top 7 (表示 >= 1k)")
print("=" * 90)
sub = df[df["endscreen_impressions"] >= 1000].copy()
top = sub.nlargest(7, "endscreen_ctr")[["video_id","title","length_min",
    "endscreen_impressions","endscreen_clicks","endscreen_ctr","views","est_revenue_jpy"]]
top["title"] = top["title"].str.slice(0,35)
print(top.to_string(index=False))

print("\n" + "=" * 90)
print("終了画面 CTR Bottom 7 (表示 >= 1k)")
print("=" * 90)
bot = sub.nsmallest(7, "endscreen_ctr")[["video_id","title","length_min",
    "endscreen_impressions","endscreen_clicks","endscreen_ctr","views","est_revenue_jpy"]]
bot["title"] = bot["title"].str.slice(0,35)
print(bot.to_string(index=False))


# ---- By video length ------------------------------------------------
print("\n" + "=" * 90)
print("動画長別 終了画面 CTR")
print("=" * 90)
df["length_bin"] = pd.cut(df["length_min"], bins=[0,15,25,35,50,80],
    labels=["<15分","15-25分","25-35分","35-50分","50-80分"])
g = df.groupby("length_bin", observed=True).agg(
    n=("video_id","count"),
    med_endscreen_ctr=("endscreen_ctr","median"),
    total_clicks=("endscreen_clicks","sum"),
    total_impressions=("endscreen_impressions","sum"),
).reset_index()
g["weighted_ctr"] = (g["total_clicks"]/g["total_impressions"]*100).round(2)
print(g.to_string(index=False))


# ---- By content tag -------------------------------------------------
print("\n" + "=" * 90)
print("コンテンツタイプ別 終了画面 CTR")
print("=" * 90)
tag_rows = []
for t in ["ガチャ系","てえてえ","初コラボ","総集編/劇場版","10分でわかる","①マーカー","②マーカー"]:
    matched = df[df["tags"].map(lambda lst: t in lst)]
    if len(matched) == 0: continue
    tag_rows.append({
        "tag": t, "n": len(matched),
        "med_endscreen_ctr": round(matched["endscreen_ctr"].median(),2),
        "total_clicks": int(matched["endscreen_clicks"].sum()),
        "total_impressions": int(matched["endscreen_impressions"].sum()),
    })
tag_df = pd.DataFrame(tag_rows)
tag_df["weighted_ctr"] = (tag_df["total_clicks"]/tag_df["total_impressions"]*100).round(2)
tag_df = tag_df.sort_values("med_endscreen_ctr", ascending=False)
print(tag_df.to_string(index=False))


# ---- End-screen vs revenue, end-screen vs subs ----------------------
print("\n" + "=" * 90)
print("終了画面 CTR と他指標の相関")
print("=" * 90)
for col in ["views","est_revenue_jpy","subs_gained","avg_view_pct","length_min"]:
    rho = df[["endscreen_ctr",col]].corr(method="spearman").iloc[0,1]
    print(f"  endscreen_ctr vs {col:<18s} : Spearman ρ = {rho:+.2f}")


# ---- Lost-clicks estimation -----------------------------------------
print("\n" + "=" * 90)
print("「機会損失クリック」推定 (CTR を Top10 動画水準に上げた場合)")
print("=" * 90)
benchmark = sub.nlargest(10, "endscreen_ctr")["endscreen_ctr"].median()
print(f"  ベンチマーク CTR (Top 10 中央値): {benchmark:.2f}%")
df["potential_clicks"] = df["endscreen_impressions"] * benchmark / 100
df["lost_clicks"] = (df["potential_clicks"] - df["endscreen_clicks"]).clip(lower=0)
total_lost = df["lost_clicks"].sum()
total_actual = df["endscreen_clicks"].sum()
print(f"  実クリック合計  : {total_actual:,.0f}")
print(f"  ベンチマーク合計: {df['potential_clicks'].sum():,.0f}")
print(f"  機会損失クリック : {total_lost:,.0f}  (現状の {total_lost/total_actual*100:.0f}% 増加余地)")
print()
print("最大の機会損失動画 Top 7:")
loss = df.sort_values("lost_clicks", ascending=False).head(7)[
    ["video_id","title","length_min","endscreen_ctr","endscreen_impressions",
     "endscreen_clicks","potential_clicks","lost_clicks","views"]
].copy()
loss["title"] = loss["title"].str.slice(0,30)
print(loss.to_string(index=False))


# ---- Save -----------------------------------------------------------
df.to_csv(OUT_DIR / "endscreen_analysis.csv", index=False)
tag_df.to_csv(OUT_DIR / "endscreen_by_tag.csv", index=False)


# ---- Plot -----------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Panel 1: distribution
ax = axes[0,0]
vals = df["endscreen_ctr"].dropna()
ax.hist(vals, bins=10, color="#1f77b4", edgecolor="black", alpha=0.85)
ax.axvline(vals.median(), color="#d62728", linestyle="-",
    label=f"中央値 {vals.median():.2f}%")
ax.axvline(2.0, color="#2ca02c", linestyle="--", label="一般良好水準 2%")
ax.set_xlabel("終了画面 CTR (%)")
ax.set_ylabel("動画本数")
ax.set_title(f"終了画面 CTR の分布 (n={len(vals)})")
ax.legend()
ax.grid(True, alpha=0.3)

# Panel 2: by length
ax = axes[0,1]
bars = ax.bar(g["length_bin"].astype(str), g["weighted_ctr"],
    color="#1f77b4", edgecolor="black", linewidth=0.5)
for i, row in g.iterrows():
    ax.text(i, row["weighted_ctr"]+0.05,
        f"n={row['n']}\n{row['weighted_ctr']:.2f}%",
        ha="center", va="bottom", fontsize=9, color="#444")
ax.set_xlabel("動画の長さ")
ax.set_ylabel("終了画面 CTR (加重平均, %)")
ax.set_title("動画長別 終了画面 CTR")
ax.grid(True, alpha=0.3, axis="y")

# Panel 3: by tag
ax = axes[1,0]
tag_plot = tag_df.copy()
ax.barh(tag_plot["tag"], tag_plot["weighted_ctr"],
    color="#1f77b4", edgecolor="black", linewidth=0.5)
ax.axvline(df["endscreen_ctr"].median(), color="#d62728", linestyle="--",
    label=f"全体中央値 {df['endscreen_ctr'].median():.2f}%")
for i, row in tag_plot.iterrows():
    pos = list(tag_plot.index).index(i)
    ax.text(row["weighted_ctr"]+0.05, pos, f"n={row['n']}",
        va="center", fontsize=8, color="#444")
ax.set_xlabel("終了画面 CTR (加重平均, %)")
ax.set_title("コンテンツタイプ別 終了画面 CTR")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3, axis="x")

# Panel 4: scatter end-screen CTR vs length, sized by views
ax = axes[1,1]
ax.scatter(df["length_min"], df["endscreen_ctr"],
    s=df["views"]/3000, alpha=0.6, color="#1f77b4", edgecolor="black", linewidth=0.5)
for _, r in df.iterrows():
    ax.annotate(r["video_id"], (r["length_min"], r["endscreen_ctr"]),
        xytext=(3,3), textcoords="offset points", fontsize=6, color="#444")
ax.set_xlabel("動画の長さ (分)")
ax.set_ylabel("終了画面 CTR (%)")
ax.set_title("動画長 vs 終了画面 CTR (バブル = 視聴回数)")
ax.grid(True, alpha=0.3)

plt.suptitle("終了画面エンゲージメント分析 — セッション継続のレバー", fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "endscreen.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'endscreen_analysis.csv'}")
print(f"Wrote: {OUT_DIR / 'endscreen_by_tag.csv'}")
