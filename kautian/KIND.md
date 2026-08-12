# Detail-kind lookup contract

`kautian/kind/v1/` answers a question taigi-ear used to answer by booting two
containers: **which icon does the word-details modal show for this id, before
either container has loaded?** Built by `kautian/build_kind.py` from
`kautian/kautian.db`, `concised/v3/detail.idx`, and `kautian/rel/v1/detail.idx`.

```
kautian/kind/v1/detail-kind.bin   maxId + 1 bytes, one per id, no header
kautian/kind/v1/meta.json         provenance and the tally
```

`detail-kind.bin` is **not** the `kautian/v1/` container format — there is
nothing to range-fetch here, so there is nothing to index. Byte `id` is `id`'s
kind, read straight off: `kinds[bin[id]]`.

| byte | kind | meaning |
| --- | --- | --- |
| `0` | `full` | the id has its own entry — kautian and/or concised speak for it directly |
| `1` | `bound` | 單字不成詞者, covered only by concised's Mandarin hint |
| `2` | `named` | entry-less, silent in concised, but named by another headword in `kautian/rel/v1/` |
| `3` | `none` | entry-less and silent everywhere — a genuine dead end |

**Default fill is `0` (`full`).** An id with no `詞目` row at all — including
every gap in kautian's id space above `詞目` row count — resolves to `full`,
matching a client that never saw a type for it and falls through to its
richest rendering. This is load-bearing: getting the default wrong would make
every never-seen id look bound, named, or dead instead of ordinary.

## What it mirrors

This is a precomputed cache of `resolveKind` in taigi-ear's
`src/features/compose/useWordDetailKind.ts`, not a new classification. The
logic, matched exactly:

```
for each id in 0..maxId:
    label = 詞目類型 for id, or None
    if label not in {單字不成詞者, 近反義詞不單列詞目者, 臺華共同詞}:
        kind = full
    elif id is live in concised/v3/ (detail.idx length > 0):
        kind = bound if label == 單字不成詞者 else full
    elif id is live in kautian/rel/v1/ (detail.idx length > 0):
        kind = named
    else:
        kind = none
```

The three labels are the same entry-less types `concised/v3/` and
`kautian/rel/v1/` already use (see `kautian/DETAIL.md` and
`kautian/RELATIONS.md`) — a headword that owns its own 義項 is always `full`,
regardless of whether it also happens to be named by another headword or
described in concised.

"Live in X" reuses `kautian/detail/container.py`'s `read_lengths`, the same
function that writes and would read back any `detail.idx` — this container
does not reimplement uint16 index parsing.

## meta.json

```json
{
  "buildDate": "2026-08-11",
  "kautianDbSha256": "…",
  "concisedIdxSha256": "…",
  "relationsIdxSha256": "…",
  "generatorCommit": "…",
  "maxId": 30284,
  "kinds": ["full", "bound", "named", "none"],
  "tally": {"full": 23218, "bound": 2913, "named": 3078, "none": 1076}
}
```

Three digests, not one: `kautianDbSha256` pins the type table, and
`concisedIdxSha256` / `relationsIdxSha256` pin the two sibling containers this
table was computed against. A client that pins its own copies of
`concised/v3/` and `kautian/rel/v1/` can compare hashes to detect a
`detail-kind.bin` built against a different pair before trusting it — the
lookup table is only a cache of what those two containers say, and it goes
stale exactly when either of them is rebuilt.

## Rebuilding

```
python3 kautian/build_kind.py \
    --db kautian/kautian.db \
    --concised-idx concised/v3/detail.idx \
    --relations-idx kautian/rel/v1/detail.idx \
    --out kautian/kind/v1/
python3 -m unittest discover -s kautian/tests
```

`detail-kind.bin` is byte-identical across rebuilds of the same three inputs.

**Never republish a version path.** The next time `concised/v3/` or
`kautian/rel/v1/` moves to a new version, this container builds
`kautian/kind/v2/` alongside it.
