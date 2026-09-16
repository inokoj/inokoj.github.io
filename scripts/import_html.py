"""publications.html（現行の手書き版）を解析して data/publications.csv を生成する（初回移行用）。

使い方:  python scripts/import_html.py [publications.html] [data/publications.csv]
解析できなかった箇所は標準エラーに WARNING として出力する。
"""
import csv
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pubcommon import COLUMNS, MONTHS, CATEGORIES  # noqa: E402

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "publications.html")
DST = Path(sys.argv[2] if len(sys.argv) > 2 else "data/publications.csv")

RE_SECTION = re.compile(r'<h2 id="(\w+)" class="subsection-title">')
RE_LI = re.compile(r"<li>(.*?)</li>", re.S)
RE_A = re.compile(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', re.S)
RE_STRONG = re.compile(r"<strong[^>]*>(.*?)</strong>", re.S)
RE_TAG = re.compile(r"<[^>]+>")
# 末尾の年 ", March. 2019." / ", October 2025." / ", 2023." / " 2019." など
# 年の後ろに "(オーラル)" や "Accepted." が付いている場合は tail として venue 末尾に括弧書きで残す
RE_YEAR_TAIL = re.compile(
    r"[,，]?\s*(?:(?P<mon>[A-Za-z]+)\.?\s+)?(?P<year>(?:19|20)\d\d)\s*[.．]?"
    r"\s*(?P<tail>\(.*\)|[A-Za-z]+\.?)?\s*$")
RE_VOL = re.compile(r"\bVol\.?\s*(?P<vol>[\w\-]+)", re.I)
RE_NO = re.compile(r"\bNo\.?\s*(?P<no>[\w\-]+)", re.I)
RE_PP = re.compile(r"\bpp?\.\s*(?P<pp>[\w\-–_]+)", re.I)
RE_JOURNAL_SPLIT = re.compile(r",\s*(?=(?:Vol|No|pp?)\b\.?)", re.I)


def clean(s: str) -> str:
    s = html.unescape(RE_TAG.sub("", s))
    return re.sub(r"\s+", " ", s).strip()


def parse_li(raw: str, category: str, warn):
    links, awards, texts = [], [], []
    for line in re.split(r"<br\s*/?>", raw):
        for href, label in RE_A.findall(line):
            links.append(f"{clean(label)} | {html.unescape(href).strip()}")
        line = RE_A.sub("", line)
        for a in RE_STRONG.findall(line):
            awards.append(clean(a))
        line = RE_STRONG.sub("", line)
        t = clean(line).strip("[] ,")
        # リンクを取り除いた残骸（"[] []" など）を捨てる
        t = re.sub(r"^[\[\]\s,]+$", "", t)
        if t:
            texts.append(t)
    if len(texts) < 3:
        warn(f"text lines < 3: {texts}")
        while len(texts) < 3:
            texts.append("")
    authors, title, venue = texts[0], texts[1], texts[-1]
    middle = texts[2:-1]
    # 最終行に年がなく直前の行にある場合（"Accepted." など）は直前の行を venue にする
    if not re.search(r"(?:19|20)\d\d", venue) and middle and re.search(r"(?:19|20)\d\d", middle[-1]):
        venue = middle.pop() + " " + venue
    title_ja = ""
    if middle and re.fullmatch(r"[（(].*[)）]", middle[0]):
        title_ja = middle.pop(0)[1:-1].strip()
    note = "\n".join(middle)

    year = month = ""
    m = RE_YEAR_TAIL.search(venue)
    if m:
        year = m.group("year")
        mon = (m.group("mon") or "").lower()
        if mon:
            if mon in MONTHS:
                month = str(MONTHS[mon])
            else:
                warn(f"unknown month word '{mon}' in venue: {venue}")
                m = None
    if m:
        tail = (m.group("tail") or "").strip().rstrip(".")
        venue = venue[: m.start()].rstrip(" ,，.")
        if tail:
            venue += " " + (tail if tail.startswith("(") else f"({tail})")
    else:
        warn(f"year not found in venue: {venue!r}")

    # researchmap 用の分解（best effort）。journal 名は venue の "Vol/No/pp" 直前まで
    journal = volume = number = pages = ""
    if category in ("journal", "kaisetsu", "conference_i"):
        mv, mn, mp = RE_VOL.search(venue), RE_NO.search(venue), RE_PP.search(venue)
        if mv or mn or mp:
            journal = RE_JOURNAL_SPLIT.split(venue)[0].strip()
            volume = mv.group("vol") if mv else ""
            number = mn.group("no") if mn else ""
            pages = mp.group("pp") if mp else ""
            if "XXXX" in pages:
                pages = ""

    return {
        "category": category,
        "year": year,
        "month": month,
        "authors": authors.rstrip(" ."),
        "title": re.sub(r"(?<!\.)\.$", "", title.strip()),
        "title_ja": title_ja,
        "note": note,
        "venue": venue,
        "links": "\n".join(links),
        "award": "; ".join(awards),
        "hidden": "",
        "journal": journal,
        "volume": volume,
        "number": number,
        "pages": pages,
    }


def main():
    src = SRC.read_text(encoding="utf-8")
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)  # コメントアウトされたリンク等は無視
    # セクションごとに分割
    parts = RE_SECTION.split(src)  # [pre, id1, body1, id2, body2, ...]
    rows = []
    n = 0
    for i in range(1, len(parts), 2):
        cat, body = parts[i], parts[i + 1]
        if cat not in CATEGORIES:
            print(f"WARNING: unknown section id {cat}", file=sys.stderr)
            continue
        for raw in RE_LI.findall(body):
            n += 1
            idx = n

            def warn(msg, idx=idx):
                print(f"WARNING [{cat} #{idx}]: {msg}", file=sys.stderr)

            row = {c: "" for c in COLUMNS}
            row.update(parse_li(raw, cat, warn))
            row["id"] = f"p{idx:04d}"
            rows.append(row)

    DST.parent.mkdir(parents=True, exist_ok=True)
    with DST.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} entries -> {DST}")


if __name__ == "__main__":
    main()
