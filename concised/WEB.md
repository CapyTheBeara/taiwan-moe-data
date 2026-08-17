# concised.web.json — the Concised set as one document

`concised/v3/` answers one 詞目id at a time over HTTP range requests.
`concised.web.json` is the same data in the other shape: one JSON file small
enough to ship whole, so a client that wants the entire Mandarin fallback set
resident — offline, or to search across every definition at once — fetches it
once instead of issuing thousands of range requests.

    python3 concised/build_web_json.py \
        --kautian-db kautian/kautian.db \
        --concised-db concised/concised.db \
        --out concised/web/concised.web.json

Measured on the shipped databases:

| | |
|---|---:|
| headwords | 7,516 |
| entries (polyphones contribute several) | 7,983 |
| raw JSON | 1,679,387 B |
| `brotli -q 11 --lgwin 24` | **483,043 B (471.7 KB)** |

Serve it with `Content-Encoding: br`; the browser decompresses natively and
`response.json()` resolves to the document. Precompress at deploy time — edge
compression runs at a much lower quality level and gives up 10–20% of that.

## It uses kautian's decoder, unmodified

`kautian/web/kautian.mjs` reads this document as-is. That reuse is deliberate,
and it is what constrains the format: Concised carries no romanisation and no
cross-table joins, so none of the decoder's interesting machinery applies.

- no `tailo` columns — there is no Tâi-lô here, only 注音一式 and 漢語拼音;
- no derived columns — nothing to join against;
- therefore no reading model, and `model` rides as `{}`, since only
  `decodeTailo` ever reads it.

What is left is the two column shapes every KTWEB1 document already has: a plain
JSON array, and `{enum, at}`. The decoder fills in 詞目 and 義項 for its derived
rules, and neither table is in this document — that path is covered by a test
rather than by assumption, because it is the one that would break first if the
decoder changed.

```js
const doc = await (await fetch("/concised.web.json")).json();
const { 簡編 } = decode(doc);
簡編[0].釋義;
```

## One table, one row per entry

`簡編`, ordered by 詞目id, then by the order `records.build` emitted the
readings — which is `多音排序` numerically, then `字詞號`.

| column | |
|---|---|
| `詞目id` | the kautian id, integer; the join key, and shared with `concised/v3` |
| `字詞名` | headword |
| `字詞號` | source entry id — **a string, with its leading zeros** |
| `注音一式`, `漢語拼音` | readings |
| `變體類型`, `變體注音`, `變體漢語拼音` | variant reading, when there is one |
| `相似詞`, `相反詞` | |
| `釋義` | the definition, and the bulk of the bytes |
| `多音參見訊息` | cross-reference to another reading of the same headword |

A polyphone contributes one row per reading, so `詞目id` is not unique.

## Absent columns

The container's records omit a blank column entirely. A columnar table has no
way to say "absent" per row, so a dropped column reads back as `null`. Dropping
the null keys off a decoded row returns the container's record exactly, and that
round trip is asserted against the real databases in
`concised/tests/test_web_json.py`.

## Population

Not this document's decision. `concised.detail.source.read` and
`concised.detail.records.build` choose which headwords earn a record and which
columns survive on each, and `concised/web/webjson.py` flattens whatever they
return — the same two functions `build_concised_detail.py` calls.

So the document and the container cannot disagree about their contents without
`records.build` disagreeing with itself. That is why there is no second copy of
the population rule here, and why the parity test asserts the round trip to
`records.build` rather than comparing against a checked-in expectation.

The rule itself is documented in `CONCISED_DETAIL.md`: the 臺華共同詞 and
單字不成詞者 headwords, minus the ones whose kautian record already carries 義項.

## This is a projection

Only the headwords 教典 leaves without 義項 are here, and only the columns that
carry content on them — `concised.db` holds ~45,130 entries and fifteen columns.
The .db remains the archival form; this cannot rebuild it.
