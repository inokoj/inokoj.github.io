"""publications.csv の列定義など、import_html.py / build.py で共有する定義。"""

# マスタ（Google スプレッドシート / data/publications.csv）の列
COLUMNS = [
    "id",          # 任意。エラー表示や照合レポートで行を指すラベル。新規行は空欄でよい
    "category",    # journal / invited / conference_i / conference_j / book / kaisetsu / other
    "year",        # 発行年（並び順と researchmap の出版年月に使用）
    "month",       # 発行月（任意, 1-12）
    "authors",     # サイト表示どおりの著者文字列（末尾のピリオドは不要）
    "title",       # タイトル
    "title_ja",    # 和訳タイトル（journal の括弧書き）。任意
    "note",        # タイトルの下に追加表示する行（書籍の章題など）。セル内改行で複数行
    "venue",       # 掲載先の表示文字列（末尾の ", 2024." は不要。build が year を付ける）
    "links",       # 「ラベル | URL」を1行ずつ（セル内改行）。例: Link | https://...
    "award",       # 受賞（赤字表示）。複数は ; 区切り
    "hidden",      # TRUE ならサイトに表示しない
    # ---- researchmap 連携用（任意）----
    "rm_id",       # researchmap の業績ID（手動指定用。通常は data/researchmap_ids.csv で管理するので空欄）
    "rm_target",   # published_papers / presentations / books_etc / misc（空欄なら category から自動）
    "rm_type",     # 掲載種別/会議種別/著書種別（空欄なら category から自動）
    "rm_skip",     # TRUE なら researchmap 出力から除外
    "journal",     # 誌名（空欄なら venue を使用）
    "volume",
    "number",
    "pages",       # "12-34" 形式
    "doi",
    "referee",     # TRUE/FALSE（空欄なら category から自動）
    "lang",        # jpn / eng（空欄なら title から自動判定）
]

CATEGORIES = {
    "journal":      "学術雑誌 (Journal papers)",
    "invited":      "招待講演 (Invited talk)",
    "conference_i": "国際会議 (International conference)",
    "conference_j": "全国大会・研究会",
    "book":         "書籍 (Books)",
    "kaisetsu":     "学会誌",
    "other":        "Others",
}

# category → researchmap の (target, type, referee, international) 既定値
RM_DEFAULTS = {
    "journal":      ("published_papers", "scientific_journal", "TRUE", None),
    "conference_i": ("published_papers", "international_conference_proceedings", "TRUE", "TRUE"),
    "conference_j": ("published_papers", "symposium", "FALSE", "FALSE"),
    "invited":      ("presentations", "invited_oral_presentation", None, None),
    "book":         ("books_etc", "scholarly_book", None, None),
    "kaisetsu":     ("misc", "introduction_scientific_journal", "FALSE", None),
    "other":        ("presentations", "others", None, None),
}

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})


def is_japanese(s: str) -> bool:
    return any("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" for ch in s)


def norm_title(s: str) -> str:
    """タイトル照合用の正規化（NFKC・小文字化・英数字と仮名漢字以外を除去）。"""
    import re
    import unicodedata
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[^0-9a-z぀-ヿ一-鿿]+", "", s)
