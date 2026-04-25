# 広告スロット データ運用

YouTube Studio の「広告ブレイク」スクショを蓄積し、解析パイプラインで使える形で
正規化保存する場所です。`analysis/breaks_audit.py` がここを Single Source of
Truth として読み込みます。

## ディレクトリ構成

```
data/ad_slots/
├── README.md            ← このファイル
├── breaks.csv           ← 抽出済みタイムスタンプ（マスター）
├── coverage.csv         ← 取り込み進捗トラッカー
└── screenshots/         ← 画像の元データ
    ├── bv2iwq17LVY.png
    ├── 8zzMPgZ6bC8.png
    └── ...
```

## ワークフロー（ユーザー操作）

1. **YouTube Studio** で対象動画を開く
   → 「収益受け取り」→ 「動画再生中」→ 「広告ブレイク」一覧
2. スクショを撮り、**ファイル名を `<video_id>.png`** にして
   `data/ad_slots/screenshots/` 直下に保存
3. Claude にメッセージ
   `「<video_id> のスクショ追加した」`
4. Claude が画像を読み、`breaks.csv` と `coverage.csv` を追記更新
5. `analysis/breaks_audit.py` を再実行 → 最新の最適化レポート

## ファイル名ルール

| OK | NG |
|---|---|
| `bv2iwq17LVY.png` | `screenshot1.png`（誰の動画か不明） |
| `bv2iwq17LVY_1.png`, `bv2iwq17LVY_2.png`（複数枚に分かれる場合） | `フレンとこ.png`（日本語タイトル） |

`video_id` は YouTube URL の `?v=XXXXXXXXXXX` 部分。
`analysis/report/cleaned.csv` の `video_id` 列と完全一致させます。

## breaks.csv スキーマ

| 列名 | 型 | 説明 |
|---|---|---|
| `video_id` | string | YouTube 動画 ID |
| `break_index` | int | 当該動画内での連番（1始まり） |
| `raw_timestamp` | string | スクショの表示文字列そのまま（例: `0:22:15:30`） |
| `position_sec` | int | 秒換算（フレーム/centi-second 部分は切り捨て） |
| `position_hms` | string | `H:MM:SS` 正規化表示 |
| `inserted_by` | string | `manual` / `auto` |
| `has_warning` | bool | YouTube が警告アイコン (⚠️) を表示しているか |
| `ad_type` | string | `skippable` / `non_skippable` / `bumper` / 空（不明時） |
| `screenshot` | string | 元画像のファイル名（`screenshots/` 配下） |
| `note` | string | 重複・配置警告などの所見 |

## タイムスタンプ表記の注意

YouTube Studio のフィールドは動画長によって 2 形式あります:

| 表記 | 例 | パース |
|---|---|---|
| `H:MM:SS:FF` | `0:22:15:30` | 60 分超の動画。最後の `FF` はフレーム or centi-second |
| `MM:SS:FF` | `14:21:58` | 60 分未満の動画 |

**重要**: 末尾の `FF` 部分が `30`, `41`, `58` などになるのは正常（フレーム精度）。
ただし**同一動画で 30 秒未満の差で複数 slot がある場合は重複扱い**（YouTube の最低
間隔ルールにより片方が無効化される）。

## coverage.csv

取り込み進捗の一覧。新しい動画の優先度判断に使います。
未取り込み動画は `analysis/breaks_audit.py` が自動で警告します。
