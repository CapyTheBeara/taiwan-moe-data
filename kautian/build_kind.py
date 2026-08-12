#!/usr/bin/env python3
"""
build_kind.py — Precompute the word-details modal's four-way icon call
(full/bound/named/none) per kautian 詞目id into one flat byte array, so
taigi-ear can resolve it from a single static file instead of booting
concised/v3/ and kautian/rel/v1/ at runtime just to ask "which icon".

kautian/kind/v1/detail-kind.bin is `maxId + 1` bytes, one per id, no header:
byte `id` is `kind[id]` from `KINDS` in kautian/kind/records.py. It is not the
kautian/v1/ container format — there is nothing to range-fetch, so there is
nothing to index.

Stdlib-only. Deterministic: detail-kind.bin is byte-identical across rebuilds
of the same three inputs.

Usage:
    python3 kautian/build_kind.py \\
        --db kautian/kautian.db \\
        --concised-idx concised/v3/detail.idx \\
        --relations-idx kautian/rel/v1/detail.idx \\
        --out kautian/kind/v1/
"""

import argparse
import datetime
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kautian.build_detail import generator_commit, sha256
from kautian.kind import records, source


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--concised-idx", required=True, type=Path)
    parser.add_argument("--relations-idx", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    types, concised_live, relations_live, max_id = source.read(
        args.db, args.concised_idx, args.relations_idx
    )
    blob = records.build(types, concised_live, relations_live, max_id)
    (args.out / "detail-kind.bin").write_bytes(blob)

    tally = Counter(blob)
    meta = {
        "buildDate": datetime.date.today().isoformat(),
        "kautianDbSha256": sha256(args.db),
        "concisedIdxSha256": sha256(args.concised_idx),
        "relationsIdxSha256": sha256(args.relations_idx),
        "generatorCommit": generator_commit(Path(__file__).resolve().parent.parent),
        "maxId": max_id,
        "kinds": list(records.KINDS),
        "tally": {kind: tally[index] for index, kind in enumerate(records.KINDS)},
    }
    (args.out / "meta.json").write_text(
        json.dumps(meta, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"{len(blob)} B, max id {max_id}, tally {dict(meta['tally'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
