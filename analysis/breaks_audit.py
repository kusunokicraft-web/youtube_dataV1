"""
Audit configured ad-break positions against retention.

For each video with mid-roll timestamps, evaluate:
  - effective slot count (deduping breaks <30s apart)
  - whether each slot lies within the average watch window
  - estimated reach (% of viewers who see each slot)
  - placement gap analysis
  - recommended re-placement
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ANALYTICS = ROOT / "analysis" / "report" / "cleaned.csv"
BREAKS = ROOT / "data" / "ad_slots" / "breaks.csv"

# Approximate retention curve for compilation/long-form vtuber content.
# Calibrated so that area-under-curve through avg_watch_time matches data.
# Format: list of (position_pct, retention_pct).
RETENTION_CURVE = [
    (0.00, 1.00),
    (0.02, 0.85),  # initial drop within first ~2%
    (0.05, 0.78),
    (0.10, 0.70),
    (0.20, 0.58),
    (0.30, 0.48),
    (0.40, 0.40),
    (0.50, 0.32),
    (0.60, 0.25),
    (0.70, 0.20),
    (0.80, 0.15),
    (0.90, 0.10),
    (1.00, 0.06),
]


def retention_at(pct: float) -> float:
    pct = max(0.0, min(1.0, pct))
    for (p1, r1), (p2, r2) in zip(RETENTION_CURVE, RETENTION_CURVE[1:]):
        if p1 <= pct <= p2:
            t = (pct - p1) / (p2 - p1) if p2 > p1 else 0
            return r1 + t * (r2 - r1)
    return RETENTION_CURVE[-1][1]


# --- Load data --------------------------------------------------------
analytics = pd.read_csv(ANALYTICS)
breaks = pd.read_csv(BREAKS)

# Dedupe ad slots that are <30s apart (YouTube's enforced minimum)
def mark_effective(group: pd.DataFrame) -> pd.DataFrame:
    g = group.sort_values("position_sec").reset_index(drop=True).copy()
    g["effective"] = True
    last_kept = -10**9
    for i, row in g.iterrows():
        if row["position_sec"] - last_kept < 30:
            g.at[i, "effective"] = False
        else:
            last_kept = row["position_sec"]
    return g


breaks = breaks.groupby("video_id", group_keys=False)[breaks.columns.tolist()].apply(mark_effective)


# --- Per-video audit --------------------------------------------------
def audit(video_id: str) -> dict:
    a = analytics[analytics["video_id"] == video_id].iloc[0]
    b = breaks[breaks["video_id"] == video_id].copy()
    length = a["length_sec"]
    avg_watch = a["avg_watch_sec"]

    b["pos_pct"] = b["position_sec"] / length
    b["before_avg_watch"] = b["position_sec"] <= avg_watch
    b["estimated_reach"] = b["position_sec"].map(lambda s: retention_at(s / length))

    # Effective (dedup) summary
    eff = b[b["effective"]].copy()

    # Estimated impressions from current setup
    pre_roll_imp = a["monetized_playbacks"]  # 1.0 per session (always fires)
    midroll_imp_est = (eff["estimated_reach"] * a["monetized_playbacks"]).sum()
    total_est_ads = pre_roll_imp + midroll_imp_est
    total_est_per_session = total_est_ads / a["monetized_playbacks"]
    actual_per_session = a["ad_impressions"] / a["monetized_playbacks"]

    return {
        "analytics": a,
        "breaks": b,
        "effective": eff,
        "estimated_ads_per_session": total_est_per_session,
        "actual_ads_per_session": actual_per_session,
        "midroll_imp_est": midroll_imp_est,
    }


# --- Recommended placement -------------------------------------------
def recommend_placement(length: float, avg_watch: float,
                        gap_min: float = 5.0,
                        first_at_min: float = 3.5) -> list[float]:
    """Return recommended break positions in seconds."""
    gap_s = gap_min * 60
    first_s = first_at_min * 60
    horizon = min(length, avg_watch * 1.3)  # extend a little past avg for tail viewers
    out = []
    t = first_s
    while t <= horizon:
        out.append(round(t))
        t += gap_s
    return out


def projected_session_ads(length: float, avg_watch: float,
                           positions: list[float]) -> float:
    """Avg ads per session given a placement, including pre-roll."""
    midroll = sum(retention_at(p / length) for p in positions)
    return 1.0 + midroll  # 1 pre-roll + retention-weighted mid-rolls


# --- Run for all videos with break data -------------------------------
def fmt_hms(s: float) -> str:
    s = int(round(s))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


reports = []
for vid in breaks["video_id"].unique():
    r = audit(vid)
    a = r["analytics"]
    print(f"\n{'='*78}\n動画: {a['title']}")
    print(f"video_id={vid}  長さ={a['length_sec']/60:.1f}分  平均視聴={a['avg_watch_sec']/60:.1f}分")
    print(f"視聴={int(a['views']):,}  収益化再生={int(a['monetized_playbacks']):,}  "
          f"広告表示={int(a['ad_impressions']):,}  est_revenue=¥{a['est_revenue_jpy']:,.0f}")

    print(f"\n【現状の広告ブレイク (raw {len(r['breaks'])}本 / 有効 {len(r['effective'])}本)】")
    print("idx  pos       pct    有効   avg内  到達率  警告")
    for _, row in r["breaks"].iterrows():
        flag_eff = "○" if row["effective"] else "×重複"
        flag_aw = "○" if row["before_avg_watch"] else "×超過"
        warn = "⚠" if str(row.get("has_warning", "")).upper() == "TRUE" else ""
        print(f"  {int(row['break_index'])}  {row['position_hms']}  "
              f"{row['pos_pct']*100:5.1f}%  {flag_eff}   {flag_aw}    "
              f"{row['estimated_reach']*100:5.1f}%  {warn}")

    print(f"\n  実測広告/セッション : {r['actual_ads_per_session']:.2f}")
    print(f"  モデル推定          : {r['estimated_ads_per_session']:.2f}")

    # Recommendation
    rec = recommend_placement(a["length_sec"], a["avg_watch_sec"],
                              gap_min=5.0, first_at_min=3.5)
    rec_per_session = projected_session_ads(a["length_sec"], a["avg_watch_sec"], rec)
    print(f"\n【推奨配置 (5分間隔・初回3:30・avg視聴×1.3まで)】 {len(rec)}本")
    for i, p in enumerate(rec, 1):
        reach = retention_at(p / a["length_sec"])
        print(f"  {i}  {fmt_hms(p)}   推定到達率 {reach*100:.1f}%")

    print(f"\n  推奨配置時の広告/セッション : {rec_per_session:.2f}")

    # Revenue projection
    cpm = a["cpm_jpy"]  # ¥ per ad impression × 1000
    creator_share = 0.55
    cpm_decay_factor = 0.92 ** max(0, len(rec) - len(r["effective"]))

    gross_now = r["actual_ads_per_session"] * a["monetized_playbacks"] * cpm / 1000
    gross_rec = rec_per_session * a["monetized_playbacks"] * cpm * cpm_decay_factor / 1000
    net_now = gross_now * creator_share + (a["est_revenue_jpy"] - gross_now * creator_share)
    net_rec = gross_rec * creator_share + (a["est_revenue_jpy"] - gross_now * creator_share)
    uplift = net_rec - a["est_revenue_jpy"]
    print(f"\n  現収益: ¥{a['est_revenue_jpy']:,.0f}")
    print(f"  推奨配置後 (net 推定): ¥{net_rec:,.0f}  (+¥{uplift:,.0f}, {uplift/a['est_revenue_jpy']*100:+.1f}%)")

    reports.append({
        "video_id": vid,
        "title": a["title"],
        "length_min": a["length_sec"] / 60,
        "avg_watch_min": a["avg_watch_sec"] / 60,
        "raw_slots": len(r["breaks"]),
        "effective_slots": len(r["effective"]),
        "slots_before_avg_watch": int(r["effective"]["before_avg_watch"].sum()),
        "actual_ads_per_session": r["actual_ads_per_session"],
        "recommended_slots": len(rec),
        "rec_ads_per_session": rec_per_session,
        "current_rev": a["est_revenue_jpy"],
        "projected_rev": net_rec,
        "uplift_jpy": uplift,
        "uplift_pct": uplift / a["est_revenue_jpy"] * 100,
    })

pd.DataFrame(reports).to_csv(ROOT / "analysis" / "report" / "breaks_audit.csv", index=False)
