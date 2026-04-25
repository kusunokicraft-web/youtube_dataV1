"""
Generate ad-slot ingestion coverage report.

Joins data/ad_slots/breaks.csv against the long-form video universe
to produce data/ad_slots/coverage.csv: a per-video status that shows
which videos already have ad-break data and which are still missing,
ordered by revenue impact (highest first).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ANALYTICS = ROOT / "analysis" / "report" / "cleaned.csv"
BREAKS = ROOT / "data" / "ad_slots" / "breaks.csv"
SCREENSHOTS = ROOT / "data" / "ad_slots" / "screenshots"
OUT = ROOT / "data" / "ad_slots" / "coverage.csv"


def main() -> None:
    analytics = pd.read_csv(ANALYTICS)
    long_df = analytics[analytics["format"] == "Long"].copy()

    if BREAKS.exists():
        breaks = pd.read_csv(BREAKS)
    else:
        breaks = pd.DataFrame(columns=["video_id", "has_warning", "screenshot"])

    breaks["has_warning"] = breaks["has_warning"].astype(str).str.upper().eq("TRUE")

    per_video = (
        breaks.groupby("video_id")
        .agg(
            slots_recorded=("break_index", "count"),
            warnings=("has_warning", "sum"),
            screenshots=("screenshot", lambda s: ",".join(sorted(set(x for x in s if isinstance(x, str))))),
        )
        .reset_index()
    )

    cov = long_df.merge(per_video, on="video_id", how="left")
    cov["slots_recorded"] = cov["slots_recorded"].fillna(0).astype(int)
    cov["warnings"] = cov["warnings"].fillna(0).astype(int)
    cov["screenshots"] = cov["screenshots"].fillna("")
    cov["status"] = cov["slots_recorded"].map(lambda n: "ingested" if n > 0 else "pending")
    cov["screenshot_on_disk"] = cov["video_id"].map(
        lambda v: (SCREENSHOTS / f"{v}.png").exists()
        or any(SCREENSHOTS.glob(f"{v}*"))
    )

    cov_out = cov[
        [
            "video_id",
            "title",
            "published_at",
            "length_sec",
            "avg_watch_sec",
            "views",
            "est_revenue_jpy",
            "status",
            "slots_recorded",
            "warnings",
            "screenshot_on_disk",
            "screenshots",
        ]
    ].sort_values("est_revenue_jpy", ascending=False)

    cov_out.to_csv(OUT, index=False)

    total = len(cov_out)
    done = (cov_out["status"] == "ingested").sum()
    rev_done = cov_out.loc[cov_out["status"] == "ingested", "est_revenue_jpy"].sum()
    rev_total = cov_out["est_revenue_jpy"].sum()

    print(f"Coverage: {done}/{total} videos ingested "
          f"({done/total*100:.0f}% by count, {rev_done/rev_total*100:.0f}% by revenue)")
    print(f"Wrote: {OUT.relative_to(ROOT)}\n")

    pending = cov_out[cov_out["status"] == "pending"].head(10)
    if not pending.empty:
        print("Top pending videos by revenue:")
        for _, row in pending.iterrows():
            print(f"  {row['video_id']}  ¥{row['est_revenue_jpy']:>10,.0f}  "
                  f"{str(row['title'])[:50]}")


if __name__ == "__main__":
    main()
