"""
test_meta.py — the provenance block the browser documents carry.

`version` is a cache key a browser holds across sessions, so what matters is
not its value but its stability: same inputs, same key; either input changed,
different key. And it must ride where the decoder cannot trip over it.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from kautian import meta
from kautian.build_web_json import write_split
from kautian.opt import container, webjson
from kautian.tests.test_optimized import write_db

DECODER = REPO_ROOT / "kautian" / "web" / "kautian.mjs"
NODE = shutil.which("node")

def empty_document(workspace):
    """A real, minimal KTWEB1 document — `to_document` needs a schema, not a dict."""
    schema, data, header = container.read_database(write_db(Path(workspace) / "source.db", {}))
    return webjson.to_document(schema, data, header)


DRIVER = """
import { readFileSync } from "node:fs";
import { decodeColumns } from "%s";
const document = JSON.parse(readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(Object.keys(decodeColumns(document))));
"""


class Version(unittest.TestCase):
    def test_the_same_commit_and_digests_give_the_same_version(self):
        self.assertEqual(
            meta.version("abc", {"one.db": "111", "two.db": "222"}),
            meta.version("abc", {"one.db": "111", "two.db": "222"}),
        )

    def test_source_order_does_not_change_the_version(self):
        self.assertEqual(
            meta.version("abc", {"one.db": "111", "two.db": "222"}),
            meta.version("abc", {"two.db": "222", "one.db": "111"}),
        )

    def test_a_changed_dataset_changes_the_version(self):
        self.assertNotEqual(
            meta.version("abc", {"one.db": "111"}),
            meta.version("abc", {"one.db": "112"}),
        )

    def test_a_changed_generator_changes_the_version(self):
        self.assertNotEqual(
            meta.version("abc", {"one.db": "111"}),
            meta.version("abd", {"one.db": "111"}),
        )

    def test_a_renamed_source_changes_the_version(self):
        self.assertNotEqual(
            meta.version("abc", {"one.db": "111"}),
            meta.version("abc", {"two.db": "111"}),
        )


class Block(unittest.TestCase):
    def test_it_digests_every_named_source(self):
        with tempfile.TemporaryDirectory() as workspace:
            first = Path(workspace) / "first.db"
            second = Path(workspace) / "second.db"
            first.write_bytes(b"one")
            second.write_bytes(b"two")
            block = meta.build({first.name: first, second.name: second})
        self.assertEqual(sorted(block["sources"]), ["first.db", "second.db"])
        self.assertNotEqual(block["sources"]["first.db"], block["sources"]["second.db"])
        self.assertEqual(len(block["version"]), meta.VERSION_DIGITS)

    def test_a_repo_git_cannot_read_reports_an_unknown_commit(self):
        with tempfile.TemporaryDirectory() as workspace:
            block = meta.build({}, repo_root=workspace)
        self.assertEqual(block["generatorCommit"], meta.UNKNOWN)


@unittest.skipIf(NODE is None, "node is not installed")
class Decoder(unittest.TestCase):
    def test_the_decoder_ignores_it(self):
        with tempfile.TemporaryDirectory() as workspace:
            document = empty_document(workspace)
            document["meta"] = meta.build({})
            path = Path(workspace) / "document.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            driver = Path(workspace) / "driver.mjs"
            driver.write_text(DRIVER % DECODER.as_posix(), encoding="utf-8")
            result = subprocess.run(
                [NODE, str(driver), str(path)],
                capture_output=True,
                text=True,
                check=True,
            )
        decoded = json.loads(result.stdout)
        self.assertIn("詞目", decoded)
        self.assertNotIn("meta", decoded)


class Split(unittest.TestCase):
    def test_the_split_index_carries_it(self):
        with tempfile.TemporaryDirectory() as workspace:
            document = empty_document(workspace)
            document["meta"] = meta.build({})
            write_split(document, Path(workspace) / "split")
            index = json.loads(
                (Path(workspace) / "split" / "index.json").read_text(encoding="utf-8")
            )
        self.assertEqual(index["meta"], document["meta"])

    def test_a_document_without_one_still_splits(self):
        with tempfile.TemporaryDirectory() as workspace:
            document = empty_document(workspace)
            write_split(document, Path(workspace) / "split")
            index = json.loads(
                (Path(workspace) / "split" / "index.json").read_text(encoding="utf-8")
            )
        self.assertNotIn("meta", index)


if __name__ == "__main__":
    unittest.main()
