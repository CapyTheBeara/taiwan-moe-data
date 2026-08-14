import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from kautian.opt import codec, container, tables, tailo

REAL_DB = REPO_ROOT / "kautian" / "kautian.db"

FULL_SCHEMA = {
    "詞目": ('"詞目id" INTEGER, "詞目類型" TEXT, "漢字" TEXT, "羅馬字" TEXT, "分類" TEXT, "羅馬字音檔檔名" TEXT'),
    "義項": '"詞目id" INTEGER, "義項id" INTEGER, "詞性" TEXT, "解說" TEXT',
    "例句": (
        '"詞目id" INTEGER, "義項id" INTEGER, "例句順序" INTEGER, "漢字" TEXT, '
        '"羅馬字" TEXT, "華語" TEXT, "音檔檔名" TEXT'
    ),
    "又唸作": '"詞目id" INTEGER, "漢字" TEXT, "羅馬字" TEXT',
    "合音唸作": '"詞目id" INTEGER, "漢字" TEXT, "羅馬字" TEXT',
    "俗唸作": '"詞目id" INTEGER, "漢字" TEXT, "羅馬字" TEXT',
    "語音差異": '"詞目id" INTEGER, "漢字" TEXT, ' + ", ".join(f'"{name}" TEXT' for name in tables.ACCENTS),
    "詞彙比較": '"華語詞目id" INTEGER, "華語詞目" TEXT, "腔" TEXT, "漢字" TEXT, "羅馬字" TEXT',
    "名": '"漢字" TEXT, "羅馬字" TEXT, "建議順序" INTEGER, "類型" TEXT',
    "姓": '"漢字" TEXT, "羅馬字" TEXT, "建議順序" INTEGER, "類型" TEXT',
    "異用字": '"詞目id" INTEGER, "漢字" TEXT, "異用字" TEXT',
    "義項tuì義項近義": (
        '"義項id" INTEGER, "詞目漢字" TEXT, "解說" TEXT, "對應義項id" INTEGER, '
        '"對應詞目漢字" TEXT, "對應解說" TEXT'
    ),
    "義項tuì義項反義": (
        '"義項id" INTEGER, "詞目漢字" TEXT, "解說" TEXT, "對應義項id" INTEGER, '
        '"對應詞目漢字" TEXT, "對應解說" TEXT'
    ),
    "義項tuì詞目近義": '"義項id" INTEGER, "詞目漢字" TEXT, "解說" TEXT, "對應詞目id" INTEGER, "對應詞目漢字" TEXT',
    "義項tuì詞目反義": '"義項id" INTEGER, "詞目漢字" TEXT, "解說" TEXT, "對應詞目id" INTEGER, "對應詞目漢字" TEXT',
    "詞目tuì詞目近義": '"詞目id" INTEGER, "詞目漢字" TEXT, "對應詞目id" INTEGER, "對應詞目漢字" TEXT',
    "詞目tuì詞目反義": '"詞目id" INTEGER, "詞目漢字" TEXT, "對應詞目id" INTEGER, "對應詞目漢字" TEXT',
    "羅馬字清單": '"羅馬字" TEXT, "來源" TEXT',
    "漢字羅馬字對應": '"漢字" TEXT, "羅馬字" TEXT, "來源" TEXT',
}


def write_db(path, rows):
    """Build a database the way the original was built: one table per transaction.

    SQLite allocates b-tree pages in the order writes arrive, so this sequence is
    part of what byte-identity is asserted against.
    """
    connection = sqlite3.connect(path)
    connection.execute("pragma page_size=4096")
    for table, declaration in FULL_SCHEMA.items():
        connection.execute(f'create table "{table}" ({declaration})')
        table_rows = rows.get(table, [])
        if table_rows:
            marks = ", ".join("?" * len(table_rows[0]))
            connection.executemany(f'insert into "{table}" values ({marks})', table_rows)
        connection.commit()
    connection.close()
    return path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TestCodec(unittest.TestCase):
    def test_varints_survive_a_roundtrip(self):
        values = [0, 1, 127, 128, 16383, 16384, 999999]
        self.assertEqual(codec.decode_varints(codec.encode_varints(values), len(values)), values)

    def test_zigzag_carries_negative_values(self):
        values = [-99, -1, 0, 1, 99]
        self.assertEqual(codec.decode_zigzag(codec.encode_zigzag(values), len(values)), values)

    def test_deltas_survive_a_non_monotonic_column(self):
        values = [5, 5, 9, 2, 40]
        self.assertEqual(codec.decode_deltas(codec.encode_deltas(values), len(values)), values)

    def test_a_text_column_rejects_an_embedded_separator(self):
        with self.assertRaises(ValueError):
            codec.encode_texts(["fine", "not\nfine"])

    def test_masks_pack_eight_flags_to_a_byte(self):
        flags = [True, False, False, True, True, False, False, False, True]
        self.assertEqual(len(codec.encode_mask(flags)), 2)
        self.assertEqual(codec.decode_mask(codec.encode_mask(flags), len(flags)), flags)

    def test_sections_survive_empty_members(self):
        sections = [b"ab", b"", b"c", b""]
        self.assertEqual(codec.unpack_sections(codec.pack_sections(sections)), sections)


class TestTailo(unittest.TestCase):
    def test_render_inverts_tokenize_for_every_orthography(self):
        for reading in [
            "tsi̍t-luí-hue",
            "Lí kóng--kuè ê uē, it-tīng ài ē-kì--tit.",
            'Kóo-tsá sî-tāi, “Gio̍k-tsénn” kiò-tsò “Ta-pa-nî”.',
            "I 2003 nî ū lâi.",
            "Lán tsò tāi-tsì , li̍p-tiûnn tio̍h-ài kian-tīng.",
            "",
        ]:
            self.assertEqual(tailo.render(*tailo.tokenize(reading)), reading)

    def test_the_model_ranks_a_frequent_reading_first(self):
        model = tailo.build_model([("一", "tsi̍t"), ("一", "tsi̍t"), ("一", "it")])
        self.assertEqual(model["一"], ["tsi̍t", "it"])

    def test_the_model_breaks_ties_alphabetically(self):
        model = tailo.build_model([("二", "jī"), ("二", "lī")])
        self.assertEqual(model["二"], ["jī", "lī"])

    def test_a_reading_that_does_not_align_is_reported(self):
        self.assertTrue(tailo.aligns("一蕊花", "tsi̍t-luí-hue"))
        self.assertFalse(tailo.aligns("一蕊花", "tsi̍t-luí"))


class TestRoundtrip(unittest.TestCase):
    def roundtrip(self, rows):
        workspace = Path(tempfile.mkdtemp())
        source = write_db(workspace / "source.db", rows)
        blob = container.encode(source)
        manifest, columns = container.decode(blob)
        rebuilt = workspace / "rebuilt.db"
        container.rebuild(manifest, columns, rebuilt)
        return source, rebuilt, columns

    def test_a_synthetic_database_rebuilds_byte_for_byte(self):
        source, rebuilt, _ = self.roundtrip(
            {
                "詞目": [
                    (1, "主詞目", "一", "tsi̍t", "數詞、量詞", "1(1)"),
                    (2, "主詞目", "一蕊花", "tsi̍t-luí-hue", None, "2(1)"),
                    (3, "臺華共同詞", "清楚", None, None, None),
                ],
                "義項": [(1, 1, "數詞", "數目。"), (1, 2, None, "全部的。"), (2, 3, "名詞", "一朵花。")],
                "例句": [
                    (1, 1, 1, "一蕊花", "tsi̍t-luí-hue", "一朵花", "1-1-1"),
                    (1, 1, 2, "一二三", "it-jī-sann", "一二三", "1-1-2"),
                    (1, 2, 1, "規身軀", "kui-sin-khu", "全身", "1-2-1"),
                ],
                "義項tuì義項近義": [(1, "一", "數目。", 3, "一蕊花", "一朵花。")],
                "羅馬字清單": [("tsi̍t", "詞目,例句"), ("it", "名,姓")],
            }
        )
        self.assertEqual(sha256(rebuilt), sha256(source))

    def test_a_row_that_violates_a_derived_rule_still_survives(self):
        """異用字.漢字 is normally 詞目.漢字; a row where it is not must not be lost."""
        _, _, columns = self.roundtrip(
            {
                "詞目": [(1, "主詞目", "一", "tsi̍t", None, "1(1)")],
                "異用字": [(1, "蜀", "壹")],
            }
        )
        self.assertEqual(columns["異用字"]["漢字"], ["蜀"])

    def test_an_audio_filename_that_breaks_the_pattern_still_survives(self):
        _, _, columns = self.roundtrip(
            {"詞目": [(1, "主詞目", "一", "tsi̍t", None, "surprise(9)"), (2, "主詞目", "二", "jī", None, None)]}
        )
        self.assertEqual(columns["詞目"]["羅馬字音檔檔名"], ["surprise(9)", None])

    def test_a_null_is_not_confused_with_an_empty_string(self):
        _, _, columns = self.roundtrip(
            {"詞目": [(1, "主詞目", "一", None, "", "1(1)"), (2, "主詞目", "二", "jī", None, "2(1)")]}
        )
        self.assertEqual(columns["詞目"]["羅馬字"], [None, "jī"])
        self.assertEqual(columns["詞目"]["分類"], ["", None])

    def test_an_empty_database_rebuilds(self):
        source, rebuilt, _ = self.roundtrip({})
        self.assertEqual(sha256(rebuilt), sha256(source))


@unittest.skipUnless(REAL_DB.exists(), "kautian.db is not present in this checkout")
class TestRealDatabase(unittest.TestCase):
    def test_kautian_db_rebuilds_byte_for_byte(self):
        blob = container.encode(REAL_DB)
        manifest, columns = container.decode(blob)
        with tempfile.TemporaryDirectory() as workspace:
            rebuilt = Path(workspace) / "rebuilt.db"
            container.rebuild(manifest, columns, rebuilt)
            self.assertEqual(sha256(rebuilt), sha256(REAL_DB))

    def test_the_container_is_deterministic(self):
        self.assertEqual(container.encode(REAL_DB), container.encode(REAL_DB))


if __name__ == "__main__":
    unittest.main()
