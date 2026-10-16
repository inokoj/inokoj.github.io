# 論文リストの一元管理（Google スプレッドシート → publications.html / researchmap）

```
Google スプレッドシート（マスタ）
      │ python scripts/build.py --fetch
      ▼
data/publications.csv（リポジトリ内のスナップショット。フォールバック兼バックアップ）
      ├─► publications.html          ← templates/publications.template.html に流し込み
      └─► researchmap/rm_*.csv       ← researchmap にまだ無い業績だけ（researchmap 公開 API と自動照合）
```

## いつもの手順

1. スプレッドシートに行を追加・修正する。
2. 手元で実行する:
   ```
   python scripts/build.py --fetch
   ```
   - `publications.html` が更新される
   - researchmap の登録済み業績と自動で照合し、**まだ登録されていない業績**の一覧が表示され、
     `researchmap/rm_*.csv` に書き出される
3. 候補を researchmap に登録したいとき: researchmap にログイン →「研究者・業績インポート」→
   `researchmap/` のファイルをアップロード（整合性チェック後に更新）。
   登録後にもう一度 `python scripts/build.py --fetch` を実行すると、登録済みになった業績は候補から消える。
4. `git commit -am "Update publications"` → `git push`

GitHub Actions「Build publications」も毎日 03:00 JST にシートを取得して `publications.html` を更新する
（researchmap の処理はしない）。

### researchmap 登録候補になる条件

次のすべてを満たす行が候補になる:

- researchmap にタイトル（英語・日本語どちらか）が一致する業績が無い
- `year` が `researchmap_since`（`scripts/config.json`、既定 2025）以降。一時的に変えるなら `--rm-since 2024` など
- シートの `rm_skip` も `hidden` も `TRUE` でない

**登録するつもりのない業績**は、シートの `rm_skip` 列を `TRUE` にすれば候補から外れる。
researchmap 側でタイトルを少し変えて登録したなどで照合できないときは、シートの `rm_id` 列に
researchmap の業績 ID を入れれば登録済み扱いになる。

照合結果は `data/researchmap_ids.csv`（タイトル → researchmap 業績 ID の対応表）に自動で記録される。
手で編集する必要はない。

## シートの列

| 列 | 内容 |
|---|---|
| `id` | 任意。エラー表示で行を指すためのラベル。**新規行は空欄でよい**（重複しても警告のみ） |
| `category` | （カテゴリ別シートでは不要。シート名が使われる）1 枚シート方式のときは `journal` / `invited` / `conference_i` / `conference_j` / `book` / `kaisetsu` / `other` |
| `year`, `month` | 発行年（必須）・月（任意）。カテゴリ内はこの降順で表示。同じ年月内はシートの行順。**月はサイトには表示されず**、並び順と researchmap の出版年月にのみ使う |
| `authors` | 表示どおりの著者文字列。末尾のピリオドは不要（自動で付く） |
| `title` | タイトル。末尾のピリオドは不要 |
| `title_ja` | 和訳タイトル（括弧書きで表示）。任意 |
| `note` | タイトルの下に追加表示する行（書籍の章題など）。セル内改行（Ctrl+Enter）で複数行 |
| `venue` | 掲載先。`Advanced Robotics, Vol. 38, No. 24, pp. 256-266` のように年より前まで |
| `links` | `ラベル | URL` を 1 行に 1 つ（セル内改行）。例: `Link | https://...` |
| `award` | 受賞（赤字で表示）。複数は `;` 区切り |
| `hidden` | `TRUE` でサイトに表示しない |
| `rm_skip` | `TRUE` で researchmap 登録候補から外す |
| `rm_id` | 自動照合できない業績の researchmap 業績 ID（通常は空欄） |
| `rm_target` / `rm_type` | researchmap の業績種別・掲載種別を上書きしたいとき（空欄なら category から自動） |
| `journal`, `volume`, `number`, `pages`, `doi`, `referee`, `lang` | researchmap 用の構造化情報（任意。空欄なら venue 等から補完） |

category → researchmap の既定マッピングは `scripts/pubcommon.py` の `RM_DEFAULTS` を参照。

## スクリプト

| ファイル | 役割 |
|---|---|
| `scripts/build.py` | これだけ使えばよい。`--fetch`（シート取得）`--no-rm`（researchmap 処理なし）`--rm-since YEAR` `--rm-all`（登録済みも update として出力）`--check`（検証のみ） |
| `scripts/rmsync.py` | researchmap 公開 API との照合（build.py から呼ばれる） |
| `scripts/pubcommon.py` | 列定義・カテゴリ・マッピング |
| `templates/publications.template.html` | ページの枠。デザイン変更はこちらを編集（`{{PUBLICATIONS}}` が差し替え位置） |
| `scripts/import_html.py`, `scripts/split_csv.py` | 初回移行用。通常は使わない |

`publications.html` は生成物なので直接編集しない（次回ビルドで上書きされる）。

## トラブルシューティング

- **あるカテゴリの論文がまるごと消える**: Google の CSV 出力（gviz）がシート先頭の数行をヘッダと誤認していた。
  build.py は URL に `headers=1` を自動で付けて防いでいる。それでもカテゴリが 0 行になったときは
  `data/publications.csv` を上書きせずに止まるので、シート名と 1 行目（列名）を確認する。
- **researchmap に接続できない**: 警告を出して、前回の対応表だけで候補を判定する。

## 初期セットアップ（済み。作り直すときだけ）

スプレッドシートは **カテゴリごとに 7 枚のシート**（シート名 = `journal`, `invited`, `conference_i`,
`conference_j`, `book`, `kaisetsu`, `other`）で管理する。

1. `python scripts/split_csv.py` で `data/sheets/<category>.csv` を作る。
2. 新しいスプレッドシートにシートを 7 枚用意して上記の名前を付け、各シートで ファイル > インポート >
   アップロード > 対応する CSV を「現在のシートを置換」で読み込む
   （**「テキストを数値、日付、数式に変換する」のチェックは外す**）。
3. 「リンクを知っている全員が閲覧可」で共有し、CSV 取得 URL を作る（`{sheet}` はそのまま書く）:
   ```
   https://docs.google.com/spreadsheets/d/<SHEET_ID>/gviz/tq?tqx=out:csv&sheet={sheet}
   ```
4. `scripts/config.example.json` を `scripts/config.json` にコピーして URL を書く（git 管理外）。
   GitHub Actions 用に Settings > Secrets and variables > Actions に `SHEET_CSV_URL` を登録する。

カテゴリを増やすときは `scripts/pubcommon.py` の `CATEGORIES` / `RM_DEFAULTS` にも追加する。
