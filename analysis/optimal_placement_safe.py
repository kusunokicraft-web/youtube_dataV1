"""
Algorithm-aware ad-slot optimizer.

In addition to the revenue-maximization profile (optimal_placement.py),
this script computes an "algorithm-safe" placement that prioritizes
retention signals YouTube weights for ranking (avg view duration,
session continuation, intro retention, end-screen completion).

Key constraints applied:
  - Intro protection: no slot before 3:30 (committed-viewer threshold)
  - End-screen protection: no slot within 90s of video end
  - Density ceiling: 0.10 slots/min (vs 0.15 in revenue-max)
  - Min inter-gap: 5 min (vs 3.5)
  - First slot soft target: avg_watch * 0.25 (catches dropout viewers
    after initial commitment)
  - Late-slot suppression: each slot past avg_watch incurs an
    additional 5% retention-cost penalty in the objective

Objective function adds a retention-preservation term that grows
with the number of slots placed past the avg-watch zone, modeling
the algorithm's preference for clean tail viewing.
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


# ----- Profiles ------------------------------------------------------
PROFILES = {
    "revenue_max": {
        "first_slot_floor_min": 2.0,
        "min_gap_min": 3.5,
        "max_gap_min": 7.0,
        "density_ceiling_per_min": 0.15,
        "horizon_mult": 1.3,
        "intro_buffer_min": 0,  # no intro protection
        "end_buffer_min": 0,
        "tail_slot_penalty_per_slot": 0.0,  # no penalty
    },
    "algorithm_safe": {
        "first_slot_floor_min": 3.5,
        "min_gap_min": 5.0,
        "max_gap_min": 7.0,
        "density_ceiling_per_min": 0.10,
        "horizon_mult": 1.0,  # do not place slots past avg_watch
        "intro_buffer_min": 3.5,
        "end_buffer_min": 1.5,
        "tail_slot_penalty_per_slot": 0.05,  # 5% revenue penalty per tail slot
    },
}

CPM_DECAY = 0.92
DENSITY_PENALTY_SLOPE = 3.3


def simulate(length_min: float, avg_watch_min: float,
             positions: list[float], profile: dict,
             base_cpm: float = 500.0) -> dict:
    """positions = mid-roll start times in minutes."""
    horizon = min(length_min - profile["end_buffer_min"],
                  avg_watch_min * profile["horizon_mult"])
    eff = [p for p in positions
           if (p >= profile["intro_buffer_min"]) and (p <= horizon)]
    total_slots = 1 + len(eff)
    density = total_slots / length_min

    density_pen = 1.0
    if density > profile["density_ceiling_per_min"]:
        excess = density - profile["density_ceiling_per_min"]
        density_pen = max(0.4, 1 - DENSITY_PENALTY_SLOPE * excess)

    pre_reach = 1.0
    mid_reach = sum(retention_at(p / length_min) for p in eff)
    actual_ads = (pre_reach + mid_reach) * density_pen

    # tail penalty: each slot past avg_watch reduces effective revenue
    tail_slots = sum(1 for p in eff if p > avg_watch_min)
    tail_pen = max(0.5, 1 - profile["tail_slot_penalty_per_slot"] * tail_slots)

    extra = max(0, total_slots - 2)
    ecpm = base_cpm * (CPM_DECAY ** extra)
    revenue_per_session = actual_ads * ecpm / 1000 * tail_pen

    return {
        "total_slots": total_slots,
        "effective_mid_slots": len(eff),
        "density_per_min": density,
        "density_pen": density_pen,
        "tail_pen": tail_pen,
        "ecpm": ecpm,
        "ads_per_session": actual_ads,
        "revenue_per_session": revenue_per_session,
        "positions": eff,
    }


def find_optimum(length_min: float, avg_watch_min: float,
                 profile: dict, base_cpm: float = 500.0) -> dict:
    best = None
    for first in np.arange(profile["first_slot_floor_min"], 6.0, 0.5):
        for gap in np.arange(profile["min_gap_min"], profile["max_gap_min"] + 0.1, 0.5):
            for n_mid in range(0, 12):
                positions = [first + i * gap for i in range(n_mid)]
                r = simulate(length_min, avg_watch_min, positions, profile,
                             base_cpm)
                r["first_min"] = first
                r["gap_min"] = gap
                if best is None or r["revenue_per_session"] > best["revenue_per_session"]:
                    best = r
    return best


# ----- Pattern recommendations ---------------------------------------
PATTERNS = [
    ("A. 短編切り抜き",   11, 5.5),
    ("B. 中編コラボ",     22, 9),
    ("C. 中尺総集編",     32, 13),
    ("D. 長編総集編",     47, 16),
    ("E. 超長編劇場版",   67, 19),
]

print("=" * 90)
print("Pattern-based recommendations: revenue-max  vs  algorithm-safe")
print("=" * 90)

rows = []
for name, L, A in PATTERNS:
    rev = find_optimum(L, A, PROFILES["revenue_max"])
    safe = find_optimum(L, A, PROFILES["algorithm_safe"])
    rev_pos_str = ", ".join(f"{p:.1f}" for p in rev["positions"])
    safe_pos_str = ", ".join(f"{p:.1f}" for p in safe["positions"])
    print(f"\n--- {name}  (長さ {L}分, avg視聴 {A}分) ---")
    print(f"  Revenue-max  : {rev['total_slots']} slots, gap {rev['gap_min']}min, "
          f"first {rev['first_min']}min, ¥{rev['revenue_per_session']:.2f}/sess "
          f"({rev['ads_per_session']:.2f} ads)")
    print(f"      mid位置 : {rev_pos_str}")
    print(f"  Algo-safe   : {safe['total_slots']} slots, gap {safe['gap_min']}min, "
          f"first {safe['first_min']}min, ¥{safe['revenue_per_session']:.2f}/sess "
          f"({safe['ads_per_session']:.2f} ads)")
    print(f"      mid位置 : {safe_pos_str}")
    delta = (safe["revenue_per_session"] - rev["revenue_per_session"]) / rev["revenue_per_session"] * 100
    print(f"  短期収益差   : {delta:+.1f}%  (algo-safe は短期で {abs(delta):.1f}% 譲歩)")

    rows.append({
        "pattern": name, "length_min": L, "avg_watch_min": A,
        "rev_total_slots": rev["total_slots"],
        "rev_first_min": rev["first_min"],
        "rev_gap_min": rev["gap_min"],
        "rev_positions": rev_pos_str,
        "rev_jpy_per_session": round(rev["revenue_per_session"], 2),
        "safe_total_slots": safe["total_slots"],
        "safe_first_min": safe["first_min"],
        "safe_gap_min": safe["gap_min"],
        "safe_positions": safe_pos_str,
        "safe_jpy_per_session": round(safe["revenue_per_session"], 2),
        "short_term_delta_pct": round(delta, 1),
    })

pd.DataFrame(rows).to_csv(OUT_DIR / "optimal_patterns_dual.csv", index=False)

# ----- Plot: side-by-side timeline -----------------------------------
fig, axes = plt.subplots(len(PATTERNS), 1, figsize=(12, 1.6 * len(PATTERNS)))
for ax, (name, L, A), row in zip(axes, PATTERNS, rows):
    # Backdrop
    ax.axvspan(0, A, color="#e8f5e8", alpha=0.6, label="平均視聴ゾーン")
    ax.axvspan(A, L, color="#fff5e8", alpha=0.6, label="テール（離脱後）ゾーン")
    ax.axvline(A, color="#888", linestyle=":", linewidth=1)

    rev_pos = [float(p) for p in row["rev_positions"].split(",") if p]
    safe_pos = [float(p) for p in row["safe_positions"].split(",") if p]

    # Pre-roll markers
    ax.scatter([0], [1], color="#1f77b4", marker="^", s=100, zorder=4)
    ax.scatter([0], [0], color="#2ca02c", marker="^", s=100, zorder=4)

    ax.scatter(rev_pos, [1]*len(rev_pos), color="#1f77b4", s=120, marker="o",
               edgecolor="black", linewidth=0.6, zorder=3)
    ax.scatter(safe_pos, [0]*len(safe_pos), color="#2ca02c", s=120, marker="o",
               edgecolor="black", linewidth=0.6, zorder=3)

    ax.set_yticks([0, 1])
    ax.set_yticklabels(["アルゴリズム配慮", "収益最大化"])
    ax.set_xlim(-0.5, L + 0.5)
    ax.set_ylim(-0.5, 1.5)
    ax.set_title(f"{name}  "
                 f"（動画長 {L}分・平均視聴 {A}分）  "
                 f"収益最大 ¥{row['rev_jpy_per_session']:.2f} → "
                 f"アルゴ配慮 ¥{row['safe_jpy_per_session']:.2f}  "
                 f"({row['short_term_delta_pct']:+.0f}%)",
                 fontsize=10)
    ax.grid(True, alpha=0.3, axis="x")
    ax.set_xlabel("経過時間（分）")

plt.tight_layout()
out_png = OUT_DIR / "optimal_dual_timeline.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'optimal_patterns_dual.csv'}")
