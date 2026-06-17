"""
Intervention log validator and status reporter.

Reads data/interventions/interventions.csv, validates schema, and reports:
  - Currently active (planned / executed / evaluating)
  - Due for evaluation (eval_after_days passed but status != evaluated)
  - Statistics by type / status

Usage:
    python analysis/intervention_log.py
"""

from datetime import date
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "interventions" / "interventions.csv"

REQUIRED_COLS = {
    "date", "target", "type", "change",
    "eval_after_days", "status", "evaluated_date", "result", "notes",
}
VALID_TYPES = {
    "ad_slot", "title", "thumbnail", "cadence", "length", "series",
    "collab", "meta", "description", "cohort_def",
    "strategy_decision", "external_event",
}
VALID_STATUSES = {"planned", "executed", "evaluating", "evaluated", "cancelled"}


def main() -> int:
    if not LOG.exists():
        print(f"ERROR: {LOG} does not exist")
        return 1

    df = pd.read_csv(LOG, parse_dates=["date"], dtype=str, keep_default_na=False)
    df["date"] = pd.to_datetime(df["date"])

    # ---- Schema validation ----
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        print(f"ERROR: missing columns {missing}")
        return 1

    issues = []
    for i, row in df.iterrows():
        if row["type"] not in VALID_TYPES:
            issues.append(f"row {i}: invalid type '{row['type']}'")
        if row["status"] not in VALID_STATUSES:
            issues.append(f"row {i}: invalid status '{row['status']}'")
        if not row["target"]:
            issues.append(f"row {i}: target is empty")
        if not row["change"]:
            issues.append(f"row {i}: change is empty")

    if issues:
        print("VALIDATION ISSUES:")
        for x in issues:
            print(f"  {x}")
        print()

    # ---- Stats ----
    print("=" * 70)
    print(f"介入ログサマリー（{LOG.name}）")
    print("=" * 70)
    print(f"総エントリ数: {len(df)}")
    print()
    print("Status 別:")
    for s, n in df["status"].value_counts().items():
        print(f"  {s:<12s}: {n}")
    print()
    print("Type 別:")
    for t, n in df["type"].value_counts().items():
        print(f"  {t:<20s}: {n}")
    print()

    # ---- Due for evaluation ----
    today = pd.Timestamp(date.today())
    needs_eval = df[df["status"].isin(["executed", "evaluating"])].copy()
    needs_eval["eval_days_int"] = pd.to_numeric(
        needs_eval["eval_after_days"], errors="coerce"
    )
    needs_eval = needs_eval[needs_eval["eval_days_int"].notna()]
    if len(needs_eval):
        needs_eval["eval_due"] = needs_eval["date"] + pd.to_timedelta(
            needs_eval["eval_days_int"].astype(int), unit="D"
        )
        overdue = needs_eval[needs_eval["eval_due"] <= today]
        upcoming = needs_eval[
            (needs_eval["eval_due"] > today)
            & (needs_eval["eval_due"] <= today + pd.Timedelta(days=30))
        ]
        if len(overdue):
            print("=" * 70)
            print(f"⚠️  評価期日を過ぎている介入: {len(overdue)} 件")
            print("=" * 70)
            for _, r in overdue.iterrows():
                days_over = (today - r["eval_due"]).days
                print(
                    f"  {r['date'].date()} | {r['type']:<18s} | "
                    f"target={r['target']:<15s} | "
                    f"期日 {r['eval_due'].date()} (+{days_over}日経過)"
                )
                print(f"    change: {r['change']}")
            print()
        if len(upcoming):
            print("=" * 70)
            print(f"📅 30 日以内に評価期日: {len(upcoming)} 件")
            print("=" * 70)
            for _, r in upcoming.iterrows():
                days_left = (r["eval_due"] - today).days
                print(
                    f"  {r['date'].date()} | {r['type']:<18s} | "
                    f"期日 {r['eval_due'].date()} ({days_left} 日後)"
                )
                print(f"    change: {r['change']}")

    # ---- Recent executed (last 90 days) ----
    recent = df[
        (df["date"] >= today - pd.Timedelta(days=90))
        & (df["status"].isin(["executed", "evaluating", "evaluated"]))
    ].sort_values("date", ascending=False)
    if len(recent):
        print()
        print("=" * 70)
        print(f"直近 90 日の介入: {len(recent)} 件")
        print("=" * 70)
        for _, r in recent.iterrows():
            print(
                f"  {r['date'].date()} | {r['type']:<18s} | "
                f"target={r['target']:<15s} | status={r['status']}"
            )
            print(f"    {r['change']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
