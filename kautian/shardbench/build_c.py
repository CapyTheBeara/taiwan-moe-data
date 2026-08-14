"""Shard C: the rest of the kautian dictionary, ordered alphabetically by tailo.

Covers every headword not in the app corpus, plus everything the app
currently reaches for remotely: kautian/v1 (senses + examples + outbound
relations), kautian/rel/v1 (inbound relations), entry-types.json, and the
Compose lexicon (derivable from the headword table, so it costs ~nothing).
"""
import os, json, sys, sqlite3, brotli, lzma, unicodedata, re
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from codec import *
from reading import ReadingModel, han_chars

DB = os.environ.get('KAUTIAN_DB', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kautian.db'))
con = sqlite3.connect(DB)
q = lambda s: con.execute(s).fetchall()
corpus = set(int(k) for k in json.load(open(os.environ.get('TAIGI_EAR_DATA', '/home/user/taigi-ear/public/data/') + 'words.json')))

br = lambda b: len(brotli.compress(b, quality=11))
xz = lambda b: len(lzma.compress(b, preset=9 | lzma.PRESET_EXTREME))

TAG = re.compile(r'^【[^】]*】')


def readings(rom):
    """Split a 羅馬字 field into its /-separated readings, each with any
    leading 【文】/【白】/【俗】 tag lifted off."""
    out = []
    for part in (rom or '').split('/'):
        m = TAG.match(part)
        out.append((m.group(0) if m else '', part[m.end():] if m else part))
    return out


def strip_sub(h):
    return (h or '').replace('【替】', '')


def tailo_key(s):
    d = unicodedata.normalize('NFD', readings(s)[0][1] if s else '')
    return ''.join(c for c in d if not unicodedata.combining(c)).lower()


ORDER = sys.argv[1] if len(sys.argv) > 1 else 'tailo'
rows = [r for r in q('select 詞目id,詞目類型,漢字,羅馬字,分類,羅馬字音檔檔名 from 詞目')
        if r[0] not in corpus]
if ORDER == 'tailo':
    rows.sort(key=lambda r: (tailo_key(r[3]), r[0]))
elif ORDER == 'hanji':
    rows.sort(key=lambda r: (strip_sub(r[2]), r[0]))
else:
    rows.sort(key=lambda r: r[0])

ids = [r[0] for r in rows]
S = {}

# ---------------------------------------------------------- headwords
S['h.id'] = uvarints(delta(ids))
S['h.type'] = dict_section([r[1] for r in rows])
_hhan = [strip_sub(r[2]) for r in rows]
S['h.substitute'] = bitmask(['【替】' in (r[2] or '') for r in rows])
_cats = [r[4] or '' for r in rows]
S['h.cat'] = uvarints(len(x.split(',')) if x else 0 for x in _cats) + \
    dict_section([t for x in _cats for t in (x.split(',') if x else [])])

# audio filename: "<詞目id>(<n>)" -- verify, store only exceptions
afx = []
for k, r in enumerate(rows):
    if r[5] is None:
        continue
    m = re.fullmatch(re.escape(str(r[0])) + r'\((\d+)\)', r[5])
    if not m:
        afx.append((k, r[5]))
S['h.audio'] = bitmask([r[5] is not None for r in rows]) + \
    uvarints(int(re.fullmatch(re.escape(str(r[0])) + r'\((\d+)\)', r[5]).group(1))
             for r in rows if r[5] is not None and
             re.fullmatch(re.escape(str(r[0])) + r'\((\d+)\)', r[5])) + \
    uvarint(len(afx)) + uvarints(k for k, _ in afx) + text_section([v for _, v in afx])

# ---------------------------------------------------------- senses
sen = defaultdict(list)
for wid, sid, p, d in q('select 詞目id,義項id,詞性,解說 from 義項 order by 詞目id,義項id'):
    if wid not in corpus:
        sen[wid].append((sid, p, d))
sl = [(i, s) for i in ids for s in sen.get(i, [])]
S['s.count'] = uvarints(len(sen.get(i, [])) for i in ids)
S['s.id'] = uvarints(delta([s[0] for _, s in sl]))
S['s.pos'] = dict_section([s[1] or '' for _, s in sl])
_defs = [s[2] or '' for _, s in sl]

# ---------------------------------------------------------- examples
exs = defaultdict(list)
for wid, sid, o, h, t, m, af in q(
        'select 詞目id,義項id,例句順序,漢字,羅馬字,華語,音檔檔名 from 例句 order by 詞目id,義項id,例句順序'):
    if wid not in corpus:
        exs[(wid, sid)].append((o, h, t, m, af))
sense_ord = {}
for i in ids:
    for n, s in enumerate(sen.get(i, [])):
        sense_ord[(i, s[0])] = n + 1
el = [(i, s[0], e) for i, s in sl for e in exs.get((i, s[0]), [])]
S['e.count'] = uvarints(len(exs.get((i, s[0]), [])) for i, s in sl)
S['e.order'] = uvarints(e[0] for _, _, e in el)
_ehan = [e[1] or '' for _, _, e in el]
_eman = [e[3] or '' for _, _, e in el]
# audio filename: "<詞目id>-<sense ordinal>-<例句順序>"
eafx = []
for k, (i, sid, e) in enumerate(el):
    want = f'{i}-{sense_ord[(i, sid)]}-{e[0]}'
    if e[4] is not None and e[4] != want:
        eafx.append((k, e[4]))
S['e.audio'] = bitmask([e[4] is not None for _, _, e in el]) + \
    uvarint(len(eafx)) + uvarints(k for k, _ in eafx) + text_section([v for _, v in eafx])

# ---------------------------------------------------------- reading model
alt_rows = []
for reg, tbl in (('又', '又唵作'), ('俗', '俗唵作'), ('合音', '合音唵作')):
    for wid, h, t in q(f'select 詞目id,漢字,羅馬字 from {tbl}'):
        if wid not in corpus:
            alt_rows.append((reg, wid, h, t))


def flatten(hanjis, roms):
    """One (hanji, single-reading) pair per /-separated reading."""
    hs, ts, tags, counts = [], [], [], []
    for h, r in zip(hanjis, roms):
        rs = readings(r)
        counts.append(len(rs))
        for tag, t in rs:
            hs.append(strip_sub(h))
            ts.append(t)
            tags.append(tag)
    return hs, ts, tags, counts


hh, ht, htag, hcnt = flatten([r[2] for r in rows], [r[3] for r in rows])
eh, et, etag, ecnt = flatten([e[1] for _, _, e in el], [e[2] for _, _, e in el])
ah, at, atag, acnt = flatten([r[2] for r in alt_rows], [r[3] for r in alt_rows])

rm = ReadingModel(list(zip(hh, ht)) + list(zip(eh, et)) + list(zip(ah, at)))
S['rm.header'] = rm.header()


def rom_column(hs, ts, tags, counts):
    blob, nl, ne = rm.encode_column(hs, ts)
    return (uvarints(counts) + dict_section(tags) + blob), nl, ne


S['h.tailo'], nl_h, ne_h = rom_column(hh, ht, htag, hcnt)
S['e.tailo'], nl_e, ne_e = rom_column(eh, et, etag, ecnt)
S['alt'] = uvarints(delta([r[1] for r in alt_rows])) + dict_section([r[0] for r in alt_rows]) + \
    text_section([strip_sub(r[2]) for r in alt_rows]) + rom_column(ah, at, atag, acnt)[0]

CJK = int(sys.argv[2]) if len(sys.argv) > 2 else 1
if CJK:
    _cm = CharModel(_defs + _eman + _ehan + _hhan)
    S['cjk.model'] = _cm.header()
    enc = lambda col: b''.join(_cm.encode(x) for x in col)
else:
    enc = text_section
S['h.hanji'] = enc(_hhan)
S['s.def'] = enc(_defs)
S['e.hanji'] = enc(_ehan)
S['e.mandarin'] = enc(_eman)

# ---------------------------------------------------------- relations
rel = bytearray()
for tbl, cols in [('詞目tuì詞目近義', '詞目id,對應詞目id'), ('詞目tuì詞目反義', '詞目id,對應詞目id'),
                  ('義項tuì詞目近義', '義項id,對應詞目id'), ('義項tuì詞目反義', '義項id,對應詞目id'),
                  ('義項tuì義項近義', '義項id,對應義項id'), ('義項tuì義項反義', '義項id,對應義項id')]:
    r = q(f'select {cols} from {tbl} order by 1,2')
    grp = defaultdict(list)
    for a, b in r:
        grp[a].append(b)
    keys = sorted(grp)
    rel += uvarint(len(keys)) + uvarints(delta(keys)) + \
        uvarints(len(grp[k]) for k in keys) + \
        b''.join(uvarints(delta(sorted(grp[k]))) for k in keys)
S['relations'] = bytes(rel)

# ---------------------------------------------------------- extras
iy = q('select 詞目id,漢字,異用字 from 異用字')
S['異用字'] = uvarints(delta([x[0] for x in iy])) + text_section([x[2] or '' for x in iy])
yc = q('select * from 語音差異')
S['語音差異'] = uvarints(delta([x[0] for x in yc])) + \
    text_section([c or '' for x in yc for c in x[2:12]])

# ---------------------------------------------------------- concised fallback
cc = sqlite3.connect(os.environ.get('CONCISED_DB', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'concised', 'concised.db')))
need = {r[0]: strip_sub(r[2]) for r in rows
        if r[1] in ('臺華共同詞', '單字不成詞者')}
cn = {}
for r in cc.execute('select 字詞名,注音一式,漢語拼音,釋義 from concised'):
    cn.setdefault(r[0], []).append(r)
hit = sorted((w, need[w]) for w in need if need[w] in cn)
_flat = [r for w, h in hit for r in cn[h]]
S['cn.ids'] = uvarints(delta([w for w, _ in hit])) + uvarints(len(cn[h]) for _, h in hit)
S['cn.zhuyin'] = text_section([r[1] or '' for r in _flat])
S['cn.pinyin'] = text_section([r[2] or '' for r in _flat])
_cn_def = [r[3] or '' for r in _flat]
if CJK:
    _cm2 = CharModel(_cn_def)
    S['cn.model'] = _cm2.header()
    S['cn.def'] = b''.join(_cm2.encode(x) for x in _cn_def)
else:
    S['cn.def'] = text_section(_cn_def)
print(f'   concised fallback: {len(hit):,}/{len(need):,} headwords matched, {len(_flat):,} readings')

# ---------------------------------------------------------- report
print(f'##### shard C ({ORDER} order): {len(rows):,} headwords, {len(sl):,} senses, '
      f'{len(el):,} examples, {len(alt_rows):,} alt readings')
print(f'   tailo literal fallbacks: headword {nl_h}/{len(hh)}, example {nl_e}/{len(eh)}')
blob = b''.join(S[k] for k in sorted(S))
print(f'   TOTAL  raw {len(blob):>9,}  br {br(blob):>8,}  xz {xz(blob):>8,}')
for k in sorted(S, key=lambda k: -br(S[k])):
    print(f'      {k:14s} raw {len(S[k]):>9,}  br {br(S[k]):>8,}')
