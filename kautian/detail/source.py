import sqlite3

TABLES = (
    "義項",
    "例句",
    "異用字",
    "語音差異",
    "詞目tuì詞目近義",
    "詞目tuì詞目反義",
    "義項tuì義項近義",
    "義項tuì義項反義",
    "義項tuì詞目近義",
    "義項tuì詞目反義",
)


def _rows(connection, table):
    cursor = connection.execute(f'select * from "{table}"')
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor]


def read(db_path):
    """Read every table the detail records draw on into plain dicts."""
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {table: _rows(connection, table) for table in TABLES}
        headwords = _rows(connection, "詞目")
    finally:
        connection.close()

    sense_owner = {row["義項id"]: row["詞目id"] for row in tables["義項"]}
    categories = {
        row["詞目id"]: row["分類"] for row in headwords if row["分類"] not in (None, "")
    }
    max_id = max(row["詞目id"] for row in headwords)
    return tables, sense_owner, categories, max_id
