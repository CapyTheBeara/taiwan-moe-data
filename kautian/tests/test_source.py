import tempfile
import unittest
from pathlib import Path

from kautian.detail import source
from support import build_db


class TestRead(unittest.TestCase):
    def read(self, rows):
        path = Path(tempfile.mkdtemp()) / "synthetic.db"
        build_db(path, rows)
        return source.read(path)

    def test_sense_owner_maps_義項id_to_its_headword(self):
        _, sense_owner, _, _ = self.read(
            {
                "詞目": [(3, "詞", "一刀兩斷", "it-to", "交際應酬", "3(1)")],
                "義項": [(3, 8, "熟語", "斷絕關係。")],
            }
        )
        self.assertEqual(sense_owner, {8: 3})

    def test_max_id_comes_from_詞目_not_the_row_count(self):
        _, _, _, max_id = self.read({"詞目": [(1, "詞", "一", "it", "", ""), (30284, "詞", "尾", "bué", "", "")]})
        self.assertEqual(max_id, 30284)

    def test_an_empty_分類_is_not_a_category(self):
        _, _, categories, _ = self.read(
            {"詞目": [(1, "詞", "一", "it", "", ""), (2, "詞", "二", "jī", "交際應酬", "")]}
        )
        self.assertEqual(categories, {2: "交際應酬"})

    def test_every_table_is_read(self):
        tables, _, _, _ = self.read({"詞目": [(1, "詞", "一", "it", "", "")]})
        self.assertEqual(set(tables), set(source.TABLES))


if __name__ == "__main__":
    unittest.main()
