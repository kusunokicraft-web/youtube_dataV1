"""
YouTube channel analytics: professional exploratory data analysis.

Loads the analytics CSV, computes data-quality, descriptive, temporal,
format, engagement, monetization and correlation views, and writes
results to text/markdown output for the report.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "全期間公開済みyoutube動画アナリティクス - 表データ.csv"
OUT = ROOT / "analysis" / "report"
OUT.mkdir(parents=True, exist_ok=True)


# --- Load -------------------------------------------------------------
raw = pd.read_csv(CSV)
totals = raw.iloc[0].copy()
df = raw.iloc[1:].copy().reset_index(drop=True)

# Shorter, analysis-friendly names
rename = {
    "コンテンツ": "video_id",
    "動画のタイトル": "title",
    "動画公開時刻": "published_at",
    "長さ": "length_sec",
    "エンゲージ ビュー": "engaged_views",
    "平均視聴時間": "avg_watch_time",
    "平均視聴率 (%)": "avg_view_pct",
    "YouTube Premium (JPY)": "premium_jpy",
    "動画再生ページの広告 (JPY)": "page_ad_jpy",
    "推定 DoubleClick 収益 (JPY)": "doubleclick_jpy",
    "推定 AdSense 収益 (JPY)": "adsense_jpy",
    "YouTube 広告収益 (JPY)": "yt_ad_rev_jpy",
    "広告の表示回数": "ad_impressions",
    "再生回数に基づく CPM (JPY)": "cpm_playback_jpy",
    "CPM (JPY)": "cpm_jpy",
    "RPM (JPY)": "rpm_jpy",
    "収益化対象の推定再生回数": "monetized_playbacks",
    "YouTube Premium の視聴回数": "premium_views",
    "YouTube Premium 総再生時間（単位: 時間）": "premium_watch_hours",
    "終了画面要素のクリック数": "endscreen_clicks",
    "終了画面要素の表示回数": "endscreen_impressions",
    "終了画面要素のクリック率 (%)": "endscreen_ctr",
    "視聴回数": "views",
    "総再生時間（単位: 時間）": "watch_hours",
    "チャンネル登録者": "subs_gained",
    "推定収益 (JPY)": "est_revenue_jpy",
    "インプレッション数": "impressions",
    "インプレッションのクリック率 (%)": "impression_ctr",
}
df = df.rename(columns=rename)

# --- Type coercion ---------------------------------------------------
df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")

num_cols = [c for c in df.columns if c not in {"video_id", "title", "published_at", "avg_watch_time"}]
for c in num_cols:
    df[c] = pd.to_numeric(df[c], errors="coerce")


def _hms_to_sec(x: str | float) -> float:
    if pd.isna(x):
        return np.nan
    s = str(x)
    m = re.match(r"^(\d+):(\d+):(\d+)$", s)
    if not m:
        return np.nan
    h, mi, se = map(int, m.groups())
    return h * 3600 + mi * 60 + se


df["avg_watch_sec"] = df["avg_watch_time"].map(_hms_to_sec)

# Formats: YouTube Shorts (<= 60s) vs long-form
df["format"] = np.where(df["length_sec"] <= 60, "Shorts", "Long")

# Derived metrics
df["rev_per_view"] = df["est_revenue_jpy"] / df["views"]
df["watch_hours_per_view"] = df["watch_hours"] / df["views"]
df["subs_per_1k_views"] = df["subs_gained"] / df["views"] * 1000
df["impressions_per_view"] = df["impressions"] / df["views"]

# --- Reporting helpers -----------------------------------------------
lines: list[str] = []


def h(s: str, level: int = 2) -> None:
    lines.append("")
    lines.append("#" * level + " " + s)


def p(s: str = "") -> None:
    lines.append(s)


def tbl(frame: pd.DataFrame, floatfmt: str = "{:,.2f}") -> None:
    disp = frame.copy()
    for c in disp.columns:
        if pd.api.types.is_float_dtype(disp[c]):
            disp[c] = disp[c].map(lambda v: "" if pd.isna(v) else floatfmt.format(v))
        elif pd.api.types.is_integer_dtype(disp[c]):
            disp[c] = disp[c].map(lambda v: "" if pd.isna(v) else f"{int(v):,}")
    lines.append(disp.to_markdown(index=False))


def kv(label: str, value: str) -> None:
    lines.append(f"- **{label}**: {value}")


# --- 1. Data quality --------------------------------------------------
h("1. データ品質アセスメント")
kv("動画本数 (合計行除く)", f"{len(df)}")
kv("公開期間", f"{df['published_at'].min():%Y-%m-%d} 〜 {df['published_at'].max():%Y-%m-%d}")
kv("分析実行基準日", "2026-04-25")

missing = df[num_cols].isna().sum()
missing = missing[missing > 0].sort_values(ascending=False)
h("主要欠損", level=3)
if missing.empty:
    p("欠損なし")
else:
    miss_df = missing.rename("missing").to_frame()
    miss_df["rate_%"] = (miss_df["missing"] / len(df) * 100).round(1)
    tbl(miss_df.reset_index().rename(columns={"index": "field"}))

# Totals reconciliation
h("合計行との突き合わせ", level=3)
jp_field = {
    "views": "視聴回数",
    "engaged_views": "エンゲージ ビュー",
    "watch_hours": "総再生時間（単位: 時間）",
    "est_revenue_jpy": "推定収益 (JPY)",
    "subs_gained": "チャンネル登録者",
    "impressions": "インプレッション数",
}
rec = []
for f, jp in jp_field.items():
    reported = pd.to_numeric(totals[jp], errors="coerce")
    computed = df[f].sum(skipna=True)
    diff = computed - reported
    rec.append({
        "field": f,
        "reported": reported,
        "sum_of_rows": computed,
        "diff": diff,
        "diff_pct": (diff / reported * 100) if reported else np.nan,
    })
tbl(pd.DataFrame(rec))

# Anomalies
h("異常値・要確認データ", level=3)
anomalies = []
for _, r in df.iterrows():
    issues = []
    if pd.notna(r["avg_view_pct"]) and r["avg_view_pct"] > 100:
        issues.append(f"平均視聴率 {r['avg_view_pct']:.1f}% (>100%)")
    if pd.notna(r["subs_gained"]) and r["subs_gained"] < 0:
        issues.append(f"登録者 {int(r['subs_gained'])} (負値)")
    if pd.notna(r["impression_ctr"]) and r["impression_ctr"] == 0 and r["impressions"] > 0:
        issues.append("CTR=0%")
    if issues:
        anomalies.append({
            "video_id": r["video_id"],
            "title": r["title"][:40] + ("…" if len(str(r["title"])) > 40 else ""),
            "issues": "; ".join(issues),
        })
tbl(pd.DataFrame(anomalies))

# --- 2. Descriptive ---------------------------------------------------
h("2. 記述統計（主要KPI）")
kpis = ["views", "watch_hours", "est_revenue_jpy", "subs_gained", "rpm_jpy",
        "impression_ctr", "avg_view_pct", "length_sec"]
desc = df[kpis].describe(percentiles=[0.25, 0.5, 0.75, 0.9]).T
desc = desc[["count", "mean", "50%", "std", "min", "90%", "max"]].rename(
    columns={"50%": "median", "90%": "p90"}
)
tbl(desc.reset_index().rename(columns={"index": "metric"}))

# Concentration
sorted_views = df["views"].sort_values(ascending=False)
top1 = sorted_views.iloc[0] / sorted_views.sum() * 100
top5 = sorted_views.iloc[:5].sum() / sorted_views.sum() * 100
top10 = sorted_views.iloc[:10].sum() / sorted_views.sum() * 100
sorted_rev = df["est_revenue_jpy"].sort_values(ascending=False)
r_top1 = sorted_rev.iloc[0] / sorted_rev.sum() * 100
r_top5 = sorted_rev.iloc[:5].sum() / sorted_rev.sum() * 100
r_top10 = sorted_rev.iloc[:10].sum() / sorted_rev.sum() * 100

h("集中度（パレート分析）", level=3)
kv("視聴回数 Top1 / Top5 / Top10 のシェア", f"{top1:.1f}% / {top5:.1f}% / {top10:.1f}%")
kv("推定収益 Top1 / Top5 / Top10 のシェア", f"{r_top1:.1f}% / {r_top5:.1f}% / {r_top10:.1f}%")

# --- 3. Format split (Shorts vs Long) --------------------------------
h("3. フォーマット比較 (Shorts ≤60s vs Long)")
fmt = df.groupby("format").agg(
    videos=("video_id", "count"),
    total_views=("views", "sum"),
    total_rev_jpy=("est_revenue_jpy", "sum"),
    total_subs=("subs_gained", "sum"),
    median_views=("views", "median"),
    median_rpm=("rpm_jpy", "median"),
    median_ctr=("impression_ctr", "median"),
    median_view_pct=("avg_view_pct", "median"),
).reset_index()
fmt["rev_share_%"] = fmt["total_rev_jpy"] / fmt["total_rev_jpy"].sum() * 100
fmt["views_share_%"] = fmt["total_views"] / fmt["total_views"].sum() * 100
tbl(fmt)

# --- 4. Temporal analysis --------------------------------------------
h("4. 時系列分析")
df["year"] = df["published_at"].dt.year
yearly = df.groupby("year").agg(
    videos=("video_id", "count"),
    views=("views", "sum"),
    revenue=("est_revenue_jpy", "sum"),
    subs=("subs_gained", "sum"),
    median_views=("views", "median"),
    median_rpm=("rpm_jpy", "median"),
).reset_index().sort_values("year")
tbl(yearly)

# Age of video — how long it has been live (days) on 2026-04-25
asof = pd.Timestamp("2026-04-25")
df["age_days"] = (asof - df["published_at"]).dt.days
df["views_per_day"] = df["views"] / df["age_days"].replace(0, np.nan)

h("1日あたり視聴回数 (viral velocity)", level=3)
vel = df[["video_id", "title", "published_at", "age_days", "views", "views_per_day", "est_revenue_jpy"]].copy()
vel = vel.sort_values("views_per_day", ascending=False).head(10)
vel["title"] = vel["title"].str.slice(0, 50)
tbl(vel)

# --- 5. Engagement ---------------------------------------------------
h("5. エンゲージメント分析")
long_df = df[df["format"] == "Long"].copy()
short_df = df[df["format"] == "Shorts"].copy()

eng_stats = pd.DataFrame({
    "metric": ["impression_ctr", "avg_view_pct", "avg_watch_sec", "endscreen_ctr", "subs_per_1k_views"],
    "Long_median": [long_df[m].median() for m in ["impression_ctr", "avg_view_pct", "avg_watch_sec", "endscreen_ctr", "subs_per_1k_views"]],
    "Shorts_median": [short_df[m].median() for m in ["impression_ctr", "avg_view_pct", "avg_watch_sec", "endscreen_ctr", "subs_per_1k_views"]],
})
tbl(eng_stats)

# Best/worst CTR among long-form with meaningful impressions
h("Long-form インプレッションCTR上位/下位 (>=100k impressions)", level=3)
ctr_pool = long_df[long_df["impressions"] >= 100_000].copy()
top_ctr = ctr_pool.nlargest(5, "impression_ctr")[["title", "impressions", "impression_ctr", "views", "length_sec"]]
bot_ctr = ctr_pool.nsmallest(5, "impression_ctr")[["title", "impressions", "impression_ctr", "views", "length_sec"]]
top_ctr["title"] = top_ctr["title"].str.slice(0, 45)
bot_ctr["title"] = bot_ctr["title"].str.slice(0, 45)
p("**上位**")
tbl(top_ctr)
p("**下位**")
tbl(bot_ctr)

# --- 6. Monetization -------------------------------------------------
h("6. 収益性分析")
# Top revenue videos
top_rev = df.nlargest(10, "est_revenue_jpy")[
    ["video_id", "title", "published_at", "format", "views", "est_revenue_jpy", "rpm_jpy", "cpm_jpy"]
].copy()
top_rev["title"] = top_rev["title"].str.slice(0, 45)
h("推定収益 Top10", level=3)
tbl(top_rev)

# RPM distribution per format
h("RPM (1,000再生あたりJPY) 分布", level=3)
rpm = df.groupby("format")["rpm_jpy"].describe(percentiles=[0.25, 0.5, 0.75]).reset_index()
tbl(rpm)

# Long-form revenue efficiency (rev / view)
h("Long-form 収益効率: 収益/再生 Top5 & Bottom5 (>=50k views)", level=3)
eff_pool = long_df[long_df["views"] >= 50_000].copy()
eff_pool["yen_per_view"] = eff_pool["est_revenue_jpy"] / eff_pool["views"]
p("**収益効率Top5**")
te = eff_pool.nlargest(5, "yen_per_view")[["title", "views", "est_revenue_jpy", "yen_per_view", "rpm_jpy", "avg_view_pct"]].copy()
te["title"] = te["title"].str.slice(0, 45)
tbl(te)
p("**収益効率Bottom5**")
be = eff_pool.nsmallest(5, "yen_per_view")[["title", "views", "est_revenue_jpy", "yen_per_view", "rpm_jpy", "avg_view_pct"]].copy()
be["title"] = be["title"].str.slice(0, 45)
tbl(be)

# --- 7. Length correlation -------------------------------------------
h("7. 動画の長さとパフォーマンス")
bins = [0, 60, 600, 1200, 1800, 2400, 3000, 3600, 10000]
labels = ["Shorts(≤1m)", "1-10m", "10-20m", "20-30m", "30-40m", "40-50m", "50-60m", "60m+"]
df["length_bin"] = pd.cut(df["length_sec"], bins=bins, labels=labels, include_lowest=True)
len_tbl = df.groupby("length_bin", observed=True).agg(
    videos=("video_id", "count"),
    median_views=("views", "median"),
    median_rev=("est_revenue_jpy", "median"),
    median_rpm=("rpm_jpy", "median"),
    median_ctr=("impression_ctr", "median"),
    median_view_pct=("avg_view_pct", "median"),
).reset_index()
tbl(len_tbl)

# --- 8. Correlation --------------------------------------------------
h("8. 相関分析 (Long-form のみ)")
corr_cols = ["length_sec", "avg_view_pct", "avg_watch_sec", "impression_ctr",
             "endscreen_ctr", "views", "est_revenue_jpy", "rpm_jpy",
             "subs_gained", "impressions"]
corr = long_df[corr_cols].corr(method="spearman").round(2)
tbl(corr.reset_index().rename(columns={"index": ""}))

# --- 9. Collab / series keyword analysis -----------------------------
h("9. シリーズ・コラボ別パフォーマンス")
# Simple keyword tagging from title
def tag_row(title: str) -> str:
    t = str(title)
    tags = []
    if re.search(r"総集編|総まとめ|まとめ①|まとめ②|劇場版|10分でわかる", t):
        tags.append("compilation")
    if "ガチャ" in t:
        tags.append("gacha")
    if re.search(r"てえてえ|てぇてぇ|てえてぇ", t):
        tags.append("teetee")
    if "初コラボ" in t:
        tags.append("first_collab")
    if re.search(r"フレン|戌亥|ベル|リゼ|サロメ|マリン|みこ|星川|鈴原|栞葉|サラ", t):
        tags.append("collab")
    return ",".join(tags) if tags else "other"


df["tag"] = df["title"].map(tag_row)
tag_summary = (
    df.assign(tag=df["tag"].str.split(","))
      .explode("tag")
      .groupby("tag")
      .agg(videos=("video_id", "count"),
           median_views=("views", "median"),
           total_views=("views", "sum"),
           median_rev=("est_revenue_jpy", "median"),
           total_rev=("est_revenue_jpy", "sum"))
      .sort_values("total_rev", ascending=False)
      .reset_index()
)
tbl(tag_summary)

# --- Save -------------------------------------------------------------
(OUT / "analysis.md").write_text("\n".join(lines), encoding="utf-8")

# Quick cleaned dataset for reference
df.to_csv(OUT / "cleaned.csv", index=False)

print("Wrote:", OUT / "analysis.md")
print("Rows:", len(df))
