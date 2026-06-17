"""
Conservative life-plan revenue projection with k=0.57 decay model.

Uses the rigorously-fitted 30+ min Long-form decay (R^2=0.52) instead
of the all-Long-form fit. Projects:
  - Existing 26-video tail
  - New monthly releases (V2 strategy applied)
  - Total annual cash flow over 5 / 10 years
"""

import sys, numpy as np, pandas as pd
sys.path.insert(0, "analysis")
from _exclusions import EXCLUDED_VIDEO_IDS as EXC

an = pd.read_csv("analysis/report/cleaned.csv", parse_dates=["published_at"])
asof = pd.Timestamp("2026-04-25")
an["age_days"] = (asof - an["published_at"]).dt.days.clip(lower=1)
an["length_min"] = an["length_sec"] / 60

# Use 30+ min Long-form fit (R^2 = 0.52)
df30_all = an[(an["format"]=="Long") & (an["views"]>0) &
              (~an["video_id"].isin(EXC))].copy()
df30_all = df30_all.dropna(subset=["est_revenue_jpy"])
df30 = df30_all[df30_all["length_min"]>=30].copy()
xl = np.log(df30["age_days"].values)
yl = np.log(df30["est_revenue_jpy"].clip(lower=1).values)
k, a_ = np.polyfit(xl, yl, 1)
print(f"Decay model (revenue) k = {k:.3f} (R^2 calc'd separately)")

# Geometric mean of lifetime revenue at year 10 (mature 30+ videos)
mature30 = df30[df30["age_days"]>=180].copy()
mature30["scale_c"] = mature30["est_revenue_jpy"]/(mature30["age_days"]**k)
mature30["rev_year_10"] = mature30["scale_c"]*((10*365)**k)
geo_mean_lifetime = np.exp(np.log(mature30["rev_year_10"]).mean())
median_lifetime = mature30["rev_year_10"].median()
print(f"30+ min mature (n={len(mature30)}):")
print(f"  Geometric mean 10y lifetime : ¥{geo_mean_lifetime:>9,.0f}")
print(f"  Median 10y lifetime         : ¥{median_lifetime:>9,.0f}")

# V2 multiplier: +30% RPM × +15% views = 1.495x ≈ 1.5x
v2_mult = 1.30 * 1.15
print(f"V2 multiplier: {v2_mult:.2f}x")

# Per-video typical year-1 revenue
year1_share = (365**k) / ((10*365)**k)  # year 1 / 10y lifetime
print(f"Year 1 share = 1 / {(10*365)**k / 365**k:.2f} = {year1_share:.3f}")

scenarios = {
    "保守 (geom mean × V2)": geo_mean_lifetime * v2_mult,
    "中央値 × V2": median_lifetime * v2_mult,
    "保守 (V2なし)": geo_mean_lifetime,
}

# Project channel revenue for 1-10 years under monthly publication
def project(years: int, lifetime_per_video: float,
            n_per_year: int, existing_df: pd.DataFrame) -> dict:
    """ Compute total channel revenue accumulated over `years` years. """
    end_day = years * 365
    # Existing tail
    tail = 0
    for _, r in existing_df.iterrows():
        scale_c = r["views"] / (r["age_days"]**k) if r["age_days"]>0 else 0
        rpv = r["est_revenue_jpy"]/r["views"]
        a0 = r["age_days"]
        a1 = r["age_days"] + end_day
        future_views = scale_c * (a1**k - a0**k)
        tail += future_views * rpv
    # New videos: c_new = lifetime / (10y)^k
    c_new = lifetime_per_video / ((10*365)**k)
    new_revenue = 0
    interval = 365 / n_per_year
    tau = 0
    while tau < end_day:
        age_at_end = end_day - tau
        new_revenue += c_new * (age_at_end ** k)
        tau += interval
    return {"existing_tail": tail, "new": new_revenue,
            "total": tail + new_revenue}

# Annual revenue calculation per scenario
print(f"\n=== Channel年商投影 (k={k:.2f}, 月 1 本ペース) ===")
print(f"{'シナリオ':<30s}{'1y累計':>10s}{'年率':>10s}{'5y累計':>10s}{'5y年率':>10s}{'10y累計':>10s}")
for name, lifetime in scenarios.items():
    proj_1 = project(1, lifetime, 12, df30_all)
    proj_5 = project(5, lifetime, 12, df30_all)
    proj_10 = project(10, lifetime, 12, df30_all)
    print(f"{name:<30s} ¥{proj_1['total']:>8,.0f} ¥{proj_1['total']:>8,.0f}/年 "
          f"¥{proj_5['total']:>8,.0f} ¥{proj_5['total']/5:>8,.0f}/年 "
          f"¥{proj_10['total']:>8,.0f}")

print(f"\n=== Different cadences (V2 lifetime ¥{geo_mean_lifetime*v2_mult/10000:.0f}万) ===")
for cadence_name, n_per in [("月 1 本", 12), ("月 1.5 本", 18), ("月 2 本", 24)]:
    p5 = project(5, geo_mean_lifetime*v2_mult, n_per, df30_all)
    p10 = project(10, geo_mean_lifetime*v2_mult, n_per, df30_all)
    print(f"{cadence_name:<10s}: 5y累計 ¥{p5['total']:,.0f} (年¥{p5['total']/5:,.0f})  "
          f"10y累計 ¥{p10['total']:,.0f} (年¥{p10['total']/10:,.0f})")

# Investment & wealth simulation under conservative scenario
print(f"\n=== ライフプラン Phase 1 再計算（保守シナリオ）===")
# Assume: V2 + month 1 pace
target_lifetime = geo_mean_lifetime * v2_mult
proj_5 = project(5, target_lifetime, 12, df30_all)
proj_10 = project(10, target_lifetime, 12, df30_all)

avg_annual_5 = proj_5["total"] / 5
avg_annual_10 = proj_10["total"] / 10

# Phase 1 income components
print(f"\n[Phase 1 月収構成・5 年平均]")
print(f"  YouTube 月平均  : ¥{avg_annual_5/12:>9,.0f} ({avg_annual_5/12/10000:.0f}万円)")
print(f"  YouTube 年商    : ¥{avg_annual_5:>9,.0f} ({avg_annual_5/10000:.0f}万円)")
print(f"  バイト 月収 (15万円想定): ¥150,000")
print(f"  合計月収        : ¥{150000 + avg_annual_5/12:>9,.0f} ({(150000+avg_annual_5/12)/10000:.0f}万円)")

# Investment capacity
print(f"\n[投資原資・5 年平均]")
# Assume living expenses + tax 17万/月 = 204万/年 covered by baito
# YouTube 全額投資
print(f"  YouTube → 投資  : ¥{avg_annual_5:>9,.0f}/年 ({avg_annual_5/10000:.0f}万円/年)")
# Tax shelter: NISA + iDeCo + 小規模
print(f"  NISA つみたて (年120万)")
print(f"  iDeCo (年27.6万 or 81.6万)")
print(f"  残り → NISA 成長枠 / 普通預金")

# Wealth at year 10 (5% return)
def compound(annual_invest, years, rate=0.05):
    total = 0
    for y in range(years):
        total = (total + annual_invest) * (1+rate)
    return total

print(f"\n[10 年後の資産]")
for rate, label in [(0.05, "年率 5%"), (0.07, "年率 7%")]:
    wealth_year_5 = compound(avg_annual_5, 5, rate)
    wealth_year_10 = compound(avg_annual_5, 10, rate)
    print(f"  {label}: 5y → ¥{wealth_year_5:,.0f} ({wealth_year_5/10000:.0f}万円)  "
          f"10y → ¥{wealth_year_10:,.0f} ({wealth_year_10/10000:.0f}万円)")

# Channel value at year 10 (remaining lifetime value of catalog)
# Approximation: existing tail value over next 10 years (already computed) + new videos remaining value
print(f"\n[10 年時点のチャネル残存価値]")
# Already-built catalog of existing + 10 years of new releases
# Each new video at year 10 has age 0-3650 days; remaining = lifetime - earned
new_remaining = 0
c_new = target_lifetime / ((10*365)**k)
interval = 365/12
tau = 0
while tau < 10*365:
    age_at_year10 = 10*365 - tau
    remaining = target_lifetime - c_new * (age_at_year10**k)
    new_remaining += max(0, remaining)
    tau += interval
print(f"  新作カタログの残存価値（V2 想定）: ¥{new_remaining:,.0f} ({new_remaining/10000:.0f}万円)")
total_year_10 = wealth_year_10 + new_remaining
print(f"  10 年時点の総資産（投資 + チャネル残存）: ¥{total_year_10:,.0f} ({total_year_10/10000:.0f}万円)")
