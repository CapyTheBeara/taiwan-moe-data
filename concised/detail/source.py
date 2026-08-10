import sqlite3

from concised.detail.records import COLUMNS
from kautian.detail import records as kautian_records
from kautian.detail import source as kautian_source

SHARED_TYPE = "臺華共同詞"
BOUND_TYPE = "單字不成詞者"
ENTRYLESS_TYPES = (SHARED_TYPE, BOUND_TYPE)
SUBSTITUTE = "【替】"


def _headwords(connection):
    marks = ", ".join("?" * len(ENTRYLESS_TYPES))
    cursor = connection.execute(
        f'select "詞目id", "漢字" from "詞目" where "詞目類型" in ({marks}) order by "詞目id"',
        ENTRYLESS_TYPES,
    )
    return [
        (word_id, hanji.replace(SUBSTITUTE, "").strip())
        for word_id, hanji in cursor
        if hanji and hanji.replace(SUBSTITUTE, "").strip()
    ]


def _entries(connection):
    columns = ", ".join(f'"{column}"' for column in COLUMNS)
    cursor = connection.execute(
        f'select {columns} from "concised" order by cast("多音排序" as integer), "字詞號"'
    )
    entries = {}
    for row in cursor:
        entry = dict(zip(COLUMNS, row))
        name = (entry["字詞名"] or "").strip()
        if name:
            entries.setdefault(name, []).append(entry)
    return entries


def _covered_by_kautian(kautian_db):
    """The ids kautian/v1 gives a record, derived by running its own builder.

    A 詞目類型 says the headword has no 義項; it does not promise the headword has
    no record at all. 102 單字不成詞者 carry an 異用字 or a 語音差異 and nothing
    else, which is enough for kautian/v1 to hold them. Those ids are dropped here
    so "no id is live in both containers" stays a fact rather than a hope — the
    client tries kautian first, so a record here would be unreachable bytes.
    """
    tables, sense_owner, categories, _ = kautian_source.read(kautian_db)
    return set(kautian_records.build(tables, sense_owner, categories))


def read(kautian_db, concised_db):
    """Read the entry-less headwords, the Concised entries, and the kautian id space."""
    kautian = sqlite3.connect(f"file:{kautian_db}?mode=ro", uri=True)
    try:
        headwords = _headwords(kautian)
        max_id = kautian.execute('select max("詞目id") from "詞目"').fetchone()[0]
    finally:
        kautian.close()

    covered = _covered_by_kautian(kautian_db)
    headwords = [pair for pair in headwords if pair[0] not in covered]

    concised = sqlite3.connect(f"file:{concised_db}?mode=ro", uri=True)
    try:
        entries = _entries(concised)
    finally:
        concised.close()

    return headwords, entries, max_id
