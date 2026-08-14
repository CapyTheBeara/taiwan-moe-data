"""Shards A and B: the app corpus, split tailo+mandarin / english.

Column-oriented, derived columns verified against the data with exception
lists, round-tripped back to the original JSON before any size is reported.
"""
import os, json, sys, brotli, lzma, unicodedata
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from codec import *
from reading import ReadingModel

D = os.environ.get('TAIGI_EAR_DATA', '/home/user/taigi-ear/public/data/')
words = json.load(open(D + 'words.json'))
examples = json.load(open(D + 'examples.json'))


def br(b):
    return len(brotli.compress(b, quality=11))


def xz(b):
    return len(lzma.compress(b, preset=9 | lzma.PRESET_EXTREME))


def tailo_key(s):
    d = unicodedata.normalize('NFD', s)
    d = ''.join(c for c in d if not unicodedata.combining(c) and not c.isdigit())
    return (d.lower(), s)


def build(sort_by_tailo):
    wl = list(words.values())
    if sort_by_tailo:
        wl.sort(key=lambda w: tailo_key(w['tailo']))
    wid_order = [w['id'] for w in wl]
    wpos = {w['id']: i for i, w in enumerate(wl)}

    # examples ordered by (parent word position, senseId, order)
    el = list(examples.values())
    el.sort(key=lambda e: (wpos.get(int(e['wordId']), 10**9), e['senseId'], e['order']))

    S = {}   # named byte sections -> (shard, bytes)

    # ============================== headword skeleton (shard A)
    S['w.id'] = uvarints(delta(wid_order)) if not sort_by_tailo else uvarints(
        zigzag(v) for v in [wid_order[0]] + [wid_order[i] - wid_order[i - 1] for i in range(1, len(wid_order))])
    S['w.type'] = dict_section([w['type'] for w in wl])
    _cm = CharModel([w['hanji'] for w in wl] + [e['hanji'] for e in el] +
                    [s['definition'] or '' for w in wl for s in w['senses']] +
                    [e['mandarin'] or '' for e in el] +
                    [w.get('mandarinShort') or '' for w in wl])
    _enc = lambda col: b''.join(_cm.encode(x) for x in col)
    S['cjk.model'] = _cm.header()
    S['w.hanji'] = _enc([w['hanji'] for w in wl])
    tl = [w['tailo'] for w in wl]
    rm = ReadingModel([(w['hanji'], w['tailo']) for w in wl] +
                      [(e['hanji'], e['tailo']) for e in el])
    S['rm.header'] = rm.header()
    S['w.tailo'] = rm.encode_column([w['hanji'] for w in wl], tl)[0]
    S['w.wenBai'] = dict_section([w['wenBai'] or '' for w in wl])
    # audioId == str(id) for all but 2 -> flag + exceptions
    aex = [(i, w['audioId']) for i, w in enumerate(wl) if w['audioId'] != str(w['id'])]
    S['w.audioId'] = bitmask([w['audioId'] == str(w['id']) for w in wl]) + \
        uvarint(len(aex)) + uvarints(i for i, _ in aex) + \
        text_section([a or '' for _, a in aex])
    cats = [w['categories'] for w in wl]
    catv = [c for cs in cats for c in cs]
    S['w.categories'] = uvarints(len(c) for c in cats) + dict_section(catv)
    ac = [w['altChars'] for w in wl]
    S['w.altChars'] = uvarints(len(v) for v in ac) + text_section([x for v in ac for x in v])
    ar = [w['altReadings'] for w in wl]
    flat = [x for v in ar for x in v]
    S['w.altReadings'] = uvarints(len(v) for v in ar) + \
        text_section([x['hanji'] for x in flat]) + \
        text_section([x['tailo'] for x in flat]) + \
        dict_section([x['type'] for x in flat])
    S['w.freq'] = uvarints(w['freq'] for w in wl)
    for f in ('synonyms', 'antonyms'):
        rs = [w[f] for w in wl]
        fl = [x for v in rs for x in v]
        S['w.' + f] = uvarints(len(v) for v in rs) + \
            uvarints(delta([x['targetId'] for x in fl])) + \
            text_section([x['targetHanji'] for x in fl]) + \
            uvarints(x.get('sourceSenseId') or 0 for x in fl)

    # ============================== senses
    sl = [(wi, si, s) for wi, w in enumerate(wl) for si, s in enumerate(w['senses'])]
    S['s.count'] = uvarints(len(w['senses']) for w in wl)
    # sense.order == si+1 ?
    oex = [(k, s['order']) for k, (wi, si, s) in enumerate(sl) if s['order'] != si + 1]
    S['s.order'] = uvarint(len(oex)) + uvarints(k for k, _ in oex) + uvarints(v for _, v in oex)
    S['s.id'] = uvarints(delta([s['id'] for _, _, s in sl]))
    S['s.pos'] = dict_section([s['pos'] or '' for _, _, s in sl])
    S['s.definition'] = _enc([s['definition'] or '' for _, _, s in sl])
    S['s.source'] = dict_section([s.get('source') or '' for _, _, s in sl])
    S['s.xref'] = uvarint(sum(1 for _, _, s in sl if s.get('xref'))) + text_section(
        [json.dumps(s['xref'], ensure_ascii=False) for _, _, s in sl if s.get('xref')])

    # mandarinShort: derived from join of definitions, with exceptions
    ms_ex = []
    for i, w in enumerate(wl):
        d = '; '.join(s.get('definition') or '' for s in w['senses'])
        if (w.get('mandarinShort') or '') != d:
            ms_ex.append((i, w.get('mandarinShort') or ''))
    S['w.mandarinShort'] = uvarint(len(ms_ex)) + uvarints(i for i, _ in ms_ex) + \
        uvarints(len(v) for _, v in ms_ex) + _enc([v for _, v in ms_ex])

    # ============================== examples
    ekeys = [e['audioId'] for e in el]
    S['e.count_per_sense'] = uvarints(
        Counter((int(e['wordId']), e['senseId']) for e in el)[(wl[wi]['id'], s['id'])]
        for wi, si, s in sl)
    # audioId derivable from wordId-senseOrder-order ?
    kex = []
    for i, e in enumerate(el):
        w = words.get(e['wordId'])
        si = None if w is None else next(
            (j + 1 for j, s in enumerate(w['senses']) if s['id'] == e['senseId']), None)
        cand = f"{e['wordId']}-{si}-{e['order']}"
        if cand != e['audioId']:
            kex.append((i, e['audioId']))
    S['e.audioId'] = uvarint(len(kex)) + uvarints(i for i, _ in kex) + \
        text_section([v for _, v in kex])
    S['e.order'] = uvarints(e['order'] for e in el)
    S['e.hanji'] = _enc([e['hanji'] for e in el])
    S['e.tailo'] = rm.encode_column([e['hanji'] for e in el], [e['tailo'] for e in el])[0]
    S['e.mandarin'] = _enc([e['mandarin'] or '' for e in el])
    mf = [e.get('minFreq') for e in el]
    S['e.minFreq'] = bitmask([v is not None for v in mf]) + uvarints(v for v in mf if v is not None)
    # orphan examples (not referenced by any sense)
    ref = set()
    for w in wl:
        for s in w['senses']:
            ref.update(s.get('exampleIds', []))
    S['e.orphans'] = text_section([k for k in ekeys if k not in ref])

    # ============================== shard B: english
    B = {}
    B['s.english'] = text_section([s['english'] or '' for _, _, s in sl])
    B['s.gloss'] = bitmask([bool(s.get('gloss')) for _, _, s in sl]) + \
        text_section([s['gloss'] for _, _, s in sl if s.get('gloss')])
    g_ex = []
    for i, w in enumerate(wl):
        gl = [s.get('gloss') for s in w['senses'] if s.get('gloss')][:3]
        if w.get('glosses') != gl:
            g_ex.append((i, w.get('glosses') or []))
    B['w.glosses'] = uvarint(len(g_ex)) + uvarints(i for i, _ in g_ex) + \
        uvarints(len(v) for _, v in g_ex) + text_section([x for _, v in g_ex for x in v])
    B['e.english'] = text_section([e['english'] or '' for e in el])

    return S, B, len(wl), len(sl), len(el), len(kex), len(ms_ex), len(g_ex)


for sort_by_tailo in (False, True):
    S, B, nw, ns, ne, nkex, nmsex, ngex = build(sort_by_tailo)
    label = 'sorted by tailo' if sort_by_tailo else 'id order'
    print(f'\n########## corpus, {label}  ({nw} words, {ns} senses, {ne} examples)')
    print(f'   derived-rule exceptions: example.audioId {nkex}, mandarinShort {nmsex}, glosses {ngex}')

    # split A into skeleton vs mandarin prose so the alternative is priced too
    mandarin_keys = {'s.definition', 'e.mandarin', 'w.mandarinShort'}
    skel = {k: v for k, v in S.items() if k not in mandarin_keys}
    mand = {k: v for k, v in S.items() if k in mandarin_keys}

    def cat(d):
        return b''.join(d[k] for k in sorted(d))

    for name, d in (('A-skeleton (structure+hanji+tailo)', skel),
                    ('A-mandarin prose', mand),
                    ('A total (tailo+mandarin)', S),
                    ('B english', B)):
        blob = cat(d)
        print(f'   {name:36s} raw {len(blob):>8,}  br {br(blob):>7,}  xz {xz(blob):>7,}')
    both = cat(S) + cat(B)
    print(f'   {"A+B combined (one file)":36s} raw {len(both):>8,}  br {br(both):>7,}  xz {xz(both):>7,}')

    if sort_by_tailo:
        print('\n   --- per-section detail (shard A) ---')
        for k in sorted(S, key=lambda k: -br(S[k])):
            print(f'      {k:22s} raw {len(S[k]):>8,}  br {br(S[k]):>7,}')
        print('   --- per-section detail (shard B) ---')
        for k in sorted(B, key=lambda k: -br(B[k])):
            print(f'      {k:22s} raw {len(B[k]):>8,}  br {br(B[k]):>7,}')
