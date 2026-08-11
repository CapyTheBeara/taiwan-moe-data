import sqlite3

from kautian.relations.records import ANTONYM_OF, SYNONYM_OF

ENTRYLESS_TYPES = ("單字不成詞者", "近反義詞不單列詞目者", "臺華共同詞")

BY_WORD = "詞目id"
BY_SENSE = "義項id"

EDGES = (
    (SYNONYM_OF, "詞目tuì詞目近義", BY_WORD, "對應詞目id", BY_WORD),
    (ANTONYM_OF, "詞目tuì詞目反義", BY_WORD, "對應詞目id", BY_WORD),
    (SYNONYM_OF, "義項tuì詞目近義", BY_SENSE, "對應詞目id", BY_WORD),
    (ANTONYM_OF, "義項tuì詞目反義", BY_SENSE, "對應詞目id", BY_WORD),
    (SYNONYM_OF, "義項tuì義項近義", BY_SENSE, "對應義項id", BY_SENSE),
    (ANTONYM_OF, "義項tuì義項反義", BY_SENSE, "對應義項id", BY_SENSE),
)
"""The six relation tables, each read as "詞目漢字 names the far end".

The near end is the naming headword; four tables key it by 義項id and both ends
of the 義項tuì義項 pair are senses, so each is resolved through 義項 the same way
kautian/detail/records.py resolves 對應詞目id.
"""


def _sense_owner(connection):
    return {
        sense_id: word_id
        for word_id, sense_id in connection.execute('select "詞目id", "義項id" from "義項"')
    }


def _eligible(connection):
    marks = ", ".join("?" * len(ENTRYLESS_TYPES))
    cursor = connection.execute(
        f'select "詞目id" from "詞目" where "詞目類型" in ({marks})', ENTRYLESS_TYPES
    )
    return {word_id for (word_id,) in cursor}


def _edges(connection, sense_owner):
    found = []
    for group, table, near, target_column, far in EDGES:
        cursor = connection.execute(
            f'select "{near}", "詞目漢字", "{target_column}" from "{table}"'
        )
        for near_id, hanji, far_id in cursor:
            word_id = sense_owner.get(near_id) if near == BY_SENSE else near_id
            target = sense_owner.get(far_id) if far == BY_SENSE else far_id
            if word_id is None or target is None:
                continue
            found.append((group, word_id, (hanji or "").strip(), target))
    return found


def read(db_path):
    """Read the relation edges, the entry-less id space, and kautian's max id."""
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        sense_owner = _sense_owner(connection)
        edges = _edges(connection, sense_owner)
        eligible = _eligible(connection)
        max_id = connection.execute('select max("詞目id") from "詞目"').fetchone()[0]
    finally:
        connection.close()
    return edges, eligible, max_id
