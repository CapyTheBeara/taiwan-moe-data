"""
webjson.py — the Concised entry-less headword set as a KTWEB1 document.

`concised/v3/` answers one 詞目id at a time over HTTP range requests. This is the
other shape of the same data: one JSON file small enough to ship whole, decoded
in the browser by `kautian/web/kautian.mjs` — the same decoder, unmodified.

That reuse is the point, and it is what constrains the format here. Concised
carries no romanisation and no cross-table joins, so none of the decoder's
interesting machinery applies: no `tailo` columns, no derived rules, and
therefore no reading model. Every column is either a plain JSON array or an
`enum`, both of which the decoder already handles. `model` rides as `{}` because
only `decodeTailo` reads it.

The population is not this module's decision. `concised.detail.records.build`
picks which headwords earn a record and which columns survive on each one, and
this module flattens whatever that returns. So the document and the container
cannot disagree about their contents without `records.build` disagreeing with
itself — parity by construction rather than by a matching pair of rules.

One row per (詞目id, Concised entry), so a polyphone contributes several rows in
the order `records.build` emitted them. The container's records omit a blank
column entirely; the columnar form has no way to say "absent" per row, so a
dropped column reads back as `None`. Dropping the null keys off a decoded row
returns the container's record exactly.
"""

from concised.detail.records import COLUMNS
from kautian.opt.webjson import FORMAT, enum_column, is_enumerable

TABLE = "簡編"
ID_COLUMN = "詞目id"
DOCUMENT_COLUMNS = (ID_COLUMN,) + COLUMNS


def to_columns(records):
    """Flatten the built records into one list per column, one row per entry."""
    values = {column: [] for column in DOCUMENT_COLUMNS}
    for word_id in sorted(records):
        for entry in records[word_id]["concised"]:
            values[ID_COLUMN].append(word_id)
            for column in COLUMNS:
                values[column].append(entry.get(column))
    return values


def to_document(records):
    """Build the KTWEB1 document from `concised.detail.records.build` output."""
    columns = to_columns(records)
    rows = len(columns[ID_COLUMN])
    return {
        "format": FORMAT,
        "model": {},
        "tables": [
            {
                "name": TABLE,
                "columns": list(DOCUMENT_COLUMNS),
                "rows": rows,
                "values": {
                    column: enum_column(values) if is_enumerable(values) else values
                    for column, values in columns.items()
                },
            }
        ],
    }
