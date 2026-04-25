"""
Ad-slot gap analysis.

For each video computes:
  - pre-roll-to-first-slot gap (= position_sec of first slot)
  - inter-slot gaps (consecutive slots)
  - last-slot-to-end gap
  - whether each gap falls inside the avg watch window

Aggregates:
  - distribution of inter-slot gaps across the channel
  - sub-30s gaps (YouTube min violation)
  - very wide gaps (> 10min) where mid-roll inventory is wasted
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BREAKS = ROOT / "data" / "ad_slots" / "breaks.csv"
ANALYTICS = ROOT / "analysis" / "report" / "cleaned.csv"
OUT_DIR = ROOT / "analysis" / "report"

# ---- Load -----------------------------------------------------------
b = pd.read_csv(BREAKS)
a = pd.read_csv(ANALYTICS)
b = b.merge(a[["video_id", "title", "length_sec", "avg_watch_sec",
               "ad_impressions", "monetized_playbacks", "rpm_jpy",
               "est_revenue_jpy"]],
            on="video_id")
b = b.sort_values(["video_id", "position_sec"]).reset_index(drop=True)

# ---- Compute per-slot gaps ------------------------------------------
records = []
for vid, g in b.groupby("video_id"):
    g = g.sort_values("position_sec").reset_index(drop=True)
    length = g["length_sec"].iloc[0]
    avg_watch = g["avg_watch_sec"].iloc[0]
    positions = g["position_sec"].tolist()

    pre_gap = positions[0]  # 0 -> first slot
    end_gap = length - positions[-1]
    inter = [positions[i+1] - positions[i] for i in range(len(positions)-1)]

    for i, p in enumerate(positions):
        prev_gap = pre_gap if i == 0 else positions[i] - positions[i-1]
        next_gap = end_gap if i == len(positions)-1 else positions[i+1] - positions[i]
        records.append({
            "video_id": vid,
            "break_index": i + 1,
            "position_sec": p,
            "position_hms": g["position_hms"].iloc[i],
            "gap_before_sec": prev_gap,
            "gap_after_sec": next_gap,
            "is_first": i == 0,
            "is_last": i == len(positions) - 1,
            "pos_pct": p / length,
            "in_avg_watch": p <= avg_watch,
        })

slots = pd.DataFrame(records)

# ---- Per-video summary ----------------------------------------------
def summarize(g: pd.DataFrame) -> pd.Series:
    inter = g.loc[~g["is_first"], "gap_before_sec"]
    return pd.Series({
        "video_id": g["video_id"].iloc[0],
        "n_slots": len(g),
        "pre_gap_sec": g.loc[g["is_first"], "gap_before_sec"].iloc[0],
        "end_gap_sec": g.loc[g["is_last"], "gap_after_sec"].iloc[0],
        "min_inter_sec": inter.min() if len(inter) else np.nan,
        "median_inter_sec": inter.median() if len(inter) else np.nan,
        "max_inter_sec": inter.max() if len(inter) else np.nan,
        "n_sub30s": (inter < 30).sum() if len(inter) else 0,
        "n_short_lt2min": (inter < 120).sum() if len(inter) else 0,
        "n_wide_gt10min": (inter > 600).sum() if len(inter) else 0,
    })

per_video = (
    slots.groupby("video_id", group_keys=False)[slots.columns.tolist()]
    .apply(summarize)
    .reset_index(drop=True)
    .merge(a[["video_id", "title", "length_sec", "avg_watch_sec",
              "rpm_jpy", "est_revenue_jpy"]], on="video_id")
)
per_video["length_min"] = per_video["length_sec"] / 60
per_video["avg_watch_min"] = per_video["avg_watch_sec"] / 60
per_video["pre_gap_min"] = per_video["pre_gap_sec"] / 60
per_video["end_gap_min"] = per_video["end_gap_sec"] / 60
per_video["median_inter_min"] = per_video["median_inter_sec"] / 60
per_video["max_inter_min"] = per_video["max_inter_sec"] / 60
per_video = per_video.sort_values("est_revenue_jpy", ascending=False)
per_video.to_csv(OUT_DIR / "slot_gaps_per_video.csv", index=False)

# ---- Channel distribution ------------------------------------------
inter_all = slots.loc[~slots["is_first"], "gap_before_sec"]

print("=" * 70)
print("Inter-slot gap distribution (all 65 inter-slot gaps from 19 videos)")
print("=" * 70)
print(f"  n = {len(inter_all)}")
print(f"  min      : {inter_all.min():.0f}s ({inter_all.min()/60:.1f}min)")
print(f"  p25      : {inter_all.quantile(0.25):.0f}s ({inter_all.quantile(0.25)/60:.1f}min)")
print(f"  median   : {inter_all.median():.0f}s ({inter_all.median()/60:.1f}min)")
print(f"  p75      : {inter_all.quantile(0.75):.0f}s ({inter_all.quantile(0.75)/60:.1f}min)")
print(f"  max      : {inter_all.max():.0f}s ({inter_all.max()/60:.1f}min)")
print(f"  mean     : {inter_all.mean():.0f}s ({inter_all.mean()/60:.1f}min)")

print(f"\n  sub-30s (YouTube min violation): {(inter_all < 30).sum()} / {len(inter_all)}")
print(f"  < 2 min                         : {(inter_all < 120).sum()}")
print(f"  > 10 min                        : {(inter_all > 600).sum()}")
print(f"  > 15 min                        : {(inter_all > 900).sum()}")

print("\n" + "=" * 70)
print("Pre-roll-to-first-slot gap (across 19 videos)")
print("=" * 70)
pre = per_video["pre_gap_sec"]
print(f"  median: {pre.median():.0f}s ({pre.median()/60:.1f}min)")
print(f"  range : {pre.min():.0f}s 〜 {pre.max():.0f}s ({pre.max()/60:.1f}min)")

print("\n" + "=" * 70)
print("Per-video table (sorted by revenue)")
print("=" * 70)
disp = per_video[["video_id", "n_slots", "length_min", "avg_watch_min",
                  "pre_gap_min", "median_inter_min", "max_inter_min",
                  "end_gap_min", "n_sub30s", "n_wide_gt10min"]]
print(disp.to_string(index=False))

# ---- Plot: gap distribution histogram + per-video boxplot -----------
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Hist of inter-slot gaps
axes[0].hist(inter_all / 60, bins=20, color="#1f77b4", edgecolor="black", alpha=0.8)
axes[0].axvline(5, color="#2ca02c", linestyle="--", label="recommended 5min")
axes[0].axvline(inter_all.median() / 60, color="#d62728", linestyle="-",
                label=f"median {inter_all.median()/60:.1f}min")
axes[0].set_xlabel("Inter-slot gap (minutes)")
axes[0].set_ylabel("Count")
axes[0].set_title(f"Distribution of inter-slot gaps  (n={len(inter_all)})")
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# Per-video gap profile (each video as a horizontal line)
ax2 = axes[1]
pv_sorted = per_video.sort_values("length_sec").reset_index(drop=True)
for i, (_, row) in enumerate(pv_sorted.iterrows()):
    g = slots[slots["video_id"] == row["video_id"]].sort_values("position_sec")
    ax2.plot([0, row["length_sec"]/60], [i, i], color="#cccccc", linewidth=1, zorder=1)
    ax2.axvline(row["avg_watch_sec"]/60, ymin=0, ymax=1, alpha=0.0)  # placeholder
    ax2.scatter(g["position_sec"]/60, [i]*len(g),
                color="#1f77b4", s=30, zorder=3)
    ax2.scatter(row["avg_watch_sec"]/60, i, marker="|", color="#d62728",
                s=200, linewidth=2, zorder=4)

ax2.set_yticks(range(len(pv_sorted)))
ax2.set_yticklabels(pv_sorted["video_id"], fontsize=8)
ax2.set_xlabel("Time (minutes)")
ax2.set_title("Slot positions per video  (red | = avg watch time)")
ax2.grid(True, alpha=0.3, axis="x")

plt.tight_layout()
out_png = OUT_DIR / "slot_gaps.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'slot_gaps_per_video.csv'}")
