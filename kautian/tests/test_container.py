import json
import struct
import tempfile
import unittest
from pathlib import Path

from kautian.detail import container

PROVENANCE = {"dbSha256": "abc", "generatorCommit": "def", "buildDate": "2026-08-03"}


class TestEncode(unittest.TestCase):
    def test_is_compact_sorted_and_not_ascii_escaped(self):
        self.assertEqual(container.encode({"b": 1, "a": "一"}), '{"a":"一","b":1}'.encode())

    def test_measures_utf8_bytes_not_characters(self):
        blob = container.encode({"a": "𪜶"})
        self.assertEqual(len(blob), 12)
        self.assertEqual(len(blob.decode("utf-8")), 9)


class TestWrite(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())

    def write(self, records, max_id):
        return container.write(records, max_id, self.out, PROVENANCE)

    def lengths(self):
        raw = (self.out / "detail.idx").read_bytes()
        return list(struct.unpack(f"<{len(raw) // 2}H", raw))

    def test_index_spans_the_whole_id_space(self):
        self.write({2: {"a": 1}}, 4)
        self.assertEqual(len(self.lengths()), 5)

    def test_a_missing_id_gets_length_zero_and_no_bytes(self):
        self.write({2: {"a": 1}}, 4)
        self.assertEqual(self.lengths(), [0, 0, 7, 0, 0])
        self.assertEqual((self.out / "detail.bin").read_bytes(), container.HEADER + b'{"a":1}')

    def test_the_header_holds_a_NUL_so_hosts_sniff_the_file_as_binary(self):
        self.write({1: {"a": "一"}}, 1)
        self.assertIn(b"\x00", (self.out / "detail.bin").read_bytes()[: len(container.HEADER)])

    def test_containerBytes_counts_the_header_but_the_index_does_not(self):
        meta = self.write({1: {"a": 1}}, 1)
        self.assertEqual(meta["headerBytes"], len(container.HEADER))
        self.assertEqual(meta["containerBytes"], len(container.HEADER) + 7)
        self.assertEqual(meta["containerBytes"], (self.out / "detail.bin").stat().st_size)
        self.assertEqual(sum(self.lengths()), 7)

    def test_offsets_slice_each_record_back_out(self):
        records = {1: {"a": "一"}, 2: {"b": "𪜶"}, 3: {"c": "x"}}
        meta = self.write(records, 3)
        blob = (self.out / "detail.bin").read_bytes()
        lengths = self.lengths()
        start = meta["headerBytes"]
        for word_id in range(4):
            end = start + lengths[word_id]
            if lengths[word_id]:
                self.assertEqual(json.loads(blob[start:end].decode("utf-8")), records[word_id])
            start = end
        self.assertEqual(meta["containerBytes"], len(blob))

    def test_meta_counts_and_sentinel(self):
        meta = self.write({1: {"a": "一" * 20}, 2: {"b": 1}}, 2)
        blob = (self.out / "detail.bin").read_bytes()
        self.assertEqual(meta["liveIds"], 2)
        self.assertEqual(meta["maxId"], 2)
        self.assertEqual(meta["dbSha256"], "abc")
        self.assertEqual(meta["sentinel"]["id"], 1)
        head = meta["headerBytes"]
        self.assertEqual(bytes.fromhex(meta["sentinel"]["head"]), blob[head : head + 32])

    def test_a_record_over_the_uint16_ceiling_is_refused(self):
        with self.assertRaises(ValueError):
            self.write({1: {"a": "x" * 70000}}, 1)


if __name__ == "__main__":
    unittest.main()
