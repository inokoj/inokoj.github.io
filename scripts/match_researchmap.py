"""researchmap に登録済みの業績と data/publications.csv をタイトルで突き合わせ、
対応表 data/researchmap_ids.csv（タイトル → researchmap 業績ID）を更新する。

使い方:
  python scripts/match_researchmap.py            # 照合結果を表示するだけ（dry run）
  python scripts/match_researchmap.py --apply    # 一意に一致した行を対応表に追記
  python scripts/match_researchmap.py --apply --baseline
        # さらに、一致しなかった行も rm_id="skip" として対応表に入れる（＝現時点の全行を「対応済み」扱いにし、
        # 以後シートに追加した行だけが researchmap 出力の対象になる）

researchmap の公開 API（認証不要）から published_papers / presentations / books_etc / misc を取得する。
対応表にある業績は build.py の researchmap 出力（insert）から外れる。
スプレッドシートの rm_id 列に値がある行はそちらが優先される（対応表は不要）。

典型的な運用: シートに追加 → build.py --fetch で CSV 化 → researchmap にアップロード
  → 本スクリプト --apply（登録されたものが対応表に入り、次回から出力されない）
"""
import argparse
import csv
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pubcommon import norm_title  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "publications.csv"
IDS_PATH = ROOT / "data" / "researchmap_ids.csv"
CONFIG = ROOT / "scripts" / "config.json"
TARGETS = ["published_papers", "presentations", "books_etc", "misc"]
TITLE_KEYS = {"published_papers": "paper_title", "presentations": "presentation_title",
              "books_etc": "book_title", "misc": "paper_title"}
IDS_COLUMNS = ["key", "title", "year", "rm_target", "rm_id"]


def load_ids() -> dict[str, dict]:
    """対応表を読む: 正規化タイトル -> {title, year, rm_target, rm_id}"""
    if not IDS_PATH.exists():
        return {}
    return {r["key"]: r for r in csv.DictReader(IDS_PATH.open(encoding="utf-8-sig"))}


def save_ids(table: dict[str, dict]) -> None:
    with IDS_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=IDS_COLUMNS, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in sorted(table.values(), key=lambda r: (r.get("year") or "", r["title"])):
            w.writerow(r)


def fetch_all(permalink: str, target: str) -> list[dict]:
    items, start = [], 1
    while True:
        url = f"https://api.researchmap.jp/{permalink}/{target}?limit=1000&start={start}"
        req = urllib.request.Request(url, headers={"User-Agent": "pub-sync/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        items += d.get("items", [])
        if len(items) >= d.get("total_items", 0) or not d.get("items"):
            return items
        start += len(d["items"])


def label(r: dict) -> str:
    return r.get("id") or f"row {r['_line']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--permalink", default=None, help="researchmap の permalink（既定: config.json の researchmap_permalink）")
    ap.add_argument("--quiet", action="store_true", help="UNMATCHED の一覧を表示しない")
    ap.add_argument("--baseline", action="store_true",
                    help="一致しなかった行も rm_id=skip で対応表に入れ、以後の出力対象から外す")
    args = ap.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    permalink = args.permalink or cfg.get("researchmap_permalink")
    if not permalink:
        sys.exit("--permalink か scripts/config.json の researchmap_permalink を指定してください")

    # researchmap 側: 正規化タイトル -> [(target, id, 表示タイトル)]
    index: dict[str, list[tuple[str, str, str]]] = {}
    for t in TARGETS:
        items = fetch_all(permalink, t)
        print(f"researchmap {t}: {len(items)} items")
        for it in items:
            titles = it.get(TITLE_KEYS[t], {}) or {}
            for lang_title in titles.values():
                if lang_title:
                    index.setdefault(norm_title(lang_title), []).append((t, it["rm:id"], lang_title))

    table = load_ids()
    used_ids = {r["rm_id"] for r in table.values()}
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
    for i, r in enumerate(rows, start=2):
        r["_line"] = i

    new = ambiguous = unmatched = already = skipped = 0
    for r in rows:
        key = norm_title(r["title"])
        if r.get("rm_id") or key in table:
            already += 1
            continue
        cands = []
        for title in (r["title"], r.get("title_ja", "")):
            if title:
                cands += index.get(norm_title(title), [])
        cands = [c for c in dict.fromkeys(cands) if c[1] not in used_ids]
        if len(cands) == 1:
            t, rid, _ = cands[0]
            table[key] = {"key": key, "title": r["title"], "year": r.get("year", ""), "rm_target": t, "rm_id": rid}
            used_ids.add(rid)
            new += 1
            print(f"MATCHED   {label(r)}: {r['title'][:60]} -> {t}/{rid}")
        else:
            if len(cands) > 1:
                ambiguous += 1
                print(f"AMBIGUOUS {label(r)}: {r['title'][:60]} -> {[(c[0], c[1]) for c in cands]}")
            else:
                unmatched += 1
                if not args.quiet:
                    print(f"UNMATCHED {label(r)} [{r['category']} {r['year']}]: {r['title'][:70]}")
            if args.baseline:
                table[key] = {"key": key, "title": r["title"], "year": r.get("year", ""),
                              "rm_target": "", "rm_id": "skip"}
                skipped += 1

    print(f"\nnew={new} ambiguous={ambiguous} unmatched={unmatched} already={already}"
          + (f" -> baseline skip={skipped}" if args.baseline else ""))
    if args.apply:
        save_ids(table)
        print(f"written -> {IDS_PATH} ({len(table)} entries)")
    elif new:
        print("（--apply を付けると data/researchmap_ids.csv に書き込みます）")


if __name__ == "__main__":
    main()
