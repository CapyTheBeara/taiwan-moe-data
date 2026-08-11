# Concised detail container contract

`concised/v3/` is the Mandarin counterpart to `kautian/v1/`: what a browser
reads to show what 《國語辭典簡編本》 holds about one headword, without a server
and without SQLite. Built by `concised/build_concised_detail.py` from
`concised/concised.db` and `kautian/kautian.db`.

```
concised/v3/detail.bin   concatenated JSON records, no separators
concised/v3/detail.idx   uint16 little-endian record lengths, ids 0…maxId
concised/v3/meta.json    provenance and the integrity constants
```

`v2` added the 單字不成詞者 characters to `v1`'s 臺華共同詞 words. `v3` adds the
101 of those characters that `v2` withheld because `kautian/v1` holds a
senseless record for them — see "What gets a record". Every `v2` record is
byte-identical in `v3`, and every `v1` record in `v2`. Both stay published —
version paths are immutable — but nothing should point at them.

**The format is `kautian/v1/`'s, byte for byte** — same 16-byte header, same
prefix-sum index, same sentinel self-check, same `Range` addressing. Read
`kautian/DETAIL.md` for all of it; only the magic differs (`CNDETAIL1` rather
than `KTDETAIL1`), and both writers are the same `kautian/detail/container.py`.

**Never republish a version path.** The next MOE refresh builds `concised/v4/`.

## It is indexed by kautian 詞目id

This is the whole trick. The index space is kautian's — `0…30284`, `maxId`
taken across every 詞目 row, not just the ones with a record — so a client
addresses this container with the id it already has, and `lengths[id] === 0`
answers "no Mandarin entry for this headword" with no request. One client
implementation serves both containers; only the base URL changes.

## What gets a record

Two of the five `詞目類型` values, both of them kinds the dictionary leaves with
no 義項 of its own — precisely the headwords whose detail modal would otherwise
be empty:

| 詞目類型 | headwords | matched | what it is |
|---|---|---|---|
| `臺華共同詞` | 5,548 | 4,603 | a word that means what its Mandarin counterpart means |
| `單字不成詞者` | 3,104 | 2,913 | a character that does not stand alone as a word |

The two are **not** the same claim, and the difference matters to the client.
For 臺華共同詞 the dictionary itself asserts the Mandarin equivalence, so the
Concised entry is that word's definition. For 單字不成詞者 it asserts only that
the character is bound; the Concised entry is what the *same character* means in
Mandarin, which is a strong hint and not a translation. A client that renders
both must say which one it is showing. `詞目類型` is not carried in the record —
the app already has it, keyed by id, and duplicating it here would be a second
copy to keep true.

Headwords are matched to the Concised dictionary on 漢字 = 字詞名, after stripping
the `【替】` substitute marker so the join key is the hanji the app displays. The
1,136 misses are genuine absences — 簡編本 is MOE's reduced dictionary for
learners, so 山泉水, 水桶 and 小產 are simply not in it, and neither are the
characters Taigi writes phonetically (囡, 迌, 肨, 虼). They get no record, exactly
as an unmatched id does.

**No id whose `kautian/v1` record carries 義項 is live here**, and that is derived
rather than assumed: `_covered_by_kautian` runs kautian's own record builder and
drops every id whose record holds senses. Ids whose record holds *no* senses stay
eligible, and that distinction is the difference between `v2` and `v3`.

109 entry-less headwords carry an 異用字 or a 語音差異 and nothing else, which is
enough to earn a `kautian/v1` record with no `senses` in it. `v2` dropped all 109
to keep "no id is live in both containers" literally true. That cost more than it
bought: 101 of them match 簡編本, and a client that stops at the kautian hit shows
a hero card with nothing under it — 呵 `o` and 預 `ī` among them. `v3` gives those
101 their Mandarin record.

**So the client rule is not "try kautian, else concised" — it is "try kautian; a
record with no `senses` is not a Taiwanese entry, so fall through to concised".**
A client that returns on any kautian hit will still show those 101 as blank.
The 8 that match nothing in 簡編本 have only their 異用字 or 語音差異 to show,
which is what the kautian record already holds.

## Record shape

A compact JSON object per headword, carrying one group key. The array holds
more than one row only for a 多音 character — a name with several readings,
ordered by 多音排序 then 字詞號.

```json
{"concised":[{"字詞名":"入場券","字詞號":"5238000271",
  "注音一式":"ㄖㄨˋ　ㄔㄤˇ　ㄑㄩㄢˋ","漢語拼音":"rù chǎng quàn",
  "釋義":"1.進入某場所時，持有許可進入的票券。[例]今晚職棒賽的入場券，一票難求。\n2.…"}]}
```

| key | column |
|---|---|
| `字詞名` | the Mandarin headword |
| `字詞號` | the Concised dictionary's own entry number |
| `注音一式` / `漢語拼音` | the reading, Bopomofo and Pinyin |
| `變體類型` / `變體注音` / `變體漢語拼音` | the variant reading, where there is one |
| `釋義` | the definition |
| `相似詞` / `相反詞` | related words, `[似]` / `[反]` prefixed |
| `多音參見訊息` | cross-reference to this character's other reading |

As in `kautian/v1/`, group keys are ASCII because they are the API surface,
inner keys are the database's own column names, and **an empty value is an
absent key** — read a missing key as empty, never as an error. The xlsx export
pads unused cells with spaces, so `變體類型: "  "` is absent, not `"  "`.

Columns the dictionary carries for character lookup rather than reading —
`部首字`, `總筆畫數`, `部首外筆畫數` — are dropped. `多音排序` orders the array
and is not emitted.

## 釋義 is a text blob, and stays one

The definition is unstructured text and is passed through verbatim apart from
trimming the export's ragged leading and trailing whitespace. Senses are
numbered `1.`, `2.` and separated by `\n` or `\r\n`; examples follow a `[例]`
marker inside the sense; `△` introduces an alternative name, `§` a foreign
etymology, and a bare `◎` appears with nothing after it. Interior whitespace is
left exactly as the source has it, ideographic spaces and nbsp included.

Parsing that belongs in the client, not here. A parser bug in the generator
would mean rebuilding and re-pinning an immutable version path; in the client
it ships with the next deploy.

## meta.json

Two digests rather than one, because the container has two inputs: the content
comes from `concisedDbSha256`, the id space from `kautianDbSha256`. Both must be
pinned for a rebuild to be reproducible. Everything else — `containerBytes`,
`headerBytes`, `liveIds`, `maxId`, `sentinel` — means what it means in
`kautian/DETAIL.md`, and the same self-check is mandatory before trusting any
offset.

## Rebuilding

```
python3 concised/build_concised_detail.py --kautian-db kautian/kautian.db \
    --concised-db concised/concised.db --out concised/v3/
python3 -m unittest discover -s concised/tests
python3 -m unittest discover -s kautian/tests
```

`detail.bin` and `detail.idx` are byte-identical across rebuilds of the same two
databases. Run the kautian suite too: all three containers are written by the
same module. `detail.bin` must never be tracked by Git LFS — `raw.githubusercontent.com`
serves an LFS pointer instead of the file.
