"""data/publications.csv をカテゴリごとの CSV（data/sheets/<category>.csv）に分割する。
カテゴリ別シート方式でスプレッドシートを作るとき、各シートへの初期インポート用に使う。
category 列は（シート名で決まるので）出力しない。

使い方:  python scripts/split_csv.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pubcommon import COLUMNS, CATEGORIES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "publications.csv"
OUT_DIR = ROOT / "data" / "sheets"


def main():
    rows = list(csv.DictReader(SRC.open(encoding="utf-8-sig")))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cols = [c for c in COLUMNS if c != "category"]
    for cat in CATEGORIES:
        part = [r for r in rows if r["category"] == cat]
        path = OUT_DIR / f"{cat}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            w.writerows(part)
        print(f"{cat}: {len(part)} rows -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
