# スクリーンショット運用ルール

`data/screenshots/` 配下にアップロードしてください。Claude Code が直接画像を読み、
タイムスタンプを CSV へ抽出します（外部 OCR ツール不要）。

## ディレクトリ構成

```
data/screenshots/
├── midroll/        ← 「動画再生中」の広告ブレイク一覧スクショ
└── retention/      ← 「視聴者維持」グラフのスクショ（任意）
```

## ファイル命名規則

ファイル名に **video_id を含めて**ください。私はファイル名から動画を特定します。

**OK 例**:
- `bv2iwq17LVY.png`
- `bv2iwq17LVY_midroll.png`
- `bv2iwq17LVY_top.png`, `bv2iwq17LVY_bottom.png` （長くて2枚に分かれる場合）

**NG 例**:
- `screenshot1.png`（どの動画か不明）
- `フレンとこ.png`（日本語タイトルだと突き合わせ困難）

video_id は `analysis/report/cleaned.csv` の `video_id` 列、または YouTube URL の `?v=XXXXXXXXXXX` 部分です。

## どこのスクショが欲しいか

### A. ミッドロール位置（最優先）

YouTube Studio → 該当動画の **「編集」** → 左メニュー **「収益受け取り」**
→ ページ内の **「動画再生中」** セクション

具体的に欲しい情報:
- **広告ブレイクのタイムスタンプ一覧**（例: `0:03:30`, `0:08:15`, ...）
- 「自動挿入」ON/OFF の表示
- 各ブレイクの**広告タイプ**（スキッパブル / ノンスキッパブル / バンパー など）が表示されている場合はそれも

タイムライン棒グラフより、**テキストでタイムスタンプが並んでいる箇所**のスクショの方が抽出精度が高いです。

### B. 視聴者維持率（あれば精度UP）

YouTube Studio → 動画 → **「アナリティクス」** → **「エンゲージメント」** タブ
→ **「視聴者維持率」** グラフ全体

可能なら CSV エクスポート（︙メニュー）の方が精度が高いですが、スクショでも読めます。

## 優先順位（収益インパクト順）

最初は以下 5 本だけで十分です。これで月 ¥80〜100k の改善余地を特定できます。

| 優先 | video_id | タイトル | 現収益 |
|---|---|---|---|
| 1 | `bv2iwq17LVY` | フレンとこ① | ¥775k |
| 2 | `8zzMPgZ6bC8` | 30万ガチャ | ¥414k |
| 3 | `27WNi57l-L8` | さんばかてえてえ① | ¥262k |
| 4 | `IfqMm5O2yKI` | 56万ガチャ | ¥220k |
| 5 | `4ZYJdZRvDwo` | イブアン① | ¥211k |

## 抽出後の出力

私が画像を読み取り、以下を生成します:

`data/midroll_breaks.csv`:
```csv
video_id,break_index,position_sec,position_hms,ad_type,inserted_by
bv2iwq17LVY,1,210,0:03:30,skippable,manual
bv2iwq17LVY,2,540,0:09:00,skippable,manual
...
```

その上で `analysis/midroll_optimization.py` を拡張し、**各動画ごとに「次にどの秒へ追加すべきか／どこは離脱誘発で外すべきか」**を秒単位で提案します。
