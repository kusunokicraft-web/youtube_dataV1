"""
Life-plan revenue projection: 5 active years + 5 harvest years.

Realistic constraint: VTuber subject (Ange) likely to graduate, genre
trends shift. Active production caps at ~5 years.

Years 1-5: post monthly (60 new videos)
Years 6-10: harvest mode (decay of 26 existing + 60 new)
"""

import sys, numpy as np, pandas as pd
sys.path.insert(0, "analysis")
from _exclusions import EXCLUDED_VIDEO_IDS as EXC

an = pd.read_csv("analysis/report/cleaned.csv", parse_dates=["published_at"])
asof = pd.Timestamp("2026-04-25")
an["age_days"] = (asof - an["published_at"]).dt.days.clip(lower=1)
an["length_min"] = an["length_sec"] / 60

df30_all = an[(an["format"]=="Long") & (an["views"]>0) &
              (~an["video_id"].isin(EXC))].copy()
df30_all = df30_all.dropna(subset=["est_revenue_jpy"])
df30 = df30_all[df30_all["length_min"]>=30].copy()
xl = np.log(df30["age_days"].values)
yl = np.log(df30["est_revenue_jpy"].clip(lower=1).values)
k, a_ = np.polyfit(xl, yl, 1)
print(f"Decay model k = {k:.3f}")

mature30 = df30[df30["age_days"]>=180].copy()
mature30["scale_c"] = mature30["est_revenue_jpy"]/(mature30["age_days"]**k)
mature30["rev_year_10"] = mature30["scale_c"]*((10*365)**k)
geo_mean = np.exp(np.log(mature30["rev_year_10"]).mean())
print(f"Per-video 10y lifetime (V2 なし): ¥{geo_mean:,.0f}")

# c_new: revenue scale per new video
c_new = geo_mean / ((10*365)**k)


def existing_tail_revenue(start_day: int, end_day: int) -> float:
    """ Revenue from existing 26 videos between calendar days [start, end] (asof=day 0). """
    total = 0
    for _, r in df30_all.iterrows():
        scale_c = r["views"] / (r["age_days"]**k)
        rpv = r["est_revenue_jpy"]/r["views"]
        a0 = r["age_days"] + start_day
        a1 = r["age_days"] + end_day
        future_views = scale_c * (a1**k - a0**k)
        total += future_views * rpv
    return total


def new_video_revenue_window(publish_day: float, start_day: float,
                             end_day: float) -> float:
    """ Revenue from one new video (published at publish_day) between
    calendar days [start_day, end_day]. Uses cumulative integral of c*age^k. """
    if end_day <= publish_day:
        return 0
    a0 = max(0, start_day - publish_day)
    a1 = end_day - publish_day
    if a0 == 0:
        a0 = 1  # avoid 0^k issues at publish day
    return c_new * (a1**k - a0**k)


def yearly_revenue(year_idx: int, n_active_years: int = 5,
                   n_per_year: int = 12) -> dict:
    """ Revenue earned during year `year_idx` (1-indexed). """
    start = (year_idx - 1) * 365
    end = year_idx * 365
    tail = existing_tail_revenue(start, end)
    interval = 365 / n_per_year
    new_total = 0
    # Iterate publications across active years only
    max_publish_day = n_active_years * 365
    tau = 0
    while tau < max_publish_day:
        new_total += new_video_revenue_window(tau, start, end)
        tau += interval
    return {"year": year_idx, "tail": tail, "new": new_total,
            "total": tail + new_total}


print("\n=== 5 年制作 + 5 年 harvest シナリオ ===")
print(f"{'年次':<8}{'既存tail':>12}{'新作':>12}{'年商計':>12}{'累計':>14}")
print("-" * 60)
cumulative = 0
yearly = []
for y in range(1, 11):
    r = yearly_revenue(y, n_active_years=5, n_per_year=12)
    cumulative += r["total"]
    yearly.append({**r, "cumulative": cumulative})
    marker = "  ← 制作終了" if y == 5 else ""
    print(f"{y}年目   ¥{r['tail']:>9,.0f}  ¥{r['new']:>9,.0f}  "
          f"¥{r['total']:>9,.0f}  ¥{cumulative:>11,.0f}{marker}")

active_total = sum(yr["total"] for yr in yearly[:5])
harvest_total = sum(yr["total"] for yr in yearly[5:])
print(f"\n5 年累計（制作期）: ¥{active_total:,.0f} ({active_total/10000:.0f}万)")
print(f"6-10 年累計（harvest）: ¥{harvest_total:,.0f} ({harvest_total/10000:.0f}万)")
print(f"10 年累計: ¥{active_total+harvest_total:,.0f} ({(active_total+harvest_total)/10000:.0f}万)")

# Investment portfolio under this trajectory
def compound(rate: float) -> dict:
    """ Compound investment year-by-year. Each year's full revenue is invested. """
    bal_5 = bal_10 = 0
    for y in range(10):
        bal_10 = (bal_10 + yearly[y]["total"]) * (1 + rate)
        if y < 5:
            bal_5 = (bal_5 + yearly[y]["total"]) * (1 + rate)
    return {"5y": bal_5, "10y": bal_10}


print("\n=== 投資ポートフォリオ（YouTube 全額投資） ===")
for r in [0.05, 0.07]:
    c = compound(r)
    print(f"  年率 {r:.0%}: 5 年 ¥{c['5y']:,.0f} ({c['5y']/10000:.0f}万)  "
          f"10 年 ¥{c['10y']:,.0f} ({c['10y']/10000:.0f}万)")

# Channel residual value at year 10
# = future earnings beyond year 10 from the 86-video catalog
year10_day = 10 * 365
year20_day = 20 * 365  # cap at year 20
residual_existing = existing_tail_revenue(year10_day, year20_day)
residual_new = 0
tau = 0
while tau < 5 * 365:
    a0 = year10_day - tau
    a1 = year20_day - tau
    if a1 > a0 > 0:
        residual_new += c_new * (a1**k - a0**k)
    tau += 365 / 12
print(f"\n=== 10 年時点のチャネル残存価値（11-20 年分） ===")
print(f"  既存 26 動画: ¥{residual_existing:,.0f} ({residual_existing/10000:.0f}万)")
print(f"  新作 60 動画: ¥{residual_new:,.0f} ({residual_new/10000:.0f}万)")
print(f"  合計: ¥{residual_existing+residual_new:,.0f} "
      f"({(residual_existing+residual_new)/10000:.0f}万)")

# Total assets at year 10
print(f"\n=== 10 年後総資産（YouTube 全額投資 + チャネル残存 + 防衛資金 200 万） ===")
for r in [0.05, 0.07]:
    c = compound(r)
    total = c["10y"] + residual_existing + residual_new + 2_000_000
    print(f"  年率 {r:.0%}: ¥{total:,.0f} ({total/10000:.0f}万)")
