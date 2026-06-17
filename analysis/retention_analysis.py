"""
Compare real retention curves against the synthetic model and
re-evaluate ad-slot placement using actual viewer drop-off data.

Inputs:
  data/retention/<video_id>.csv (visually digitized curves)
  data/ad_slots/breaks.csv     (current slot configuration)
  analysis/report/cleaned.csv  (analytics)

Outputs:
  analysis/report/retention_calibration.csv (synthetic vs real)
  analysis/report/retention_curves.png (overlay plot)
  analysis/report/slot_real_reach.csv (actual reach per slot)
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
RETENTION_DIR = ROOT / "data" / "retention"
BREAKS = ROOT / "data" / "ad_slots" / "breaks.csv"
ANALYTICS = ROOT / "analysis" / "report" / "cleaned.csv"
OUT_DIR = ROOT / "analysis" / "report"


# Synthetic curve used in prior analyses
SYNTHETIC = [
    (0.00, 1.00), (0.02, 0.85), (0.05, 0.78), (0.10, 0.70),
    (0.20, 0.58), (0.30, 0.48), (0.40, 0.40), (0.50, 0.32),
    (0.60, 0.25), (0.70, 0.20), (0.80, 0.15), (0.90, 0.10),
    (1.00, 0.06),
]


def synth(pct: float) -> float:
    pct = max(0.0, min(1.0, pct))
    for (p1, r1), (p2, r2) in zip(SYNTHETIC, SYNTHETIC[1:]):
        if p1 <= pct <= p2:
            t = (pct - p1) / (p2 - p1) if p2 > p1 else 0
            return r1 + t * (r2 - r1)
    return SYNTHETIC[-1][1]


def real_reach(curve: pd.DataFrame, sec: float) -> float:
    """Linearly interpolate retention at given sec from a digitized curve."""
    curve = curve.sort_values("position_sec").reset_index(drop=True)
    if sec <= curve["position_sec"].iloc[0]:
        return curve["retention_pct"].iloc[0] / 100
    if sec >= curve["position_sec"].iloc[-1]:
        return curve["retention_pct"].iloc[-1] / 100
    for i in range(len(curve) - 1):
        s1, s2 = curve["position_sec"].iloc[i], curve["position_sec"].iloc[i+1]
        if s1 <= sec <= s2:
            r1, r2 = curve["retention_pct"].iloc[i], curve["retention_pct"].iloc[i+1]
            t = (sec - s1) / (s2 - s1) if s2 > s1 else 0
            return (r1 + t * (r2 - r1)) / 100
    return curve["retention_pct"].iloc[-1] / 100


# ---- Load -----------------------------------------------------------
analytics = pd.read_csv(ANALYTICS)
breaks = pd.read_csv(BREAKS)
breaks["has_warning"] = breaks["has_warning"].astype(str).str.upper().eq("TRUE")

retention_files = sorted(RETENTION_DIR.glob("*.csv"))
retention_files = [f for f in retention_files if f.name not in {"REQUEST_LIST.csv"}]

curves = {}
for f in retention_files:
    vid = f.stem
    curves[vid] = pd.read_csv(f)

print(f"Loaded {len(curves)} retention curves: {sorted(curves.keys())}\n")


# ---- Per-video calibration -----------------------------------------
calib = []
for vid, curve in curves.items():
    a = analytics[analytics["video_id"] == vid].iloc[0]
    length = a["length_sec"]
    avg_watch = a["avg_watch_sec"]

    real_at_avg = real_reach(curve, avg_watch)
    synth_at_avg = synth(avg_watch / length)
    real_at_30s = real_reach(curve, 30)

    # Compute area under curve = expected avg view %
    pcts = curve["retention_pct"].values / 100
    secs = curve["position_sec"].values
    auc = np.trapezoid(pcts, secs) / length

    calib.append({
        "video_id": vid,
        "title": str(a["title"])[:38],
        "length_min": round(length / 60, 1),
        "avg_watch_min": round(avg_watch / 60, 1),
        "real_at_30s_pct": round(real_at_30s * 100, 1),
        "real_at_avg_watch_pct": round(real_at_avg * 100, 1),
        "synth_at_avg_watch_pct": round(synth_at_avg * 100, 1),
        "delta_real_minus_synth": round((real_at_avg - synth_at_avg) * 100, 1),
        "auc_avg_view_pct": round(auc * 100, 1),
        "reported_avg_view_pct": round(a["avg_view_pct"], 1),
        "auc_vs_reported": round(auc * 100 - a["avg_view_pct"], 1),
    })

calib_df = pd.DataFrame(calib)
calib_df.to_csv(OUT_DIR / "retention_calibration.csv", index=False)
print("=" * 90)
print("Per-video calibration (synthetic vs real retention)")
print("=" * 90)
print(calib_df.to_string(index=False))


# ---- Per-slot real reach -------------------------------------------
slot_rows = []
for vid in curves.keys():
    curve = curves[vid]
    a = analytics[analytics["video_id"] == vid].iloc[0]
    bs = breaks[breaks["video_id"] == vid].sort_values("position_sec")
    for _, b in bs.iterrows():
        rr = real_reach(curve, b["position_sec"])
        sr = synth(b["position_sec"] / a["length_sec"])
        slot_rows.append({
            "video_id": vid,
            "break_index": int(b["break_index"]),
            "position_hms": b["position_hms"],
            "position_sec": int(b["position_sec"]),
            "position_pct": round(b["position_sec"] / a["length_sec"] * 100, 1),
            "real_reach_pct": round(rr * 100, 1),
            "synth_reach_pct": round(sr * 100, 1),
            "delta_pp": round((rr - sr) * 100, 1),
            "has_warning": b["has_warning"],
        })
slot_real = pd.DataFrame(slot_rows)
slot_real.to_csv(OUT_DIR / "slot_real_reach.csv", index=False)

print("\n" + "=" * 90)
print("Per-slot reach: real vs synthetic")
print("=" * 90)
print(slot_real.to_string(index=False))


# ---- Re-compute ads/session per video using real curves -------------
print("\n" + "=" * 90)
print("ads/session comparison: actual vs synthetic-model vs real-curve-model")
print("=" * 90)
recomp = []
for vid in curves.keys():
    a = analytics[analytics["video_id"] == vid].iloc[0]
    if pd.isna(a["monetized_playbacks"]) or a["monetized_playbacks"] == 0:
        continue
    actual_aps = a["ad_impressions"] / a["monetized_playbacks"]
    bs = breaks[(breaks["video_id"] == vid)].sort_values("position_sec")
    # Dedupe slots <30s apart
    eff_pos = []
    last = -1e9
    for _, b in bs.iterrows():
        if b["position_sec"] - last >= 30:
            eff_pos.append(b["position_sec"])
            last = b["position_sec"]
    real_mid = sum(real_reach(curves[vid], p) for p in eff_pos)
    synth_mid = sum(synth(p / a["length_sec"]) for p in eff_pos)
    recomp.append({
        "video_id": vid,
        "title": str(a["title"])[:35],
        "actual_aps": round(actual_aps, 2),
        "synth_model_aps": round(1 + synth_mid, 2),
        "real_model_aps": round(1 + real_mid, 2),
        "synth_gap": round(actual_aps - (1 + synth_mid), 2),
        "real_gap": round(actual_aps - (1 + real_mid), 2),
    })
recomp_df = pd.DataFrame(recomp)
print(recomp_df.to_string(index=False))


# ---- Optimal slot positions per video using REAL curve --------------
print("\n" + "=" * 90)
print("Optimal slot positions using REAL retention (5 min gap, first ≥3:30)")
print("=" * 90)


def find_optimal_real(vid: str, length_sec: float, avg_watch_sec: float,
                       gap_min: float = 5.0, first_min_floor: float = 3.5):
    horizon = avg_watch_sec  # algorithm-safe: don't place past avg watch
    best_score = -1
    best_positions = []
    for first_sec in [3.5*60, 4.0*60, 4.5*60, 5.0*60]:
        pos = []
        t = first_sec
        while t <= horizon:
            pos.append(t)
            t += gap_min * 60
        # score = sum reach
        score = sum(real_reach(curves[vid], p) for p in pos)
        if score > best_score:
            best_score = score
            best_positions = pos
    return best_positions, best_score


for vid in curves.keys():
    a = analytics[analytics["video_id"] == vid].iloc[0]
    pos, reach = find_optimal_real(vid, a["length_sec"], a["avg_watch_sec"])
    pos_str = " / ".join(f"{int(p//60)}:{int(p%60):02d}" for p in pos)
    print(f"  {vid:14s} (avg_watch {a['avg_watch_sec']/60:.1f}min): "
          f"{len(pos)} mid @ {pos_str}  Σreach={reach:.2f}")


# ---- Plot retention curves ------------------------------------------
fig, ax = plt.subplots(figsize=(12, 6))

# Synthetic reference
synth_pcts = np.linspace(0, 1, 100)
synth_vals = [synth(p) * 100 for p in synth_pcts]
ax.plot(synth_pcts * 100, synth_vals, "--", color="black", linewidth=2,
        alpha=0.7, label="合成モデル（仮定）")

palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
for color, (vid, curve) in zip(palette, curves.items()):
    a = analytics[analytics["video_id"] == vid].iloc[0]
    length = a["length_sec"]
    pcts = curve["position_sec"] / length * 100
    ax.plot(pcts, curve["retention_pct"], "-", color=color, linewidth=1.6,
            label=f"{vid} ({length/60:.0f}min)")

    # Mark current slot positions on curve
    bs = breaks[breaks["video_id"] == vid].sort_values("position_sec")
    for _, b in bs.iterrows():
        rr = real_reach(curve, b["position_sec"])
        marker = "X" if b["has_warning"] else "o"
        ax.scatter(b["position_sec"]/length*100, rr*100,
                   color=color, marker=marker, s=70,
                   edgecolor="black", linewidth=0.5, zorder=5)

ax.set_xlabel("動画内の位置（%）")
ax.set_ylabel("視聴維持率（%）")
ax.set_title("視聴維持率カーブ: 合成モデル vs 実データ "
             "(○ = 現状スロット, X = 警告付きスロット)")
ax.legend(loc="upper right", fontsize=8)
ax.grid(True, alpha=0.3)
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)

plt.tight_layout()
out_png = OUT_DIR / "retention_curves.png"
plt.savefig(out_png, dpi=140)
print(f"\nWrote: {out_png}")
print(f"Wrote: {OUT_DIR / 'retention_calibration.csv'}")
print(f"Wrote: {OUT_DIR / 'slot_real_reach.csv'}")
