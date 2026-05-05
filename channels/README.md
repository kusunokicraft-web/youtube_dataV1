# channels/ — YouTube チャンネル管理体系

> 作成日: 2026-05-05
> 全 YouTube チャンネル（既存・企画中・公開後）を統一フォーマットで管理。

## 全チャンネル一覧

| # | チャンネル | プラットフォーム | ジャンル | 状態 | 公開日 |
|---|---|---|---|---|---|
| 01 | **にじさんじ切り抜き V1** | YouTube | VTuber 切り抜き（アンジュ・カトリーナ系）| **公開中** | 過去 |
| 02 | **猫間しおり**（仮）| YouTube | VTuber 投資・節約・ガジェット解説 | **企画完了・公開準備中** | 2026-09 予定 |
| 03 | **いじんだもん** | YouTube | 歴史・教養エンタメ（ずんだもん）| **企画中** | 未定（見本作り 6-10 ヶ月後）|

## ファイル構成（チャンネル共通テンプレ）

各チャンネルフォルダの中身:

```
NN_<channel_id>/
├── README.md           概要・現状サマリ
├── plan.md             事業企画書（コンセプト・ターゲット・戦略）
├── content_plan.md     動画企画リスト・公開順序
├── analytics/
│   ├── YYYY-MM.md      月次アナリティクス（登録者・再生・CTR・維持率）
│   └── YYYY-MM.csv     数値データ（時系列分析用）
└── reports/
    └── YYYY-MM_summary.md  月次レポート・所感
```

→ 詳細は `_template/` 参照。

## ファイル一覧

| ファイル | 内容 |
|---|---|
| **`README.md`**（本書）| 全チャンネル一覧・体系説明 |
| **`COMPARISON.md`** | 全チャンネル横断比較（KPI 統一・収益・コスト・実績）|
| `_template/` | 新規チャンネル追加時のテンプレ（README / plan / content_plan）|
| `01_nijisanji_kirinuki/` | 既存切り抜き V1（実体は `data/` `analysis/` にも分散）|
| `02_nekoma_shiori/` | 猫間しおり VTuber（実体は `new_channel/` 配下に詳細あり）|
| `03_ijindamon/` | いじんだもん 歴史教養（企画書 plan.md 完備）|

## チャンネル管理運用ルール

### 新規チャンネル追加時

1. `_template/` をコピーして `NN_<channel_id>/` を作成
2. README.md / plan.md / content_plan.md を埋める
3. `COMPARISON.md` の比較表に新規行を追加
4. `channels/README.md`（本書）の全チャンネル一覧に追加
5. commit & push

### 月次アナリティクス更新

1. 各チャンネルの `analytics/YYYY-MM.md` に当月数値を記録
2. `analytics/YYYY-MM.csv` に時系列データを追記
3. `reports/YYYY-MM_summary.md` に所感・改善案を記録
4. `COMPARISON.md` の最新値を更新

### 廃止・統合

- 廃止チャンネルは `99_archived_<channel_id>/` にリネーム
- 統合は `plan.md` で経緯記録、フォルダは保持

## 関連ドキュメント

- `../lifeplan/LIFE_PLAN.md` — ライフプラン全体（YouTube 副業の位置付け）
- `../new_channel/` — 猫間しおり詳細企画群（business_plan / simulations / character_design / candidates 等）
- `../data/`, `../analysis/` — 既存切り抜きチャンネル（V1）のデータ・分析

## 改訂履歴

| 日付 | 内容 |
|---|---|
| 2026-05-05 | 初版（channels/ 体系作成、いじんだもん新規追加、既存 V1・猫間しおりインデックス化）|
