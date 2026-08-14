"""Per-column bench: which representation wins after brotli-11 / lzma."""
import os, json, sys, brotli, lzma
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from codec import *

D = os.environ.get('TAIGI_EAR_DATA', '/home/user/taigi-ear/public/data/')
words = json.load(open(D + 'words.json'))
examples = json.load(open(D + 'examples.json'))


def br(b):
    return len(brotli.compress(b, quality=11))


def xz(b):
    return len(lzma.compress(b, preset=9 | lzma.PRESET_EXTREME))


def show(name, variants):
    print(f'\n== {name}')
    base = None
    for label, blob in variants:
        b, x = br(blob), xz(blob)
        if base is None:
            base = b
        print(f'   {label:28s} raw {len(blob):>8,}  br {b:>7,}  xz {x:>7,}  ({b/base:.2f}x)')


wl = list(words.values())
el = list(examples.values())

# ---- word tailo
col = [w['tailo'] for w in wl]
tm = TailoModel(col)
bad = check_tailo_roundtrip(col)
print('tailo roundtrip failures (word):', len(bad))
enc = tm.header() + b''.join(tm.encode(s) for s in col)
show('word.tailo (2,577)', [
    ('raw json array', json.dumps(col, ensure_ascii=False).encode()),
    ('text section', text_section(col)),
    ('front-coded (sorted)', front_coded(sorted(col))),
    ('syllable model', enc),
])

# ---- example tailo
ecol = [e['tailo'] for e in el]
print('tailo roundtrip failures (example):', len(check_tailo_roundtrip(ecol)))
tm2 = TailoModel(col + ecol)
enc2 = tm2.header() + b''.join(tm2.encode(s) for s in col + ecol)
show('word+example tailo (8,068)', [
    ('text section', text_section(col + ecol)),
    ('syllable model (shared)', enc2),
])

# ---- hanji
hj = [w['hanji'] for w in wl] + [e['hanji'] for e in el]
cm = CharModel(hj)
show('word+example hanji (8,068)', [
    ('text section', text_section(hj)),
    ('char model', cm.header() + b''.join(cm.encode(s) for s in hj)),
])

# ---- mandarin prose: sense.definition + example.mandarin
defs = [s['definition'] or '' for w in wl for s in w['senses']]
mand = [e['mandarin'] or '' for e in el]
cm2 = CharModel(defs + mand)
show('mandarin prose (defs+ex)', [
    ('text section', text_section(defs + mand)),
    ('char model', cm2.header() + b''.join(cm2.encode(s) for s in defs + mand)),
])

# ---- english prose
eng = [s['english'] or '' for w in wl for s in w['senses']] + [e['english'] or '' for e in el]
glo = [s.get('gloss') or '' for w in wl for s in w['senses']]
words_tok = Counter()
for s in eng:
    words_tok.update(s.split(' '))
vocab = [x for x, _ in words_tok.most_common()]
vix = {x: i for i, x in enumerate(vocab)}
tokblob = text_section(vocab) + b''.join(
    uvarint(len(s.split(' '))) + uvarints(vix[t] for t in s.split(' ')) for s in eng)
show('english prose (10,311)', [
    ('text section', text_section(eng)),
    ('word-token model', tokblob),
])
show('english glosses (4,820)', [
    ('text section', text_section(glo)),
])

# ---- integers
ids = [w['id'] for w in wl]
show('word.id (2,577, ascending)', [
    ('text/json', json.dumps(ids).encode()),
    ('varint raw', uvarints(ids)),
    ('delta+zigzag varint', uvarints(delta(ids))),
])
freq = [w['freq'] for w in wl]
show('word.freq', [
    ('varint raw', uvarints(freq)),
])
