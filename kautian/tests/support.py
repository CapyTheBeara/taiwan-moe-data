import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from kautian.detail.records import ACCENT_COLUMNS

SCHEMA = {
    "詞目": ("詞目id", "詞目類型", "漢字", "羅馬字", "分類", "羅馬字音檔檔名"),
    "義項": ("詞目id", "義項id", "詞性", "解說"),
    "例句": ("詞目id", "義項id", "例句順序", "漢字", "羅馬字", "華語", "音檔檔名"),
    "異用字": ("詞目id", "漢字", "異用字"),
    "語音差異": ("詞目id", "漢字") + ACCENT_COLUMNS,
    "詞目tuì詞目近義": ("詞目id", "詞目漢字", "對應詞目id", "對應詞目漢字"),
    "詞目tuì詞目反義": ("詞目id", "詞目漢字", "對應詞目id", "對應詞目漢字"),
    "義項tuì義項近義": ("義項id", "詞目漢字", "解說", "對應義項id", "對應詞目漢字", "對應解說"),
    "義項tuì義項反義": ("義項id", "詞目漢字", "解說", "對應義項id", "對應詞目漢字", "對應解說"),
    "義項tuì詞目近義": ("義項id", "詞目漢字", "解說", "對應詞目id", "對應詞目漢字"),
    "義項tuì詞目反義": ("義項id", "詞目漢字", "解說", "對應詞目id", "對應詞目漢字"),
}


def build_db(path, rows):
    """Write a synthetic kautian.db holding only the rows a test needs."""
    connection = sqlite3.connect(path)
    for table, columns in SCHEMA.items():
        declared = ", ".join(f'"{column}"' for column in columns)
        connection.execute(f'create table "{table}" ({declared})')
        for row in rows.get(table, []):
            marks = ", ".join("?" * len(columns))
            connection.execute(f'insert into "{table}" values ({marks})', row)
    connection.commit()
    connection.close()
    return path


def accents(word_id, hanji, reading):
    return (word_id, hanji) + (reading,) * len(ACCENT_COLUMNS)
