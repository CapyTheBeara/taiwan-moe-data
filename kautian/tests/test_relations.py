import tempfile
import unittest
from pathlib import Path

from kautian.relations import records, source
from support import build_db


def headword(word_id, hanji, word_type="主詞目"):
    return (word_id, word_type, hanji, "tâi-gí", "", "")


class TestRead(unittest.TestCase):
    def read(self, rows):
        path = Path(tempfile.mkdtemp()) / "synthetic.db"
        build_db(path, rows)
        return source.read(path)

    def test_a_詞目tuì詞目_edge_is_read_as_the_named_end(self):
        edges, _, _ = self.read(
            {
                "詞目": [headword(3042, "囥歲"), headword(17707, "𠢕囥歲", "近反義詞不單列詞目者")],
                "詞目tuì詞目近義": [(3042, "囥歲", 17707, "𠢕囥歲")],
            }
        )
        self.assertEqual(edges, [("synonymOf", 3042, "囥歲", 17707)])

    def test_a_義項_keyed_near_end_resolves_to_its_headword(self):
        edges, _, _ = self.read(
            {
                "詞目": [headword(3042, "囥歲"), headword(17707, "𠢕囥歲", "近反義詞不單列詞目者")],
                "義項": [(3042, 88, "動", "囥歲。")],
                "義項tuì詞目近義": [(88, "囥歲", "囥歲。", 17707, "𠢕囥歲")],
            }
        )
        self.assertEqual(edges, [("synonymOf", 3042, "囥歲", 17707)])

    def test_both_ends_of_a_義項tuì義項_edge_resolve_to_headwords(self):
        edges, _, _ = self.read(
            {
                "詞目": [headword(3042, "囥歲"), headword(17707, "𠢕囥歲", "近反義詞不單列詞目者")],
                "義項": [(3042, 88, "動", "囥歲。"), (17707, 99, "動", "gâu khǹg-hè.")],
                "義項tuì義項近義": [(88, "囥歲", "囥歲。", 99, "𠢕囥歲", "gâu khǹg-hè.")],
            }
        )
        self.assertEqual(edges, [("synonymOf", 3042, "囥歲", 17707)])

    def test_an_edge_whose_義項id_has_no_headword_is_skipped(self):
        edges, _, _ = self.read(
            {
                "詞目": [headword(17707, "𠢕囥歲", "近反義詞不單列詞目者")],
                "義項tuì詞目近義": [(88, "囥歲", "囥歲。", 17707, "𠢕囥歲")],
            }
        )
        self.assertEqual(edges, [])

    def test_only_the_entryless_headword_types_are_eligible(self):
        _, eligible, _ = self.read(
            {
                "詞目": [
                    headword(1, "一刀兩斷"),
                    headword(3522, "事", "單字不成詞者"),
                    headword(17743, "人品", "臺華共同詞"),
                    headword(20000, "刁", "近反義詞不單列詞目者"),
                    headword(25000, "附錄詞", "附錄"),
                ]
            }
        )
        self.assertEqual(eligible, {3522, 17743, 20000})

    def test_max_id_spans_the_whole_kautian_id_space(self):
        _, _, max_id = self.read(
            {"詞目": [headword(1, "一"), headword(30284, "尾")]}
        )
        self.assertEqual(max_id, 30284)


class TestBuild(unittest.TestCase):
    def test_a_record_names_the_headword_that_names_it(self):
        built = records.build([("synonymOf", 3042, "囥歲", 17707)], {17707})
        self.assertEqual(
            built, {17707: {"synonymOf": [{"詞目id": 3042, "漢字": "囥歲"}]}}
        )

    def test_a_headword_that_is_not_entryless_gets_no_record(self):
        self.assertEqual(records.build([("synonymOf", 3042, "囥歲", 1)], {17707}), {})

    def test_the_same_pair_through_several_義項_is_one_entry(self):
        built = records.build(
            [("synonymOf", 3042, "囥歲", 17707), ("synonymOf", 3042, "囥歲", 17707)],
            {17707},
        )
        self.assertEqual(built[17707]["synonymOf"], [{"詞目id": 3042, "漢字": "囥歲"}])

    def test_a_headword_that_names_itself_is_dropped(self):
        self.assertEqual(records.build([("synonymOf", 17707, "𠢕囥歲", 17707)], {17707}), {})

    def test_an_edge_with_no_漢字_to_show_is_dropped(self):
        self.assertEqual(records.build([("synonymOf", 3042, "", 17707)], {17707}), {})

    def test_both_groups_land_in_one_record_synonyms_first(self):
        built = records.build(
            [("antonymOf", 4858, "帝", 14758), ("synonymOf", 3042, "囥歲", 14758)],
            {14758},
        )
        self.assertEqual(list(built[14758]), ["synonymOf", "antonymOf"])

    def test_names_are_ordered_by_詞目id_not_by_edge_order(self):
        built = records.build(
            [("synonymOf", 900, "後", 17707), ("synonymOf", 100, "先", 17707)],
            {17707},
        )
        self.assertEqual([row["詞目id"] for row in built[17707]["synonymOf"]], [100, 900])


if __name__ == "__main__":
    unittest.main()
