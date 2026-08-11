# Inbound-relation container contract

`kautian/rel/v1/` answers one question `kautian/v1/` cannot: **which headwords
name this one?** Built by `kautian/build_relations.py` from `kautian/kautian.db`.

```
kautian/rel/v1/detail.bin   concatenated JSON records, no separators
kautian/rel/v1/detail.idx   uint16 little-endian record lengths, ids 0…maxId
kautian/rel/v1/meta.json    provenance and the integrity constants
```

**The format is `kautian/v1/`'s, byte for byte** — same 16-byte header, same
prefix-sum index, same sentinel self-check, same `Range` addressing, same
kautian 詞目id index space. Read `kautian/DETAIL.md` for all of it; only the
magic differs (`KTREL001`). Both writers are `kautian/detail/container.py`.

**Never republish a version path.** The next MOE refresh builds `kautian/rel/v2/`.

## Why it exists

`kautian/v1/` stores every relation on the headword that *declares* it: 好 says
it is similar to 讚, and nothing on 讚 says so. That is the right shape for a
record you reach by id — until the id you hold is one the dictionary never gave
an entry to.

3,018 headwords carry 詞目類型 `近反義詞不單列詞目者`, "listed only as a near or
opposite meaning, not as a headword of its own". They have no 義項, no 例句 and
no outbound relations, so `kautian/v1/` has no record for them and
`concised/v3/` does not cover their type. A client showing one had a name, a
reading, and a sentence saying the dictionary declines to define it. The word it
*is* a synonym of — the one useful fact the dictionary holds — was reachable
only by scanning all 22,070 relation rows.

This container is that scan, inverted and indexed.

## What gets a record

Every **entry-less** headword that at least one other headword names. The three
entry-less 詞目類型 are the same ones `concised/` uses, and for the same reason:
a headword with 義項 of its own already answers for itself, so a record here
would be bytes nothing reads.

| 詞目類型 | headwords | named by another | what a record adds |
|---|---|---|---|
| `近反義詞不單列詞目者` | 3,018 | 3,010 | the only content the dictionary holds for it |
| `臺華共同詞` | 5,548 | 595 | a Taigi cross-reference beside the Mandarin definition |
| `單字不成詞者` | 3,104 | 14 | a Taigi cross-reference beside the Mandarin hint |

3,619 records, 228,884 B. The 8 `近反義詞不單列詞目者` with no record at all are
genuine dead ends — nothing in the dictionary points at them.

This container and `concised/v3/` **do** overlap, by design: 63 臺華共同詞 and 2
單字不成詞者 have both a Mandarin definition and a Taigi word naming them, and
both are worth showing. They are separate lookups answering separate questions,
not a fallback chain.

## Record shape

```json
{"synonymOf":[{"詞目id":3042,"漢字":"囥歲"}],
 "antonymOf":[{"詞目id":4858,"漢字":"帝"}]}
```

| key | meaning |
|---|---|
| `synonymOf` | headwords that list this one as a near meaning (近義) |
| `antonymOf` | headwords that list this one as an opposite meaning (反義) |

Both groups are optional and **an empty group is an absent key** — read a
missing key as empty, never as an error. `synonymOf` comes first where both are
present. Names are ordered by `詞目id`, and a headword naming the same target
through several 義項 appears once.

As in `kautian/v1/`, group keys are ASCII because they are the API surface,
inner keys are the database's own column names, and a name carries an id and a
label, never the naming headword's definition — that definition already exists
in its own record, one lookup away, and the id is what makes the label
clickable.

`漢字` is the source row's own `詞目漢字`, passed through as the dictionary
writes it. The `【替】` substitute marker is **not** stripped here, unlike the
`concised/` join key: there it is a join key that has to match 字詞名, here it is
a label the client displays and the marker is part of what the dictionary says.

## The six tables it inverts

| table | near end | far end |
|---|---|---|
| `詞目tuì詞目近義` / `詞目tuì詞目反義` | 詞目id | 對應詞目id |
| `義項tuì詞目近義` / `義項tuì詞目反義` | 義項id | 對應詞目id |
| `義項tuì義項近義` / `義項tuì義項反義` | 義項id | 對應義項id |

Every 義項id is resolved to its 詞目id through the 義項 table — the same
resolution `kautian/detail/records.py` does for `對應詞目id`. An edge whose
義項id has no owning headword is skipped rather than guessed at, and a headword
that names itself yields nothing: the dictionary has a handful of both and
neither says anything to a reader.

Sense granularity is dropped on purpose. "好 lists you as a synonym" is the
claim a client can render and link; "好's 義項 3 lists you" would need 好's
record fetched to say anything more, which is the lookup the client makes anyway
when the reader taps through.

## meta.json

`dbSha256` pins the one input. Everything else — `containerBytes`,
`headerBytes`, `liveIds`, `maxId`, `sentinel` — means what it means in
`kautian/DETAIL.md`, and the same self-check is mandatory before trusting any
offset.

## Rebuilding

```
python3 kautian/build_relations.py --db kautian/kautian.db --out kautian/rel/v1/
python3 -m unittest discover -s kautian/tests
python3 -m unittest discover -s concised/tests
```

`detail.bin` and `detail.idx` are byte-identical across rebuilds of the same
database. Run the concised suite too: all three containers are written by the
same module. `detail.bin` must never be tracked by Git LFS —
`raw.githubusercontent.com` serves an LFS pointer instead of the file.
