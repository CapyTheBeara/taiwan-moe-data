"""
tailo.py — model the Tâi-lô reading of a headword against its 漢字.

Tâi-lô is one syllable per Han character, and most characters have exactly one
attested reading, so a syllable is usually free: encode its rank in that
character's reading list and the common case costs a zero byte the entropy coder
folds away. Everything around the syllables — the hyphen/space/`--` joins,
punctuation, spacing — is not derivable from them, so `tokenize` hands it back
verbatim as separators rather than trying to model it. That makes
`render(*tokenize(text)) == text` true by construction for every input, which is
what lets the encoder treat a failed *alignment* (syllable count against Han
character count) as the only fallback case it has to carry.

The reading model is built from (漢字, 羅馬字) pairs the decoder already holds,
so it costs nothing on the wire. Callers must build it from a table that has
already been decoded, never from the column being decoded.
"""

import re

HAN = re.compile(r"[㐀-鿿\U00020000-\U0002ffff]")
SYLLABLE = re.compile(r"(?:[^\W\d_]|[̀-ͯ]|')+", re.UNICODE)
ESCAPE_RANK = 255


def han_characters(hanji):
    return [character for character in hanji if HAN.match(character)]


def tokenize(reading):
    """Split a Tâi-lô string into syllables and the separators around them.

    Returns (syllables, separators) with len(separators) == len(syllables) + 1:
    a leading separator, one between each pair, and a trailing one. Either list
    may hold empty strings.
    """
    syllables = []
    separators = []
    position = 0
    for match in SYLLABLE.finditer(reading):
        separators.append(reading[position : match.start()])
        syllables.append(match.group())
        position = match.end()
    separators.append(reading[position:])
    return syllables, separators


def render(syllables, separators):
    out = separators[0]
    for index, syllable in enumerate(syllables):
        out += syllable + separators[index + 1]
    return out


def build_model(pairs):
    """Rank each character's readings by frequency, ties broken alphabetically.

    The tie-break is load-bearing: encoder and decoder derive the model
    independently, so any ordering they did not both compute would desynchronise
    the rank column.
    """
    counts = {}
    for hanji, reading in pairs:
        if not hanji or not reading:
            continue
        characters = han_characters(hanji)
        syllables = tokenize(reading)[0]
        if len(characters) != len(syllables) or len(characters) != len(hanji):
            continue
        for character, syllable in zip(characters, syllables):
            readings = counts.setdefault(character, {})
            key = syllable.lower()
            readings[key] = readings.get(key, 0) + 1
    return {
        character: [syllable for syllable, _ in sorted(readings.items(), key=lambda item: (-item[1], item[0]))]
        for character, readings in counts.items()
    }


def aligns(hanji, reading):
    """True when the reading has exactly one syllable per Han character."""
    if not hanji or not reading:
        return False
    characters = han_characters(hanji)
    return bool(characters) and len(characters) == len(tokenize(reading)[0])
