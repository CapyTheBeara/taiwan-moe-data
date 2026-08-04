import unittest

from concised.detail import records
from support import kept


class TestEntry(unittest.TestCase):
    def test_a_column_padded_with_spaces_is_absent(self):
        shaped = records.entry({"字詞名": "人品", "變體類型": "  ", "變體漢語拼音": " "})
        self.assertEqual(shaped, {"字詞名": "人品"})

    def test_a_missing_or_null_column_is_absent(self):
        shaped = records.entry({"字詞名": "人品", "釋義": None})
        self.assertEqual(shaped, {"字詞名": "人品"})

    def test_columns_outside_the_kept_set_are_dropped(self):
        shaped = records.entry({"字詞名": "人品", "部首字": "人 ", "總筆畫數": "2"})
        self.assertEqual(shaped, {"字詞名": "人品"})

    def test_only_the_ragged_edges_are_trimmed_never_the_body(self):
        blob = "1.拉起、抽出。[例]拔刀、拔草　◎    \n2.吸出。[例]拔毒    \n3.除去。[例]拔禍根\xa0 "
        shaped = records.entry({"字詞名": "拔", "釋義": blob})
        self.assertEqual(shaped["釋義"], blob.rstrip())
        self.assertIn("    \n2.吸出。", shaped["釋義"])


class TestBuild(unittest.TestCase):
    def test_a_headword_the_concised_does_not_cover_gets_no_record(self):
        built = records.build([(17803, "山泉水")], {"人品": [{"字詞名": "人品", "字詞號": "1"}]})
        self.assertEqual(built, {})

    def test_a_matched_headword_is_keyed_by_its_kautian_id(self):
        entries = {"人品": [{"字詞名": "人品", "字詞號": "520100002", "釋義": "人的品格。"}]}
        built = records.build([(17743, "人品")], entries)
        self.assertEqual(
            built,
            {17743: {"concised": [kept("人品", 字詞號="520100002", 釋義="人的品格。")]}},
        )

    def test_a_多音_headword_keeps_every_reading_in_the_order_given(self):
        entries = {
            "扒": [
                {"字詞名": "扒", "字詞號": "0023", "漢語拼音": "bā"},
                {"字詞名": "扒", "字詞號": "0297", "漢語拼音": "pá"},
            ]
        }
        built = records.build([(1, "扒")], entries)
        self.assertEqual([row["漢語拼音"] for row in built[1]["concised"]], ["bā", "pá"])

    def test_two_headwords_sharing_a_hanji_both_get_the_record(self):
        entries = {"人品": [{"字詞名": "人品", "字詞號": "1"}]}
        built = records.build([(17743, "人品"), (17744, "人品")], entries)
        self.assertEqual(list(built), [17743, 17744])

    def test_a_row_with_nothing_left_after_shaping_promotes_no_record(self):
        built = records.build([(1, "人品")], {"人品": [{"字詞名": "", "釋義": "  "}]})
        self.assertEqual(built, {})

    def test_the_only_group_key_is_concised(self):
        built = records.build([(1, "人品")], {"人品": [{"字詞名": "人品"}]})
        self.assertEqual(list(built[1]), ["concised"])


if __name__ == "__main__":
    unittest.main()
