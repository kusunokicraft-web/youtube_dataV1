"""
Collab pair performance analysis.

Extracts Vtuber names mentioned in each video's title, identifies
the primary pair/trio (typically アンジュ + others), and ranks pairs
by performance. Identifies untapped pairs that appeared in some
content but never got a dedicated video.
"""

from pathlib import Path
import re
import sys
import itertools
from collections import Counter

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

# Curated Vtuber name dictionary (label -> regex pattern)
VTUBERS = {
    "アンジュ": r"アンジュ|カトリーナ",
    "フレン":   r"フレン|フレン・E|ルスタリオ",
    "戌亥とこ": r"戌亥|戍亥|とこ",  # both kanji variants
    "リゼ":     r"リゼ|ヘルエスタ|皇女",
    "栞葉るり": r"栞葉|るり",
    "ベル":     r"ベルモンド|バンデラス|ベルさん|ベル(?!ア)",
    "笹木":     r"笹木|笹ベル",
    "サロメ":   r"サロメ|壱百満天原",
    "竜胆":     r"竜胆|みこと様|みこアン",
    "鈴原るる": r"鈴原|るる(?!ス)",
    "早瀬走":   r"早瀬",
    "夢追":     r"夢追|夢星家|パパ",
    "星川":     r"星川|サラ",
    "イブラヒム": r"イブアン|イブラヒム",
    "マリン":   r"マリン|宝鐘|アンマリ",
    "ホロライブ": r"ホロライブ",
}


def extract_vtubers(title: str) -> set:
    t = str(title)
    found = set()
    for label, pat in VTUBERS.items():
        if re.search(pat, t):
            found.add(label)
    return found


def primary_pair(vtubers: set) -> tuple:
    """Pick the channel's typical 'X + アンジュ' or '2-3 person' pair signature."""
    vt = vtubers - {"ホロライブ"}
    if not vt:
        return ("(unknown)",)
    return tuple(sorted(vt))


# ---- Load and tag --------------------------------------------------
an = pd.read_csv(ANALYTICS, parse_dates=["published_at"])
asof = pd.Timestamp("2026-04-25")
an["age_days"] = (asof - an["published_at"]).dt.days.clip(lower=1)
an["views_per_day"] = an["views"] / an["age_days"]
an["rev_per_day"] = an["est_revenue_jpy"] / an["age_days"]

# Performance index (#6)
mask_long = an["format"] == "Long"
x_log = np.log(an.loc[mask_long, "age_days"].values)
y_log = np.log(an.loc[mask_long, "views"].clip(lower=1).values)
k, a_ = np.polyfit(x_log, y_log, 1)
c = np.exp(a_)
an["expected_views"] = c * (an["age_days"] ** k)
an["performance_index"] = an["views"] / an["expected_views"]

EXC = {"7FyovEYud1A", "cbEDMw-fPWc"}
df = an[(an["format"] == "Long") & (an["views"] > 0)].copy()
df = df[~df["video_id"].isin(EXC)]

df["vtubers"] = df["title"].map(extract_vtubers)
df["pair"] = df["vtubers"].map(primary_pair)
df["pair_label"] = df["pair"].map(lambda t: " × ".join(t))


# ---- Per-video tagging summary -------------------------------------
print("=" * 90)
print("各動画のVtuberタグ付け結果")
print("=" * 90)
disp = df[["video_id","title","pair_label","views","est_revenue_jpy"]].copy()
disp["title"] = disp["title"].str.slice(0, 35)
print(disp.sort_values("est_revenue_jpy", ascending=False).to_string(index=False))


# ---- Vtuber appearance frequency -----------------------------------
print("\n" + "=" * 90)
print("Vtuber出現頻度")
print("=" * 90)
all_vtubers = []
for s in df["vtubers"]:
    all_vtubers.extend(list(s))
vt_count = Counter(all_vtubers)
for vt, n in vt_count.most_common():
    matched = df[df["vtubers"].map(lambda s: vt in s)]
    total_rev = matched["est_revenue_jpy"].sum()
    median_perf = matched["performance_index"].median()
    print(f"  {vt:<12s}  {n:>3d} 本  総収益 ¥{total_rev:>10,.0f}  "
          f"中央perf指数 {median_perf:>5.2f}")


# ---- Pair performance ----------------------------------------------
print("\n" + "=" * 90)
print("ペア/グループ別 パフォーマンス")
print("=" * 90)
pair_stats = df.groupby("pair_label").agg(
    n=("video_id", "count"),
    median_perf_idx=("performance_index", "median"),
    median_views_per_day=("views_per_day", "median"),
    total_revenue=("est_revenue_jpy", "sum"),
    median_revenue=("est_revenue_jpy", "median"),
).reset_index().sort_values("total_revenue", ascending=False)
print(pair_stats.to_string(index=False))


# ---- Pair contribution to total revenue ---------------------------
print("\n" + "=" * 90)
print("ペア別収益寄与")
print("=" * 90)
total = pair_stats["total_revenue"].sum()
pair_stats["pct_of_total"] = (pair_stats["total_revenue"] / total * 100).round(1)
print(pair_stats[["pair_label","n","total_revenue","pct_of_total"]].to_string(index=False))


# ---- "アンジュ+X" 2-person pair specific -----------------------
print("\n" + "=" * 90)
print("「アンジュ + X」の2人ペア限定の比較")
print("=" * 90)
two_person = df[df["pair"].map(lambda t: len(t) == 2 and "アンジュ" in t)].copy()
two_person["partner"] = two_person["pair"].map(
    lambda t: [x for x in t if x != "アンジュ"][0])
partner_stats = two_person.groupby("partner").agg(
    n=("video_id","count"),
    median_perf_idx=("performance_index","median"),
    median_views=("views","median"),
    total_revenue=("est_revenue_jpy","sum"),
).reset_index().sort_values("total_revenue", ascending=False)
print(partner_stats.to_string(index=False))


# ---- Untapped pair candidates ---------------------------------------
print("\n" + "=" * 90)
print("未開拓ペア候補 (本データで言及あるが単独ペア動画なし)")
print("=" * 90)
# Vtubers that appear in 3+ person collabs but no dedicated 2-person pair
all_pairs = set()
for s in df["vtubers"]:
    if "アンジュ" in s:
        for partner in (s - {"アンジュ", "ホロライブ"}):
            all_pairs.add(partner)
solo_pairs = set(partner_stats["partner"].tolist())
untapped = all_pairs - solo_pairs
for partner in sorted(untapped):
    matched = df[df["vtubers"].map(lambda s: partner in s)]
    print(f"  {partner:<12s}  共演 {len(matched)} 本  "
          f"未だ「アンジュ × {partner}」単独ペア動画なし")


# ---- Save ----
df.to_csv(OUT_DIR / "collab_pair_analysis.csv", index=False)
pair_stats.to_csv(OUT_DIR / "collab_pair_stats.csv", index=False)
partner_stats.to_csv(OUT_DIR / "collab_partner_stats.csv", index=False)


# ---- Plot ----
fig, axes = plt.subplots(2, 2, figsize=(15, 11))

# Panel 1: pair total revenue (top 10)
ax = axes[0, 0]
top_pairs = pair_stats.head(10).copy()
ax.barh(top_pairs["pair_label"], top_pairs["total_revenue"],
        color="#1f77b4", edgecolor="black", linewidth=0.5)
for i, row in top_pairs.iterrows():
    pos = list(top_pairs.index).index(i)
    ax.text(row["total_revenue"], pos, f"  n={row['n']} / ¥{row['total_revenue']:,.0f}",
            va="center", fontsize=8, color="#444")
ax.set_xlabel("総収益 (円)")
ax.set_title("ペア/グループ別 総収益 Top 10")
ax.invert_yaxis()
ax.grid(True, alpha=0.3, axis="x")

# Panel 2: アンジュ + X partners
ax = axes[0, 1]
ps = partner_stats.copy()
ax.barh(ps["partner"], ps["total_revenue"],
        color="#2ca02c", edgecolor="black", linewidth=0.5)
for i, row in ps.iterrows():
    pos = list(ps.index).index(i)
    ax.text(row["total_revenue"], pos,
            f"  n={row['n']}, perf{row['median_perf_idx']:.2f}",
            va="center", fontsize=8, color="#444")
ax.set_xlabel("総収益 (円)")
ax.set_title("「アンジュ + X」ペアの相手別 総収益")
ax.invert_yaxis()
ax.grid(True, alpha=0.3, axis="x")

# Panel 3: Vtuber appearance frequency
ax = axes[1, 0]
vt_freq = pd.DataFrame(vt_count.most_common(), columns=["vtuber", "count"])
ax.barh(vt_freq["vtuber"], vt_freq["count"],
        color="#1f77b4", edgecolor="black", linewidth=0.5)
ax.set_xlabel("出演動画本数")
ax.set_title("Vtuber 出演頻度")
ax.invert_yaxis()
ax.grid(True, alpha=0.3, axis="x")

# Panel 4: pair perf vs n (bubble = revenue)
ax = axes[1, 1]
viz = pair_stats[pair_stats["n"] >= 1].copy()
ax.scatter(viz["n"], viz["median_perf_idx"],
           s=np.sqrt(viz["total_revenue"].fillna(0))/3,
           alpha=0.6, color="#1f77b4", edgecolor="black", linewidth=0.5)
for _, r in viz.iterrows():
    ax.annotate(r["pair_label"][:15], (r["n"], r["median_perf_idx"]),
                xytext=(3,3), textcoords="offset points",
                fontsize=7, color="#444")
ax.axhline(1.0, color="black", linestyle="--", linewidth=1, label="軌道どおり")
ax.set_xlabel("動画本数 (n)")
ax.set_ylabel("中央パフォーマンス指数")
ax.set_title("ペア別 制作本数 × パフォーマンス指数 (バブル=総収益)")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

plt.suptitle("コラボペア別パフォーマンス分析", fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "collab_pairs.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'collab_pair_analysis.csv'}")
print(f"Wrote: {OUT_DIR / 'collab_pair_stats.csv'}")
