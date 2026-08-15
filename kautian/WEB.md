# `kautian.web.json` — the whole dictionary, decoded in a browser

A 1.45 MB brotli file that a React app fetches once and turns into plain
JavaScript objects with `kautian/web/kautian.mjs` — no WASM, no build step, no
dependency, and no SQLite.

|                                          |          shipped |                     to decode |
| ---------------------------------------- | ---------------: | ----------------------------- |
| row-object JSON (`KTJSON1`)              |     2,286,506 B  | nothing                       |
| columnar JSON, nothing modelled          |     1,786,097 B  | zip columns into rows         |
| \+ derived rules                          |     1,581,696 B  | \+ joins and templates         |
| \+ tailo ranks, model shipped             |     1,481,704 B  | \+ rank lookup                 |
| **`kautian.web.json` (`KTWEB1`)**        | **1,445,394 B**  | **\+ an enum table lookup**    |
| `kautian.ktz`                            |     1,325,703 B  | a full port, and LZMA in WASM |

All brotli `-q 11 --lgwin 24`, over the same 19 tables and 746,857 values.

Build it — the dataset can come from the .db, from a `KTJSON1` document, or from
the container, and the output is the same either way:

```bash
python3 kautian/build_web_json.py --db kautian/kautian.db --out kautian.web.json
brotli -q 11 --lgwin 24 kautian.web.json      # at deploy time; brotli is not stdlib
```

```js
import { decode } from "./kautian.mjs";

const doc = await (await fetch("/kautian.web.json")).json();   // served Content-Encoding: br
const { 詞目, 例句, 義項 } = decode(doc);
例句[0];  // { 詞目id: 1, 義項id: 1, 例句順序: 1, 漢字: "一蕊花", 羅馬字: "tsi̍t luí hue", … }
```

## Memory

Node 22, heap measured after a forced GC with only the named structure alive:

| what you hold | steady | peak while loading |
| --- | ---: | ---: |
| `decode(doc)` — every table as row objects | 29.0 MB | ~66 MB |
| `decodeColumns(doc)` — every table, columnar | 22.1 MB | ~66 MB |
| `decodeColumns(doc, {only: ["詞目","義項","例句"]})` | 16.3 MB | ~56 MB |
| the same three, decoded a table at a time | 16.3 MB | 32.4 MB |
| `decodeColumns(doc, {only: ["詞目"]})` | 5.4 MB | ~39 MB |

Three things move this number, in the order worth trying:

1. **Hold columns, not rows.** `decodeColumns` returns one array per column;
   `rows(columns, start, end)` shapes the page a view is rendering. Row objects
   for the whole dictionary cost 7 MB and almost nothing needs them.
2. **Ask for fewer tables.** `only` decodes what you name. 詞目, 義項 and 例句
   are most of the corpus; the other sixteen tables together are 6 MB.
3. **Never hold the whole document.** Peak is dominated by the parsed JSON, not
   by the result — the document is roughly as large as what it decodes to, and
   both are alive at once. Passing `context` lets each table be decoded from a
   document containing only itself, so peak tracks the largest single table.
   Split the file per table at build time and peak halves.

Two smaller things: fetch with `response.json()` rather than parsing a string
you already materialised — the browser parses from the network stream and skips
a ~14 MB copy — and release the document as soon as decoding returns, since
nothing in the result references it except the strings it keeps alive anyway.

Timing on the real document: 84 ms to decompress (the browser does this for you,
off the main thread), 68 ms to parse, 238 ms to decode all 153,191 rows.

## Why it stops where it does

The last 136 KB down to `kautian.ktz` cost more than they are worth.

LZMA is not in any browser — `DecompressionStream` does gzip and deflate only —
so the container needs a compressor in the bundle before any of its own decoding
starts. And its romanisation model is *derived* on both sides: rank each
character's readings by frequency, ties broken alphabetically. Encoder and
decoder must compute byte-identical orderings from the same table, in two
languages with different default sort rules. Disagree by one tie and the rank
column desynchronises from that point on — silently, into plausible-looking
wrong readings, not an exception. Shipping the model instead costs 23 KB
compressed and deletes the entire failure mode.

Everything cheaper than that is kept. The derived columns are the container's
own rules — the composed audio filenames, the example ordering, the denormalised
join columns — re-run in JavaScript as string templates and `Map` lookups, worth
204 KB for about forty lines. The romanisation ranks are worth another 100 KB
for about fifty more.

What remains is close to the floor: 例句, 義項 and 詞目 are about 1.27 MB of the
1.45 MB, and they are prose — definitions and example sentences. No modelling
removes those; only a context-mixing coder would, and no browser has one.

## Format

```
{ "format": "KTWEB1",
  "model":  { "一": ["tsi̍t", "it"], … },
  "tables": [ { "name", "columns", "rows", "values": { column: … } } ] }
```

`tables` is an array, not an object, because the order is load-bearing: a
derived column reads only columns earlier in its own table plus tables decoded
before it, which is what lets the decoder resolve everything in one forward
pass. It has to — a `tailo` column is decoded against a 漢字 column that is
itself derived.

A column takes one of four shapes:

| Shape | Meaning |
| --- | --- |
| `[…]` | the values, as they are |
| `{enum, at}` | `at` indexes `enum`, so repeated values are one shared string |
| `{rule, args, at, is}` | re-run `rule`, then overwrite rows `at` with `is` |
| `{tailo, aligned, ranks, escapes, caps, separators, literals}` | one rank per Han character into `model` |

A derived rule is never trusted blind: the encoder runs it against the real rows
and stores every row where it disagrees, so correctness does not depend on the
rule being right — only on the comparison having been done. In `aligned`, `2` is
NULL and `0` is a reading that has no one-syllable-per-character alignment and
rides in `literals`, so an absent reading is never confused with an empty one.

## This is a projection, not the archive

Every row and every value survives, but the `sqlite_master` statements and the
SQLite header fields do not, so `kautian.db` cannot be rebuilt from this
document. `kautian.ktz` remains the archival form — see `kautian/OPTIMIZED.md`.

It is also whole-dictionary by design, which is the opposite shape from
`kautian/v1/`, `kautian/rel/v1/`, `kautian/kind/v1/` and `concised/v3/`. Those
are range-fetchable: one headword's detail over HTTP, a few kilobytes, nothing
resident. Use them for lookup. Use this when the app wants the entire dictionary
in memory — offline use, or search across the whole corpus.

## Tests

```bash
python3 -m unittest kautian.tests.test_web_json
```

`test_web_json.py` runs `kautian/web/kautian.mjs` under node and compares its
output against the database, value by value, on both a synthetic database and
the real one. The port is the whole risk of this format, so a pure-Python check
would prove nothing; the tests skip if node is not installed.
