import sqlite3

from kautian.detail import container


def _types(connection):
    cursor = connection.execute('select "詞目id", "詞目類型" from "詞目"')
    return {word_id: label for word_id, label in cursor}


def _live_ids(idx_path):
    lengths = container.read_lengths(idx_path)
    return {word_id for word_id, length in enumerate(lengths) if length > 0}


def read(db_path, concised_idx_path, relations_idx_path):
    """Read 詞目類型 by id, kautian's max id, and which ids are live in each
    sibling container.

    `concised_idx_path` and `relations_idx_path` are `detail.idx` files from
    concised/v3/ and kautian/rel/v1/ respectively — reused as-is via
    `container.read_lengths`, the same helper their own writer's index format
    is defined by.
    """
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        types = _types(connection)
        max_id = connection.execute('select max("詞目id") from "詞目"').fetchone()[0]
    finally:
        connection.close()

    concised_live = _live_ids(concised_idx_path)
    relations_live = _live_ids(relations_idx_path)
    return types, concised_live, relations_live, max_id
