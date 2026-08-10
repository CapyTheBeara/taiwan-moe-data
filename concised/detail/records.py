COLUMNS = (
    "字詞名",
    "字詞號",
    "注音一式",
    "漢語拼音",
    "變體類型",
    "變體注音",
    "變體漢語拼音",
    "相似詞",
    "相反詞",
    "釋義",
    "多音參見訊息",
)


def entry(row):
    """Keep the Concised columns that carry content, dropping the padded blanks."""
    kept = {}
    for column in COLUMNS:
        value = (row.get(column) or "").strip()
        if value:
            kept[column] = value
    return kept


def build(headwords, entries):
    """Shape one record per entry-less headword the Concised dictionary covers."""
    records = {}
    for word_id, name in headwords:
        rows = [shaped for shaped in (entry(row) for row in entries.get(name, ())) if shaped]
        if rows:
            records[word_id] = {"concised": rows}
    return records
