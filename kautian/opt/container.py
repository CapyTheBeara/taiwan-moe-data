"""
container.py — encode kautian.db to the optimised container and back.

The container is a manifest plus a flat list of opaque byte sections, LZMA'd as
a whole. The manifest fixes the section order, so decoding is a single forward
pass with no offsets to trust. Everything needed to rebuild the SQLite file
byte-for-byte — page size, the header counters SQLite does not recompute, and
the `sqlite_master` statements in creation order — rides in the manifest.

LZMA rather than brotli because this repository is stdlib-only, and on this
payload it also wins: 1,325,532 B against brotli -11's 1,350,704 B. The columnar
layout is what both are really exploiting, not either codec's dictionary.
"""

import json
import lzma
import sqlite3

from kautian.opt import codec, tables
from kautian.opt.tailo import ESCAPE_RANK, aligns, build_model, han_characters, render, tokenize

MAGIC = b"KTOPT1\n"
UNIT = "\x1f"
HEADER_FIELDS = {
    "pageSize": (16, 2),
    "fileChangeCounter": (24, 4),
    "schemaCookie": (40, 4),
    "schemaFormat": (44, 4),
    "textEncoding": (56, 4),
    "userVersion": (60, 4),
    "versionValidFor": (92, 4),
    "sqliteVersion": (96, 4),
}


def _read_header(path):
    with open(path, "rb") as handle:
        head = handle.read(100)
    return {name: int.from_bytes(head[at : at + size], "big") for name, (at, size) in HEADER_FIELDS.items()}


def _columns(connection, table):
    return [(row[1], row[2].upper()) for row in connection.execute(f'pragma table_info("{table}")')]


def _read_tables(connection):
    master = connection.execute("select name, sql from sqlite_master where type='table' order by rowid").fetchall()
    schema = []
    data = {}
    for name, sql in master:
        columns = _columns(connection, name)
        schema.append({"name": name, "sql": sql, "columns": columns})
        rows = connection.execute(f'select * from "{name}"').fetchall()
        data[name] = {column: [row[index] for row in rows] for index, (column, _) in enumerate(columns)}
        data[name]["__rows__"] = len(rows)
    return schema, data


def _encode_tailo(hanji_values, readings, model):
    aligned, ranks, escapes, caps, separators, literals = [], bytearray(), [], [], [], []
    for hanji, reading in zip(hanji_values, readings):
        if not aligns(hanji, reading):
            aligned.append(False)
            literals.append(reading)
            continue
        aligned.append(True)
        syllables, gaps = tokenize(reading)
        for character, syllable in zip(han_characters(hanji), syllables):
            caps.append(syllable[:1].isupper())
            lowered = syllable.lower()
            candidates = model.get(character)
            if candidates and lowered in candidates and candidates.index(lowered) < ESCAPE_RANK:
                ranks.append(candidates.index(lowered))
            else:
                ranks.append(ESCAPE_RANK)
                escapes.append(lowered)
        separators.append(UNIT.join(gaps))
    return [
        codec.encode_mask(aligned),
        bytes(ranks),
        codec.encode_texts(escapes),
        codec.encode_mask(caps),
        codec.encode_texts(separators),
        codec.encode_texts(literals),
    ]


def _decode_tailo(sections, hanji_values, model, count):
    aligned = codec.decode_mask(sections[0], count)
    ranks = sections[1]
    escapes = codec.decode_texts(sections[2])
    caps = codec.decode_mask(sections[3], len(ranks))
    separators = codec.decode_texts(sections[4])
    literals = codec.decode_texts(sections[5])
    out = []
    rank_at = escape_at = separator_at = literal_at = 0
    for index in range(count):
        if not aligned[index]:
            out.append(literals[literal_at])
            literal_at += 1
            continue
        syllables = []
        for character in han_characters(hanji_values[index]):
            rank = ranks[rank_at]
            if rank == ESCAPE_RANK:
                syllable = escapes[escape_at]
                escape_at += 1
            else:
                syllable = model[character][rank]
            if caps[rank_at]:
                syllable = syllable[:1].upper() + syllable[1:]
            rank_at += 1
            syllables.append(syllable)
        out.append(render(syllables, separators[separator_at].split(UNIT)))
        separator_at += 1
    return out


def _encode_column(table, column, plan, rows, context, model):
    values = rows[column]
    nullable = any(value is None for value in values)
    sections = [codec.encode_mask([value is None for value in values])] if nullable else []
    present = [value for value in values if value is not None]
    kind = plan[0]
    if kind == tables.DERIVED:
        predicted = tables.RULES[plan[1]](context, rows, *plan[2])
        exceptions = [index for index, value in enumerate(values) if value is not None and value != predicted[index]]
        sections += [
            codec.encode_deltas(exceptions),
            codec.encode_texts([str(values[index]) for index in exceptions]),
        ]
        return sections, {"exceptions": len(exceptions)}
    if kind == tables.DELTA:
        sections.append(codec.encode_deltas(present))
    elif kind == tables.INT:
        sections.append(codec.encode_zigzag(present))
    elif kind == tables.TEXT:
        sections.append(codec.encode_texts(present))
    elif kind == tables.ENUM:
        table_values = sorted(set(present))
        lookup = {value: index for index, value in enumerate(table_values)}
        sections += [codec.encode_texts(table_values), codec.encode_varints(lookup[value] for value in present)]
    elif kind == tables.TAGSET:
        masks = [sum(1 << tables.TAGS.index(tag) for tag in value.split(",") if tag in tables.TAGS) for value in present]
        sections.append(codec.encode_varints(masks))
    elif kind == tables.TAILO:
        hanji = [rows[plan[1]][index] for index, value in enumerate(values) if value is not None]
        sections += _encode_tailo(hanji, present, model)
    else:
        raise ValueError(f"unknown plan {kind} for {table}.{column}")
    return sections, {}


def _decode_column(table, column, plan, sections, at, count, nullable, declared_type, decoded, context, model):
    nulls = codec.decode_mask(sections[at], count) if nullable else [False] * count
    at += 1 if nullable else 0
    present_count = count - sum(nulls)
    kind = plan[0]
    if kind == tables.DERIVED:
        literals = codec.decode_texts(sections[at + 1])
        exceptions = dict(zip(codec.decode_deltas(sections[at], len(literals)), literals))
        predicted = tables.RULES[plan[1]](context, decoded, *plan[2])
        cast = int if declared_type == "INTEGER" else str
        return [
            None if nulls[index] else (cast(exceptions[index]) if index in exceptions else predicted[index])
            for index in range(count)
        ], at + 2
    if kind == tables.DELTA:
        present = codec.decode_deltas(sections[at], present_count)
        at += 1
    elif kind == tables.INT:
        present = codec.decode_zigzag(sections[at], present_count)
        at += 1
    elif kind == tables.TEXT:
        present = codec.decode_texts(sections[at])
        at += 1
    elif kind == tables.ENUM:
        table_values = codec.decode_texts(sections[at])
        present = [table_values[index] for index in codec.decode_varints(sections[at + 1], present_count)]
        at += 2
    elif kind == tables.TAGSET:
        present = [
            ",".join(tag for bit, tag in enumerate(tables.TAGS) if mask & (1 << bit))
            for mask in codec.decode_varints(sections[at], present_count)
        ]
        at += 1
    elif kind == tables.TAILO:
        hanji = [value for value, is_null in zip(decoded[plan[1]], nulls) if not is_null]
        present = _decode_tailo(sections[at : at + 6], hanji, model, present_count)
        at += 6
    else:
        raise ValueError(f"unknown plan {kind} for {table}.{column}")
    iterator = iter(present)
    return [None if is_null else next(iterator) for is_null in nulls], at


def encode(db_path):
    """Read a kautian.db and return the compressed container bytes."""
    connection = sqlite3.connect(db_path)
    connection.text_factory = str
    schema, data = _read_tables(connection)
    connection.close()

    source_table, hanji_column, reading_column = tables.MODEL_SOURCE
    model = build_model(zip(data[source_table][hanji_column], data[source_table][reading_column]))

    manifest = {"version": 1, "header": _read_header(db_path), "tables": []}
    sections = []
    context = {}
    for entry in schema:
        name = entry["name"]
        rows = data[name]
        plan = tables.PLAN[name]
        columns = []
        for column, declared in entry["columns"]:
            column_sections, extra = _encode_column(name, column, plan[column], rows, context, model)
            nullable = any(value is None for value in rows[column])
            columns.append({"name": column, "type": declared, "nullable": nullable, **extra})
            sections += column_sections
        manifest["tables"].append(
            {"name": name, "sql": entry["sql"], "rows": rows["__rows__"], "columns": columns}
        )
        context[name] = rows
    body = codec.pack_sections([json.dumps(manifest, ensure_ascii=False).encode("utf-8")] + sections)
    return MAGIC + lzma.compress(body, preset=9 | lzma.PRESET_EXTREME)


def decode(blob):
    """Return (manifest, {table: {column: values}}) from container bytes."""
    if not blob.startswith(MAGIC):
        raise ValueError("not a KTOPT1 container")
    sections = codec.unpack_sections(lzma.decompress(blob[len(MAGIC) :]))
    manifest = json.loads(sections[0].decode("utf-8"))
    at = 1
    context = {}
    model = None
    for entry in manifest["tables"]:
        name = entry["name"]
        plan = tables.PLAN[name]
        count = entry["rows"]
        decoded = {}
        for column in entry["columns"]:
            decoded[column["name"]], at = _decode_column(
                name,
                column["name"],
                plan[column["name"]],
                sections,
                at,
                count,
                column["nullable"],
                column["type"],
                decoded,
                context,
                model,
            )
        context[name] = decoded
        if name == tables.MODEL_SOURCE[0]:
            model = build_model(zip(decoded[tables.MODEL_SOURCE[1]], decoded[tables.MODEL_SOURCE[2]]))
    return manifest, context


def rebuild(manifest, context, out_path):
    """Write a SQLite file from decoded columns, reproducing the original bytes.

    The original was built one table at a time, each in its own transaction.
    SQLite allocates b-tree pages in the order writes arrive, so the same
    sequence is what makes the page images line up; anything the engine does not
    recompute is patched back from the manifest afterwards.
    """
    connection = sqlite3.connect(out_path)
    connection.execute(f"pragma page_size={manifest['header']['pageSize']}")
    for entry in manifest["tables"]:
        connection.execute(entry["sql"])
        columns = [column["name"] for column in entry["columns"]]
        rows = list(zip(*[context[entry["name"]][column] for column in columns]))
        if rows:
            marks = ", ".join("?" * len(columns))
            connection.executemany(f'insert into "{entry["name"]}" values ({marks})', rows)
        connection.commit()
    connection.close()
    _patch_header(out_path, manifest["header"])


def _patch_header(path, header):
    with open(path, "r+b") as handle:
        for name, (at, size) in HEADER_FIELDS.items():
            handle.seek(at)
            handle.write(header[name].to_bytes(size, "big"))
