import tempfile
import unittest

from concised.detail import source
from support import build_dbs, entry, headword


ANY_HEADWORD = [headword(1, "尾", "主詞目")]
"""A 詞目 row for the tests that only care about the Concised side.

Reading the kautian coverage set spans the whole 詞目 table, so an empty one is
not a state a real database is ever in.
"""


class TestRead(unittest.TestCase):
    def read(self, headwords, entries, kautian_rows=None):
        kautian_db, concised_db = build_dbs(
            tempfile.mkdtemp(), headwords, entries, kautian_rows
        )
        return source.read(kautian_db, concised_db)

    def test_only_the_entryless_headword_types_are_read(self):
        headwords, _, _ = self.read(
            [
                headword(1, "一刀兩斷", "主詞目"),
                headword(3522, "事", "單字不成詞者"),
                headword(17743, "人品"),
                headword(20000, "刁", "近反義詞不單列詞目者"),
            ],
            [],
        )
        self.assertEqual(headwords, [(3522, "事"), (17743, "人品")])

    def test_a_headword_kautian_already_covers_is_dropped(self):
        headwords, _, _ = self.read(
            [headword(3522, "事", "單字不成詞者"), headword(17743, "人品")],
            [],
            {"異用字": [(3522, "事", "代")]},
        )
        self.assertEqual(headwords, [(17743, "人品")])

    def test_the_join_key_drops_the_替_marker(self):
        headwords, _, _ = self.read([headword(1, "乜【替】")], [])
        self.assertEqual(headwords, [(1, "乜")])

    def test_max_id_spans_the_whole_kautian_id_space_not_just_the_entryless_types(self):
        _, _, max_id = self.read(
            [headword(17743, "人品"), headword(30284, "尾", "主詞目")],
            [],
        )
        self.assertEqual(max_id, 30284)

    def test_entries_are_keyed_by_字詞名(self):
        _, entries, _ = self.read(ANY_HEADWORD, [entry("人品", 釋義="人的品格。")])
        self.assertEqual(list(entries), ["人品"])
        self.assertEqual(entries["人品"][0]["釋義"], "人的品格。")

    def test_a_多音_name_keeps_every_row_ordered_by_多音排序(self):
        _, entries, _ = self.read(
            ANY_HEADWORD,
            [
                entry("扒", number="0297", order="2", 漢語拼音="pá"),
                entry("扒", number="0023", order="1", 漢語拼音="bā"),
            ],
        )
        self.assertEqual([row["漢語拼音"] for row in entries["扒"]], ["bā", "pá"])

    def test_多音排序_orders_numerically_not_as_text(self):
        _, entries, _ = self.read(
            ANY_HEADWORD,
            [
                entry("扒", number="a", order="10", 漢語拼音="tenth"),
                entry("扒", number="b", order="9", 漢語拼音="ninth"),
            ],
        )
        self.assertEqual([row["漢語拼音"] for row in entries["扒"]], ["ninth", "tenth"])


if __name__ == "__main__":
    unittest.main()
