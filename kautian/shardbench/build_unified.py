"""Corrected pricing for the 'ship the whole dictionary' shape:
a unified headword index, all senses, relations, and MoE examples,
priced with the derived-romanisation + id-order techniques.
"""
import os, json, sys, sqlite3, brotli
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from codec import *
from reading import ReadingModel

D = os.environ.get('TAIGI_EAR_DATA', '/home/user/taigi-ear/public/data/')
K = os.environ.get('KAUTIAN_DB', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kautian.db'))
C = os.environ.get('CONCISED_DB', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'concised', 'concised.db'))
br = lambda b: len(brotli.compress(b, quality=11))
k = sqlite3.connect(K)
q = lambda s: k.execute(s).fetchall()

# ---------------- unified headword index: every reading + 詞目類型 + freq
lex = json.load(open(D + 'lexicon.json'))
kind = {r[0]: r[1] for r in q('select 詞目id,詞目類型 from 詞目')}
rows = sorted(lex, key=lambda r: (r[0], r[1], r[2], r[4], r[6]))
U = {}
U['id'] = uvarints(delta([r[0] for r in rows]))
U['hanji'] = text_section([r[1] for r in rows])
rm = ReadingModel([(r[1], r[2]) for r in rows])
U['rm'] = rm.header()
U['tailo'] = rm.encode_column([r[1] for r in rows], [r[2] for r in rows])[0]
U['register'] = dict_section([r[4] for r in rows])
U['sub'] = bitmask([r[5] for r in rows])
U['rtype'] = dict_section([r[6] for r in rows])
f = [r[7] if len(r) > 7 else None for r in rows]
U['freq'] = bitmask([x is not None for x in f]) + uvarints(x for x in f if x is not None)
U['kind'] = dict_section([kind.get(r[0], '') for r in rows])
uni = b''.join(U[x] for x in sorted(U))
print(f'unified headword index   {br(uni):>9,} br   ({len(rows):,} readings, '
      f'{len({r[0] for r in rows}):,} headwords, incl. 詞目類型)')
for x in sorted(U, key=lambda x: -br(U[x])):
    print(f'    {x:10s} {br(U[x]):>8,}')

# ---------------- all senses (kautian 義項 + concised fallback)
sen = q('select 詞目id,義項id,詞性,解說 from 義項 order by 詞目id,義項id')
S = {'id': uvarints(delta([r[1] for r in sen])),
     'wid': uvarints(delta([r[0] for r in sen])),
     'pos': dict_section([r[2] or '' for r in sen])}
cm = CharModel([r[3] or '' for r in sen])
S['model'] = cm.header()
S['def'] = b''.join(cm.encode(r[3] or '') for r in sen)
cc = sqlite3.connect(C)
cn = {}
for r in cc.execute('select 字詞名,注音一式,漢語拼音,釋義 from concised'):
    cn.setdefault(r[0], []).append(r)
withsense = {r[0] for r in sen}
need = sorted((wid, (h or '').replace('【替】', ''))
              for wid, h in q('select 詞目id,漢字 from 詞目') if wid not in withsense)
hit = [(w, h) for w, h in need if h in cn]
flat = [r for w, h in hit for r in cn[h]]
cm2 = CharModel([r[3] or '' for r in flat])
S['cn.ids'] = uvarints(delta([w for w, _ in hit])) + uvarints(len(cn[h]) for _, h in hit)
S['cn.zhuyin'] = text_section([r[1] or '' for r in flat])
S['cn.pinyin'] = text_section([r[2] or '' for r in flat])
S['cn.model'] = cm2.header()
S['cn.def'] = b''.join(cm2.encode(r[3] or '') for r in flat)
sb = b''.join(S[x] for x in sorted(S))
print(f'\nall senses               {br(sb):>9,} br   ({len(sen):,} 義項 over {len(withsense):,} '
      f'headwords + {len(hit):,} concised)')

# ---------------- relations
rel = bytearray()
from collections import defaultdict
for tbl, cols in [('詞目tuì詞目近義', '詞目id,對應詞目id'), ('詞目tuì詞目反義', '詞目id,對應詞目id'),
                  ('義項tuì詞目近義', '義項id,對應詞目id'), ('義項tuì詞目反義', '義項id,對應詞目id'),
                  ('義項tuì義項近義', '義項id,對應義項id'), ('義項tuì義項反義', '義項id,對應義項id')]:
    g = defaultdict(list)
    for a, b in q(f'select {cols} from {tbl}'):
        g[a].append(b)
    ks = sorted(g)
    rel += uvarint(len(ks)) + uvarints(delta(ks)) + uvarints(len(g[x]) for x in ks) + \
        b''.join(uvarints(delta(sorted(g[x]))) for x in ks)
print(f'relations                {br(bytes(rel)):>9,} br')

# ---------------- all MoE example sentences
ex = q('select 詞目id,義項id,例句順序,漢字,羅馬字,華語 from 例句 order by 詞目id,義項id,例句順序')
rmE = ReadingModel([(r[3] or '', r[4] or '') for r in ex])
cm3 = CharModel([r[3] or '' for r in ex] + [r[5] or '' for r in ex])
X = {'sid': uvarints(delta([r[1] for r in ex])), 'ord': uvarints(r[2] for r in ex),
     'rm': rmE.header(), 'model': cm3.header(),
     'hanji': b''.join(cm3.encode(r[3] or '') for r in ex),
     'mandarin': b''.join(cm3.encode(r[5] or '') for r in ex),
     'tailo': rmE.encode_column([r[3] or '' for r in ex], [r[4] or '' for r in ex])[0]}
xb = b''.join(X[x] for x in sorted(X))
print(f'all MoE examples         {br(xb):>9,} br   ({len(ex):,} 例句)')
