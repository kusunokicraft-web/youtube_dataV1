"""
Channel-level ad-slot placement analysis.

Aggregates the per-video audit across all ingested videos to
test specific hypotheses about current placement behavior and
quantify the total uplift opportunity.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ANALYTICS = ROOT / "analysis" / "report" / "cleaned.csv"
BREAKS = ROOT / "data" / "ad_slots" / "breaks.csv"
OUT = ROOT / "analysis" / "report"

# ---- Retention curve (same as breaks_audit.py) -----------------------
RETENTION_CURVE = [
    (0.00, 1.00), (0.02, 0.85), (0.05, 0.78), (0.10, 0.70),
    (0.20, 0.58), (0.30, 0.48), (0.40, 0.40), (0.50, 0.32),
    (0.60, 0.25), (0.70, 0.20), (0.80, 0.15), (0.90, 0.10),
    (1.00, 0.06),
]


def retention_at(pct: float) -> float:
    pct = max(0.0, min(1.0, pct))
    for (p1, r1), (p2, r2) in zip(RETENTION_CURVE, RETENTION_CURVE[1:]):
        if p1 <= pct <= p2:
            t = (pct - p1) / (p2 - p1) if p2 > p1 else 0
            return r1 + t * (r2 - r1)
    return RETENTION_CURVE[-1][1]


# ---- Load -----------------------------------------------------------
analytics = pd.read_csv(ANALYTICS)
breaks = pd.read_csv(BREAKS)
breaks["has_warning"] = breaks["has_warning"].astype(str).str.upper().eq("TRUE")

# Effective slot: dedupe breaks <30s apart
def mark_effective(g: pd.DataFrame) -> pd.DataFrame:
    g = g.sort_values("position_sec").reset_index(drop=True).copy()
    g["effective"] = True
    last_kept = -10**9
    for i, row in g.iterrows():
        if row["position_sec"] - last_kept < 30:
            g.at[i, "effective"] = False
        else:
            last_kept = row["position_sec"]
    return g


breaks = breaks.groupby("video_id", group_keys=False)[breaks.columns.tolist()].apply(mark_effective)

# Join analytics context
ctx_cols = ["video_id", "title", "length_sec", "avg_watch_sec", "views",
            "monetized_playbacks", "ad_impressions", "est_revenue_jpy",
            "yt_ad_rev_jpy", "cpm_jpy", "rpm_jpy"]
joined = breaks.merge(analytics[ctx_cols], on="video_id", how="left")
joined["pos_pct"] = joined["position_sec"] / joined["length_sec"]
joined["rel_to_avg_watch"] = joined["position_sec"] / joined["avg_watch_sec"]
joined["before_avg_watch"] = joined["position_sec"] <= joined["avg_watch_sec"]
joined["reach"] = joined["pos_pct"].map(retention_at)

# ---- Per-video summary ---------------------------------------------
def summarize_video(vid: str) -> dict:
    a = analytics[analytics["video_id"] == vid].iloc[0]
    eff = joined[(joined["video_id"] == vid) & joined["effective"]]
    raw = joined[joined["video_id"] == vid]
    first_slot = eff["position_sec"].min() if len(eff) else np.nan
    last_slot = eff["position_sec"].max() if len(eff) else np.nan
    slots_in_avg = eff["before_avg_watch"].sum()
    total_reach = eff["reach"].sum()  # sum of mid-roll reaches (impressions model)
    expected_ads_per_session = 1.0 + total_reach  # +1 for pre-roll
    actual_ads_per_session = a["ad_impressions"] / a["monetized_playbacks"] if a["monetized_playbacks"] else np.nan
    return {
        "video_id": vid,
        "title": a["title"][:40],
        "length_min": round(a["length_sec"] / 60, 1),
        "avg_watch_min": round(a["avg_watch_sec"] / 60, 1),
        "inserted_by": raw["inserted_by"].iloc[0] if len(raw) else "",
        "raw_slots": len(raw),
        "effective_slots": len(eff),
        "duplicates": len(raw) - len(eff),
        "warnings": int(raw["has_warning"].sum()),
        "slots_in_golden_zone": int(slots_in_avg),
        "first_slot_sec": first_slot,
        "first_slot_pct_of_avg": round(first_slot / a["avg_watch_sec"], 2) if first_slot else np.nan,
        "last_slot_pct_of_length": round(last_slot / a["length_sec"], 2) if last_slot else np.nan,
        "model_ads_per_session": round(expected_ads_per_session, 2),
        "actual_ads_per_session": round(actual_ads_per_session, 2),
        "model_gap": round(actual_ads_per_session - expected_ads_per_session, 2),
        "views": int(a["views"]),
        "est_revenue_jpy": a["est_revenue_jpy"],
        "rpm_jpy": a["rpm_jpy"],
    }


per_video = pd.DataFrame([summarize_video(v) for v in breaks["video_id"].unique()])
per_video = per_video.sort_values("est_revenue_jpy", ascending=False)
per_video.to_csv(OUT / "ad_slots_per_video.csv", index=False)

# ---- Hypothesis tests ----------------------------------------------
print("="*80)
print("Channel ad-slot placement analysis")
print("="*80)
print(f"Videos analyzed: {len(per_video)}")
print(f"Total slots: {len(joined)}  (effective: {joined['effective'].sum()}, "
      f"duplicates: {(~joined['effective']).sum()}, warnings: {joined['has_warning'].sum()})")

# H1: "First slot is consistently too late"
print("\n" + "-"*80)
print("H1: 最初の slot は平均視聴時間のどれくらいの比率に置かれているか")
print("-"*80)
first_slot_pct = per_video["first_slot_pct_of_avg"].dropna()
print(f"  n={len(first_slot_pct)}")
print(f"  median first_slot_sec / avg_watch_sec = {first_slot_pct.median():.2f}")
print(f"  distribution quartiles: {first_slot_pct.quantile([0.25, 0.5, 0.75]).tolist()}")
early = (first_slot_pct <= 0.3).sum()
late = (first_slot_pct >= 0.8).sum()
print(f"  avg視聴の30%以下（早期）: {early} / {len(first_slot_pct)} 動画")
print(f"  avg視聴の80%以上（遅延）: {late} / {len(first_slot_pct)} 動画")

# H2: "Golden zone (0 .. avg_watch) is consistently under-utilized"
print("\n" + "-"*80)
print("H2: ゴールデンゾーン（0〜avg視聴）への slot 配置数")
print("-"*80)
in_gz = per_video["slots_in_golden_zone"]
total_slots = per_video["effective_slots"]
print(f"  ゴールデンゾーン内 slot 総数: {in_gz.sum()} / 有効 slot 総数: {total_slots.sum()}")
print(f"  ゴールデンゾーン内比率: {in_gz.sum()/total_slots.sum()*100:.1f}%")
print(f"  動画あたりの中央値: {in_gz.median():.1f} 本（有効中央値: {total_slots.median():.1f} 本）")
zero_gz = (in_gz == 0).sum()
print(f"  ゴールデンゾーンに1本も slot がない動画: {zero_gz} / {len(per_video)} ({zero_gz/len(per_video)*100:.0f}%)")

# H3: "Auto placement is demonstrably different from manual"
print("\n" + "-"*80)
print("H3: 自動挿入 vs 手動挿入の比較")
print("-"*80)
for tag in ["manual", "auto"]:
    sub = per_video[per_video["inserted_by"] == tag]
    if len(sub) == 0:
        continue
    print(f"  {tag}: n={len(sub)}  "
          f"first_slot_pct={sub['first_slot_pct_of_avg'].median():.2f}  "
          f"slots_in_gz={sub['slots_in_golden_zone'].median():.1f}  "
          f"effective_slots_per_min={((sub['effective_slots']/sub['length_min']).median()):.2f}  "
          f"RPM={sub['rpm_jpy'].median():.0f}")

# H4: "Warnings cluster on placements that violate something specific"
print("\n" + "-"*80)
print("H4: 警告 (⚠) の特徴")
print("-"*80)
warned = joined[joined["has_warning"]]
if len(warned):
    print(f"  警告 slot 数: {len(warned)}")
    print(f"  平均 pos_pct: {warned['pos_pct'].mean()*100:.1f}%")
    print(f"  pos_pct 分布: min={warned['pos_pct'].min()*100:.1f}%  "
          f"median={warned['pos_pct'].median()*100:.1f}%  "
          f"max={warned['pos_pct'].max()*100:.1f}%")
    print(f"  rel_to_avg_watch 分布: min={warned['rel_to_avg_watch'].min():.2f}  "
          f"median={warned['rel_to_avg_watch'].median():.2f}  "
          f"max={warned['rel_to_avg_watch'].max():.2f}")
    # Gap to nearest neighbor
    print("\n  警告 slot の詳細:")
    for _, r in warned.iterrows():
        print(f"    {r['video_id']}  #{int(r['break_index'])}  "
              f"pos={r['position_hms']}  pos%={r['pos_pct']*100:.1f}%  "
              f"rel_to_avg={r['rel_to_avg_watch']:.2f}")

# H5: "Model gap reveals how wrong our retention model is per video"
print("\n" + "-"*80)
print("H5: モデル推定 vs 実測の乖離")
print("-"*80)
gap = per_video[["video_id", "title", "model_ads_per_session",
                 "actual_ads_per_session", "model_gap", "inserted_by"]].copy()
print(f"  モデル gap 中央値: {gap['model_gap'].median():+.2f}")
print(f"  gap 分布: {gap['model_gap'].describe().round(2).to_dict()}")
print("  大きく乖離している動画（|gap| >= 0.3）:")
big = gap[gap["model_gap"].abs() >= 0.3].sort_values("model_gap")
for _, r in big.iterrows():
    print(f"    {r['video_id']:<12s}  gap={r['model_gap']:+.2f}  "
          f"({r['inserted_by']:<6s})  {r['title'][:40]}")

# H6: Total channel uplift opportunity (recompute using same model as breaks_audit.py)
print("\n" + "-"*80)
print("H6: 総収益アップサイド（保守版: 5分間隔, 初回3:30, avg×1.3まで）")
print("-"*80)

CREATOR_SHARE = 0.55
CPM_DECAY = 0.92


def recommend_slots(length_sec: float, avg_watch_sec: float) -> list[float]:
    gap = 300
    first = 210
    horizon = min(length_sec, avg_watch_sec * 1.3)
    out = []
    t = first
    while t <= horizon:
        out.append(t)
        t += gap
    return out


rows = []
for _, r in per_video.iterrows():
    a = analytics[analytics["video_id"] == r["video_id"]].iloc[0]
    if pd.isna(a["cpm_jpy"]) or pd.isna(a["monetized_playbacks"]):
        continue
    eff_now = joined[(joined["video_id"] == r["video_id"]) & joined["effective"]]
    current = eff_now.shape[0] + 1  # pre-roll
    rec_positions = recommend_slots(a["length_sec"], a["avg_watch_sec"])
    rec_reach = sum(retention_at(p / a["length_sec"]) for p in rec_positions)
    rec_per_session = 1.0 + rec_reach
    extra_slots = max(0, len(rec_positions) + 1 - current)
    decay = CPM_DECAY ** extra_slots
    actual_per_session = r["actual_ads_per_session"]
    gross_now = actual_per_session * a["monetized_playbacks"] * a["cpm_jpy"] / 1000
    gross_rec = rec_per_session * a["monetized_playbacks"] * a["cpm_jpy"] * decay / 1000
    net_now = a["est_revenue_jpy"]
    net_rec = (gross_rec - gross_now) * CREATOR_SHARE + a["est_revenue_jpy"]
    rows.append({
        "video_id": r["video_id"],
        "current_rev": net_now,
        "projected_rev": net_rec,
        "uplift_jpy": net_rec - net_now,
        "uplift_pct": (net_rec / net_now - 1) * 100,
    })

channel = pd.DataFrame(rows)
print(f"  対象動画: {len(channel)} / 19")
print(f"  現収益合計: ¥{channel['current_rev'].sum():,.0f}")
print(f"  推奨配置後合計: ¥{channel['projected_rev'].sum():,.0f}")
print(f"  アップサイド: ¥{channel['uplift_jpy'].sum():,.0f} "
      f"(+{channel['uplift_jpy'].sum()/channel['current_rev'].sum()*100:.1f}%)")

# Save
channel.to_csv(OUT / "ad_slots_channel_projection.csv", index=False)
