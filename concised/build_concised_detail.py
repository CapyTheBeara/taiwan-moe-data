#!/usr/bin/env python3
"""
build_concised_detail.py — Turn concised.db into the range-fetchable Mandarin
detail container: detail.bin (concatenated JSON records), detail.idx (uint16
record lengths) and meta.json, indexed by kautian 詞目id so a client addresses
this container exactly as it addresses kautian/v1/.

Only 臺華共同詞 headwords get a record. Stdlib-only. Deterministic: detail.bin
and detail.idx are byte-identical across rebuilds of the same two databases.

Usage:
    python3 concised/build_concised_detail.py --kautian-db kautian/kautian.db \
        --concised-db concised/concised.db --out concised/v1/
"""

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from concised.detail import records, source
from kautian.build_detail import generator_commit, sha256
from kautian.detail import container

MAGIC = "CNDETAIL1"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--kautian-db", required=True, type=Path)
    parser.add_argument("--concised-db", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    headwords, entries, max_id = source.read(args.kautian_db, args.concised_db)
    built = records.build(headwords, entries)
    provenance = {
        "concisedDbSha256": sha256(args.concised_db),
        "kautianDbSha256": sha256(args.kautian_db),
        "generatorCommit": generator_commit(Path(__file__).resolve().parent.parent),
        "buildDate": datetime.date.today().isoformat(),
    }
    meta = container.write(built, max_id, args.out, provenance, container.magic(MAGIC))
    print(
        f"{meta['liveIds']} of {len(headwords)} 臺華共同詞 matched, "
        f"{meta['containerBytes']} B, max id {max_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
