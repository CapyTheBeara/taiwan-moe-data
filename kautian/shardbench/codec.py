"""Byte-level primitives for the shard container.

Mirrors the ideas in taiwan-moe-data kautian/opt/codec.py but standalone:
varint / zigzag / delta / text sections / bitmask, plus a Tai-lo syllable
model and a hanji character model.
"""

import unicodedata
from collections import Counter


# ---------------------------------------------------------------- varint

def uvarint(n):
    if n < 0:
        raise ValueError(n)
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def uvarints(seq):
    out = bytearray()
    for n in seq:
        out += uvarint(n)
    return bytes(out)


class Reader:
    def __init__(self, buf, pos=0):
        self.buf = buf
        self.pos = pos

    def uvarint(self):
        shift = 0
        val = 0
        while True:
            b = self.buf[self.pos]
            self.pos += 1
            val |= (b & 0x7F) << shift
            if not (b & 0x80):
                return val
            shift += 7

    def take(self, n):
        s = self.buf[self.pos:self.pos + n]
        self.pos += n
        return s


def zigzag(n):
    return (n << 1) ^ (n >> 63) if n >= 0 else ((-n) << 1) - 1


def unzigzag(n):
    return (n >> 1) if not (n & 1) else -((n + 1) >> 1)


def delta(values):
    out = []
    prev = 0
    for v in values:
        out.append(zigzag(v - prev))
        prev = v
    return out


def undelta(zz):
    out = []
    prev = 0
    for z in zz:
        prev += unzigzag(z)
        out.append(prev)
    return out


# ---------------------------------------------------------------- sections

def text_section(strings):
    """count, then lengths, then the concatenated utf-8 blob."""
    blobs = [s.encode('utf-8') for s in strings]
    return uvarint(len(blobs)) + uvarints(len(b) for b in blobs) + b''.join(blobs)


def read_text_section(r):
    n = r.uvarint()
    lens = [r.uvarint() for _ in range(n)]
    return [r.take(L).decode('utf-8') for L in lens]


def bitmask(flags):
    out = bytearray()
    acc = 0
    bits = 0
    for f in flags:
        acc |= (1 if f else 0) << bits
        bits += 1
        if bits == 8:
            out.append(acc)
            acc = 0
            bits = 0
    if bits:
        out.append(acc)
    return uvarint(len(flags)) + bytes(out)


def read_bitmask(r):
    n = r.uvarint()
    raw = r.take((n + 7) // 8)
    return [bool(raw[i >> 3] & (1 << (i & 7))) for i in range(n)]


def dict_section(values):
    """Low-cardinality column -> (symbol table, varint code per row)."""
    freq = Counter(values)
    syms = [s for s, _ in freq.most_common()]
    idx = {s: i for i, s in enumerate(syms)}
    return text_section(syms) + uvarints(idx[v] for v in values)


def read_dict_section(r, n):
    syms = read_text_section(r)
    return [syms[r.uvarint()] for _ in range(n)]


def front_coded(sorted_strings):
    """Shared-prefix coding for a sorted string column."""
    out = bytearray(uvarint(len(sorted_strings)))
    prev = ''
    body = bytearray()
    for s in sorted_strings:
        i = 0
        m = min(len(prev), len(s))
        while i < m and prev[i] == s[i]:
            i += 1
        tail = s[i:].encode('utf-8')
        out += uvarint(i) + uvarint(len(tail))
        body += tail
        prev = s
    return bytes(out) + bytes(body)


# ---------------------------------------------------------- Tai-lo model

TONE_MARKS = '́̀̂̄̍̆̌́̀'
SEP_CHARS = set(" -—")


def tokenize_tailo(s):
    """Split into (syllables, separators) with render(*tokenize(x)) == x.

    A syllable is a run of letters/tone-marks/digits; everything else
    (spaces, hyphens, punctuation, capitalisation is preserved in the
    syllable itself) is a verbatim separator.
    """
    d = unicodedata.normalize('NFD', s)
    syls = []
    seps = []
    cur = []
    sep = []
    for ch in d:
        if ch.isalnum() or unicodedata.combining(ch):
            if sep or not cur:
                seps.append(''.join(sep))
                sep = []
            cur.append(ch)
        else:
            if cur:
                syls.append(''.join(cur))
                cur = []
            sep.append(ch)
    if cur:
        syls.append(''.join(cur))
    seps.append(''.join(sep))
    return syls, seps


def render_tailo(syls, seps):
    out = []
    for i, sy in enumerate(syls):
        out.append(seps[i])
        out.append(sy)
    out.append(seps[len(syls)])
    return unicodedata.normalize('NFC', ''.join(out))


def check_tailo_roundtrip(strings):
    bad = []
    for s in strings:
        sy, sp = tokenize_tailo(s)
        if render_tailo(sy, sp) != unicodedata.normalize('NFC', s):
            bad.append(s)
    return bad


class TailoModel:
    """Frequency-ordered syllable + separator dictionaries."""

    def __init__(self, corpus):
        sylf = Counter()
        sepf = Counter()
        for s in corpus:
            sy, sp = tokenize_tailo(s)
            sylf.update(sy)
            sepf.update(sp)
        self.syls = [x for x, _ in sylf.most_common()]
        self.seps = [x for x, _ in sepf.most_common()]
        self.syl_ix = {s: i for i, s in enumerate(self.syls)}
        self.sep_ix = {s: i for i, s in enumerate(self.seps)}

    def header(self):
        return text_section(self.syls) + text_section(self.seps)

    def encode(self, s):
        sy, sp = tokenize_tailo(s)
        out = bytearray(uvarint(len(sy)))
        for x in sy:
            out += uvarint(self.syl_ix[x])
        for x in sp:
            out += uvarint(self.sep_ix[x])
        return bytes(out)

    def decode(self, r):
        n = r.uvarint()
        sy = [self.syls[r.uvarint()] for _ in range(n)]
        sp = [self.seps[r.uvarint()] for _ in range(n + 1)]
        return render_tailo(sy, sp)


class CharModel:
    """Frequency-ordered character dictionary, for CJK-heavy columns."""

    def __init__(self, corpus):
        f = Counter()
        for s in corpus:
            f.update(s)
        self.chars = [c for c, _ in f.most_common()]
        self.ix = {c: i for i, c in enumerate(self.chars)}

    def header(self):
        return text_section([''.join(self.chars)])

    def encode(self, s):
        return uvarint(len(s)) + uvarints(self.ix[c] for c in s)

    def decode(self, r):
        n = r.uvarint()
        return ''.join(self.chars[r.uvarint()] for _ in range(n))
