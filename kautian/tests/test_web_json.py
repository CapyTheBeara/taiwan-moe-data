"""
test_web_json.py — the JavaScript decoder must agree with the Python encoder.

The document is only useful if `kautian/web/kautian.mjs` reproduces the dataset
exactly, so these tests run the real decoder under node and compare every value
against the database. A pure-Python check would prove nothing here: the whole
risk of the format lives in the port.
"""

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from kautian.opt import container, webjson
from kautian.tests.test_optimized import write_db

REAL_DB = REPO_ROOT / "kautian" / "kautian.db"
DECODER = REPO_ROOT / "kautian" / "web" / "kautian.mjs"
NODE = shutil.which("node")

DRIVER = """
import { readFileSync, writeFileSync } from "node:fs";
import { decode } from "%s";
const document = JSON.parse(readFileSync(process.argv[2], "utf8"));
writeFileSync(process.argv[3], JSON.stringify(decode(document)));
"""


def expected_rows(schema, data):
    """The dataset as row objects — what the decoder has to reproduce."""
    return {
        entry["name"]: [
            dict(zip([name for name, _ in entry["columns"]], values))
            for values in zip(*[data[entry["name"]][name] for name, _ in entry["columns"]])
        ]
        for entry in schema
    }


def decode_with_node(document, workspace):
    driver = workspace / "driver.mjs"
    driver.write_text(DRIVER % DECODER.as_uri())
    source = workspace / "document.json"
    result = workspace / "rows.json"
    source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    subprocess.run(
        [NODE, "--max-old-space-size=4096", str(driver), str(source), str(result)],
        check=True,
        capture_output=True,
    )
    return json.loads(result.read_text(encoding="utf-8"))


@unittest.skipUnless(NODE, "node is not available")
class TestWebDocument(unittest.TestCase):
    def roundtrip(self, rows):
        workspace = Path(tempfile.mkdtemp())
        schema, data, header = container.read_database(write_db(workspace / "source.db", rows))
        document = webjson.to_document(schema, data, header)
        return expected_rows(schema, data), decode_with_node(document, workspace)

    def test_a_synthetic_database_decodes_to_the_same_rows(self):
        expected, decoded = self.roundtrip(
            {
                "詞目": [
                    (1, "主詞目", "一", "tsi̍t", "數詞、量詞", "1(1)"),
                    (2, "主詞目", "一蕊花", "tsi̍t-luí-hue", None, "2(1)"),
                    (3, "臺華共同詞", "清楚", None, "", None),
                ],
                "義項": [(1, 1, "數詞", "數目。"), (1, 2, None, "全部的。"), (2, 3, "名詞", "一朵花。")],
                "例句": [
                    (1, 1, 1, "一蕊花", "tsi̍t-luí-hue", "一朵花", "1-1-1"),
                    (1, 1, 2, "一二三", "It-jī-sann", "一二三", "1-1-2"),
                    (1, 2, 1, "規身軀", "kui-sin-khu", "全身", "1-2-1"),
                ],
                "義項tuì義項近義": [(1, "一", "數目。", 3, "一蕊花", "一朵花。")],
                "羅馬字清單": [("tsi̍t", "詞目,例句"), ("it", "名,姓")],
                "異用字": [(1, "蜀", "壹")],
            }
        )
        self.assertEqual(decoded, expected)

    def test_a_capitalised_reading_survives(self):
        expected, decoded = self.roundtrip(
            {
                "詞目": [(1, "主詞目", "一", "tsi̍t", None, "1(1)")],
                "義項": [(1, 1, None, "數目。")],
                "例句": [(1, 1, 1, "一二三", "It-jī-sann.", "一二三", "1-1-1")],
            }
        )
        self.assertEqual(decoded["例句"][0]["羅馬字"], "It-jī-sann.")
        self.assertEqual(decoded, expected)

    def test_a_reading_the_model_cannot_align_rides_as_a_literal(self):
        expected, decoded = self.roundtrip(
            {
                "詞目": [(1, "主詞目", "一蕊花", "tsi̍t-luí", None, "1(1)")],
                "名": [("一蕊花", "tsi̍t-luí", 1, "女")],
            }
        )
        self.assertEqual(decoded["名"][0]["羅馬字"], "tsi̍t-luí")
        self.assertEqual(decoded, expected)

    def test_a_row_that_violates_a_derived_rule_still_survives(self):
        _, decoded = self.roundtrip(
            {"詞目": [(1, "主詞目", "一", "tsi̍t", None, "surprise(9)")], "異用字": [(1, "蜀", "壹")]}
        )
        self.assertEqual(decoded["異用字"][0]["漢字"], "蜀")
        self.assertEqual(decoded["詞目"][0]["羅馬字音檔檔名"], "surprise(9)")

    def test_a_null_is_not_confused_with_an_empty_string(self):
        _, decoded = self.roundtrip({"詞目": [(1, "主詞目", "一", None, "", "1(1)")]})
        self.assertIsNone(decoded["詞目"][0]["羅馬字"])
        self.assertEqual(decoded["詞目"][0]["分類"], "")

    def test_an_empty_database_decodes_to_empty_tables(self):
        expected, decoded = self.roundtrip({})
        self.assertEqual(decoded, expected)
        self.assertEqual(decoded["詞目"], [])


@unittest.skipUnless(NODE and REAL_DB.exists(), "node or kautian.db is not available")
class TestWebDocumentAgainstTheRealDatabase(unittest.TestCase):
    def test_every_value_survives_the_javascript_decoder(self):
        schema, data, header = container.read_database(REAL_DB)
        document = webjson.to_document(schema, data, header)
        with tempfile.TemporaryDirectory() as workspace:
            decoded = decode_with_node(document, Path(workspace))
        expected = expected_rows(schema, data)
        self.assertEqual(sorted(decoded), sorted(expected))
        for table in expected:
            self.assertEqual(decoded[table], expected[table], f"{table} does not match")


if __name__ == "__main__":
    unittest.main()
