import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from concised.detail.records import COLUMNS

CONCISED_COLUMNS = (
    "字詞名",
    "字詞號",
    "部首字",
    "總筆畫數",
    "部首外筆畫數",
    "多音排序",
    "注音一式",
    "變體類型",
    "變體注音",
    "漢語拼音",
    "變體漢語拼音",
    "相似詞",
    "相反詞",
    "釋義",
    "多音參見訊息",
)

KAUTIAN_COLUMNS = ("詞目id", "詞目類型", "漢字", "羅馬字", "分類", "羅馬字音檔檔名")


def _create(connection, table, columns, rows):
    declared = ", ".join(f'"{column}"' for column in columns)
    connection.execute(f'create table "{table}" ({declared})')
    marks = ", ".join("?" * len(columns))
    for row in rows:
        connection.execute(f'insert into "{table}" values ({marks})', row)


def build_dbs(directory, headwords, entries):
    """Write a synthetic kautian.db and concised.db holding only what a test needs."""
    kautian_db = Path(directory) / "kautian.db"
    concised_db = Path(directory) / "concised.db"

    connection = sqlite3.connect(kautian_db)
    _create(connection, "詞目", KAUTIAN_COLUMNS, headwords)
    connection.commit()
    connection.close()

    connection = sqlite3.connect(concised_db)
    _create(connection, "concised", CONCISED_COLUMNS, entries)
    connection.commit()
    connection.close()

    return kautian_db, concised_db


def headword(word_id, hanji, word_type="臺華共同詞"):
    return (word_id, word_type, hanji, "tâi-gí", "", "")


def entry(name, number="1", order="0", **overrides):
    values = dict.fromkeys(CONCISED_COLUMNS, "")
    values["字詞名"] = name
    values["字詞號"] = number
    values["多音排序"] = order
    values.update(overrides)
    return tuple(values[column] for column in CONCISED_COLUMNS)


def kept(name, **overrides):
    shaped = {"字詞名": name, "字詞號": "1", **overrides}
    return {column: shaped[column] for column in COLUMNS if column in shaped}
