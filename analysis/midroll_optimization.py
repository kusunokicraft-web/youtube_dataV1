"""
Mid-roll ad slot optimization — diagnostic analysis.

Quantifies the current ad density per video, the addressable
mid-roll inventory based on average retention, and projects
revenue uplift from optimizing slot count and placement.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "analysis" / "report" / "cleaned.csv"
OUT = ROOT / "analysis" / "report"

CREATOR_SHARE = 0.55  # YouTube ad-rev share (~55/45)
CPM_DECAY_PER_EXTRA_AD = 0.92  # eCPM erosion per additional mid-roll
GAP_MIN_CONSERVATIVE = 5.0
GAP_MIN_AGGRESSIVE = 4.0

df = pd.read_csv(SRC, parse_dates=["published_at"])
long_df = df[(df["format"] == "Long") & (df["views"] > 0)].copy()

# --- 1. Observed ad density -------------------------------------------
long_df["ads_per_monetized_play"] = long_df["ad_impressions"] / long_df["monetized_playbacks"]
long_df["ads_per_view"] = long_df["ad_impressions"] / long_df["views"]
long_df["minutes"] = long_df["length_sec"] / 60.0
long_df["avg_watch_min"] = long_df["avg_watch_sec"] / 60.0

# Monetized fill rate: how often does a view trigger any ad at all?
long_df["monetized_fill"] = long_df["monetized_playbacks"] / long_df["views"]


# --- 2. Theoretical mid-roll inventory --------------------------------
# Slots = 1 pre-roll + N mid-rolls, where mid-rolls fall every `gap` minutes
# only within the average watch window (otherwise no impression generated).
def slots_in_window(window_min: float, gap_min: float) -> int:
    if pd.isna(window_min) or window_min <= 0:
        return 0
    return 1 + max(0, int(window_min // gap_min))


long_df["slots_conservative"] = long_df["avg_watch_min"].map(
    lambda w: slots_in_window(w, GAP_MIN_CONSERVATIVE)
)
long_df["slots_aggressive"] = long_df["avg_watch_min"].map(
    lambda w: slots_in_window(w, GAP_MIN_AGGRESSIVE)
)

# --- 3. Revenue projection --------------------------------------------
# Model: gross ad rev = views * monetized_fill * slots_per_session * eCPM/1000
# Hold monetized_fill and base eCPM constant, vary slots_per_session.
# Apply CPM decay for each *additional* slot beyond the current count.
long_df["base_ecpm"] = long_df["cpm_jpy"]  # observed eCPM per ad impression
long_df["gross_now"] = long_df["yt_ad_rev_jpy"]

# Premium + other revenue is independent of mid-roll count
long_df["non_ad_rev"] = (long_df["est_revenue_jpy"] - long_df["yt_ad_rev_jpy"] * CREATOR_SHARE).clip(lower=0)


def projected_gross(row: pd.Series, target_slots: int) -> float:
    if pd.isna(row["base_ecpm"]) or pd.isna(row["monetized_playbacks"]):
        return np.nan
    current = row["ads_per_monetized_play"] if pd.notna(row["ads_per_monetized_play"]) else 1.0
    extra = max(0, target_slots - current)
    decay = CPM_DECAY_PER_EXTRA_AD ** extra
    ecpm = row["base_ecpm"] * decay
    return target_slots * row["monetized_playbacks"] * ecpm / 1000.0


for tier, slots_col in [("conservative", "slots_conservative"), ("aggressive", "slots_aggressive")]:
    gross_col = f"gross_{tier}"
    net_col = f"net_{tier}"
    uplift_col = f"uplift_{tier}_pct"
    long_df[gross_col] = long_df.apply(lambda r: projected_gross(r, r[slots_col]), axis=1)
    long_df[net_col] = long_df[gross_col] * CREATOR_SHARE + long_df["non_ad_rev"]
    long_df[uplift_col] = (long_df[net_col] / long_df["est_revenue_jpy"] - 1) * 100

# Don't recommend reducing — only count uplift opportunities
long_df["recommend_action"] = np.where(
    long_df["ads_per_monetized_play"] >= long_df["slots_conservative"] * 0.95,
    "OK / fine-tune placement",
    np.where(
        long_df["ads_per_monetized_play"] >= long_df["slots_conservative"] * 0.7,
        "Add 1 mid-roll",
        "Add 2+ mid-rolls",
    ),
)


# --- 4. Channel-level outlook -----------------------------------------
def total(c: str) -> float:
    return long_df[c].sum(skipna=True)


now_total = total("est_revenue_jpy")
cons_total = total("net_conservative")
agg_total = total("net_aggressive")
gross_now = total("gross_now")
gross_cons = total("gross_conservative")

print("=== Channel-level outlook (Long-form only) ===")
print(f"Net revenue NOW           : ¥{now_total:,.0f}")
print(f"Net revenue CONSERVATIVE  : ¥{cons_total:,.0f}  ({(cons_total/now_total-1)*100:+.1f}%)")
print(f"Net revenue AGGRESSIVE    : ¥{agg_total:,.0f}  ({(agg_total/now_total-1)*100:+.1f}%)")
print(f"  (gross ad: now ¥{gross_now:,.0f} → cons ¥{gross_cons:,.0f})")

# --- 5. Density bucket summary ----------------------------------------
def bucket(x: float) -> str:
    if pd.isna(x):
        return "unknown"
    if x < 1.2:
        return "A. <1.2  (pre-roll only)"
    if x < 2.0:
        return "B. 1.2-2 (1 mid-roll)"
    if x < 3.0:
        return "C. 2-3   (2 mid-rolls)"
    if x < 4.0:
        return "D. 3-4   (3 mid-rolls)"
    return "E. 4+    (heavy)"


long_df["density_bucket"] = long_df["ads_per_monetized_play"].map(bucket)
bucket_summary = (
    long_df.groupby("density_bucket")
    .agg(
        videos=("video_id", "count"),
        med_min=("minutes", "median"),
        med_watch_min=("avg_watch_min", "median"),
        med_ads_per_play=("ads_per_monetized_play", "median"),
        med_cpm=("cpm_jpy", "median"),
        med_rpm=("rpm_jpy", "median"),
    )
    .reset_index()
)

print("\n=== Density bucket summary ===")
print(bucket_summary.to_string(index=False))

# --- 6. Per-video action sheet ---------------------------------------
sheet_cols = [
    "video_id", "title", "minutes", "avg_watch_min",
    "monetized_fill", "ads_per_monetized_play",
    "slots_conservative", "slots_aggressive",
    "cpm_jpy", "est_revenue_jpy",
    "net_conservative", "uplift_conservative_pct",
    "net_aggressive", "uplift_aggressive_pct",
    "recommend_action",
]
sheet = long_df[sheet_cols].copy().sort_values("est_revenue_jpy", ascending=False)
sheet.to_csv(OUT / "ad_action_sheet.csv", index=False)
bucket_summary.to_csv(OUT / "ad_density_buckets.csv", index=False)

print("\n=== Top 10 revenue-uplift opportunities (conservative) ===")
top = sheet[(sheet["est_revenue_jpy"] > 0) & sheet["uplift_conservative_pct"].notna()] \
    .sort_values("uplift_conservative_pct", ascending=False).head(10)
disp = top[["title", "minutes", "avg_watch_min", "ads_per_monetized_play",
            "slots_conservative", "est_revenue_jpy", "net_conservative",
            "uplift_conservative_pct", "recommend_action"]].copy()
disp["title"] = disp["title"].str.slice(0, 38)
print(disp.to_string(index=False))

print("\n=== Highest-revenue videos: current density vs target ===")
top_rev = sheet.head(10).copy()
top_rev_disp = top_rev[["title", "minutes", "avg_watch_min", "ads_per_monetized_play",
                        "slots_conservative", "est_revenue_jpy",
                        "uplift_conservative_pct", "recommend_action"]].copy()
top_rev_disp["title"] = top_rev_disp["title"].str.slice(0, 38)
print(top_rev_disp.to_string(index=False))
