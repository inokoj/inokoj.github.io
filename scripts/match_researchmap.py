"""researchmap に既に登録済みの業績と data/publications.csv をタイトルで突き合わせ、
rm_id（researchmap 業績ID）を埋める。

使い方:
  python scripts/match_researchmap.py            # 照合結果を表示するだけ（dry run）
  python scripts/match_researchmap.py --apply    # 一意に一致した行の rm_id / rm_target を CSV に書き込む

researchmap の公開 API（認証不要）から published_papers / presentations / books_etc / misc を取得する。
rm_id が埋まった行は build.py の researchmap 出力で「update」扱いになる（--rm-all 指定時のみ出力）。
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pubcommon import COLUMNS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "publications.csv"
CONFIG = ROOT / "scripts" / "config.json"
TARGETS = ["published_papers", "presentations", "books_etc", "misc"]
TITLE_KEYS = {"published_papers": "paper_title", "presentations": "presentation_title",
              "books_etc": "book_title", "misc": "paper_title"}


def norm_title(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[^0-9a-z぀-ヿ一-鿿]+", "", s)


def fetch_all(permalink: str, target: str) -> list[dict]:
    items, start = [], 1
    while True:
        url = f"https://api.researchmap.jp/{permalink}/{target}?limit=1000&start={start}"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "pub-sync/1.0"}), timeout=60) as r:
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

    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
    for i, r in enumerate(rows, start=2):
        r["_line"] = i
    matched = ambiguous = unmatched = already = 0
    used_ids = set()
    for r in rows:
        if r.get("rm_id"):
            already += 1
            continue
        cands = []
        for title in (r["title"], r.get("title_ja", "")):
            if title:
                cands += index.get(norm_title(title), [])
        cands = [c for c in dict.fromkeys(cands) if c[1] not in used_ids]
        if len(cands) == 1:
            t, rid, _ = cands[0]
            r["rm_id"], r["rm_target"] = rid, t
            used_ids.add(rid)
            matched += 1
        elif len(cands) > 1:
            ambiguous += 1
            print(f"AMBIGUOUS {label(r)}: {r['title'][:60]} -> {[(c[0], c[1]) for c in cands]}")
        else:
            unmatched += 1
            print(f"UNMATCHED {label(r)} [{r['category']} {r['year']}]: {r['title'][:70]}")

    print(f"\nmatched={matched} ambiguous={ambiguous} unmatched={unmatched} already={already}")
    if args.apply:
        with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"written -> {CSV_PATH}（スプレッドシート側にも rm_id / rm_target 列を反映してください）")
    else:
        print("（--apply を付けると CSV に書き込みます）")


if __name__ == "__main__":
    main()
