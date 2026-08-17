"""
webjson.py — the dataset as JSON a browser can decompress natively and turn
into objects with a small, dependency-free decoder.

`kautian.ktz` is 1.33 MB but only a Python decoder can read it: LZMA is not in
any browser, and the section format needs the full column-plan machinery. This
module answers the other question — how small can the dataset get while a
browser still decodes it with `Content-Encoding: br` plus about a hundred lines
of JavaScript.

Measured with `brotli -q 11 --lgwin 24`, against the same 19 tables:

    row objects (KTJSON1)                     2,286,506   nothing to decode
    columnar, nothing modelled                1,786,097   zip columns to rows
    + derived rules                           1,581,696   + joins and templates
    + tailo ranks, model shipped (this)       1,481,704   + rank lookup
    + tailo ranks, model derived              1,429,192   exact tie-break needed
    kautian.ktz (LZMA sections)               1,325,703   full port + LZMA

This module builds the fourth row. The last 156 KB are not worth what they
cost: LZMA in the bundle, and a reading model both ends must derive *identically*
— frequency order with an alphabetical tie-break — where any disagreement
desynchronises the rank column silently rather than failing loudly. Shipping the
model instead costs 23 KB compressed and makes that class of bug impossible.

What is left is close to the floor. 例句, 義項 and 詞目 are 1,276,439 of the
1,481,704, and they are prose — definitions and example sentences — which no
amount of modelling removes.

This is a projection, not the archive. Every row and value survives, but the
`sqlite_master` statements and header fields do not, so the .db cannot be
rebuilt from it. `kautian.ktz` remains the archival form.

Three column shapes, matching `kautian/web/kautian.mjs`:

- a plain JSON array — values as they are;
- `{rule, args, at, is}` — a derived column, as the rule to re-run plus the rows
  where it is wrong. Same rules and same forward-pass order as the container:
  a rule reads only columns earlier in its own table and tables decoded before
  it, which is what lets the decoder resolve everything in one pass;
- `{tailo, ...}` — romanisation as a rank per Han character into the shipped
  model, with escapes for the readings the model does not hold.
"""

from kautian.opt import tables
from kautian.opt.tailo import ESCAPE_RANK, aligns, build_model, han_characters, tokenize

FORMAT = "KTWEB1"
UNIT = "\x1f"

# A column is enumerated when it is long enough and repetitive enough to pay for it.
ENUM_MIN_ROWS = 64
ENUM_MAX_RATIO = 0.2

NULL, ALIGNED, LITERAL = 2, 1, 0


def _derived_column(rule, arguments, context, rows, values):
    """Store the rule, and the rows where running it would be wrong."""
    predicted = tables.RULES[rule](context, rows, *arguments)
    exceptions = [index for index, value in enumerate(values) if value != predicted[index]]
    return {
        "rule": rule,
        "args": list(arguments),
        "at": exceptions,
        "is": [values[index] for index in exceptions],
    }


def _tailo_column(hanji_column, hanji_values, values, model):
    """Store each syllable as its rank in its character's reading list.

    A row is `ALIGNED` when the reading has one syllable per Han character, and
    only then is it rank-coded; anything else rides as a literal. `NULL` is its
    own state so an absent reading is never confused with an empty one.
    """
    aligned, ranks, escapes, caps, separators, literals = [], [], [], [], [], []
    for hanji, reading in zip(hanji_values, values):
        if reading is None:
            aligned.append(NULL)
            continue
        if not aligns(hanji, reading):
            aligned.append(LITERAL)
            literals.append(reading)
            continue
        aligned.append(ALIGNED)
        syllables, gaps = tokenize(reading)
        for character, syllable in zip(han_characters(hanji), syllables):
            caps.append(1 if syllable[:1].isupper() else 0)
            lowered = syllable.lower()
            candidates = model.get(character)
            if candidates and lowered in candidates and candidates.index(lowered) < ESCAPE_RANK:
                ranks.append(candidates.index(lowered))
            else:
                ranks.append(ESCAPE_RANK)
                escapes.append(lowered)
        separators.append(UNIT.join(gaps))
    return {
        "tailo": hanji_column,
        "aligned": aligned,
        "ranks": ranks,
        "escapes": escapes,
        "caps": caps,
        "separators": separators,
        "literals": literals,
    }


def enum_column(values):
    """Store one copy of each distinct value, and an index per row.

    Worth doing twice over. On the wire the indices compress to almost nothing,
    and in the browser `JSON.parse` allocates one string per distinct value
    instead of one per row — 詞目.分類 alone is 29,591 rows over 106 values. The
    null rides in the table as an entry of its own, so no sentinel is needed.
    """
    table = []
    lookup = {}
    indices = []
    for value in values:
        key = (value is None, value)
        if key not in lookup:
            lookup[key] = len(table)
            table.append(value)
        indices.append(lookup[key])
    return {"enum": table, "at": indices}


def is_enumerable(values):
    """Enumerate a column when the repeats pay for the indirection."""
    return len(values) >= ENUM_MIN_ROWS and len(set(values)) <= len(values) * ENUM_MAX_RATIO


def to_document(schema, data, _header=None):
    """Build the browser document from a dataset.

    Takes the same triple as `container.encode_dataset`, so it does not care
    whether the dataset came from the .db, from JSON, or from a container. The
    header is accepted and ignored: byte-identity is not this format's job.
    """
    source_table, hanji_column, reading_column = tables.MODEL_SOURCE
    model = build_model(zip(data[source_table][hanji_column], data[source_table][reading_column]))

    context = {}
    document = {"format": FORMAT, "model": model, "tables": []}
    for entry in schema:
        name = entry["name"]
        rows = data[name]
        plan = tables.PLAN[name]
        values = {}
        for column, _declared in entry["columns"]:
            spec = plan[column]
            if spec[0] == tables.DERIVED:
                values[column] = _derived_column(spec[1], spec[2], context, rows, rows[column])
            elif spec[0] == tables.TAILO:
                values[column] = _tailo_column(spec[1], rows[spec[1]], rows[column], model)
            elif is_enumerable(rows[column]):
                values[column] = enum_column(rows[column])
            else:
                values[column] = rows[column]
        document["tables"].append(
            {
                "name": name,
                "columns": [column for column, _ in entry["columns"]],
                "rows": len(rows[entry["columns"][0][0]]) if entry["columns"] else 0,
                "values": values,
            }
        )
        context[name] = rows
    return document
