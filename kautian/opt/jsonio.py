"""
jsonio.py — the dataset as a JSON document, so the container can be built from
JSON and unpacked back to JSON without a SQLite file in the loop.

The compressed bytes are the same either way. Compression never sees this
document: `container.encode_dataset` takes the same (schema, columns, header)
triple whether it came from a .db, from JSON, or from another container, so
`.json -> .ktz -> .json` and `.db -> .ktz -> .db` are the same 1.3 MB payload.

The document has two halves:

- `tables` is the dictionary — one array of row objects per table, keys in
  column order, SQL NULL as JSON null. This is the half a reader wants.
- `sqlite` is the byte-identity half: the `sqlite_master` statements in creation
  order, each column's declared type, and the header fields SQLite does not
  recompute. It is a few kilobytes and it is what lets the rebuilt .db match the
  original's SHA-256. Drop it and you still have every value, but you can no
  longer reproduce the file.

Row objects rather than parallel arrays: the document is meant to be read by
something other than this repository, and column-oriented JSON is not. The cost
is the repeated keys, and it is paid in the .json file only — never on the wire.
"""

import json

FORMAT = "KTJSON1"


def to_document(manifest, context):
    """Build the JSON document from a decoded container."""
    rows = {}
    for entry in manifest["tables"]:
        names = [column["name"] for column in entry["columns"]]
        columns = [context[entry["name"]][name] for name in names]
        rows[entry["name"]] = [dict(zip(names, values)) for values in zip(*columns)]
    return {
        "format": FORMAT,
        "sqlite": {
            "header": manifest["header"],
            "tables": [
                {
                    "name": entry["name"],
                    "sql": entry["sql"],
                    "columns": [[column["name"], column["type"]] for column in entry["columns"]],
                }
                for entry in manifest["tables"]
            ],
        },
        "tables": rows,
    }


def from_document(document):
    """Return the dataset — (schema, columns, header) — held by a JSON document."""
    if document.get("format") != FORMAT:
        raise ValueError(f"not a {FORMAT} document")
    schema = [
        {"name": entry["name"], "sql": entry["sql"], "columns": [tuple(column) for column in entry["columns"]]}
        for entry in document["sqlite"]["tables"]
    ]
    data = {}
    for entry in schema:
        rows = document["tables"].get(entry["name"], [])
        data[entry["name"]] = {
            name: [_value(entry["name"], name, index, row.get(name)) for index, row in enumerate(rows)]
            for name, _ in entry["columns"]
        }
    return schema, data, document["sqlite"]["header"]


def _value(table, column, index, value):
    """Reject anything SQLite would store under a different storage class.

    A JSON reader that writes 1.0 where the database holds 1, or true where it
    holds a string, produces a file that is no longer byte-identical — and the
    mismatch would otherwise only surface as a failed SHA-256 at the very end.
    """
    if value is None or isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool)):
        return value
    raise ValueError(f"{table}.{column} row {index}: {type(value).__name__} is not a text, integer or null value")


def dump(document, path):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
