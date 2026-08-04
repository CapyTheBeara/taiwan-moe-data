import json
import struct
import tempfile
import unittest
from pathlib import Path

from concised.detail import records
from kautian.detail import container

MAGIC = container.magic("CNDETAIL1")
PROVENANCE = {"concisedDbSha256": "abc", "kautianDbSha256": "def", "buildDate": "2026-08-04"}


class TestWrite(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())

    def write(self, headwords, entries, max_id):
        built = records.build(headwords, entries)
        return built, container.write(built, max_id, self.out, PROVENANCE, MAGIC)

    def lengths(self):
        raw = (self.out / "detail.idx").read_bytes()
        return list(struct.unpack(f"<{len(raw) // 2}H", raw))

    def test_the_magic_differs_from_kautian_but_keeps_the_NUL_padding(self):
        self.assertNotEqual(MAGIC, container.HEADER)
        self.assertEqual(len(MAGIC), len(container.HEADER))
        self.assertIn(b"\x00", MAGIC)

    def test_the_index_spans_the_kautian_id_space_so_lookups_share_an_id(self):
        self.write([(2, "人品")], {"人品": [{"字詞名": "人品"}]}, 4)
        self.assertEqual(len(self.lengths()), 5)
        self.assertEqual([length > 0 for length in self.lengths()], [False, False, True, False, False])

    def test_an_unmatched_headword_reads_back_as_length_zero(self):
        _, meta = self.write([(1, "山泉水"), (2, "人品")], {"人品": [{"字詞名": "人品"}]}, 2)
        self.assertEqual(self.lengths()[1], 0)
        self.assertEqual(meta["liveIds"], 1)

    def test_offsets_slice_each_record_back_out(self):
        entries = {"人品": [{"字詞名": "人品", "釋義": "人的品格。"}], "巴": [{"字詞名": "巴"}]}
        built, meta = self.write([(1, "人品"), (3, "巴")], entries, 3)
        blob = (self.out / "detail.bin").read_bytes()
        lengths = self.lengths()
        start = meta["headerBytes"]
        for word_id in range(4):
            end = start + lengths[word_id]
            if lengths[word_id]:
                self.assertEqual(json.loads(blob[start:end].decode("utf-8")), built[word_id])
            start = end
        self.assertEqual(meta["containerBytes"], len(blob))

    def test_meta_carries_both_source_digests(self):
        _, meta = self.write([(1, "人品")], {"人品": [{"字詞名": "人品"}]}, 1)
        self.assertEqual(meta["concisedDbSha256"], "abc")
        self.assertEqual(meta["kautianDbSha256"], "def")

    def test_the_sentinel_head_is_the_first_record_in_the_container(self):
        entries = {"人品": [{"字詞名": "人品", "釋義": "人的品格，可以評價一個人。"}]}
        _, meta = self.write([(2, "人品")], entries, 2)
        blob = (self.out / "detail.bin").read_bytes()
        self.assertEqual(meta["sentinel"]["id"], 2)
        head = meta["headerBytes"]
        self.assertEqual(bytes.fromhex(meta["sentinel"]["head"]), blob[head : head + 32])


if __name__ == "__main__":
    unittest.main()
