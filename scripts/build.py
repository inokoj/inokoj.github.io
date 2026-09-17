"""マスタ（Google スプレッドシート or data/publications.csv）から
  - publications.html
  - researchmap/ 配下の業績インポート用 CSV
を生成する。

使い方:
  python scripts/build.py                 # data/publications.csv から生成
  python scripts/build.py --fetch         # スプレッドシートを取得して data/publications.csv を更新してから生成
  python scripts/build.py --rm-all        # researchmap 用 CSV に rm_id 付きの行（update）も含める
  python scripts/build.py --check         # 生成せず整合性チェックのみ

スプレッドシートの URL は環境変数 SHEET_CSV_URL か scripts/config.json の "sheet_csv_url" で指定。
URL に {sheet} を含めるとカテゴリ別シート方式（シート名 = category）、含めなければ 1 枚シート方式。
"""
import argparse
import csv
import html
import io
import json
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pubcommon import COLUMNS, CATEGORIES, RM_DEFAULTS, is_japanese, norm_title  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "publications.csv"
TEMPLATE = ROOT / "templates" / "publications.template.html"
OUT_HTML = ROOT / "publications.html"
RM_DIR = ROOT / "researchmap"
CONFIG = ROOT / "scripts" / "config.json"
IDS_PATH = ROOT / "data" / "researchmap_ids.csv"  # match_researchmap.py が作る対応表

LINK_CLASS = 'target="_blank" class="text-blue-600 hover:underline"'
AWARD_CLASS = 'class="text-red-500 font-bold"'
NO_PERIOD = {"book", "kaisetsu"}  # タイトル・著者末尾にピリオドを付けないカテゴリ

# 表示順（カテゴリ順はこの通り、カテゴリ内は year/month 降順・同値ならシートの行順）
CATEGORY_ORDER = list(CATEGORIES)


# ---------------------------------------------------------------- 読み込み
def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}


def fetch_sheet(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "publications-build/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8-sig")


def read_rows(text: str, sheet: str = "", default_category: str = "") -> list[dict]:
    rows = []
    for i, r in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        if not any(r.get(c) for c in ("authors", "title", "venue")):
            continue  # 空行
        r["_line"] = i
        r["_where"] = f"{sheet} row {i}" if sheet else f"row {i}"
        for c in COLUMNS:
            r.setdefault(c, "")
        if not r["category"]:
            r["category"] = default_category  # カテゴリ別シートでは category 列は省略可
        rows.append(r)
    return rows


def fetch_all_sheets() -> list[dict]:
    """スプレッドシートを取得して行リストにする。

    URL に "{sheet}" が含まれていればカテゴリ別シート方式:
      sheet_names（既定: 全カテゴリ名）を順に取得し、シート名を category として結合する。
    含まれていなければ 1 枚のシートから全件取得する（category 列必須）。
    設定は環境変数 SHEET_CSV_URL / SHEET_NAMES（カンマ区切り）か scripts/config.json。
    """
    import os
    from urllib.parse import quote
    cfg = load_config()
    url = os.environ.get("SHEET_CSV_URL") or cfg.get("sheet_csv_url")
    if not url:
        sys.exit("SHEET_CSV_URL (env) or scripts/config.json: sheet_csv_url が必要です")
    if "{sheet}" not in url:
        return read_rows(fetch_sheet(url))
    names_env = os.environ.get("SHEET_NAMES")
    names = [s.strip() for s in names_env.split(",")] if names_env else cfg.get("sheet_names") or list(CATEGORIES)
    rows = []
    for name in names:
        part = read_rows(fetch_sheet(url.replace("{sheet}", quote(name))), sheet=name, default_category=name)
        print(f"  sheet '{name}': {len(part)} rows")
        rows += part
    return rows


def truthy(v: str) -> bool:
    return v.strip().upper() in ("TRUE", "1", "YES", "Y", "○")


# ---------------------------------------------------------------- 検証
def validate(rows: list[dict]) -> list[str]:
    errors = []
    seen = set()
    for r in rows:
        where = f"{r['_where']} ({r.get('id') or r.get('title', '')[:30]})"
        if r["category"] not in CATEGORIES:
            errors.append(f"{where}: unknown category '{r['category']}'")
        if not re.fullmatch(r"(19|20)\d\d", r["year"]):
            errors.append(f"{where}: year must be yyyy (got '{r['year']}')")
        if r["month"] and not (r["month"].isdigit() and 1 <= int(r["month"]) <= 12):
            errors.append(f"{where}: month must be 1-12 (got '{r['month']}')")
        if not r["title"]:
            errors.append(f"{where}: title is empty")
        if r["id"]:
            if r["id"] in seen:
                errors.append(f"{where}: duplicate id")
            seen.add(r["id"])
        for ln in split_lines(r["links"]):
            if "|" not in ln:
                errors.append(f"{where}: link must be 'Label | URL' (got '{ln}')")
    return errors


def split_lines(cell: str) -> list[str]:
    # セル内改行、または " ; " 区切り
    return [x.strip() for x in re.split(r"\n|\s;\s", cell) if x.strip()]


# ---------------------------------------------------------------- HTML 生成
def esc(s: str) -> str:
    return html.escape(s, quote=False)


def sort_key(r: dict):
    return (-int(r["year"]), -int(r["month"] or 0), r["_order"])


def render_entry(r: dict) -> str:
    period = "" if r["category"] in NO_PERIOD else "."
    lines = [esc(r["authors"]) + period, esc(r["title"]) + period]
    if r["title_ja"]:
        lines.append(f"({esc(r['title_ja'])})")
    lines += [esc(x) for x in r["note"].splitlines() if x.strip()]
    # month は並び順と researchmap 出力にのみ使い、サイトには年だけを表示する
    lines.append(f"{esc(r['venue'])}, {r['year']}." if r["venue"] else f"{r['year']}.")
    links = []
    for ln in split_lines(r["links"]):
        label, _, url = ln.partition("|")
        links.append(f'[<a href="{html.escape(url.strip())}" {LINK_CLASS}>{esc(label.strip())}</a>]')
    if links:
        lines.append(" ".join(links))
    if r["award"]:
        awards = [a.strip() for a in r["award"].split(";") if a.strip()]
        lines.append(", ".join(f"<strong {AWARD_CLASS}>{esc(a)}</strong>" for a in awards))
    ind = " " * 28
    body = "<br>\n".join(ind + x for x in lines)
    return f"{' ' * 24}<li>\n{body}\n{' ' * 24}</li>"


def render_html(rows: list[dict]) -> str:
    by_cat = defaultdict(list)
    for r in rows:
        if not truthy(r["hidden"]):
            by_cat[r["category"]].append(r)
    sections = []
    for cat in CATEGORY_ORDER:
        items = sorted(by_cat.get(cat, []), key=sort_key)
        entries = "\n".join(render_entry(r) for r in items)
        sections.append(
            f"{' ' * 16}<div>\n"
            f"{' ' * 20}<h2 id=\"{cat}\" class=\"subsection-title\">{CATEGORIES[cat]}</h2>\n"
            f"{' ' * 20}<ul class=\"space-y-4 text-slate-800 publication-list\">\n"
            f"{entries}\n"
            f"{' ' * 20}</ul>\n"
            f"{' ' * 16}</div>"
        )
    tpl = TEMPLATE.read_text(encoding="utf-8")
    assert "{{PUBLICATIONS}}" in tpl, "template placeholder missing"
    return tpl.replace("{{PUBLICATIONS}}", "\n\n".join(sections))


# ---------------------------------------------------------------- researchmap 出力
# CSV 項目定義書 (https://researchmap.jp/outline/v2api/v2CSV.pdf) に基づくヘッダ
RM_HEADERS = {
    "published_papers": [
        "アクション名", "アクションタイプ", "類似業績マージ優先度", "ID", "タイトル(日本語)", "タイトル(英語)",
        "著者(日本語)", "著者(英語)", "担当区分", "概要(日本語)", "概要(英語)", "出版者・発行元(日本語)",
        "出版者・発行元(英語)", "出版年月", "誌名(日本語)", "誌名(英語)", "巻", "号", "開始ページ", "終了ページ",
        "記述言語", "査読の有無", "招待の有無", "掲載種別", "国際・国内誌", "国際共著", "DOI", "ISSN", "eISSN",
        "URL", "URL2", "主要な業績かどうか", "公開の有無"],
    "presentations": [
        "アクション名", "アクションタイプ", "類似業績マージ優先度", "ID", "タイトル(日本語)", "タイトル(英語)",
        "講演者(日本語)", "講演者(英語)", "会議名(日本語)", "会議名(英語)", "発表年月日", "開催年月日(From)",
        "開催年月日(To)", "招待の有無", "記述言語", "会議種別", "主催者(日本語)", "主催者(英語)", "開催地(日本語)",
        "開催地(英語)", "国・地域", "概要(日本語)", "概要(英語)", "国際・国内会議", "国際共著", "URL", "URL2",
        "主要な業績かどうか", "公開の有無"],
    "books_etc": [
        "アクション名", "アクションタイプ", "類似業績マージ優先度", "ID", "タイトル(日本語)", "タイトル(英語)",
        "担当区分", "著者(翻訳者)(日本語)", "著者(翻訳者)(英語)", "原著者(日本語)", "原著者(英語)",
        "担当範囲(日本語)", "担当範囲(英語)", "出版者・発行元(日本語)", "出版者・発行元(英語)", "概要(日本語)",
        "概要(英語)", "出版年月", "総ページ数", "担当ページ", "記述言語", "査読の有無", "著書種別", "国際共著",
        "DOI", "ISBN", "URL", "URL2", "主要な業績かどうか", "公開の有無"],
}
RM_HEADERS["misc"] = RM_HEADERS["published_papers"]


def rm_multi(values: list[str]) -> str:
    """複数入力可の項目: "[a,b,c]" 形式。値中の "," は "¥" でエスケープ（定義書どおり）。"""
    if not values:
        return "null"
    return "[" + ",".join(v.replace(",", "¥,") for v in values) + "]"


def rm_authors(authors: str) -> list[str]:
    # "A, B, C" / "A，B，C" / "A, B and C" を分割
    s = re.sub(r"\s+and\s+", ", ", authors)
    return [a.strip() for a in re.split(r"[,，、]", s) if a.strip()]


def rm_date(r: dict) -> str:
    return f"{r['year']}-{int(r['month']):02d}" if r["month"] else r["year"]


def rm_row(r: dict) -> tuple[str, dict]:
    cat = r["category"]
    d_target, d_type, d_referee, d_intl = RM_DEFAULTS[cat]
    target = r["rm_target"] or d_target
    rtype = r["rm_type"] or d_type
    lang = r["lang"] or ("jpn" if is_japanese(r["title"]) else "eng")
    ja = lang == "jpn"
    referee = r["referee"].upper() if r["referee"] else (d_referee or "null")
    links = [ln.partition("|")[2].strip() for ln in split_lines(r["links"])]
    urls = (links + ["null", "null"])[:2]
    doi = r["doi"] or next((re.sub(r"^https?://(dx\.)?doi\.org/", "", u) for u in links if "doi.org/" in u), "")
    pages = r["pages"].replace("–", "-")
    p_start, _, p_end = pages.rpartition("-") if "-" in pages else (pages, "", "")
    action = ("update", "doc") if r["rm_id"] else ("insert", "merge")

    base = {
        "アクション名": action[0], "アクションタイプ": action[1], "類似業績マージ優先度": "null",
        "ID": r["rm_id"] or "null",
        "タイトル(日本語)": r["title"] if ja else (r["title_ja"] or "null"),
        "タイトル(英語)": "null" if ja else r["title"],
        "記述言語": lang, "URL": urls[0], "URL2": urls[1],
        "主要な業績かどうか": "FALSE", "公開の有無": "disclosed",
    }
    authors_ja = rm_multi(rm_authors(r["authors"])) if ja else "null"
    authors_en = "null" if ja else rm_multi(rm_authors(r["authors"]))
    journal = r["journal"] or r["venue"]

    if target in ("published_papers", "misc"):
        row = {
            **base,
            "著者(日本語)": authors_ja, "著者(英語)": authors_en, "担当区分": "null",
            "概要(日本語)": "null", "概要(英語)": "null",
            "出版者・発行元(日本語)": "null", "出版者・発行元(英語)": "null",
            "出版年月": rm_date(r),
            "誌名(日本語)": journal if ja else "null", "誌名(英語)": "null" if ja else journal,
            "巻": r["volume"] or "null", "号": r["number"] or "null",
            "開始ページ": p_start.strip() or "null", "終了ページ": p_end.strip() or "null",
            "査読の有無": referee, "招待の有無": "TRUE" if cat == "invited" else "null",
            "掲載種別": rtype, "国際・国内誌": d_intl or "null", "国際共著": "null",
            "DOI": rm_multi([doi]) if doi else "null", "ISSN": "null", "eISSN": "null",
        }
    elif target == "presentations":
        row = {
            **base,
            "講演者(日本語)": authors_ja, "講演者(英語)": authors_en,
            "会議名(日本語)": journal if ja else "null", "会議名(英語)": "null" if ja else journal,
            "発表年月日": rm_date(r), "開催年月日(From)": "null", "開催年月日(To)": "null",
            "招待の有無": "TRUE" if cat == "invited" else "null", "会議種別": rtype,
            "主催者(日本語)": "null", "主催者(英語)": "null", "開催地(日本語)": "null", "開催地(英語)": "null",
            "国・地域": "null", "概要(日本語)": "null", "概要(英語)": "null",
            "国際・国内会議": "FALSE" if ja else "TRUE", "国際共著": "null",
        }
    elif target == "books_etc":
        row = {
            **base,
            "担当区分": "contributor" if r["note"] else "joint_work",
            "著者(翻訳者)(日本語)": authors_ja, "著者(翻訳者)(英語)": authors_en,
            "原著者(日本語)": "null", "原著者(英語)": "null",
            "担当範囲(日本語)": r["note"].replace("\n", "¥n") if (ja and r["note"]) else "null",
            "担当範囲(英語)": r["note"].replace("\n", "¥n") if (not ja and r["note"]) else "null",
            "出版者・発行元(日本語)": r["venue"] if ja else "null",
            "出版者・発行元(英語)": "null" if ja else r["venue"],
            "概要(日本語)": "null", "概要(英語)": "null", "出版年月": rm_date(r),
            "総ページ数": "null", "担当ページ": r["pages"] or "null", "査読の有無": referee,
            "著書種別": rtype, "国際共著": "null", "DOI": rm_multi([doi]) if doi else "null", "ISBN": "null",
        }
    else:
        raise ValueError(f"unknown rm_target '{target}' (row {r['_line']})")
    return target, row


def apply_id_table(rows: list[dict]) -> int:
    """対応表 data/researchmap_ids.csv の rm_id / rm_target を、シートで空欄の行に補う。"""
    if not IDS_PATH.exists():
        return 0
    table = {r["key"]: r for r in csv.DictReader(IDS_PATH.open(encoding="utf-8-sig"))}
    n = 0
    for r in rows:
        if r["rm_id"]:
            continue
        hit = table.get(norm_title(r["title"]))
        if not hit:
            continue
        if hit["rm_id"] == "skip":      # baseline で「対応済み扱い」にした行
            r["rm_skip"] = "TRUE"
        else:
            r["rm_id"] = hit["rm_id"]
            r["rm_target"] = r["rm_target"] or hit["rm_target"]
        n += 1
    return n


def write_researchmap(rows: list[dict], include_updates: bool, since: int) -> dict[str, int]:
    RM_DIR.mkdir(exist_ok=True)
    apply_id_table(rows)
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if truthy(r["rm_skip"]) or truthy(r["hidden"]) or int(r["year"]) < since:
            continue
        if r["rm_id"] and not include_updates:
            continue
        target, row = rm_row(r)
        groups[target].append(row)
    counts = {}
    for target, hdr in RM_HEADERS.items():
        path = RM_DIR / f"rm_{target}.csv"
        items = groups.get(target, [])
        counts[target] = len(items)
        if not items:
            if path.exists():
                path.unlink()
            continue
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            f.write(target + "\n")
            w = csv.DictWriter(f, fieldnames=hdr, lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            for row in items:
                w.writerow({h: row.get(h, "null") for h in hdr})
    return counts


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="スプレッドシートを取得して data/publications.csv を更新")
    ap.add_argument("--rm-all", action="store_true", help="researchmap CSV に rm_id 付きの行（update）も含める")
    ap.add_argument("--rm-since", type=int, default=0, metavar="YEAR",
                    help="researchmap CSV に含める最小の year（例: --rm-since 2026）")
    ap.add_argument("--check", action="store_true", help="検証のみ")
    args = ap.parse_args()

    if args.fetch:
        rows = fetch_all_sheets()
        if len(rows) < 10:
            sys.exit(f"取得した行数が少なすぎます ({len(rows)} 行)。URL が CSV を返しているか確認してください")
        with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"fetched {len(rows)} rows -> {CSV_PATH}")

    rows = read_rows(CSV_PATH.read_text(encoding="utf-8-sig"))
    for i, r in enumerate(rows):
        r["_order"] = i  # 同じ年月内の表示順 = CSV（シート）の行順
    errors = validate(rows)
    for e in errors:
        print("ERROR:", e, file=sys.stderr)
    if errors:
        sys.exit(1)
    if args.check:
        print(f"OK: {len(rows)} rows")
        return

    OUT_HTML.write_text(render_html(rows), encoding="utf-8")
    shown = sum(1 for r in rows if not truthy(r["hidden"]))
    print(f"{shown} entries -> {OUT_HTML.name}")
    counts = write_researchmap(rows, include_updates=args.rm_all, since=args.rm_since)
    print("researchmap import CSV:", ", ".join(f"{k}={v}" for k, v in counts.items()),
          "(update 含む)" if args.rm_all else "(rm_id 未設定の行のみ)",
          f"(year >= {args.rm_since})" if args.rm_since else "")


if __name__ == "__main__":
    main()
