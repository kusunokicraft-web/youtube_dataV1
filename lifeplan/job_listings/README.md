# 求人候補プール

検討中・応募中・選考中の求人を **記録 → 評価 → 分析** するための場所。
LIFE_PLAN.md §15（正社員ベースライン）の選定根拠データ。

## なぜ必要か

- 求人は時間が経つと**比較の記憶が薄れる**
- 複数並行で検討すると**条件の細部を取り違える**
- 後から「なぜこの求人を採用 / 棄却したか」を**根拠とともに振り返る**
- ライフプラン全体（A バイト / D' 正社員）に対する**経済的・QOL 上の影響**を定量化

## ディレクトリ構成

```
lifeplan/job_listings/
├── README.md             ← このファイル
├── summary.csv           ← 全求人の横断比較表
├── _template.md          ← 新規求人のテンプレート
├── dotline_jobcoach.md   ← D'（現在の正社員ベースライン）
└── [slug].md             ← 個別求人ファイル
```

ファイル名規則: `<company_slug>_<role_slug>.md`（小文字・英数・アンダースコア）

例: `dotline_jobcoach.md`, `kewpie_office.md`, `chibahosp_admin.md`

## ワークフロー（ユーザー操作）

求人を見つけたら **Claude に報告**:

1. **求人 URL or 求人票テキストを Claude に貼付**
2. Claude が:
   - `_template.md` をコピーして `<slug>.md` を作成
   - 求人票から基本情報・給与・労働時間等を抽出
   - ライフプラン適合度を評価（YouTube 制作時間 / 健康 / 副業バレ / 加齢）
   - 10 年後総資産を概算
   - D' / A プランとの比較を記載
   - `summary.csv` に行追加
3. Claude が比較サマリを Chat に返す
4. ユーザーが応募するかどうか判断
5. 応募・面接・採否などの**ステータス更新**も Claude に報告

### 報告例

```
[求人報告]
URL: https://...
（または求人票全文を貼付）
```

または自然文で:

> 「○○株式会社の事務職、見つけたから記録して」

## 評価軸（標準）

| 軸 | 評価方法 | 重み |
|---|---|---|
| 経済価値（10 年後総資産） | 給与推移 + 投資原資から計算 | ★★★ |
| YouTube 制作時間確保 | 残業実態 + 通勤時間 + シフト構造 | ★★★ |
| 健康リスク | 夜勤有無 + 業務負荷 + 精神的ストレス | ★★ |
| 副業バレリスク | 副業ポリシー + 同僚との接点 + 業界 | ★★ |
| 加齢適性 | 70 代まで継続可能性 + 厚生年金 + 退職金 | ★★ |
| 撤退柔軟性 | 試用期間 + 退職難易度 | ★ |
| 過去実績整合 | 過去の就職時の投稿空白との照合 | ★★ |

## summary.csv スキーマ

| 列名 | 型 | 説明 |
|---|---|---|
| `slug` | string | ファイル名（拡張子なし） |
| `company` | string | 会社名 |
| `role` | string | 職種名 |
| `location` | string | 勤務地（市区町村） |
| `salary_y1_man` | number | 1 年目年収（万円） |
| `salary_y10_man` | number | 10 年目想定年収（万円） |
| `overtime_hr_month` | number | 残業時間（月、実態） |
| `annual_holidays` | int | 年間休日 |
| `side_job_policy` | enum | `ok` / `ng` / `unclear` |
| `commute_min` | number | 通勤片道（分、想定手段含む） |
| `health_risk` | enum | `low` / `mid` / `high` |
| `id_reveal_risk` | enum | `low` / `mid` / `high` |
| `total_assets_10y_5pct_man` | number | 10 年後総資産概算（万円, 5%） |
| `fit_vs_dotline` | string | D' との差（`+500万` / `-200万` / `同等` 等） |
| `status` | enum | `researched` / `applied` / `interviewed` / `offered` / `rejected` / `accepted` / `declined` |
| `date_added` | ISO 8601 | 記録日 |
| `notes` | string | 備考（一行） |

## ステータス遷移

```
researched → applied → interviewed → offered → accepted
                                  ↘ rejected
                                  ↘ declined
        ↘ rejected (書類落ち)
        ↘ ignored (検討した上で応募しない)
```

## 個別求人ファイルのセクション構成

`_template.md` の構造:

```
# 会社名 - 職種

## 基本情報
## 求人スペック
## 通勤・アクセス
## ライフプラン適合度評価
## 経済的評価（10 年シミュレーション）
## 月次収支（概算）
## リスクと懸念
## 比較（A / D' / 他求人）
## 結論・推奨アクション
## 履歴ログ（応募・面接・結果）
```

## 関連ファイル

- `lifeplan/LIFE_PLAN.md` §15 — 選定された正社員ベースライン（現 D'）
- `lifeplan/LIFE_PLAN.md` §3 §7 — A バイトプラン（撤退時の戻り先）
- `analysis/lifeplan_5yr.py` — 経済シミュレーションのモデル
- `data/interventions/` — 採用後の介入記録（YouTube 関連）
