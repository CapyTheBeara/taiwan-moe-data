"""Derive a Tai-lo column from its 漢字 column.

Alignment: strip punctuation/space from the hanji, then one hanji character
maps to one Tai-lo syllable. Verified on the real data (99.93% of corpus
examples align); rows that do not align fall back to a literal.

Per syllable we store the rank of the actual reading in that character's
frequency-ordered reading list. Rank 0 is the overwhelming majority, so the
column collapses to a run of zero bytes before brotli even sees it.

Separators (space / hyphen / -- / verbatim) are NOT derivable -- they are
word-boundary information the hanji does not carry -- so they are coded as
their own small-alphabet column.
"""
import unicodedata
from collections import Counter, defaultdict
from codec import (uvarint, uvarints, text_section, Reader,
                   read_text_section, tokenize_tailo, render_tailo)

NFC = lambda s: unicodedata.normalize('NFC', s)


def han_chars(h):
    return [c for c in h if unicodedata.category(c)[0] not in 'PZ']


class ReadingModel:
    def __init__(self, pairs):
        f = defaultdict(Counter)
        for h, t in pairs:
            sy, _ = tokenize_tailo(t)
            hc = han_chars(h)
            if len(hc) == len(sy):
                for c, s in zip(hc, sy):
                    f[c][NFC(s)] += 1
        self.ranks = {c: [s for s, _ in cc.most_common()] for c, cc in f.items()}
        self.ix = {c: {s: i for i, s in enumerate(lst)} for c, lst in self.ranks.items()}

    def header(self):
        chars = sorted(self.ranks)
        return text_section([''.join(chars)]) + \
            uvarints(len(self.ranks[c]) for c in chars) + \
            text_section([s for c in chars for s in self.ranks[c]])

    def encode_column(self, hanjis, tailos):
        """Returns (bytes, n_literal_rows, n_escaped_syllables)."""
        ranks = bytearray()
        seps = []
        literals = []
        ok = bytearray()
        esc = []
        nlit = nesc = 0
        for h, t in zip(hanjis, tailos):
            sy, sp = tokenize_tailo(t)
            hc = han_chars(h)
            if len(hc) != len(sy):
                ok.append(0)
                literals.append(t)
                nlit += 1
                continue
            ok.append(1)
            for c, s in zip(hc, sy):
                r = self.ix.get(c, {}).get(NFC(s))
                if r is None:
                    ranks += uvarint(0xFF)
                    esc.append(NFC(s))
                    nesc += 1
                else:
                    ranks += uvarint(r if r < 0xFF else 0xFF)
                    if r >= 0xFF:
                        esc.append(NFC(s))
                        nesc += 1
            seps.extend(sp)
            seps.append('\x00')  # row terminator
        sepsyms = [x for x, _ in Counter(seps).most_common()]
        sepix = {x: i for i, x in enumerate(sepsyms)}
        blob = (bytes(ok) + bytes(ranks) + text_section(sepsyms) +
                uvarints(sepix[x] for x in seps) +
                text_section(esc) + text_section(literals))
        return blob, nlit, nesc


def decode_column(model, blob, n):
    """Inverse of encode_column, for verification."""
    r = Reader(blob)
    ok = [r.take(1)[0] for _ in range(n)]
    # ranks are consumed lazily against the hanji, so the caller passes them in
    return r, ok


class Verifier:
    """Decode a column back, given the same hanji the encoder saw."""

    def __init__(self, model):
        self.m = model

    def decode(self, blob, hanjis):
        n = len(hanjis)
        r = Reader(blob)
        ok = [r.take(1)[0] for _ in range(n)]
        nsyl = sum(len(han_chars(h)) for h, o in zip(hanjis, ok) if o)
        ranks = [r.uvarint() for _ in range(nsyl)]
        sepsyms = read_text_section(r)
        nseps = sum(len(han_chars(h)) + 2 for h, o in zip(hanjis, ok) if o)
        seps = [sepsyms[r.uvarint()] for _ in range(nseps)]
        esc = read_text_section(r)
        literals = read_text_section(r)
        out, ri, si, ei, li = [], 0, 0, 0, 0
        for h, o in zip(hanjis, ok):
            if not o:
                out.append(literals[li]); li += 1
                continue
            hc = han_chars(h)
            sy = []
            for c in hc:
                rk = ranks[ri]; ri += 1
                if rk == 0xFF:
                    sy.append(esc[ei]); ei += 1
                else:
                    sy.append(self.m.ranks[c][rk])
            sp = seps[si:si + len(hc) + 1]; si += len(hc) + 2
            out.append(render_tailo(sy, sp))
        return out
