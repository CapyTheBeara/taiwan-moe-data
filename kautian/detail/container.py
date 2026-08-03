import json
import struct

UINT16_MAX = 65535
SENTINEL_HEAD_BYTES = 32
HEADER = b"KTDETAIL1" + b"\x00" * 7


def encode(record):
    text = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


def write(records, max_id, out_dir, provenance):
    """Write detail.bin and detail.idx in one pass from the same encoded bytes."""
    lengths = [0] * (max_id + 1)
    sentinel_id = None
    sentinel_head = ""
    with open(out_dir / "detail.bin", "wb") as container:
        container.write(HEADER)
        for word_id in range(max_id + 1):
            record = records.get(word_id)
            blob = encode(record) if record else b""
            if len(blob) > UINT16_MAX:
                raise ValueError(f"record {word_id} is {len(blob)} B, over the uint16 ceiling")
            container.write(blob)
            lengths[word_id] = len(blob)
            if sentinel_id is None and len(blob) >= SENTINEL_HEAD_BYTES:
                sentinel_id = word_id
                sentinel_head = blob[:SENTINEL_HEAD_BYTES].hex()

    index = struct.pack(f"<{len(lengths)}H", *lengths)
    (out_dir / "detail.idx").write_bytes(index)

    meta = {
        **provenance,
        "maxId": max_id,
        "liveIds": sum(1 for length in lengths if length > 0),
        "headerBytes": len(HEADER),
        "containerBytes": len(HEADER) + sum(lengths),
        "sentinel": {"id": sentinel_id, "head": sentinel_head},
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return meta
