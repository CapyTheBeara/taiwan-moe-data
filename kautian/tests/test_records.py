import unittest

from kautian.detail import records
from support import accents


class TestGroup(unittest.TestCase):
    def test_keeps_only_the_listed_columns(self):
        rows = [{"詞目id": 1, "漢字": "一", "異用字": "蜀", "unused": "x"}]
        grouped = records.group(rows, records.BY_WORD, ("漢字", "異用字"), {})
        self.assertEqual(grouped, {1: [{"漢字": "一", "異用字": "蜀"}]})

    def test_omits_empty_values(self):
        rows = [{"詞目id": 1, "義項id": 1, "詞性": None, "解說": ""}]
        grouped = records.group(rows, records.BY_WORD, ("義項id", "詞性", "解說"), {})
        self.assertEqual(grouped, {1: [{"義項id": 1}]})

    def test_sense_keyed_rows_land_on_their_owning_headword(self):
        rows = [{"義項id": 8, "對應義項id": 9, "對應詞目漢字": "全"}]
        grouped = records.group(rows, records.BY_SENSE, ("義項id", "對應詞目id"), {8: 3, 9: 4})
        self.assertEqual(grouped, {3: [{"義項id": 8, "對應詞目id": 4}]})

    def test_drops_rows_whose_sense_has_no_owner(self):
        rows = [{"義項id": 99, "對應義項id": 9}]
        grouped = records.group(rows, records.BY_SENSE, ("義項id",), {8: 3})
        self.assertEqual(grouped, {})

    def test_leaves_an_existing_對應詞目id_alone(self):
        rows = [{"義項id": 8, "對應詞目id": 7}]
        grouped = records.group(rows, records.BY_SENSE, ("義項id", "對應詞目id"), {8: 3})
        self.assertEqual(grouped, {3: [{"義項id": 8, "對應詞目id": 7}]})


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.tables = {table: [] for _, table, _, _ in records.GROUPS}

    def build(self, categories=None):
        sense_owner = {row["義項id"]: row["詞目id"] for row in self.tables["義項"]}
        return records.build(self.tables, sense_owner, categories or {})

    def test_a_headword_with_nothing_gets_no_record(self):
        self.assertEqual(self.build({1: "交際應酬"}), {})

    def test_category_rides_along_with_real_content(self):
        self.tables["義項"] = [{"詞目id": 1, "義項id": 1, "詞性": "數詞", "解說": "數目。"}]
        built = self.build({1: "交際應酬"})
        self.assertEqual(built[1]["category"], "交際應酬")
        self.assertEqual(built[1]["senses"], [{"義項id": 1, "詞性": "數詞", "解說": "數目。"}])

    def test_an_absent_group_is_absent_not_empty(self):
        self.tables["異用字"] = [{"詞目id": 1, "漢字": "一", "異用字": "蜀"}]
        self.assertEqual(set(self.build()[1]), {"variants"})

    def test_all_ten_腔_columns_survive(self):
        columns = ("詞目id", "漢字") + records.ACCENT_COLUMNS
        self.tables["語音差異"] = [dict(zip(columns, accents(1, "八", "pueh")))]
        self.assertEqual(len(self.build()[1]["accents"][0]), 11)


if __name__ == "__main__":
    unittest.main()
