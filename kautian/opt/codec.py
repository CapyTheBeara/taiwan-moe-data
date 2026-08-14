"""
codec.py — primitive column codecs and the section container.

Every value written here is byte-exact on the way back out: text columns carry a
null mask alongside their payload, integer columns are varint or delta-varint,
and the container itself is a length-prefixed list of opaque byte sections. No
codec in this module knows anything about the dictionary.
"""

RECORD_SEPARATOR = "\n"


def write_varint(value, out):
    if value < 0:
        raise ValueError("varint values must be non-negative")
    while True:
        chunk = value & 0x7F
        value >>= 7
        out.append(chunk | 0x80 if value else chunk)
        if not value:
            return


def encode_varints(values):
    out = bytearray()
    for value in values:
        write_varint(value, out)
    return bytes(out)


def decode_varints(blob, count):
    values = []
    position = 0
    for _ in range(count):
        value = 0
        shift = 0
        while True:
            byte = blob[position]
            position += 1
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                break
        values.append(value)
    return values


def encode_zigzag(values):
    return encode_varints((value << 1) ^ (value >> 63) if value < 0 else value << 1 for value in values)


def decode_zigzag(blob, count):
    return [(value >> 1) ^ -(value & 1) for value in decode_varints(blob, count)]


def encode_deltas(values):
    """Delta-encode a monotonically non-decreasing integer column."""
    out = []
    previous = 0
    for value in values:
        out.append(value - previous)
        previous = value
    return encode_zigzag(out)


def decode_deltas(blob, count):
    values = []
    previous = 0
    for delta in decode_zigzag(blob, count):
        previous += delta
        values.append(previous)
    return values


def encode_texts(values):
    """Join newline-free strings behind a varint count.

    The count is not redundant: an empty payload is otherwise ambiguous between
    no strings at all and a single empty string, and columns hold both.
    """
    values = list(values)
    for value in values:
        if RECORD_SEPARATOR in value:
            raise ValueError("text column contains a record separator")
    out = bytearray()
    write_varint(len(values), out)
    return bytes(out) + RECORD_SEPARATOR.join(values).encode("utf-8")


def decode_texts(blob):
    position = 0
    count = 0
    shift = 0
    while True:
        byte = blob[position]
        position += 1
        count |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            break
    if not count:
        return []
    return blob[position:].decode("utf-8").split(RECORD_SEPARATOR)


def encode_mask(flags):
    """Pack booleans LSB-first, eight to a byte."""
    out = bytearray((len(flags) + 7) // 8)
    for index, flag in enumerate(flags):
        if flag:
            out[index >> 3] |= 1 << (index & 7)
    return bytes(out)


def decode_mask(blob, count):
    return [bool(blob[index >> 3] & (1 << (index & 7))) for index in range(count)]


def pack_sections(sections):
    """Serialise an ordered list of byte strings as varint lengths then bodies."""
    header = bytearray()
    write_varint(len(sections), header)
    for section in sections:
        write_varint(len(section), header)
    return bytes(header) + b"".join(sections)


def unpack_sections(blob):
    position = 0

    def read():
        nonlocal position
        value = 0
        shift = 0
        while True:
            byte = blob[position]
            position += 1
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                return value

    lengths = [read() for _ in range(read())]
    sections = []
    for length in lengths:
        sections.append(blob[position : position + length])
        position += length
    return sections
