# `kautian.ktz` — the optimised kautian.db container

A lossless re-encoding of `kautian/kautian.db`. Not a projection and not a
subset: every table, column, row, NULL and storage class survives, and the
decoder rebuilds a SQLite file that is **byte-identical** to the original —
same 2,506 pages, same SHA-256.

|                          |                |
| ------------------------ | -------------: |
| `kautian.db`             |  10,264,576 B  |
| `gzip -9` of the .db     |   4,463,822 B  |
| `brotli -11` of the .db  |   3,021,071 B  |
| **`kautian.ktz`**        | **1,325,703 B** |

7.74× the database, 2.28× better than compressing the database directly.

Build and verify:

```bash
python3 kautian/build_optimized.py --db kautian/kautian.db --verify
python3 kautian/build_optimized.py --db kautian/kautian.db --out kautian/opt/v1/kautian.ktz
```

`--verify` decodes, rebuilds, and compares SHA-256 against the input. It is the
whole contract as an executable check; run it after any change to this format.

## Why it compresses

General-purpose compressors work on bytes and cannot see that a column restates
something the reader already has. Almost all of the win here is removing those
restatements before compression, not the codec:

- **Denormalised joins.** A relation row carries a copy of both headwords' 漢字
  and both senses' 解說. `義項tuì義項近義` alone stores 13,444 copies of sense
  text that `義項` already holds — verified derivable for 13,444 of 13,444 rows.
- **Composed identifiers.** `例句.音檔檔名` is
  `{詞目id}-{sense position}-{例句順序}` for 17,907 of 17,907 rows;
  `詞目.羅馬字音檔檔名` is `{詞目id}(1)` for 22,298 of 22,298 non-null rows.
  `例句.例句順序` is the row's position in its own group.
- **Romanisation.** Tâi-lô is one syllable per Han character and most characters
  have one attested reading, so a syllable is encoded as its rank in that
  character's reading list — a zero byte in the common case. The ranking model
  is derived from `詞目`, which the decoder has already read, so it costs
  nothing on the wire.
- **Columnar layout.** Values of one kind sit together, so the entropy coder
  sees a homogeneous stream instead of interleaved row records.

## Derived columns are verified, never assumed

A derivation rule that is right 96% of the time is not a compression scheme, it
is data loss. The encoder therefore runs every rule against the real rows,
compares, and stores an exception list for the rows where the rule is wrong.
Losslessness does not depend on any rule being correct — only on the comparison
being done. The rules hold for 96–100% of rows and the remainder ride in the
exception column at full cost.

Rules and their measured hit rate:

| Rule | Columns | Holds |
| --- | --- | --- |
| `headword_audio` | `詞目.羅馬字音檔檔名` | 22,298 / 22,298 |
| `example_audio` | `例句.音檔檔名` | 17,907 / 17,907 |
| `example_order` | `例句.例句順序` | 17,907 / 17,907 |
| `sense_gloss` | `解說`, `對應解說` on the four `義項tuì*` tables | 13,444 / 13,444 |
| `sense_headword_hanji` | `詞目漢字`, `對應詞目漢字` on `義項tuì*` | 12,959 / 13,444 |
| `headword_hanji` | `漢字` on `又唸作`, `合音唸作`, `俗唸作`, `語音差異`, `異用字`; the id-paired 漢字 on `詞目tuì*` | 96–100% |

## Format

```
"KTOPT1\n" || lzma(pack_sections([manifest] + column sections))
```

`pack_sections` is a varint count, then a varint length per section, then the
bodies — so decoding is one forward pass with no offsets to trust. The manifest
is JSON and fixes everything else: the `sqlite_master` statements in creation
order, each table's row count, each column's declared type, whether it is
nullable, and the SQLite header fields the engine does not recompute.

LZMA rather than brotli because this repository is stdlib-only, and on this
payload LZMA also wins outright: 1,325,532 B against brotli -11's 1,350,704 B.
The columnar layout is what both are exploiting; the codec choice is worth ~2%.

Column plans (`kautian/opt/tables.py`) and their section layout:

| Plan | Sections after the optional null mask |
| --- | --- |
| `int` | zigzag varints |
| `delta` | delta-encoded zigzag varints |
| `text` | count-prefixed newline-joined UTF-8 |
| `enum` | value table, then indices |
| `tagset` | one bitmask varint over the nine `來源` tags |
| `tailo` | aligned mask, rank bytes, escapes, capitalisation mask, separators, unalignable literals |
| `derived` | exception row indices, exception values |

A nullable column is preceded by a null mask; the payload covers non-null rows
only. Text sections carry their own count because an empty payload is otherwise
ambiguous between no strings and one empty string — and columns hold both.

### Byte-identity is a property of the write sequence

SQLite allocates b-tree pages in the order writes arrive. The original database
was built one table at a time, each in its own transaction, so `rebuild()`
replays exactly that: `create table`, insert its rows, commit, next table.
Building all tables first and then filling them produces the same *page
contents* but a different page *order*, and the file no longer matches. After
the rebuild, the header fields SQLite does not recompute — the file change
counter, schema cookie, version-valid-for — are patched back from the manifest.

This is the fragile part of the format. It is pinned by
`TestRealDatabase.test_kautian_db_rebuilds_byte_for_byte`; if a future SQLite
changes its allocation behaviour, that test is where it will surface.

### The romanisation model must not be self-referential

`詞目.羅馬字` is stored as plain text, not rank-coded, because it is the source
the model is built from. Every other romanised column is coded against the model
derived from `詞目` after that table has been fully decoded. A column may only
be modelled against a table decoded before it.

Likewise, every derived rule reads only columns earlier in its own table's
column order, plus tables decoded earlier — which is what lets the decoder
resolve derived columns during its single forward pass. It has to: a `tailo`
column is decoded against a 漢字 column that is itself derived.

## Size by table

| Table | Rows | Sections (raw) | LZMA'd alone |
| --- | ---: | ---: | ---: |
| `例句` | 17,907 | 1,838,416 | 517,620 |
| `義項` | 23,298 | 1,172,278 | 386,200 |
| `詞目` | 29,591 | 797,964 | 257,128 |
| `漢字羅馬字對應` | 20,087 | 243,995 | 47,424 |
| `名` | 16,924 | 223,871 | 40,820 |
| `詞彙比較` | 12,271 | 320,718 | 35,884 |
| `義項tuì義項近義` | 13,444 | 75,189 | 34,168 |
| `異用字` | 3,126 | 28,684 | 14,148 |
| `義項tuì詞目近義` | 3,441 | 19,866 | 8,588 |
| `義項tuì義項反義` | 3,012 | 16,246 | 7,904 |
| `姓` | 2,473 | 27,645 | 7,564 |
| `羅馬字清單` | 3,155 | 21,777 | 7,116 |
| `又唸作` | 1,779 | 22,665 | 7,044 |
| `語音差異` | 407 | 23,683 | 4,628 |
| `詞目tuì詞目近義` | 1,399 | 7,657 | 4,532 |
| `義項tuì詞目反義` | 715 | 4,013 | 2,540 |
| `俗唸作` | 55 | 739 | 412 |
| `詞目tuì詞目反義` | 59 | 334 | 376 |
| `合音唸作` | 48 | 581 | 356 |

Per-table figures are each table's sections compressed on their own; they sum to
more than the container because the whole body shares one LZMA dictionary.

The remainder is prose — 義項 definitions, 例句 sentences and their 華語
translations — and is close to irreducible without a context-mixing coder no
practical decoder would want.

## Relationship to the other containers

Unrelated. `kautian/v1/`, `concised/v3/`, `kautian/rel/v1/` and `kautian/kind/v1/`
are range-fetchable projections built *for browsers*: one record at a time, over
HTTP, without SQLite. This is the opposite shape — the whole database, offline,
as a file you unpack back into `kautian.db`. Nothing here reads those containers
and nothing there reads this.

## Tests

```bash
python3 -m unittest discover -s kautian/tests
```

`test_optimized.py` covers the codec primitives, the Tâi-lô tokenizer's
round-trip on every orthography in the corpus, synthetic-database byte-identity,
and — when `kautian.db` is present — the real database and encoder determinism.
The rule-violation tests are the important ones: they assert that a row which
*breaks* a derived rule still survives the round trip.
