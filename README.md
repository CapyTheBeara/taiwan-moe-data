# taiwan-moe-data

A mirror of public dictionary datasets published by Taiwan's Ministry of
Education (教育部). Stored here as unmodified downloads so they don't need
to be re-fetched from the source servers on every use.

## Contents

| Path | Source | Fetched | Size | SHA-256 |
| --- | --- | --- | --- | --- |
| `kautian/kautian.db` | SQLite conversion of `kautian.ods` (rebuilt directly from the ODS row below — same fetch, all 19 sheets, full provenance) | rebuilt 2026-07-24 | 9.79 MB | `b989a5dd05d0eff43a34d72338c5aba8b8f11d1858fd7bc4c0f8415fe323a8df` |
| `kautian/kautian.ods` | [sutian.moe.edu.tw/media/senn/ods/kautian.ods](https://sutian.moe.edu.tw/media/senn/ods/kautian.ods) | 2026-07-24 | 4.47 MB | `55fd06dc98b0499449870e6abd7ca545ab9f9ef51754ffa8c2ff17359eca162b` |
| `concised/dict_concised_2014_20260626.zip` | [language.moe.gov.tw — 《國語辭典簡編本》資料下載](https://language.moe.gov.tw/001/Upload/Files/site_content/M0001/respub/dict_concised_download.html) | 2026-07-24 | 6.94 MB | `fc83d27eb3fbf6fcfdb791e7d05ef60946b58ef8e8857ed165b612217b392806` |
| `concised/concised.db` | SQLite conversion of the xlsx inside the zip above, built by `concised/build_concised_db.py` (stdlib-only, in this repo — reproducible from the zip) | 2026-07-24 | 11 MB | `31caa12c38b7b1d0d7aaed978ce82500a3f5d11130a3d3b42ac36b0f64171c35` |
| `audio/sutiau-mp3.zip` | [sutian.moe.edu.tw/media/senn/sutiau-mp3.zip](https://sutian.moe.edu.tw/media/senn/sutiau-mp3.zip) (headword audio) | 2026-07-24 | 305.5 MB | `1d7375fe704999309f263e6372b34e3af923c398ea980ca2158ebc1a39b905a9` |
| `audio/leku-mp3.zip` | [sutian.moe.edu.tw/media/senn/leku-mp3.zip](https://sutian.moe.edu.tw/media/senn/leku-mp3.zip) (example-sentence audio) | 2026-07-24 | 528.0 MB | `76078c800f26896aae83223c04e134e8685d02d2d96617f1ed811ec987af2d06` |

`kautian.ods` and `kautian.db` cover the same underlying dictionary
(教育部臺灣台語常用詞辭典 — MOE Taiwanese Hokkien Common Words Dictionary).
`kautian.db` is rebuilt directly from this `kautian.ods` fetch (all 19 sheets,
schema matched to the previous build), so the two are in sync as of
2026-07-24 (29,591 headword rows in both).

The Concised dictionary (《國語辭典簡編本》) is MOE's Mandarin dictionary
edited for students and learners of Mandarin — a separate work from the
Hokkien dictionary above.

## Derived containers

Two range-fetchable containers are built from the databases above, so a browser
can read one headword's detail over HTTP without a server and without SQLite.
They share a format and a client; each has its own contract document.

| Path | Built from | Contract | Records |
| --- | --- | --- | --- |
| `kautian/v1/` | `kautian/kautian.db` | `kautian/DETAIL.md` | 18,031 Taiwanese headwords |
| `concised/v1/` | `concised/concised.db` + `kautian/kautian.db` | `concised/CONCISED_DETAIL.md` | 4,603 臺華共同詞 headwords, Mandarin |

Both are indexed by kautian `詞目id`, and no id is live in both — the Taiwanese
and Mandarin datasets stay separate, so a client always knows which dictionary a
record came from.

## License

All dictionary text and audio in this repository is published by the
Ministry of Education, Republic of Taiwan (中華民國教育部), under:

**創用CC 姓名標示-禁止改作 3.0 臺灣授權條款**
(Creative Commons Attribution-NoDerivatives 3.0 Taiwan — CC BY-ND 3.0 TW)

License text: https://creativecommons.org/licenses/by-nd/3.0/tw/legalcode

This permits reproduction, distribution, and transmission of the works,
including for commercial purposes, provided that:

- **Attribution** is given to the Ministry of Education as the source.
- The dictionary **text/content itself is not altered**. Per MOE's own
  usage notes, the no-derivatives restriction applies to the dictionary
  content, not to file-format conversion — so mirroring/re-hosting the
  original files (as done here) is within scope of the license.

Copyright in the underlying dictionary content remains with 中華民國教育部
(Ministry of Education, R.O.C.). This repository only mirrors the original,
unmodified files for convenient reuse.

### Sources / reference links

- Taiwanese Hokkien Common Words Dictionary (教育部臺灣台語常用詞辭典):
  https://sutian.moe.edu.tw/
- MOE Dictionary Public License Portal (教育部國語辭典公眾授權網):
  https://language.moe.gov.tw/001/Upload/Files/site_content/M0001/respub/index.html
- Concised Mandarin Chinese Dictionary download page:
  https://language.moe.gov.tw/001/Upload/Files/site_content/M0001/respub/dict_concised_download.html
