"""
Life-plan revenue projection: 5 active years + 5 harvest years
with optional graduation-induced accelerated decay.

Realistic constraints:
  1. VTuber subject (Ange) likely to graduate within ~5 years
  2. Post-graduation, decay accelerates: new viewer inflow dries up,
     algorithmic recommendation weakens, genre nostalgia fades
  3. Model: multiply natural-decay revenue by g(t) where
     g(t) = 1 for t <= T_grad, exp(-λ_post * (t - T_grad)) afterwards

Scenarios for λ_post (post-grad additional decay rate):
  0.0  : no graduation effect (current channel continues forever)
  0.2  : mild — still strong nostalgia (year 10 = 37% of natural)
  0.3  : standard — gradual fade (year 10 = 22% of natural)
  0.5  : severe — talent forgotten quickly (year 10 = 8% of natural)
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

c_new = geo_mean / ((10*365)**k)
T_GRAD = 5  # graduation year


def grad_factor(year_idx: int, lam_post: float) -> float:
    """ Year-mid graduation discount factor. Applied to year `year_idx`. """
    if year_idx <= T_GRAD:
        return 1.0
    # Use year mid-point for the year's discount
    return float(np.exp(-lam_post * (year_idx - 0.5 - T_GRAD)))


def existing_tail_revenue(start_day: int, end_day: int) -> float:
    total = 0
    for _, r in df30_all.iterrows():
        scale_c = r["views"] / (r["age_days"]**k)
        rpv = r["est_revenue_jpy"]/r["views"]
        a0 = r["age_days"] + start_day
        a1 = r["age_days"] + end_day
        total += scale_c * (a1**k - a0**k) * rpv
    return total


def yearly_revenue(year_idx: int, n_active_years: int, n_per_year: int,
                   lam_post: float) -> dict:
    start = (year_idx - 1) * 365
    end = year_idx * 365
    tail = existing_tail_revenue(start, end)
    interval = 365 / n_per_year
    new_total = 0
    max_publish_day = n_active_years * 365
    tau = 0
    while tau < max_publish_day:
        a0 = max(1, start - tau)
        a1 = end - tau
        if a1 > a0:
            new_total += c_new * (a1**k - a0**k)
        tau += interval
    g = grad_factor(year_idx, lam_post)
    return {"year": year_idx, "tail": tail*g, "new": new_total*g,
            "total": (tail+new_total)*g, "g": g}


def residual_value(n_active_years: int, n_per_year: int, lam_post: float,
                   horizon_years: int = 20) -> float:
    """ Catalog earnings from year 11 to horizon, year-by-year with grad discount. """
    total = 0
    interval = 365/n_per_year
    for y in range(11, horizon_years + 1):
        start = (y - 1) * 365
        end = y * 365
        tail = existing_tail_revenue(start, end)
        new_total = 0
        tau = 0
        while tau < n_active_years*365:
            a0 = max(1, start - tau)
            a1 = end - tau
            if a1 > a0:
                new_total += c_new * (a1**k - a0**k)
            tau += interval
        g = float(np.exp(-lam_post * (y - 0.5 - T_GRAD))) if lam_post > 0 else 1.0
        total += (tail + new_total) * g
    return total


def compound(yearly_revs, rate):
    bal = 0
    for v in yearly_revs:
        bal = (bal + v) * (1 + rate)
    return bal


def run(label: str, n_per: int, lam_post: float):
    revs = [yearly_revenue(y, T_GRAD, n_per, lam_post)["total"] for y in range(1, 11)]
    cum5 = sum(revs[:5])
    cum10 = sum(revs)
    p5_5 = compound(revs[:5], 0.05) * (1.05**5)  # let years 6-10 also compound
    # simpler: compound full 10 years where years 6-10 contribute their (decayed) rev
    p10_5 = compound(revs, 0.05)
    p10_7 = compound(revs, 0.07)
    res = residual_value(T_GRAD, n_per, lam_post)
    t5 = p10_5 + res + 2_000_000
    t7 = p10_7 + res + 2_000_000
    return {"label": label, "n_per": n_per, "lam": lam_post,
            "5y累計": cum5, "10y累計": cum10,
            "p5%": p10_5, "p7%": p10_7, "残存": res,
            "総資産5%": t5, "総資産7%": t7,
            "yearly": revs}


print(f"\n{'='*100}")
print("ペース × 卒業逓減シナリオ — 10 年累計 (万円)")
print(f"{'='*100}")
print(f"{'ペース':<10}{'λ_post':<10}{'5y累計':>10}{'10y累計':>10}{'残存':>10}{'総資産5%':>12}{'総資産7%':>12}")
print("-" * 80)
all_results = []
for label, n_per in [("月1本", 12), ("月1.5本", 18), ("月2本", 24)]:
    for lam in [0.0, 0.2, 0.3, 0.5]:
        r = run(label, n_per, lam)
        all_results.append(r)
        lam_label = f"{lam:.1f}({'なし' if lam==0 else '緩' if lam<0.25 else '標準' if lam<0.4 else '急'})"
        print(f"{label:<10}{lam_label:<10}"
              f"¥{r['5y累計']/10000:>7,.0f}万¥{r['10y累計']/10000:>7,.0f}万"
              f"¥{r['残存']/10000:>7,.0f}万¥{r['総資産5%']/10000:>9,.0f}万"
              f"¥{r['総資産7%']/10000:>9,.0f}万")

# Detail year-by-year for 月2本 × λ=0.3 (standard scenario)
print(f"\n=== 推奨シナリオ詳細: 月 2 本 × λ_post=0.3（標準） ===")
target = next(r for r in all_results if r["label"]=="月2本" and r["lam"]==0.3)
print(f"{'年次':<8}{'年商':>14}{'卒業係数':>10}")
for y, v in enumerate(target["yearly"], 1):
    g = grad_factor(y, 0.3)
    note = " ←制作終了/卒業想定" if y == 5 else ""
    print(f"{y}年目  ¥{v:>11,.0f} ({v/10000:>4.0f}万)  ×{g:.2f}{note}")
