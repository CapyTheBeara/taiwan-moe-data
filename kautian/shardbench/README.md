# shardbench — sizing app data delivery formats

A measurement harness, not a shipping format. Every figure is brotli
quality 11, which is what a CDN serves.

```bash
pip install brotli
python3 kautian/shardbench/bench.py             # per-column technique comparison
python3 kautian/shardbench/build_ab.py         # three-shard split: corpus A and B
python3 kautian/shardbench/build_c.py tailo 1  # shard C: <order> <cjk-char-model>
python3 kautian/shardbench/build_tiers.py      # re-encode today's tiers in place
python3 kautian/shardbench/build_unified.py    # price shipping the whole dictionary
```

Needs `kautian.db` and `concised.db` (both in this repo) and a checkout of
`taigi-ear` for `public/data/`. `TAIGI_EAR_DATA`, `KAUTIAN_DB` and
`CONCISED_DB` override the paths.

## Three candidate shapes

**1. Three shards** — corpus Tâi-lô+Mandarin / corpus English / everything
else, alphabetical by Tâi-lô:

| Shard | br11 |
| --- | ---: |
| A — corpus Tâi-lô + Mandarin | 226,016 |
| B — corpus English | 150,792 |
| C — rest of the dictionary, Tâi-lô order | 1,401,130 |
| C — same, stored in 詞目id order | 1,305,010 |
| **Total (Tâi-lô order)** | **1,777,938** |

**2. Re-encode today's tiers in place** — keeps the resident / deferred /
gated boundaries, so Mandarin stays gated and nothing moves onto the
critical path:

| File | today | re-encoded | |
| --- | ---: | ---: | ---: |
| `lexicon.json` (lazy, `/compose`) | 394,565 | **165,277** | 0.42× |
| `words-index.json` (resident) | 73,841 | **48,722** | 0.66× |
| `detail.json` (deferred) | 387,788 | **258,741** | 0.67× |
| `mandarin.json` (gated) | 169,534 | **111,604** | 0.66× |

**3. Ship the whole dictionary:**

| | br11 |
| --- | ---: |
| curated app index (2,577 words) | 48,722 |
| `detail.json` — the app's own English | 258,741 |
| unified headword index (28,672 headwords, 34,004 readings, incl. 詞目類型) | 166,139 |
| all senses (23,298 義項 + 7,795 concised, 25,717 headwords) | 770,882 |
| relations | 47,484 |
| **total** | **1,291,968** |
| MoE example sentences, if included | +474,817 |

Against 1,035,784 br today for `words-index` + `detail` + `mandarin` +
`entry-types` + `detail-kind` + `lexicon`, which covers 2,577 words rather
than all 29,591. So the complete dictionary is **+25%**, and +71% with the
MoE example sentences.

**What that does not include: English for the other ~26,000 headwords.**
That content does not exist in any source — the app's English is its own
authored work, and it covers the curated corpus only. No encoding changes
that.

## What actually paid, and what didn't

Measured, not assumed. Ratios are against a plain length-prefixed text
section for the same column, after brotli-11.

**Paid:**

- **Deriving 羅馬字 from 漢字** — 0.38× on the corpus tailo columns
  (59,143 → 22,683 including the model header). One 漢字 character maps to
  one Tâi-lô syllable once punctuation is stripped: 99.93% of corpus
  examples align. Store the *rank* of the actual reading in that
  character's frequency-ordered reading list; rank 0 covers 91.7% of
  syllables, so the column is mostly zero bytes. Round-trips exactly on all
  8,068 corpus rows. Word-boundary separators are not derivable and stay a
  column of their own.
- **Killing the audio filename columns.** `詞目.羅馬字音檔檔名` is
  `"<詞目id>(<n>)"` and `例句.音檔檔名` is
  `"<詞目id>-<義項 ordinal>-<例句順序>"`, both without exception. 101,500 br
  → 2,339 br.
- **Dropping `searchKey` from the Compose lexicon** — a pure function of
  `tailo`, verified 34,004/34,004 against `scripts/lexicon/normalize.py`,
  and the same function already exists client-side as `storedSearchKey` /
  `bare` in `src/features/compose/core/normalize.ts`.
- **Storing reconstructible orders ascending.** The lexicon ships in
  `searchKey` order; stored in ascending 詞目id and re-sorted at load, its
  id column goes 61,431 br → 4,043 br.
- **Delta + zigzag varint on ascending id columns** — 0.61×.
- **Splitting `分類` on its commas** before dictionary coding — 1,862
  distinct strings become 199 distinct tags, 30,250 → 24,865.
- **A shared CJK character dictionary** across 解說 / 華語 / 漢字 — 0.92×.
  The smallest real win, and the one most easily dropped if decoder
  simplicity matters more.
- **Dropping the join columns on the relation tables.** Every relation row
  carries 詞目漢字 and 對應詞目漢字 alongside the ids; both are joins.

**Did not pay — measured, then discarded:**

- **A Tâi-lô syllable dictionary** (the technique `kautian/opt/` is built
  around) is *worse* than plain text at app-corpus scale: 60,001 vs
  59,043 br. Brotli already finds the repeated syllables, and the header
  never amortises over 8k rows. Deriving from 漢字 beats both by a wide
  margin. The technique is good on the 100k-row database and bad here.
- **A word-level token dictionary for English prose** — 1.16×. Brotli's LZ
  pass already does this, better.
- **Front-coding a sorted Tâi-lô column** — a genuine 0.71× on its own, but
  irrelevant once the column is derived from 漢字 instead (0.12×).

## The Tâi-lô storage order has a price

Storing shard C alphabetically by Tâi-lô rather than by 詞目id costs
**96,120 br (+7.4%)**: 詞目id and 義項id stop being ascending so their delta
columns swell (49,035 and 28,974 br), and semantically related headwords —
adjacent in id order — scatter, costing the prose columns their locality.

Tâi-lô *order* does not require Tâi-lô *storage order*. The sort key is a
pure function of a field already in the shard, so a client can sort at load
for nothing. The 96 KB buys one thing only: range-addressable sub-shards
(`a–f`, `g–m`, …) fetched independently.

## Unmeasured, and it decides the deferred tier

Decode time. An earlier prototype measured +38 ms on desktop for its own
`detail.json` design and concluded the deferred tier was not worth it. That
number does not transfer — this is a different encoder, doing more work per
record (a table lookup per syllable) but less parsing. Do not ship the
deferred tier off size figures alone; measure on a mid-range phone first.
The lexicon is exempt: already lazy, off the nav, and `JSON.parse` of
1.7 MB is not free either.

## On the earlier 1.33 MB `.ktz` claim

`.ktz` genuinely cannot be reused here — it rebuilds a SQLite file, needs a
WASM SQLite to query, and cannot be sharded, because its compression comes
from a strict cross-table dependency order. But the *inference* drawn from
it survives independently: "ship everything costs roughly 25% more than the
status quo" lands almost exactly on the 1,291,968 measured here. Right
conclusion, wrong reason — the saving comes from structural derivation in
the app's own payloads, not from anything importable out of `kautian/opt/`.
