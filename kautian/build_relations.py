#!/usr/bin/env python3
"""
build_relations.py — Turn kautian.db's six relation tables into the
range-fetchable inbound-relation container: detail.bin (concatenated JSON
records), detail.idx (uint16 record lengths) and meta.json, indexed by kautian
詞目id so a client addresses it exactly as it addresses kautian/v1/.

Only the entry-less headword types get a record. 近反義詞不單列詞目者 is the
whole point — the dictionary lists those headwords *only* as a near or opposite
meaning of another word, so this container is the only place that says which
word. Stdlib-only. Deterministic: detail.bin and detail.idx are byte-identical
across rebuilds of the same database.

Usage:
    python3 kautian/build_relations.py --db kautian/kautian.db --out kautian/rel/v1/
"""

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kautian.meta import generator_commit, sha256
from kautian.detail import container
from kautian.relations import records, source

MAGIC = "KTREL001"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    edges, eligible, max_id = source.read(args.db)
    built = records.build(edges, eligible)
    provenance = {
        "dbSha256": sha256(args.db),
        "generatorCommit": generator_commit(Path(__file__).resolve().parent.parent),
        "buildDate": datetime.date.today().isoformat(),
    }
    meta = container.write(built, max_id, args.out, provenance, container.magic(MAGIC))
    print(
        f"{meta['liveIds']} of {len(eligible)} entry-less headwords are named by "
        f"another, {meta['containerBytes']} B, max id {max_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
