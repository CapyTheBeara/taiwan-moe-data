"""Re-encode the three tiers taigi-ear already ships, keeping their
boundaries — the incremental alternative to the A/B/C re-split.

Also re-encodes lexicon.json, which is the best target of the four:
searchKey is a pure function of tailo (verified 34,004/34,004 against
scripts/lexicon/normalize.py), so the column can be dropped entirely, and
the row order is reconstructible at load, so 詞目id can stay ascending.
"""
import os, json, sys, brotli
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from codec import *
from reading import ReadingModel

D = os.environ.get('TAIGI_EAR_DATA', '/home/user/taigi-ear/public/data/')
br = lambda b: len(brotli.compress(b, quality=11))
W = json.load(open(D + 'words.json'))
E = json.load(open(D + 'examples.json'))
wl, el = list(W.values()), list(E.values())

R = {}
R['id'] = uvarints(delta([w['id'] for w in wl]))
R['type'] = dict_section([w['type'] for w in wl])
R['hanji'] = text_section([w['hanji'] for w in wl])
rmW = ReadingModel([(w['hanji'], w['tailo']) for w in wl])
R['rm'] = rmW.header()
R['tailo'] = rmW.encode_column([w['hanji'] for w in wl], [w['tailo'] for w in wl])[0]
R['wenBai'] = dict_section([w['wenBai'] or '' for w in wl])
R['audioId'] = bitmask([w['audioId'] == str(w['id']) for w in wl])
c = [w['categories'] for w in wl]
R['cats'] = uvarints(len(x) for x in c) + dict_section([t for x in c for t in x])
ac = [w['altChars'] for w in wl]
R['altChars'] = uvarints(len(x) for x in ac) + text_section([t for x in ac for t in x])
ar = [w['altReadings'] for w in wl]
fl = [x for v in ar for x in v]
R['altReadings'] = uvarints(len(v) for v in ar) + text_section([x['hanji'] for x in fl]) + \
    text_section([x['tailo'] for x in fl]) + dict_section([x['type'] for x in fl])
g = [w['glosses'] for w in wl]
R['glosses'] = uvarints(len(x) for x in g) + text_section([t for x in g for t in x])
R['freq'] = uvarints(w['freq'] for w in wl)
res = b''.join(R[k] for k in sorted(R))

sl = [(w, s) for w in wl for s in w['senses']]
Dt = {}
Dt['s.count'] = uvarints(len(w['senses']) for w in wl)
Dt['s.id'] = uvarints(delta([s['id'] for _, s in sl]))
Dt['s.pos'] = dict_section([s['pos'] or '' for _, s in sl])
Dt['s.english'] = text_section([s['english'] or '' for _, s in sl])
Dt['s.gloss'] = bitmask([bool(s.get('gloss')) for _, s in sl]) + \
    text_section([s['gloss'] for _, s in sl if s.get('gloss')])
for f in ('synonyms', 'antonyms'):
    rs = [w[f] for w in wl]
    fx = [x for v in rs for x in v]
    Dt[f] = uvarints(len(v) for v in rs) + uvarints(delta([x['targetId'] for x in fx])) + \
        text_section([x['targetHanji'] for x in fx]) + \
        uvarints(x.get('sourceSenseId') or 0 for x in fx)
rmE = ReadingModel([(e['hanji'], e['tailo']) for e in el] + [(w['hanji'], w['tailo']) for w in wl])
Dt['rm'] = rmE.header()
Dt['e.hanji'] = text_section([e['hanji'] for e in el])
Dt['e.tailo'] = rmE.encode_column([e['hanji'] for e in el], [e['tailo'] for e in el])[0]
Dt['e.english'] = text_section([e['english'] or '' for e in el])
Dt['e.key'] = uvarints(delta([int(e['wordId']) for e in el])) + \
    uvarints(e['order'] for e in el) + uvarints(delta([e['senseId'] for e in el]))
mf = [e.get('minFreq') for e in el]
Dt['e.minFreq'] = bitmask([v is not None for v in mf]) + uvarints(v for v in mf if v is not None)
det = b''.join(Dt[k] for k in sorted(Dt))

cm = CharModel([s['definition'] or '' for _, s in sl] + [e['mandarin'] or '' for e in el] +
               [w.get('mandarinShort') or '' for w in wl])
M = {'model': cm.header(),
     's.def': b''.join(cm.encode(s['definition'] or '') for _, s in sl),
     'e.man': b''.join(cm.encode(e['mandarin'] or '') for e in el),
     'short': b''.join(cm.encode(w.get('mandarinShort') or '') for w in wl)}
man = b''.join(M[k] for k in sorted(M))

lex = sorted(json.load(open(D + 'lexicon.json')), key=lambda r: (r[0], r[1], r[2], r[4], r[6]))
L = {}
L['id'] = uvarints(delta([r[0] for r in lex]))
L['hanji'] = text_section([r[1] for r in lex])
rmL = ReadingModel([(r[1], r[2]) for r in lex])
L['rm'] = rmL.header()
L['tailo'] = rmL.encode_column([r[1] for r in lex], [r[2] for r in lex])[0]
L['register'] = dict_section([r[4] for r in lex])
L['sub'] = bitmask([r[5] for r in lex])
L['rtype'] = dict_section([r[6] for r in lex])
f = [r[7] if len(r) > 7 else None for r in lex]
L['freq'] = bitmask([x is not None for x in f]) + uvarints(x for x in f if x is not None)
lexb = b''.join(L[k] for k in sorted(L))

for name, blob, today in [('lexicon.json (lazy)', lexb, 394565),
                          ('words-index.json (resident)', res, 73841),
                          ('detail.json (deferred)', det, 387788),
                          ('mandarin.json (gated)', man, 169534)]:
    print(f'{name:30s} today {today:>8,}  re-encoded {br(blob):>8,}  ({br(blob)/today:.2f}x)')
