"""
Series ① vs ② performance comparison.

Identifies sequential video pairs (manually curated) and computes
the sequel decay ratio: how much does ② perform vs ①?

Outputs:
  - per-series comparison table
  - decay summary (median ratio for views, revenue, RPM)
  - release-interval analysis
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
an["views_per_day"] = an["views"] / an["age_days"]
an["rev_per_day"] = an["est_revenue_jpy"] / an["age_days"]


def get(vid: str) -> pd.Series:
    return an[an["video_id"] == vid].iloc[0]


# Manually curated series pairs (verified by title inspection)
SERIES = [
    {
        "name": "ベルアン捏造",
        "ids": [("①", "yeahBDJu-Xg"), ("②", "4isid3PNoA8")],
        "type": "direct_sequel",
    },
    {
        "name": "みこアン",
        "ids": [("①", "tHjMQ8sV3QE"), ("②", "bP_Vn19u6Y4")],
        "type": "direct_sequel",
    },
    {
        "name": "てぇてえ総集編 (アンジュ×サロメ)",
        "ids": [("①", "g5UgDFXpIYk"), ("②", "sPtG_pnU-xw")],
        "type": "direct_sequel",
    },
    {
        "name": "ガチャ累計 (アンジュ)",
        "ids": [("①30万", "8zzMPgZ6bC8"), ("②56万", "IfqMm5O2yKI")],
        "type": "concept_sequel",
    },
    {
        "name": "10分でわかる (再アップ事故)",
        "ids": [("正", "7Wp6dxj0J5o"), ("失敗", "7FyovEYud1A")],
        "type": "reupload_failure",
    },
]

print("=" * 95)
print("Series ① vs ② performance comparison")
print("=" * 95)

rows = []
for s in SERIES:
    name = s["name"]
    print(f"\n--- {name} ({s['type']}) ---")
    if len(s["ids"]) < 2:
        continue
    label1, vid1 = s["ids"][0]
    label2, vid2 = s["ids"][1]
    v1, v2 = get(vid1), get(vid2)
    interval = (v2["published_at"] - v1["published_at"]).days

    print(f"  {label1} ({vid1}) {v1['published_at'].date()}  "
          f"length={v1['length_sec']/60:5.1f}min")
    print(f"  {label2} ({vid2}) {v2['published_at'].date()}  "
          f"length={v2['length_sec']/60:5.1f}min  "
          f"(interval: {interval} days)")
    print(f"\n  {'metric':<22s} | {label1:>12s} | {label2:>12s} | {'ratio':>8s}")
    metrics = [
        ("views", "視聴回数"),
        ("views_per_day", "視聴/日"),
        ("est_revenue_jpy", "総収益"),
        ("rev_per_day", "収益/日"),
        ("rpm_jpy", "RPM"),
        ("subs_gained", "登録者獲得"),
        ("impressions", "インプレッション"),
        ("impression_ctr", "CTR (%)"),
        ("avg_view_pct", "平均視聴率 (%)"),
    ]
    for col, jp in metrics:
        v1_v = v1[col] if col in v1 else np.nan
        v2_v = v2[col] if col in v2 else np.nan
        if pd.isna(v1_v) or pd.isna(v2_v) or v1_v == 0:
            r = np.nan
        else:
            r = v2_v / v1_v
        v1_s = f"{v1_v:>12,.1f}" if pd.notna(v1_v) else "       n/a"
        v2_s = f"{v2_v:>12,.1f}" if pd.notna(v2_v) else "       n/a"
        r_s = f"{r:>7.2f}x" if pd.notna(r) else "      n/a"
        print(f"  {jp:<22s} | {v1_s} | {v2_s} | {r_s}")

    rows.append({
        "series": name,
        "type": s["type"],
        "interval_days": interval,
        "ratio_views": v2["views"] / v1["views"] if v1["views"] else np.nan,
        "ratio_views_per_day": v2["views_per_day"] / v1["views_per_day"] if v1["views_per_day"] else np.nan,
        "ratio_revenue": v2["est_revenue_jpy"] / v1["est_revenue_jpy"] if v1["est_revenue_jpy"] else np.nan,
        "ratio_rev_per_day": v2["rev_per_day"] / v1["rev_per_day"] if v1["rev_per_day"] else np.nan,
        "ratio_rpm": v2["rpm_jpy"] / v1["rpm_jpy"] if pd.notna(v1["rpm_jpy"]) and v1["rpm_jpy"] else np.nan,
        "ratio_subs": v2["subs_gained"] / v1["subs_gained"] if v1["subs_gained"] else np.nan,
        "ratio_ctr": v2["impression_ctr"] / v1["impression_ctr"] if pd.notna(v1["impression_ctr"]) and v1["impression_ctr"] else np.nan,
        "v1_revenue": v1["est_revenue_jpy"],
        "v2_revenue": v2["est_revenue_jpy"],
    })

df_summary = pd.DataFrame(rows)
df_summary.to_csv(OUT_DIR / "series_comparison.csv", index=False)

# Aggregate (excluding reupload_failure)
print("\n" + "=" * 95)
print("Sequel decay aggregate (direct + concept sequels, excluding reupload)")
print("=" * 95)
real = df_summary[df_summary["type"] != "reupload_failure"]
for col, jp in [
    ("ratio_views", "視聴回数 ②/①"),
    ("ratio_views_per_day", "視聴/日 ②/①"),
    ("ratio_revenue", "総収益 ②/①"),
    ("ratio_rev_per_day", "収益/日 ②/①"),
    ("ratio_rpm", "RPM ②/①"),
    ("ratio_subs", "登録者 ②/①"),
    ("ratio_ctr", "CTR ②/①"),
]:
    vals = real[col].dropna()
    if len(vals) == 0:
        continue
    print(f"  {jp:<22s}  median={vals.median():.2f}x  mean={vals.mean():.2f}x  "
          f"range={vals.min():.2f}〜{vals.max():.2f}x")


# ---- Plot -----------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Panel 1: side-by-side bars per series
ax = axes[0]
real_plot = real.copy().reset_index(drop=True)
x = np.arange(len(real_plot))
width = 0.35
ax.bar(x - width/2, real_plot["v1_revenue"], width, label="①", color="#1f77b4",
       edgecolor="black", linewidth=0.5)
ax.bar(x + width/2, real_plot["v2_revenue"], width, label="②", color="#ff7f0e",
       edgecolor="black", linewidth=0.5)
ax.set_xticks(x)
ax.set_xticklabels(real_plot["series"].str.slice(0, 20),
                   rotation=20, ha="right", fontsize=9)
ax.set_ylabel("総収益 (円)")
ax.set_title("シリーズ別: ① と ② の総収益比較")
ax.legend()
ax.grid(True, alpha=0.3, axis="y")
for i, row in real_plot.iterrows():
    if pd.notna(row["ratio_revenue"]):
        max_v = max(row["v1_revenue"], row["v2_revenue"]) * 1.05
        ax.text(i, max_v, f"②/① = {row['ratio_revenue']:.2f}x",
                ha="center", fontsize=8, color="#444")

# Panel 2: ratio scatter (rev/day vs interval days)
ax = axes[1]
ax.scatter(real["interval_days"], real["ratio_rev_per_day"],
           s=120, c=["#1f77b4" if t == "direct_sequel" else "#ff7f0e"
                    for t in real["type"]],
           edgecolor="black", linewidth=0.5, alpha=0.9)
for _, r in real.iterrows():
    ax.annotate(r["series"][:14], (r["interval_days"], r["ratio_rev_per_day"]),
                xytext=(5, 5), textcoords="offset points",
                fontsize=9, color="#444")
ax.axhline(1.0, color="#7f7f7f", linestyle="--", alpha=0.6,
           label="①と同じ収益水準")
ax.set_xlabel("①からの経過日数（②公開時）")
ax.set_ylabel("②の収益/日 ÷ ①の収益/日")
ax.set_title("公開間隔 vs 続編の収益効率（②/①）")
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#1f77b4",
           markersize=10, label="直接続編", markeredgecolor="black"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#ff7f0e",
           markersize=10, label="概念続編", markeredgecolor="black"),
]
ax.legend(handles=legend_elements + [Line2D([0], [0], color="#7f7f7f",
                                             linestyle="--", label="同水準")],
          loc="upper right", fontsize=8)
ax.grid(True, alpha=0.3)

plt.suptitle("シリーズ ① vs ② パフォーマンス分析", fontsize=12, y=1.02)
plt.tight_layout()
out_png = OUT_DIR / "series_comparison.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'series_comparison.csv'}")
