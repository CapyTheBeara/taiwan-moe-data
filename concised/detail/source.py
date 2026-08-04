import sqlite3

from concised.detail.records import COLUMNS

SHARED_TYPE = "臺華共同詞"
SUBSTITUTE = "【替】"


def _headwords(connection):
    cursor = connection.execute(
        'select "詞目id", "漢字" from "詞目" where "詞目類型" = ? order by "詞目id"',
        (SHARED_TYPE,),
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


def read(kautian_db, concised_db):
    """Read the 臺華共同詞 headwords, the Concised entries, and the kautian id space."""
    kautian = sqlite3.connect(f"file:{kautian_db}?mode=ro", uri=True)
    try:
        headwords = _headwords(kautian)
        max_id = kautian.execute('select max("詞目id") from "詞目"').fetchone()[0]
    finally:
        kautian.close()

    concised = sqlite3.connect(f"file:{concised_db}?mode=ro", uri=True)
    try:
        entries = _entries(concised)
    finally:
        concised.close()

    return headwords, entries, max_id
