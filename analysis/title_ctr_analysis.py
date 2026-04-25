"""
Title pattern × CTR analysis.

Extracts structural features from titles (length, brackets,
emoji, specific keywords, name mentions) and correlates each
with impression_ctr. Identifies high-CTR title patterns to
inform new-upload naming.
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
df = an[an["format"] == "Long"].copy()
df["title"] = df["title"].astype(str)
df["title_len"] = df["title"].str.len()


# ---- Feature extraction ---------------------------------------------
def has(pattern: str, t: str) -> bool:
    return bool(re.search(pattern, t))


def emoji_count(t: str) -> int:
    return len(re.findall(r"[\U0001F300-\U0001FAFF✀-➿☀-⛿]", t))


def bracket_count(t: str) -> int:
    return len(re.findall(r"【[^】]+】", t))


df["has_bracket"] = df["title"].map(lambda t: has(r"【[^】]+】", t))
df["bracket_count"] = df["title"].map(bracket_count)
df["has_warning_kw"] = df["title"].map(lambda t: has(r"注意|爆笑|緊急|ガチ照れ|ブチギレ|微グロ", t))
df["has_groke_warning"] = df["title"].map(lambda t: has(r"グロ注意", t))
df["has_dekiru"] = df["title"].map(lambda t: has(r"10分でわかる", t))
df["has_gekijo"] = df["title"].map(lambda t: has(r"劇場版", t))
df["has_total"] = df["title"].map(lambda t: has(r"総集編|総まとめ|まとめ", t))
df["has_first_collab"] = df["title"].map(lambda t: has(r"初コラボ|初配信", t))
df["has_teetee"] = df["title"].map(lambda t: has(r"てえてえ|てぇてぇ|てえてぇ", t))
df["has_gacha"] = df["title"].map(lambda t: has(r"ガチャ|爆速", t))
df["has_first_index"] = df["title"].map(lambda t: has(r"①|その１|その1", t))
df["has_second_index"] = df["title"].map(lambda t: has(r"②|その２|その2", t))
df["has_emoji"] = df["title"].map(lambda t: emoji_count(t) > 0)
df["emoji_count"] = df["title"].map(emoji_count)
df["has_number"] = df["title"].map(lambda t: bool(re.search(r"\d{2,}万|\d{2,}人|\d{3,}", t)))
df["has_punctuation_q"] = df["title"].map(lambda t: has(r"\?|？|!|！", t))


# ---- Per-feature CTR comparison -------------------------------------
features = [
    "has_bracket", "has_warning_kw", "has_groke_warning",
    "has_dekiru", "has_gekijo", "has_total",
    "has_first_collab", "has_teetee", "has_gacha",
    "has_first_index", "has_second_index",
    "has_emoji", "has_number", "has_punctuation_q",
]

print("=" * 78)
print("CTR by binary title feature (median ± IQR)")
print("=" * 78)
print(f"{'feature':<22s}  {'present (n, CTR)':<25s}  {'absent (n, CTR)':<25s}  {'Δpp':>6s}")
print("-" * 78)
results = []
for f in features:
    present = df[df[f]]["impression_ctr"].dropna()
    absent = df[~df[f]]["impression_ctr"].dropna()
    if len(present) < 2 or len(absent) < 2:
        continue
    p_med = present.median()
    a_med = absent.median()
    delta = p_med - a_med
    print(f"{f:<22s}  n={len(present):>2d}, CTR={p_med:5.2f}%        "
          f"n={len(absent):>2d}, CTR={a_med:5.2f}%        {delta:+5.2f}")
    results.append({
        "feature": f,
        "n_present": len(present),
        "n_absent": len(absent),
        "ctr_present_med": round(p_med, 2),
        "ctr_absent_med": round(a_med, 2),
        "delta_pp": round(delta, 2),
        "ctr_present_mean": round(present.mean(), 2),
        "ctr_absent_mean": round(absent.mean(), 2),
    })

result_df = pd.DataFrame(results).sort_values("delta_pp", ascending=False)
result_df.to_csv(OUT_DIR / "title_features.csv", index=False)


# ---- Correlations with continuous features --------------------------
print("\n" + "=" * 78)
print("Continuous feature correlations with CTR")
print("=" * 78)
for col in ["title_len", "bracket_count", "emoji_count"]:
    rho = df[[col, "impression_ctr"]].corr(method="spearman").iloc[0, 1]
    print(f"  {col:<20s}  Spearman ρ = {rho:+.2f}")


# ---- Top / bottom CTR videos ---------------------------------------
print("\n" + "=" * 78)
print("Top 5 CTR videos (impressions >= 100k for reliability)")
print("=" * 78)
sub = df[df["impressions"] >= 100_000].copy()
top = sub.nlargest(5, "impression_ctr")[["video_id", "title", "impression_ctr",
                                          "impressions"]]
top["title"] = top["title"].str.slice(0, 50)
print(top.to_string(index=False))

print("\nBottom 5 CTR videos (impressions >= 100k):")
bot = sub.nsmallest(5, "impression_ctr")[["video_id", "title", "impression_ctr",
                                           "impressions"]]
bot["title"] = bot["title"].str.slice(0, 50)
print(bot.to_string(index=False))


# ---- Plot -----------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(14, 9))

# Panel 1: feature-by-feature uplift bar chart
ax = axes[0, 0]
plot_df = result_df.copy()
plot_df["display"] = plot_df["feature"].str.replace("has_", "")
ax.barh(plot_df["display"], plot_df["delta_pp"],
        color=["#2ca02c" if d > 0 else "#d62728" for d in plot_df["delta_pp"]],
        edgecolor="black", linewidth=0.5)
ax.axvline(0, color="black", linewidth=0.7)
ax.set_xlabel("CTR の差分（pp）— 該当ありが何 pp 高いか")
ax.set_title("タイトル要素別の CTR 効果")
ax.grid(True, alpha=0.3, axis="x")
for i, (_, row) in enumerate(plot_df.iterrows()):
    ax.text(row["delta_pp"] + (0.05 if row["delta_pp"] > 0 else -0.05),
            i,
            f"n={row['n_present']}",
            va="center",
            ha="left" if row["delta_pp"] > 0 else "right",
            fontsize=7,
            color="#444")

# Panel 2: title length vs CTR
ax = axes[0, 1]
sub2 = df.dropna(subset=["impression_ctr", "title_len"])
ax.scatter(sub2["title_len"], sub2["impression_ctr"],
           s=60, alpha=0.7, color="#1f77b4", edgecolor="black", linewidth=0.5)
slope, intercept = np.polyfit(sub2["title_len"], sub2["impression_ctr"], 1)
xs = np.linspace(sub2["title_len"].min(), sub2["title_len"].max(), 100)
ax.plot(xs, slope*xs + intercept, "--", color="#7f7f7f")
rho = sub2[["title_len", "impression_ctr"]].corr(method="spearman").iloc[0, 1]
ax.set_xlabel("タイトル文字数")
ax.set_ylabel("インプレッション CTR (%)")
ax.set_title(f"タイトル長 vs CTR  ρ={rho:+.2f}")
ax.grid(True, alpha=0.3)

# Panel 3: CTR distribution overall
ax = axes[1, 0]
ctr = df["impression_ctr"].dropna()
ax.hist(ctr, bins=15, color="#1f77b4", edgecolor="black", alpha=0.85)
ax.axvline(ctr.median(), color="#d62728", linestyle="-",
           label=f"中央値 {ctr.median():.2f}%")
ax.axvline(ctr.mean(), color="#2ca02c", linestyle="--",
           label=f"平均 {ctr.mean():.2f}%")
ax.set_xlabel("インプレッション CTR (%)")
ax.set_ylabel("動画本数")
ax.set_title(f"チャネル全体の CTR 分布 (n={len(ctr)})")
ax.legend()
ax.grid(True, alpha=0.3)

# Panel 4: CTR vs impressions (saturation effect)
ax = axes[1, 1]
sub3 = df.dropna(subset=["impression_ctr", "impressions"])
sub3 = sub3[sub3["impressions"] > 0]
ax.scatter(sub3["impressions"], sub3["impression_ctr"],
           s=60, alpha=0.7, color="#1f77b4", edgecolor="black", linewidth=0.5)
ax.set_xscale("log")
rho = sub3[["impressions", "impression_ctr"]].corr(method="spearman").iloc[0, 1]
ax.set_xlabel("インプレッション数（対数軸）")
ax.set_ylabel("インプレッション CTR (%)")
ax.set_title(f"露出量 vs CTR  ρ={rho:+.2f}（露出が増えると CTR は薄まる）")
ax.grid(True, alpha=0.3, which="both")

plt.suptitle(f"タイトル × CTR 分析  (n={len(df)} ロングフォーム動画)",
             fontsize=12, y=1.0)
plt.tight_layout()
out_png = OUT_DIR / "title_ctr.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'title_features.csv'}")
