"""
Optimal slot count / gap / video length simulator.

Given a video's length and avg_watch_min, sweeps slot count
and gap, applies the empirically-calibrated penalties (slot
density ceiling 0.15/min, eCPM decay 8% per extra slot above 2),
and reports the configuration that maximizes projected revenue
per monetized session.

Pattern-based recommendations are produced for the four length
buckets observed in the data.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ANALYTICS = ROOT / "analysis" / "report" / "cleaned.csv"
PV = ROOT / "analysis" / "report" / "ad_slots_per_video.csv"
OUT_DIR = ROOT / "analysis" / "report"

# ---- Calibrated retention curve (from breaks_audit.py) ---------------
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


# ---- Penalty parameters (from H5 + industry estimates) --------------
DENSITY_CEILING = 0.15  # slots per minute (incl. pre-roll)
DENSITY_PENALTY_SLOPE = 3.3  # at 0.30 slots/min, 50% of slots fail to fire
CPM_DECAY = 0.92  # eCPM multiplier for each slot beyond the 2nd
GAP_MIN = 30 / 60  # YouTube min spacing 30s
HORIZON_MULT = 1.3  # consider slots up to avg_watch * 1.3
FIRST_SLOT_FLOOR = 3.5  # don't put 1st slot before 3:30 (ad-quality buffer)


def simulate(length_min: float, avg_watch_min: float,
             n_mid_slots: int, gap_min: float,
             first_min: float, base_cpm: float = 500.0) -> dict:
    """Return projected metrics for a given configuration."""
    horizon = min(length_min, avg_watch_min * HORIZON_MULT)
    positions = [first_min + i * gap_min for i in range(n_mid_slots)]
    # drop slots beyond horizon (they generate ~zero impressions)
    eff_positions = [p for p in positions if p <= horizon]
    eff_mid = len(eff_positions)
    total_slots = 1 + eff_mid  # + pre-roll

    # Density check
    density = total_slots / length_min
    density_pen = 1.0
    if density > DENSITY_CEILING:
        excess = density - DENSITY_CEILING
        density_pen = max(0.4, 1 - DENSITY_PENALTY_SLOPE * excess)

    # Reach: pre-roll always; mid-rolls weighted by retention at their position
    pre_reach = 1.0
    mid_reach = sum(retention_at(p / length_min) for p in eff_positions)
    raw_ads_per_session = pre_reach + mid_reach
    actual_ads_per_session = raw_ads_per_session * density_pen

    # eCPM decay (each slot beyond the 2nd erodes eCPM)
    extra = max(0, total_slots - 2)
    ecpm = base_cpm * (CPM_DECAY ** extra)

    revenue_per_session = actual_ads_per_session * ecpm / 1000

    return {
        "n_mid_slots_configured": n_mid_slots,
        "total_slots": total_slots,
        "effective_mid_slots": eff_mid,
        "gap_min": gap_min,
        "first_min": first_min,
        "density_per_min": density,
        "density_penalty": density_pen,
        "ecpm_after_decay": ecpm,
        "ads_per_session": actual_ads_per_session,
        "revenue_per_session": revenue_per_session,
        "positions": eff_positions,
    }


def find_optimum(length_min: float, avg_watch_min: float,
                 base_cpm: float = 500.0) -> dict:
    """Sweep gap and slot count, return the best configuration."""
    best = None
    grid = []
    for gap in [3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0]:
        for first in [2.0, 2.5, 3.0, 3.5, 4.0]:
            for n_mid in range(0, 12):
                r = simulate(length_min, avg_watch_min, n_mid, gap, first,
                             base_cpm)
                r["first_min"] = first
                grid.append(r)
                if best is None or r["revenue_per_session"] > best["revenue_per_session"]:
                    best = r
    return best, grid


# ---- Channel data ---------------------------------------------------
an = pd.read_csv(ANALYTICS)
long_df = an[an["format"] == "Long"].copy()
long_df["avg_watch_min"] = long_df["avg_watch_sec"] / 60
long_df["length_min"] = long_df["length_sec"] / 60

print("=" * 78)
print("Pattern-based optimal placement")
print("=" * 78)

PATTERNS = [
    ("A. 短編切り抜き", 10, 12, 5.5),
    ("B. 中編コラボ",   20, 25, 9),
    ("C. 中尺総集編",  30, 35, 13),
    ("D. 長編総集編",  45, 50, 16),
    ("E. 超長編劇場版", 65, 70, 19),
]

rows = []
for name, lo, hi, avg_watch in PATTERNS:
    mid_length = (lo + hi) / 2
    best, _ = find_optimum(mid_length, avg_watch)
    print(f"\n--- {name}  (長さ {lo}-{hi}分, avg視聴 {avg_watch}分想定) ---")
    print(f"  最適 mid-roll 数 : {best['n_mid_slots_configured']} 本 "
          f"(うち有効 {best['effective_mid_slots']} 本)")
    print(f"  合計 slot 数    : {best['total_slots']} 本 (pre-roll 含む)")
    print(f"  gap            : {best['gap_min']} 分")
    print(f"  first slot     : {best['first_min']} 分")
    print(f"  density        : {best['density_per_min']:.3f} slots/分")
    print(f"  推定 ads/session: {best['ads_per_session']:.2f}")
    print(f"  推定 ¥/session  : ¥{best['revenue_per_session']:.1f}")
    print(f"  配置 (mid-roll位置): {[f'{p:.1f}' for p in best['positions']]}")
    rows.append({
        "pattern": name,
        "length_range": f"{lo}-{hi}分",
        "avg_watch_min": avg_watch,
        "optimal_mid_slots": best["n_mid_slots_configured"],
        "effective_mid_slots": best["effective_mid_slots"],
        "total_slots_incl_preroll": best["total_slots"],
        "gap_min": best["gap_min"],
        "first_min": best["first_min"],
        "density_per_min": round(best["density_per_min"], 3),
        "projected_ads_per_session": round(best["ads_per_session"], 2),
        "projected_jpy_per_session": round(best["revenue_per_session"], 1),
        "mid_positions_min": ",".join(f"{p:.1f}" for p in best["positions"]),
    })

pd.DataFrame(rows).to_csv(OUT_DIR / "optimal_patterns.csv", index=False)

# ---- Optimal video length analysis ----------------------------------
print("\n" + "=" * 78)
print("Optimal video length (¥/session × likely view count)")
print("=" * 78)

# Use empirical relationship: avg_watch_min ≈ 0.32 × length_min^0.6
# Calibrated from long_df data
mask = long_df["length_min"] > 5
slope = np.polyfit(np.log(long_df.loc[mask, "length_min"]),
                   np.log(long_df.loc[mask, "avg_watch_min"]), 1)
print(f"Empirical avg_watch ≈ {np.exp(slope[1]):.2f} × length^{slope[0]:.2f}")

length_grid = np.arange(5, 80, 2.5)
length_results = []
for L in length_grid:
    A = np.exp(slope[1]) * (L ** slope[0])
    A = min(A, L * 0.7)  # cap retention% at 70%
    best, _ = find_optimum(L, A)
    length_results.append({
        "length_min": L,
        "avg_watch_min": round(A, 1),
        "optimal_total_slots": best["total_slots"],
        "projected_jpy_per_session": best["revenue_per_session"],
    })

lr = pd.DataFrame(length_results)
print(lr.to_string(index=False))
lr.to_csv(OUT_DIR / "optimal_length_curve.csv", index=False)

# ---- Plot 1: revenue per session vs video length -------------------
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

ax = axes[0]
ax.plot(lr["length_min"], lr["projected_jpy_per_session"],
        marker="o", color="#1f77b4", linewidth=2)
ax.set_xlabel("Video length (minutes)")
ax.set_ylabel("Projected revenue per monetized session (JPY)")
ax.set_title("Revenue per session vs video length\n(assuming optimal placement)")
ax.grid(True, alpha=0.3)
peak_idx = lr["projected_jpy_per_session"].idxmax()
ax.annotate(f"peak: {lr['length_min'][peak_idx]:.0f}min  "
            f"(¥{lr['projected_jpy_per_session'][peak_idx]:.1f}/session)",
            xy=(lr["length_min"][peak_idx], lr["projected_jpy_per_session"][peak_idx]),
            xytext=(20, 20), textcoords="offset points", fontsize=9,
            arrowprops=dict(arrowstyle="->", color="#d62728"))

# ---- Plot 2: optimal slot count vs length --------------------------
ax = axes[1]
ax.plot(lr["length_min"], lr["optimal_total_slots"],
        marker="s", color="#2ca02c", linewidth=2, label="Optimal total slots")
ax.plot(lr["length_min"], lr["length_min"] * 0.15,
        linestyle="--", color="#d62728", linewidth=1, label="Density ceiling 0.15/min")
ax.set_xlabel("Video length (minutes)")
ax.set_ylabel("Slot count")
ax.set_title("Optimal slot count by video length")
ax.legend()
ax.grid(True, alpha=0.3)

plt.tight_layout()
out_png = OUT_DIR / "optimal_length_slots.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'optimal_patterns.csv'}")
print(f"Wrote: {OUT_DIR / 'optimal_length_curve.csv'}")
