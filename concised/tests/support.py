import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from concised.detail.records import COLUMNS


def _load_kautian_support():
    """kautian's own test support, by path — its tests package is not importable.

    The concised container now has to know which ids kautian/v1 already covers,
    so its fixtures need kautian's full detail schema. Borrowing the builder
    keeps that schema defined once, where kautian's own tests will notice it
    drifting.
    """
    path = ROOT / "kautian" / "tests" / "support.py"
    spec = importlib.util.spec_from_file_location("kautian_test_support", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kautian_support = _load_kautian_support()

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

def build_dbs(directory, headwords, entries, kautian_rows=None):
    """Write a synthetic kautian.db and concised.db holding only what a test needs.

    kautian_rows adds detail rows (異用字, 義項, …) for a headword, which is how a
    test says "kautian/v1 already covers this id".
    """
    kautian_db = Path(directory) / "kautian.db"
    concised_db = Path(directory) / "concised.db"

    kautian_support.build_db(kautian_db, {"詞目": headwords, **(kautian_rows or {})})

    connection = sqlite3.connect(concised_db)
    declared = ", ".join(f'"{column}"' for column in CONCISED_COLUMNS)
    connection.execute(f'create table "concised" ({declared})')
    marks = ", ".join("?" * len(CONCISED_COLUMNS))
    for row in entries:
        connection.execute(f"insert into concised values ({marks})", row)
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
