# 論文リストの一元管理（Google スプレッドシート → publications.html / researchmap）

```
Google スプレッドシート（マスタ）
      │ build.py --fetch（CSV として取得）
      ▼
data/publications.csv（リポジトリ内のスナップショット。フォールバック兼バックアップ）
      │ build.py
      ├─► publications.html          ← templates/publications.template.html に流し込み
      └─► researchmap/rm_*.csv       ← researchmap「業績インポート」画面に手動アップロード
                                        （data/researchmap_ids.csv に載っていない＝未登録の行だけ）
```

## 初期セットアップ（1回だけ）

スプレッドシートは **カテゴリごとに 7 枚のシート**（シート名 = `journal`, `invited`, `conference_i`,
`conference_j`, `book`, `kaisetsu`, `other`）で管理する。シート名がそのまま category になるので、
各シートに `category` 列は不要。

1. `python scripts/split_csv.py` で `data/sheets/<category>.csv` を作る（既に生成済み）。
2. 新しいスプレッドシートを作り、シートを 7 枚用意して上記の名前を付ける。
   各シートを開いた状態で ファイル > インポート > アップロード > 対応する CSV を選び、
   「現在のシートを置換」、区切り文字は自動、
   **「テキストを数値、日付、数式に変換する」のチェックは外す**（`pages` の `1-12` などが日付にされるのを防ぐ）。
   1 行目（ヘッダ）を「表示 > 固定 > 1 行」にしておくと編集しやすい。
3. スプレッドシートを「リンクを知っている全員が閲覧可」で共有し、CSV 取得 URL を作る
   （`{sheet}` の部分は build.py がシート名に置き換える。そのまま書く）:
   ```
   https://docs.google.com/spreadsheets/d/<SHEET_ID>/gviz/tq?tqx=out:csv&sheet={sheet}
   ```
4. ローカル: `scripts/config.example.json` を `scripts/config.json` にコピーして URL を書く（git 管理外）。
   GitHub Actions: リポジトリの Settings > Secrets and variables > Actions に `SHEET_CSV_URL` を登録
   （値は上の `{sheet}` 入り URL）。

> 1 枚のシートにまとめたい場合は、`data/publications.csv` をインポートし、URL を
> `...&sheet=publications` のように `{sheet}` を含まない形にする（このときは `category` 列が必須）。
> カテゴリを増やすときは `scripts/pubcommon.py` の `CATEGORIES` / `RM_DEFAULTS` にも追加する。

## 日常の更新手順

1. スプレッドシートに行を追加・修正する。
2. 反映方法はどちらでも:
   - **自動**: GitHub Actions「Build publications」が毎日 03:00 JST に実行（Actions タブから「Run workflow」で即時実行も可）。
     変更があれば `publications.html` と `data/publications.csv` がコミットされ、GitHub Pages に反映される。
   - **手元で**: `python scripts/build.py --fetch` → 生成結果を確認して commit / push。
3. researchmap へ「新しく追加した分だけ」反映したいとき:
   ```
   python scripts/build.py --fetch            # researchmap/rm_*.csv に未登録分だけが入る
   ```
   researchmap にログイン → 「研究者・業績インポート」→ できたファイルをアップロード（整合性チェック後に更新）。
   登録が終わったら
   ```
   python scripts/match_researchmap.py --apply   # researchmap から登録済み一覧を取得し、対応表を更新
   git commit -am "Update researchmap ids"
   ```
   これで登録済みの業績が `data/researchmap_ids.csv`（タイトル → researchmap 業績 ID の対応表）に記録され、
   次回の `build.py` では出力されなくなる。シートに何かを書き戻す必要はない。

   **「未登録」の判定**: 次のいずれにも該当しない行が出力される
   - シートの `rm_id` 列に値がある（手動で入れた場合）
   - `data/researchmap_ids.csv` にタイトルが載っている（`match_researchmap.py --apply` が追記）
   - シートの `rm_skip` が `TRUE`、または `hidden` が `TRUE`
   - `--rm-since YEAR` を付けた場合はその年より前

   **初回だけ**: 既存の業績は researchmap 側にも大半が登録済みなので、最初に一度
   ```
   python scripts/match_researchmap.py --apply --baseline
   ```
   を実行して現時点の全行を「対応済み」にしておく（タイトル一致した行は ID 付きで、一致しなかった行は
   `skip` として対応表に入る）。以後はシートに追加した行だけが出力対象になる。
   `skip` にした行を後で researchmap に登録したくなったら、対応表からその行を削除すれば次回出力される。

## シートの列

| 列 | 内容 |
|---|---|
| `id` | 任意。エラー表示・照合レポートで行を指すためのラベル。**新規行は空欄でよい**（既存の `p0001`〜は移行時の通し番号） |
| `category` | （カテゴリ別シートでは不要。シート名が使われる）1 枚シート方式のときは `journal` / `invited` / `conference_i` / `conference_j` / `book` / `kaisetsu` / `other` |
| `year`, `month` | 発行年（必須）・月（任意）。カテゴリ内はこの降順で表示。同じ年月内はシートの行順 |
| `authors` | 表示どおりの著者文字列。末尾のピリオドは不要（自動で付く） |
| `title` | タイトル。末尾のピリオドは不要 |
| `title_ja` | 和訳タイトル（括弧書きで表示）。任意 |
| `note` | タイトルの下に追加表示する行（書籍の章題など）。セル内改行（Ctrl+Enter）で複数行 |
| `venue` | 掲載先。`Advanced Robotics, Vol. 38, No. 24, pp. 256-266` のように年より前まで |
| `links` | `ラベル | URL` を 1 行に 1 つ（セル内改行）。例: `Link | https://...` |
| `award` | 受賞（赤字で表示）。複数は `;` 区切り |
| `hidden` | `TRUE` でサイトに表示しない |
| `rm_id` | researchmap の業績 ID を手動で指定したいとき。通常は空欄でよい（対応表 `data/researchmap_ids.csv` で管理） |
| `rm_target` / `rm_type` | researchmap の業績種別・掲載種別を上書きしたいとき（空欄なら category から自動） |
| `rm_skip` | `TRUE` で researchmap 出力から除外 |
| `journal`, `volume`, `number`, `pages`, `doi`, `referee`, `lang` | researchmap 用の構造化情報（任意。空欄なら venue 等から補完） |

category → researchmap の既定マッピングは `scripts/pubcommon.py` の `RM_DEFAULTS` を参照。

## スクリプト

| ファイル | 役割 |
|---|---|
| `scripts/build.py` | マスタ → HTML / researchmap CSV。`--fetch` `--check` `--rm-since YEAR` `--rm-all` |
| `scripts/import_html.py` | 旧 `publications.html` → CSV（初回移行用。通常は使わない） |
| `scripts/split_csv.py` | `data/publications.csv` → `data/sheets/<category>.csv`（カテゴリ別シートへの初期インポート用） |
| `scripts/match_researchmap.py` | researchmap 公開 API と照合して対応表 `data/researchmap_ids.csv` を更新（`--apply` で書き込み、`--baseline` で未一致分も対応済み扱い） |
| `scripts/pubcommon.py` | 列定義・カテゴリ・マッピング |
| `templates/publications.template.html` | ページの枠。デザイン変更はこちらを編集（`{{PUBLICATIONS}}` が差し替え位置） |

`publications.html` は生成物なので直接編集しない（次回ビルドで上書きされる）。
