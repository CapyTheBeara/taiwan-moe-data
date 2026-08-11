# Detail container contract

`kautian/v1/` is what a browser reads to show everything the dictionary holds
about one headword, without a server and without SQLite. Built by
`kautian/build_detail.py` from `kautian/kautian.db`.

```
kautian/v1/detail.bin   concatenated JSON records, no separators
kautian/v1/detail.idx   uint16 little-endian record lengths, ids 0…maxId
kautian/v1/meta.json    provenance and the integrity constants
```

A record is addressed by position, not by a key inside it: `offset[id]` is the
prefix sum of `detail.idx`, and `length[id]` is the record's byte length. A
length of `0` means the headword has no detail, so the index doubles as the
has-detail check. One lookup is one HTTP `Range` request:

```
start = meta.headerBytes + offset[id]
Range: bytes=<start>-<start + length[id] - 1>
```

`detail.bin` opens with a 16-byte header, `KTDETAIL1` followed by seven NUL
bytes. The index does not count it — `meta.headerBytes` does, and every fetch
adds it. It exists because the records are valid UTF-8, and a host that sniffs
content rather than extension will classify a file of pure JSON as text and
gzip it, which silently reinterprets every byte offset against the compressed
stream. The NUL forces a binary classification. See Hosting.

**Never republish a version path.** The next MOE refresh builds `kautian/v2/`.
The container and index only correspond because neither is ever overwritten.

## Record shape

A compact JSON object per headword. It does not carry its own id — its position
is its identity.

```json
{"senses":[{"義項id":8,"詞性":"熟語","解說":"一刀斬成兩段，比喻斷絕關係。"}],
 "examples":[{"義項id":8,"例句順序":1,
              "漢字":"𪜶兩兄弟仔為著拚生理，就按呢一刀兩斷無來去。",
              "羅馬字":"In nn̄g hiann-tī-á uī-tio̍h piànn-sing-lí, tō án-ne it-to-lióng-tuān bô lâi-khì.",
              "華語":"他們兄弟倆為了拚生意，就這樣斷絕關係，不相往來。",
              "音檔檔名":"3-1-1"}],
 "category":"交際應酬"}
```

Every group is optional, and **an empty value is an absent key** — at both
levels. A group with no rows is not emitted, and a column that is `NULL` or `""`
is not emitted either. Read a missing key as empty, never as an error.

| key | source | columns kept |
|---|---|---|
| `senses` | 義項 | 義項id, 詞性, 解說 |
| `examples` | 例句 | 義項id, 例句順序, 漢字, 羅馬字, 華語, 音檔檔名 |
| `variants` | 異用字 | 漢字, 異用字 |
| `accents` | 語音差異 | 漢字 + the ten 腔 columns |
| `synonyms` | 詞目tuì詞目近義 | 對應詞目id, 對應詞目漢字 |
| `antonyms` | 詞目tuì詞目反義 | 對應詞目id, 對應詞目漢字 |
| `senseSynonyms` | 義項tuì義項近義 | 義項id, 對應義項id, **對應詞目id**, 對應詞目漢字 |
| `senseAntonyms` | 義項tuì義項反義 | 義項id, 對應義項id, **對應詞目id**, 對應詞目漢字 |
| `senseWordSynonyms` | 義項tuì詞目近義 | 義項id, 對應詞目id, 對應詞目漢字 |
| `senseWordAntonyms` | 義項tuì詞目反義 | 義項id, 對應詞目id, 對應詞目漢字 |
| `category` | 詞目.分類 | scalar |

Inner keys stay in the source language, matching how the database addresses
itself. Group keys are ASCII because they are the API surface.

`對應詞目id` on the two 義項tuì義項 groups is **not in the source** — those tables
give only `對應義項id`. The generator resolves it through the same 義項id → 詞目id
map it uses to regroup the rows, and emits both. Without it the two largest
relation tables (16,456 rows, 74% of all relations) would render as text you
cannot click.

Relations carry an id and a label, never the target's definition. The source's
`對應解說` is a second copy of a definition that already exists in its own
record; inlining it costs 2.60 MB against 1.02 MB.

## Liveness

A headword gets a record iff at least one of the ten table groups is non-empty.
`category` alone never promotes an otherwise-empty headword, and neither does
audio — see below. 18,031 of 29,591 headwords have a record.

## Audio is derived, not stored

Audio lives at `https://assets.taigiear.com/audio/<name>.mp3`.

- **Headword audio** is `<詞目id>.mp3`. The database's `詞目.羅馬字音檔檔名` is
  `<詞目id>(1)` for all 22,298 rows that have one, with no exceptions, and the
  upload strips the `(1)`. It is therefore not in the record — the id is enough.
- **Example audio** is the record's `音檔檔名`, verbatim, plus `.mp3`. It is
  **not** derivable from `義項id`: the middle number is the sense's ordinal
  within its headword, not the global `義項id`, and the two diverge from the
  second headword onward.

Only part of the audio is uploaded, and the set grows over time, so nothing
here says which clips exist. A client should attempt playback and degrade when
the request 404s. The host sends no CORS headers, so availability cannot be
probed with `fetch` — use an `<audio>` element, which loads cross-origin
without them.

## Alternate readings are not here

`又唸作`, `俗唸作` and `合音唸作` are already in `taigi-search`'s `entries.json`
as sibling rows sharing the headword's id, tagged in `reading_type`. `語音差異`
is a different thing — regional pronunciation across ten 腔 — and is in the
record as `accents`.

## meta.json

```json
{"buildDate": "…", "containerBytes": 9318191, "dbSha256": "…",
 "generatorCommit": "…", "headerBytes": 16, "liveIds": 18031, "maxId": 30284,
 "sentinel": {"id": 1, "head": "7b22…"}}
```

`containerBytes` is the exact length of `detail.bin`, header included.
`sentinel` is the first record in the container and the hex of its first 32
bytes.

A client must **self-check before trusting any offset**: fetch the sentinel's
range and require the hex of its first 32 bytes to equal `sentinel.head`. If a
host compresses or rewrites the container, every offset silently shifts and
records come back mis-sliced rather than failing. A `200` where a `206` was
expected means the host ignored the range and must be treated the same way.
Where `Content-Range` is readable, also require its total to equal
`containerBytes`; `raw.githubusercontent.com` sends no
`access-control-expose-headers`, so cross-origin JS cannot read it there.

Lengths are **UTF-8 byte** lengths. Slice bytes and decode with `TextDecoder`;
never slice a decoded string. The records are ASCII-delimited JSON full of
multi-byte CJK, and id 3's example contains `𪜶`, a surrogate pair in UTF-16 —
a character/byte confusion returns a shifted record, not an error.

## Hosting

`raw.githubusercontent.com` pinned to a commit SHA works for development: it
honours `Range` with a `206` even under `Accept-Encoding: gzip`, and sends
`access-control-allow-origin: *`. It is rate-limited and is not a CDN.

**It picks the content type by sniffing the bytes, not the extension.**
Measured against the live host: eleven different extensions on an ASCII payload
— `.bin`, `.dat`, `.idx`, `.db`, `.wasm`, `.mp3`, no extension at all — every
one came back `text/plain; charset=utf-8` with `content-encoding: gzip` and a
`content-range` total equal to the *compressed* length. The same bytes with a
NUL in the first 16 came back `application/octet-stream`, no
`content-encoding`, and a true total. That is the whole reason for the header.
`detail.idx` needs no such help; it is full of NUL bytes already.

Do not assume this of any host. Before trusting a new one, `GET` a range with
`Accept-Encoding: gzip` — curl omits it by default and browsers always send it
— and require a `206`, no `content-encoding`, and a `content-range` total equal
to `containerBytes`. A `HEAD` is not a substitute: GitHub ignores ranges on
HEAD.

For production, move to R2 with `Content-Type: application/octet-stream`,
`Cache-Control: public, max-age=31536000, immutable`,
`ExposeHeaders: ["Content-Range"]`, and zone-level Brotli and Auto Minify
confirmed not to apply to the path. Only the base URL changes.

## The siblings

Two more containers cover the headwords this one leaves empty. Both are written
by this directory's `detail/container.py` — same header width, index, sentinel
and `Range` addressing, over the same kautian id space — differing only in their
magic. Changing `container.py` changes all three.

`concised/v3/` (`CNDETAIL1`) holds 《國語辭典簡編本》 for the entry-less
headwords, Mandarin. See `concised/CONCISED_DETAIL.md` — and note its client
rule: **a record here that holds no `senses` is not a Taiwanese entry**, so a
client must fall through to concised rather than stopping at the hit. 109
headwords have a record here carrying only an 異用字 or a 語音差異.

`kautian/rel/v1/` (`KTREL001`) inverts this container's six relation tables, so
an entry-less headword can name the headwords that name it — the only content
the dictionary holds for a 近反義詞不單列詞目者. See `kautian/RELATIONS.md`.

## Rebuilding

```
python3 kautian/build_detail.py --db kautian/kautian.db --out kautian/v1/
python3 -m unittest discover -s kautian/tests
python3 -m unittest discover -s concised/tests
```

`detail.bin` and `detail.idx` are byte-identical across rebuilds of the same
database. `detail.bin` must never be tracked by Git LFS — `raw.githubusercontent.com`
serves an LFS pointer instead of the file.
