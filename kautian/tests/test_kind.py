import unittest

from kautian.kind import records


class TestClassify(unittest.TestCase):
    def test_a_non_entryless_label_is_full(self):
        self.assertEqual(records.classify("主詞目", False, False), records.FULL)

    def test_no_label_is_full(self):
        self.assertEqual(records.classify(None, False, False), records.FULL)

    def test_bound_label_live_in_concised_is_bound(self):
        self.assertEqual(records.classify("單字不成詞者", True, False), records.BOUND)

    def test_relation_only_label_live_in_concised_is_full(self):
        self.assertEqual(
            records.classify("近反義詞不單列詞目者", True, False), records.FULL
        )

    def test_mandarin_shared_label_live_in_concised_is_full(self):
        self.assertEqual(records.classify("臺華共同詞", True, False), records.FULL)

    def test_entryless_dead_in_concised_live_in_relations_is_named(self):
        self.assertEqual(
            records.classify("近反義詞不單列詞目者", False, True), records.NAMED
        )

    def test_entryless_dead_in_both_is_none(self):
        self.assertEqual(records.classify("單字不成詞者", False, False), records.NONE)

    def test_no_label_is_full_even_when_dead_in_both(self):
        self.assertEqual(records.classify(None, False, False), records.FULL)


class TestBuild(unittest.TestCase):
    def test_one_id_per_branch(self):
        types = {
            0: "主詞目",
            1: "單字不成詞者",
            2: "近反義詞不單列詞目者",
            3: "臺華共同詞",
        }
        concised_live = {1, 3}
        relations_live = {2}
        blob = records.build(types, concised_live, relations_live, 3)
        self.assertEqual(
            list(blob), [records.FULL, records.BOUND, records.NAMED, records.FULL]
        )

    def test_an_id_absent_from_types_defaults_to_full(self):
        blob = records.build({}, set(), set(), 2)
        self.assertEqual(list(blob), [records.FULL, records.FULL, records.FULL])

    def test_an_entryless_id_dead_in_both_containers_is_none(self):
        blob = records.build({0: "單字不成詞者"}, set(), set(), 0)
        self.assertEqual(list(blob), [records.NONE])

    def test_emitted_length_is_max_id_plus_one(self):
        blob = records.build({}, set(), set(), 30284)
        self.assertEqual(len(blob), 30285)

    def test_tally_matches_a_recount_of_the_emitted_bytes(self):
        types = {
            0: "主詞目",
            1: "單字不成詞者",
            2: "近反義詞不單列詞目者",
            3: "臺華共同詞",
            4: "單字不成詞者",
        }
        concised_live = {1, 3}
        relations_live = {2}
        blob = records.build(types, concised_live, relations_live, 4)
        tally = {kind: 0 for kind in records.KINDS}
        for byte in blob:
            tally[records.KINDS[byte]] += 1
        self.assertEqual(
            tally, {"full": 2, "bound": 1, "named": 1, "none": 1}
        )


if __name__ == "__main__":
    unittest.main()
