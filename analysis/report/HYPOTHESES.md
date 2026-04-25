# 広告スロット 仮説レポート

**対象**: ユーザー提供スクショから取り込まれた 19 動画（Long-form 収益の 99% カバー）
**生成元データ**:
- `data/ad_slots/breaks.csv` — 84 slots のタイムスタンプ
- `analysis/report/ad_slots_per_video.csv` — 動画ごとの集計
- `analysis/report/ad_slots_channel_projection.csv` — 収益投影

---

## 1. データ概観

### 全体ボリューム

| 指標 | 値 |
|---|---|
| 取り込み動画 | 19 / 28 (Long-form) |
| 総 slot 数 | 84 |
| 有効 slot（重複除去後） | 82 |
| 重複 slot（<30秒差） | 2（すべて `bv2iwq17LVY` に集中） |
| YouTube 警告 (⚠) 付き slot | 8 |
| 挿入方式内訳 | manual 17 動画 / auto 2 動画 |

### 動画あたりの slot 数分布

| パーセンタイル | 有効 slot 数 |
|---|---|
| 最小 | 2 |
| 25% | 3 |
| 中央値 | **4** |
| 75% | 6 |
| 最大 | 8 |

### 動画長と slot 数

- slot 数が最も多い動画: `4ZYJdZRvDwo`（イブアン①, 31.5分）— **8 slots**
- slot 数が最も少ない動画: `yeahBDJu-Xg`, `sPtG_pnU-xw`, `L5nY1arYJ1M` — **2 slots**
- `slot/分` の中央値: **0.08 本/分** (manual 17 本のみ)

### 警告の集中

警告 8 件のうち **`BtP5GcSnRvA`（しげみ出産）の 4 slot すべてに警告**、次いで
`IfqMm5O2yKI`（56万ガチャ）に 2 件、`8zzMPgZ6bC8`, `g5UgDFXpIYk` に各 1 件。
警告の 50% が 1 本の動画に集中しているのは、**動画単位の構造的な配置不具合**
を示唆している可能性がある（Chunk 3 で深掘り）。

### 次以降の章立て

- Chunk 2: H1・H2 — 配置タイミングとゴールデンゾーン利用率
- Chunk 3: H3・H4 — 自動 vs 手動、警告の条件
- Chunk 4: H5・H6 — モデル乖離と総アップサイド
- Chunk 5: 統合仮説と追加で必要なデータ
