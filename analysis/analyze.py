"""かぷちゅう YouTube データ分析スクリプト

CSV から「公開済みコンテンツ」のみを抽出して、
基本指標、トップランキング、相関、効率指標を集計する。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# 日本語フォント対策（環境にあるものを順に試す）
for font in ("Noto Sans CJK JP", "IPAexGothic", "IPAGothic",
             "WenQuanYi Zen Hei", "DejaVu Sans"):
    try:
        matplotlib.font_manager.findfont(font, fallback_to_default=False)
        plt.rcParams["font.family"] = font
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "全期間コンテンツ別指標一覧（かぷちゅう） - 表データ.csv"
OUT = ROOT / "analysis"
FIG = OUT / "figures"

RENAME = {
    "コンテンツ": "video_id",
    "動画のタイトル": "title",
    "動画公開時刻": "published_at",
    "長さ": "length_sec",
    "インプレッション数": "impressions",
    "インプレッションのクリック率 (%)": "ctr_pct",
    "YouTube Premium の視聴回数": "premium_views",
    "YouTube Premium 総再生時間（単位: 時間）": "premium_watch_hours",
    "高評価率（低評価比） (%)": "like_ratio_pct",
    "視聴を継続 (%)": "retention_pct",
    "ユニーク視聴者数": "unique_viewers",
    "平均視聴率 (%)": "avg_view_pct",
    "総再生時間（単位: 時間）": "watch_hours",
    "推定収益 (JPY)": "revenue_jpy",
    "視聴回数": "views",
    "RPM (JPY)": "rpm_jpy",
}


def load() -> tuple[pd.Series, pd.DataFrame]:
    raw = pd.read_csv(DATA).rename(columns=RENAME)
    total = raw.iloc[0]  # "合計" 行
    df = raw.iloc[1:].copy()
    num_cols = [
        "length_sec", "impressions", "ctr_pct", "premium_views",
        "premium_watch_hours", "like_ratio_pct", "retention_pct",
        "unique_viewers", "avg_view_pct", "watch_hours",
        "revenue_jpy", "views", "rpm_jpy",
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    return total, df


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """公開コンテンツ（インプレッションがある）と内部用素材を分類。"""
    df = df.copy()
    df["is_published"] = (df["impressions"].fillna(0) > 0) & df["published_at"].notna()
    return df


def fmt_int(x: float | int) -> str:
    if pd.isna(x):
        return "-"
    return f"{int(round(x)):,}"


def fmt_float(x: float, digits: int = 2) -> str:
    if pd.isna(x):
        return "-"
    return f"{x:,.{digits}f}"


def section(title: str) -> str:
    return f"\n## {title}\n"


def main() -> None:
    total, df = load()
    df = classify(df)
    pub = df[df["is_published"]].copy()
    drafts = df[~df["is_published"]].copy()

    lines: list[str] = []
    lines.append("# かぷちゅう YouTube データ分析レポート\n")
    lines.append(f"対象 CSV: `{DATA.name}`\n")

    # ---- 全体サマリ ----
    lines.append(section("1. 全体サマリ"))
    summary = {
        "総動画数（CSV 行数）": len(df),
        "公開コンテンツ数": int(pub.shape[0]),
        "下書き / 内部素材数": int(drafts.shape[0]),
        "総視聴回数": fmt_int(total["views"]),
        "総再生時間（時間）": fmt_float(total["watch_hours"], 1),
        "総インプレッション数": fmt_int(total["impressions"]),
        "平均インプレッション CTR (%)": fmt_float(total["ctr_pct"], 2),
        "平均視聴率 (%)": fmt_float(total["avg_view_pct"], 2),
        "高評価率 (%)": fmt_float(total["like_ratio_pct"], 2),
        "推定収益合計（JPY）": fmt_int(total["revenue_jpy"]),
        "平均 RPM（JPY）": fmt_float(total["rpm_jpy"], 2),
        "Premium 視聴回数": fmt_int(total["premium_views"]),
        "Premium 再生時間": fmt_float(total["premium_watch_hours"], 1),
    }
    for k, v in summary.items():
        lines.append(f"- **{k}**: {v}")

    # ---- 公開コンテンツの統計量 ----
    lines.append(section("2. 公開コンテンツの統計量"))
    stat_cols = ["views", "impressions", "ctr_pct", "avg_view_pct",
                 "like_ratio_pct", "watch_hours", "revenue_jpy", "rpm_jpy",
                 "length_sec"]
    stats = pub[stat_cols].describe().T[["mean", "50%", "min", "max", "std"]]
    stats.columns = ["平均", "中央値", "最小", "最大", "標準偏差"]
    lines.append(stats.round(2).to_markdown())

    # ---- ランキング ----
    def rank_table(by: str, n: int, cols: list[str]) -> str:
        t = pub.sort_values(by, ascending=False).head(n)[cols].copy()
        t["title"] = t["title"].str.slice(0, 40) + t["title"].str.len().apply(
            lambda x: "…" if x > 40 else ""
        )
        return t.to_markdown(index=False, floatfmt=",.2f")

    lines.append(section("3. ランキング Top10"))
    lines.append("### 視聴回数 Top10")
    lines.append(rank_table("views", 10,
                            ["title", "published_at", "views", "watch_hours", "revenue_jpy"]))
    lines.append("\n### 推定収益 Top10")
    lines.append(rank_table("revenue_jpy", 10,
                            ["title", "published_at", "revenue_jpy", "rpm_jpy", "views"]))
    lines.append("\n### RPM Top10（最低 1 万再生以上）")
    rpm_pool = pub[pub["views"] >= 10000]
    t = rpm_pool.sort_values("rpm_jpy", ascending=False).head(10)
    t = t[["title", "published_at", "rpm_jpy", "views", "revenue_jpy"]].copy()
    t["title"] = t["title"].str.slice(0, 40) + t["title"].str.len().apply(
        lambda x: "…" if x > 40 else ""
    )
    lines.append(t.to_markdown(index=False, floatfmt=",.2f"))

    lines.append("\n### CTR Top10（最低 1 万インプレッション以上）")
    ctr_pool = pub[pub["impressions"] >= 10000]
    t = ctr_pool.sort_values("ctr_pct", ascending=False).head(10)
    t = t[["title", "published_at", "ctr_pct", "impressions", "views"]].copy()
    t["title"] = t["title"].str.slice(0, 40) + t["title"].str.len().apply(
        lambda x: "…" if x > 40 else ""
    )
    lines.append(t.to_markdown(index=False, floatfmt=",.2f"))

    # ---- 公開年別の集計 ----
    lines.append(section("4. 公開年別パフォーマンス"))
    pub["year"] = pub["published_at"].dt.year
    yearly = pub.groupby("year").agg(
        本数=("video_id", "count"),
        合計視聴=("views", "sum"),
        合計再生時間=("watch_hours", "sum"),
        合計収益=("revenue_jpy", "sum"),
        平均CTR=("ctr_pct", "mean"),
        平均視聴率=("avg_view_pct", "mean"),
        平均RPM=("rpm_jpy", "mean"),
    ).round(2)
    lines.append(yearly.to_markdown())

    # ---- 動画長と成果 ----
    lines.append(section("5. 動画の長さとパフォーマンス"))
    bins = [0, 5*60, 10*60, 20*60, 40*60, 60*60, 10*60*60]
    labels = ["≤5分", "5–10分", "10–20分", "20–40分", "40–60分", ">60分"]
    pub["length_bin"] = pd.cut(pub["length_sec"], bins=bins, labels=labels)
    by_len = pub.groupby("length_bin", observed=True).agg(
        本数=("video_id", "count"),
        平均視聴=("views", "mean"),
        平均再生時間=("watch_hours", "mean"),
        平均収益=("revenue_jpy", "mean"),
        平均RPM=("rpm_jpy", "mean"),
        平均視聴率=("avg_view_pct", "mean"),
    ).round(2)
    lines.append(by_len.to_markdown())

    # ---- 相関 ----
    lines.append(section("6. 主要指標の相関係数（公開コンテンツ）"))
    corr_cols = ["views", "impressions", "ctr_pct", "avg_view_pct",
                 "watch_hours", "revenue_jpy", "rpm_jpy", "length_sec"]
    corr = pub[corr_cols].corr().round(2)
    lines.append(corr.to_markdown())

    # ---- 集中度（パレート分析） ----
    lines.append(section("7. 集中度（パレート分析）"))
    sv = pub.sort_values("views", ascending=False)["views"].to_numpy()
    cum = np.cumsum(sv) / sv.sum()
    p_for = lambda ratio: int(np.searchsorted(cum, ratio) + 1)
    lines.append(
        f"- 視聴回数の **50%** を生む上位動画数: **{p_for(0.5)} 本** / {len(sv)} 本"
    )
    lines.append(
        f"- 視聴回数の **80%** を生む上位動画数: **{p_for(0.8)} 本** / {len(sv)} 本"
    )
    sr = pub.sort_values("revenue_jpy", ascending=False)["revenue_jpy"].fillna(0).to_numpy()
    cum_r = np.cumsum(sr) / sr.sum()
    p_for_r = lambda ratio: int(np.searchsorted(cum_r, ratio) + 1)
    lines.append(
        f"- 収益の **50%** を生む上位動画数: **{p_for_r(0.5)} 本**"
    )
    lines.append(
        f"- 収益の **80%** を生む上位動画数: **{p_for_r(0.8)} 本**"
    )

    # ---- タイトルキーワード分析 ----
    lines.append(section("8. タイトルキーワード別パフォーマンス"))
    keywords = {
        "アンジュ": r"アンジュ|カトリーナ",
        "リゼ": r"リゼ|ヘルエスタ",
        "サロメ": r"サロメ",
        "ベルモンド": r"ベル(?:モンド|アン|さん)",
        "戌亥とこ": r"戌亥|戍亥",
        "栞葉るり": r"栞葉|るり",
        "10分でわかる": r"10分でわかる",
        "総集編/まとめ": r"総集編|総まとめ|まとめ|劇場版",
        "てえてえ": r"てえてえ|てぇてぇ|てぇてえ",
        "初コラボ": r"初コラボ|初配信|出会い",
    }
    rows = []
    for label, pat in keywords.items():
        mask = pub["title"].fillna("").str.contains(pat, regex=True, na=False)
        sub = pub[mask]
        if len(sub) == 0:
            continue
        rows.append({
            "キーワード": label,
            "本数": len(sub),
            "合計視聴": int(sub["views"].sum()),
            "平均視聴": int(sub["views"].mean()),
            "平均CTR": round(sub["ctr_pct"].mean(), 2),
            "平均視聴率": round(sub["avg_view_pct"].mean(), 2),
            "平均RPM": round(sub["rpm_jpy"].mean(), 2),
        })
    kw = pd.DataFrame(rows).sort_values("合計視聴", ascending=False)
    lines.append(kw.to_markdown(index=False))

    # ---- 下書き素材の概況 ----
    lines.append(section("9. 内部素材 / 下書きの概況"))
    lines.append(f"- 件数: {len(drafts)} 本（インプレッションなし、限定公開や素材ファイルと推測）")
    lines.append(
        f"- 合計尺: {fmt_float(drafts['length_sec'].sum() / 3600, 1)} 時間"
    )
    lines.append(
        f"- 視聴回数（限定的アクセス分）: {fmt_int(drafts['views'].sum())}"
    )

    # ---- 主要な気づき ----
    lines.append(section("10. 主要な気づき"))
    top1 = pub.sort_values("views", ascending=False).iloc[0]
    rev_top1 = pub.sort_values("revenue_jpy", ascending=False).iloc[0]
    rpm_top1 = pub.sort_values("rpm_jpy", ascending=False).iloc[0]
    insights = [
        f"視聴回数 1 位は「{top1['title'][:25]}…」で **{fmt_int(top1['views'])} 回**、"
        f"全体の **{top1['views'] / pub['views'].sum() * 100:.1f}%** を占める。",
        f"収益 1 位は「{rev_top1['title'][:25]}…」で **{fmt_int(rev_top1['revenue_jpy'])} 円**。",
        f"RPM 最大は「{rpm_top1['title'][:25]}…」の **{fmt_float(rpm_top1['rpm_jpy'])} 円/千再生**。",
        f"平均インプレッション CTR は **{pub['ctr_pct'].mean():.2f}%**（YouTube 全体平均 2–10% の範囲内）。",
        f"動画あたり平均視聴率は **{pub['avg_view_pct'].mean():.1f}%**、長尺ほど低下する傾向。",
        f"視聴の **80%** が上位 **{p_for(0.8)} 本**（全 {len(sv)} 本中）に集中する強いパレート構造。",
    ]
    for s in insights:
        lines.append(f"- {s}")

    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")

    # ---- 派生 CSV ----
    pub.sort_values("views", ascending=False).to_csv(
        OUT / "published_videos.csv", index=False, encoding="utf-8-sig"
    )
    yearly.to_csv(OUT / "yearly_summary.csv", encoding="utf-8-sig")
    by_len.to_csv(OUT / "by_length.csv", encoding="utf-8-sig")
    kw.to_csv(OUT / "keyword_summary.csv", index=False, encoding="utf-8-sig")
    corr.to_csv(OUT / "correlation.csv", encoding="utf-8-sig")

    # ---- 図 ----
    # 1) 視聴回数 Top10 棒グラフ
    top10 = pub.sort_values("views", ascending=False).head(10)
    fig, ax = plt.subplots(figsize=(10, 5))
    short = top10["title"].str.slice(0, 22) + "…"
    ax.barh(short[::-1], top10["views"][::-1] / 1e4, color="#4C9F70")
    ax.set_xlabel("視聴回数（万回）")
    ax.set_title("視聴回数 Top10")
    fig.tight_layout()
    fig.savefig(FIG / "top10_views.png", dpi=130)
    plt.close(fig)

    # 2) 動画尺 vs 視聴回数 散布図
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(pub["length_sec"] / 60, pub["views"], alpha=0.6, color="#1f77b4")
    ax.set_xlabel("動画の長さ（分）")
    ax.set_ylabel("視聴回数")
    ax.set_yscale("log")
    ax.set_title("動画尺 × 視聴回数（対数）")
    fig.tight_layout()
    fig.savefig(FIG / "length_vs_views.png", dpi=130)
    plt.close(fig)

    # 3) パレート曲線
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(np.arange(1, len(cum) + 1), cum * 100, color="#d62728")
    ax.axhline(80, color="gray", linestyle="--", linewidth=0.8)
    ax.axhline(50, color="gray", linestyle="--", linewidth=0.8)
    ax.set_xlabel("動画ランク（視聴回数降順）")
    ax.set_ylabel("累積視聴シェア (%)")
    ax.set_title("視聴回数のパレート曲線")
    fig.tight_layout()
    fig.savefig(FIG / "pareto_views.png", dpi=130)
    plt.close(fig)

    # 4) 年別視聴回数
    fig, ax = plt.subplots(figsize=(8, 5))
    yearly_views = pub.groupby("year")["views"].sum() / 1e4
    ax.bar(yearly_views.index.astype(int).astype(str), yearly_views.values, color="#9467bd")
    ax.set_ylabel("合計視聴回数（万回）")
    ax.set_title("公開年別 合計視聴回数")
    fig.tight_layout()
    fig.savefig(FIG / "yearly_views.png", dpi=130)
    plt.close(fig)

    # 5) CTR vs 視聴率
    fig, ax = plt.subplots(figsize=(8, 5))
    sc = ax.scatter(pub["ctr_pct"], pub["avg_view_pct"],
                    s=np.clip(pub["views"] / 5000, 5, 400),
                    c=pub["rpm_jpy"].fillna(0), cmap="viridis", alpha=0.7)
    plt.colorbar(sc, label="RPM (JPY)")
    ax.set_xlabel("CTR (%)")
    ax.set_ylabel("平均視聴率 (%)")
    ax.set_title("CTR × 平均視聴率（サイズ=視聴回数, 色=RPM）")
    fig.tight_layout()
    fig.savefig(FIG / "ctr_vs_retention.png", dpi=130)
    plt.close(fig)

    # JSON サマリも書き出し
    summary_json = {
        "totals": {k: (None if pd.isna(total[k]) else float(total[k])) for k in
                   ["views", "impressions", "watch_hours", "revenue_jpy",
                    "rpm_jpy", "ctr_pct", "avg_view_pct", "like_ratio_pct"]},
        "published_count": int(pub.shape[0]),
        "draft_count": int(drafts.shape[0]),
        "pareto_50_videos": p_for(0.5),
        "pareto_80_videos": p_for(0.8),
        "revenue_pareto_50_videos": p_for_r(0.5),
        "revenue_pareto_80_videos": p_for_r(0.8),
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("DONE")
    print(f"published={len(pub)} drafts={len(drafts)}")


if __name__ == "__main__":
    main()
