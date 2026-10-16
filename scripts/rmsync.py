"""researchmap 公開 API（認証不要）から登録済み業績を取得し、マスタの行とタイトルで照合する。

照合できた業績は対応表 data/researchmap_ids.csv（正規化タイトル → researchmap 業績ID）に記録する。
build.py から呼ばれるので、通常このモジュールを直接使う必要はない。
"""
import csv
import json
import urllib.request
from pathlib import Path

from pubcommon import RM_DEFAULTS, norm_title

ROOT = Path(__file__).resolve().parent.parent
IDS_PATH = ROOT / "data" / "researchmap_ids.csv"
IDS_COLUMNS = ["key", "title", "year", "rm_target", "rm_id"]
TARGETS = ["published_papers", "presentations", "books_etc", "misc"]
TITLE_KEYS = {"published_papers": "paper_title", "presentations": "presentation_title",
              "books_etc": "book_title", "misc": "paper_title"}


def load_ids() -> dict[str, dict]:
    """対応表を読む: 正規化タイトル -> {key, title, year, rm_target, rm_id}"""
    if not IDS_PATH.exists():
        return {}
    rows = csv.DictReader(IDS_PATH.open(encoding="utf-8-sig"))
    # 旧方式の rm_id="skip"（--baseline で付けた「対応済み扱い」）は無視する
    return {r["key"]: r for r in rows if r["rm_id"] and r["rm_id"] != "skip"}


def save_ids(table: dict[str, dict]) -> None:
    with IDS_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=IDS_COLUMNS, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in sorted(table.values(), key=lambda r: (r.get("year") or "", r["title"])):
            w.writerow(r)


def _fetch_target(permalink: str, target: str) -> list[dict]:
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


def fetch_registered(permalink: str) -> dict[str, list[tuple[str, str]]]:
    """researchmap 側の業績: 正規化タイトル -> [(target, 業績ID)]"""
    index: dict[str, list[tuple[str, str]]] = {}
    for t in TARGETS:
        for it in _fetch_target(permalink, t):
            for title in (it.get(TITLE_KEYS[t]) or {}).values():
                if title:
                    index.setdefault(norm_title(title), []).append((t, it["rm:id"]))
    return index


def match(rows: list[dict], table: dict[str, dict], index: dict) -> list[dict]:
    """対応表に無い行を researchmap 側とタイトルで照合し、一致したものを table に追加する。
    researchmap 側に同名の業績が複数あるときは、category から想定される種別のものを優先する。
    戻り値: 新たに一致した行"""
    used = {e["rm_id"] for e in table.values()}
    matched = []
    for r in rows:
        key = norm_title(r["title"])
        if r["rm_id"] or key in table:
            continue
        cands = []
        for title in (r["title"], r["title_ja"]):
            if title:
                cands += index.get(norm_title(title), [])
        cands = [c for c in dict.fromkeys(cands) if c[1] not in used]
        if not cands:
            continue
        expected = r["rm_target"] or RM_DEFAULTS.get(r["category"], ("",))[0]
        target, rid = next((c for c in cands if c[0] == expected), cands[0])
        table[key] = {"key": key, "title": r["title"], "year": r["year"], "rm_target": target, "rm_id": rid}
        used.add(rid)
        matched.append(r)
    return matched
