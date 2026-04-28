# 介入ログ（Intervention Log）

V2 戦略実行・広告スロット変更・動画戦略変更などの「**意図的な介入**」を記録する場所。
将来の効果検証（before/after, cohort 比較）の根拠データとなる。

## なぜ必要か

YouTube 分析には 3 階層のノイズが混入する:

| 階層 | 内容 |
|---|---|
| A. 意図的介入 | 自分が変えた要素（V2 戦略、広告スロット変更等） |
| B. 自然減衰 | k=0.572 の power-law 経年劣化 |
| C. 外部要因 | アンジュ活動量、にじさんじトレンド、アルゴリズム変更等 |

**A の効果**だけを取り出すには、何を・いつ・どう変えたかの完全なログが必須。
記憶に頼ると半年後に「あの時何変えたっけ?」となる。**変更直後にコミット**が鉄則。

## ディレクトリ構成

```
data/interventions/
├── README.md         ← このファイル
└── interventions.csv ← 介入の時系列ログ
```

## interventions.csv スキーマ

| 列名 | 型 | 必須 | 説明 |
|---|---|---|---|
| `date` | ISO 8601 | ✓ | 介入実施日（`YYYY-MM-DD`） |
| `target` | string | ✓ | `channel` or `video_id`（複数なら `;` 区切り） |
| `type` | enum | ✓ | 下記 type 一覧から |
| `change` | string | ✓ | 変更内容の自然文記述 |
| `hypothesis` | string |  | 期待効果（「RPM +20%」「視聴維持率 +5pp」等） |
| `eval_after_days` | int |  | 評価までの待機日数（既定 60） |
| `status` | enum | ✓ | `planned` / `executed` / `evaluating` / `evaluated` / `cancelled` |
| `evaluated_date` | ISO 8601 |  | 評価実施日（評価完了時に記入） |
| `result` | string |  | 結果サマリー（評価完了時に記入） |
| `notes` | string |  | 追加コンテキスト |

### type 一覧

| type | 用途 |
|---|---|
| `ad_slot` | 広告スロット数・配置の変更 |
| `title` | タイトル戦略の変更（絵文字、長さ、フック等） |
| `thumbnail` | サムネイル戦略の変更 |
| `cadence` | 投稿頻度の変更（月 1 → 月 2 等） |
| `length` | 動画長の戦略変更（30 分以上を増やす等） |
| `series` | シリーズ化方針の変更（前後編、続編戦略等） |
| `collab` | コラボ戦略（初コラボ重視、定期コラボ等） |
| `meta` | 概要欄・タグ・終了画面の変更 |
| `description` | 概要欄の体系的変更 |
| `cohort_def` | コホート定義（V1/V2 境界等） |
| `strategy_decision` | 戦略決定（直接介入ではないが分析方針に影響） |
| `external_event` | 外部イベント記録（アンジュ卒業、コラボ機会等） |

### status の遷移

```
planned → executed → evaluating → evaluated
                 ↘ cancelled
```

- **planned**: 計画段階。実行前
- **executed**: 実行済み（評価期間に未到達）
- **evaluating**: 評価期間中（`eval_after_days` 経過待ち）
- **evaluated**: 評価完了。`result` 列に結果記入済み
- **cancelled**: 中止（理由を `notes` に）

## 運用ルール

### 介入の記録タイミング

**介入実施直後**にコミット。記憶に頼らない。
複数の変更を同時に実施した場合は **1 介入 1 行**で分けて記録。

### 同時介入の禁止

複数の type を同時に変更すると効果分離が不能になる:
- ❌ 同じ動画でタイトル + サムネ + スロット数を一度に変更
- ✅ 1 月にタイトル戦略変更、3 月にスロット最適化、6 月にサムネ刷新

最低 30 日（理想 90 日）は 1 つの変更を観察してから次を入れる。

### 評価の自動アラート

評価期日 = `date + eval_after_days`。
半年に 1 回 `analysis/intervention_eval.py`（実装予定）で `evaluating` の行を抽出し、
`status` を `evaluated` に進めて `result` を記入する。

### 評価方法

| type | 推奨評価手法 |
|---|---|
| 既存動画の `ad_slot` 変更 | Interrupted Time Series（介入前後 60 日）|
| 新規動画の `title` / `length` 等 | Cohort 比較（V1 vs V2）。age-matched で views/revenue 比較 |
| `cadence` 変更 | 期間集計（介入前 6 ヶ月 vs 後 6 ヶ月） |
| `external_event` | コホート分割の根拠として記録のみ |

## 記入例

```csv
date,target,type,change,hypothesis,eval_after_days,status,evaluated_date,result,notes
2026-04-25,channel,strategy_decision,V2 戦略策定。RPM +30% × 視聴 +15% を目標,V2 multiplier 1.49x,180,executed,,,Phase 1 開始時点
2026-05-01,bv2iwq17LVY,ad_slot,スロット数 5 → 3 に削減（avg_watch 60% 中心配置）,RPM +5-10%,60,executed,,,30+ 分動画の slot 最適化試行
2026-05-15,channel,cadence,月 1 本 → 月 2 本（隔週）に変更,年商 +60% 目標,180,executed,,,ストック型運用開始
2026-06-01,abc123def,title,絵文字を削除（1 本のみ実験）,CTR ±0,90,executed,,,
2026-07-01,channel,external_event,アンジュ・カトリーナ 配信頻度 30% 減,—,—,executed,,,コホート分析で考慮要
```

## 既知の注意点

### n=1 problem

自分のチャンネル単独では真の A/B test 不可。**因果でなく相関**しか出ない。
似たコホートの動画で**前後比較**するのが現実的な準実験。

### 時間ラグ

V2 効果は 3-6 ヶ月後に顕在化。短期の数値変動（介入後 1-2 週）は無視。
判断は最低 30 日、可能なら 60-90 日待つ。

### 多重介入

同時に複数変更すると効果が分離不能。**1 度に 1 介入**を死守。

### Selection bias

ヒット動画ばかり見て「V2 成功」と判断するのは典型的な誤り。
全 V2 動画を中央値・幾何平均で評価すること。

## 関連ファイル

- `analysis/report/cleaned.csv` — 動画別アナリティクス（介入評価のベース）
- `data/ad_slots/breaks.csv` — 広告スロット詳細（`type=ad_slot` の根拠）
- `data/retention/` — 視聴維持率カーブ（before/after 比較で使用）
- `analysis/intervention_eval.py` — 評価スクリプト（実装予定）
