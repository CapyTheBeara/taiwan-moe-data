"""
test_web_json.py — the Concised document must decode with kautian's decoder, and
must hold exactly what the container holds.

Two claims, and neither is provable in Python alone:

- `kautian/web/kautian.mjs` reads this document *unmodified*. The document has
  no 詞目 and no 義項, which the decoder fills in for its derived rules, so the
  tests run the real decoder under node rather than trusting that reading.
- the document and `concised/v3/` carry the same entries. Both come from
  `records.build`, so the test asserts the round trip back to it: drop the null
  keys off a decoded row and the container's record must reappear.
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

import support

from concised.detail import records, source
from concised.web import webjson

KAUTIAN_DB = REPO_ROOT / "kautian" / "kautian.db"
CONCISED_DB = REPO_ROOT / "concised" / "concised.db"
DECODER = REPO_ROOT / "kautian" / "web" / "kautian.mjs"
NODE = shutil.which("node")

DRIVER = """
import { readFileSync, writeFileSync } from "node:fs";
import { decode } from "%s";
const document = JSON.parse(readFileSync(process.argv[2], "utf8"));
writeFileSync(process.argv[3], JSON.stringify(decode(document)));
"""

# `only` makes the decoder fill in the tables its derived rules join against.
# Neither is in this document, so this is the path that would break first.
ONLY_DRIVER = """
import { readFileSync, writeFileSync } from "node:fs";
import { decodeColumns, rows } from "%s";
const document = JSON.parse(readFileSync(process.argv[2], "utf8"));
const columns = decodeColumns(document, { only: ["簡編"] });
const tables = {};
for (const name of Object.keys(columns)) tables[name] = rows(columns[name]);
writeFileSync(process.argv[3], JSON.stringify(tables));
"""


def decode_with_node(document, workspace, driver_source=DRIVER):
    driver = workspace / "driver.mjs"
    driver.write_text(driver_source % DECODER.as_uri())
    source_path = workspace / "document.json"
    result = workspace / "rows.json"
    source_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    subprocess.run(
        [NODE, "--max-old-space-size=4096", str(driver), str(source_path), str(result)],
        check=True,
        capture_output=True,
    )
    return json.loads(result.read_text(encoding="utf-8"))


def expected_rows(built):
    """The records as flat rows — what the decoder has to reproduce."""
    out = []
    for word_id, record in sorted(built.items()):
        for entry in record["concised"]:
            row = {webjson.ID_COLUMN: word_id}
            row.update({column: entry.get(column) for column in records.COLUMNS})
            out.append(row)
    return out


def to_records(decoded):
    """Rebuild the container's records from decoded rows: drop the null columns."""
    out = {}
    for row in decoded:
        entry = {column: value for column, value in row.items() if column != webjson.ID_COLUMN and value is not None}
        out.setdefault(row[webjson.ID_COLUMN], {"concised": []})["concised"].append(entry)
    return out


@unittest.skipUnless(NODE, "node is not available")
class TestConcisedWebDocument(unittest.TestCase):
    def roundtrip(self, headwords, entries, kautian_rows=None):
        workspace = Path(tempfile.mkdtemp())
        kautian_db, concised_db = support.build_dbs(workspace, headwords, entries, kautian_rows)
        built = records.build(*source.read(kautian_db, concised_db)[:2])
        document = webjson.to_document(built)
        return built, document, decode_with_node(document, workspace)

    def test_a_synthetic_pair_of_databases_decodes_to_the_same_rows(self):
        built, _document, decoded = self.roundtrip(
            [support.headword(1, "清楚"), support.headword(2, "事")],
            [
                support.entry("清楚", 釋義="明白。", 相似詞="明白"),
                support.entry("事", 釋義="事情。"),
            ],
        )
        self.assertEqual(decoded[webjson.TABLE], expected_rows(built))
        self.assertEqual(to_records(decoded[webjson.TABLE]), built)

    def test_the_document_holds_only_the_table(self):
        _built, document, decoded = self.roundtrip(
            [support.headword(1, "清楚")], [support.entry("清楚", 釋義="明白。")]
        )
        self.assertEqual([entry["name"] for entry in document["tables"]], [webjson.TABLE])
        self.assertEqual(sorted(decoded), [webjson.TABLE])

    def test_decoding_with_only_works_without_詞目_and_義項(self):
        """The decoder fills in the tables its rules join against; neither is here."""
        built, document, _decoded = self.roundtrip(
            [support.headword(1, "清楚")], [support.entry("清楚", 釋義="明白。")]
        )
        with tempfile.TemporaryDirectory() as workspace:
            decoded = decode_with_node(document, Path(workspace), ONLY_DRIVER)
        self.assertEqual(sorted(decoded), [webjson.TABLE])
        self.assertEqual(decoded[webjson.TABLE], expected_rows(built))

    def test_a_dropped_column_reads_back_as_null_not_an_empty_string(self):
        _built, _document, decoded = self.roundtrip(
            [support.headword(1, "清楚")], [support.entry("清楚", 釋義="明白。")]
        )
        row = decoded[webjson.TABLE][0]
        self.assertIsNone(row["相似詞"])
        self.assertEqual(row["釋義"], "明白。")
        self.assertEqual(to_records(decoded[webjson.TABLE])[1]["concised"][0].get("相似詞"), None)

    def test_a_polyphone_keeps_every_reading_in_order(self):
        built, _document, decoded = self.roundtrip(
            [support.headword(1, "重")],
            [
                support.entry("重", number="2", order="1", 釋義="分量大。"),
                support.entry("重", number="1", order="0", 釋義="再一次。"),
            ],
        )
        rows = decoded[webjson.TABLE]
        self.assertEqual([row["釋義"] for row in rows], ["再一次。", "分量大。"])
        self.assertEqual(rows, expected_rows(built))

    def test_a_headword_the_concised_dictionary_misses_earns_no_row(self):
        _built, _document, decoded = self.roundtrip(
            [support.headword(1, "清楚"), support.headword(2, "無此詞")],
            [support.entry("清楚", 釋義="明白。")],
        )
        self.assertEqual([row[webjson.ID_COLUMN] for row in decoded[webjson.TABLE]], [1])

    def test_a_headword_kautian_already_defines_earns_no_row(self):
        """A kautian record carrying 義項 shadows this container, and this document."""
        _built, _document, decoded = self.roundtrip(
            [support.headword(1, "清楚"), support.headword(2, "事")],
            [support.entry("清楚", 釋義="明白。"), support.entry("事", 釋義="事情。")],
            kautian_rows={"義項": [(2, 1, "名詞", "代誌。")]},
        )
        self.assertEqual([row[webjson.ID_COLUMN] for row in decoded[webjson.TABLE]], [1])

    def test_an_empty_result_decodes_to_an_empty_table(self):
        _built, document, decoded = self.roundtrip([support.headword(1, "無此詞")], [])
        self.assertEqual(document["tables"][0]["rows"], 0)
        self.assertEqual(decoded[webjson.TABLE], [])


@unittest.skipUnless(
    NODE and KAUTIAN_DB.exists() and CONCISED_DB.exists(), "node or a database is not available"
)
class TestAgainstTheRealDatabases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = records.build(*source.read(KAUTIAN_DB, CONCISED_DB)[:2])
        cls.document = webjson.to_document(cls.built)
        with tempfile.TemporaryDirectory() as workspace:
            cls.decoded = decode_with_node(cls.document, Path(workspace))[webjson.TABLE]

    def test_every_value_survives_the_javascript_decoder(self):
        self.assertEqual(self.decoded, expected_rows(self.built))

    def test_the_decoded_document_rebuilds_the_container_records(self):
        """The claim the whole step rests on: same entries as concised/v3."""
        self.assertEqual(to_records(self.decoded), self.built)

    def test_every_value_keeps_its_storage_class(self):
        """`字詞號` has leading zeros: an id that came back as a number is a changed value."""
        compared = 0
        for want, got in zip(expected_rows(self.built), self.decoded):
            for column, value in want.items():
                self.assertIs(type(value), type(got[column]), f"{column} changed storage class")
                compared += 1
        self.assertEqual(compared, len(self.decoded) * len(webjson.DOCUMENT_COLUMNS))
        self.assertTrue(any(isinstance(row["字詞號"], str) for row in self.decoded))
