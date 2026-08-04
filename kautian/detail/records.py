ACCENT_COLUMNS = (
    "鹿港偏泉腔",
    "三峽偏泉腔",
    "臺北偏泉腔",
    "宜蘭偏漳腔",
    "臺南混合腔",
    "高雄混合腔",
    "金門偏泉腔",
    "馬公偏泉腔",
    "新竹偏泉腔",
    "臺中偏漳腔",
)

BY_WORD = "詞目id"
BY_SENSE = "義項id"

GROUPS = (
    ("senses", "義項", BY_WORD, ("義項id", "詞性", "解說")),
    ("examples", "例句", BY_WORD, ("義項id", "例句順序", "漢字", "羅馬字", "華語", "音檔檔名")),
    ("variants", "異用字", BY_WORD, ("漢字", "異用字")),
    ("accents", "語音差異", BY_WORD, ("漢字",) + ACCENT_COLUMNS),
    ("synonyms", "詞目tuì詞目近義", BY_WORD, ("對應詞目id", "對應詞目漢字")),
    ("antonyms", "詞目tuì詞目反義", BY_WORD, ("對應詞目id", "對應詞目漢字")),
    ("senseSynonyms", "義項tuì義項近義", BY_SENSE, ("義項id", "對應義項id", "對應詞目id", "對應詞目漢字")),
    ("senseAntonyms", "義項tuì義項反義", BY_SENSE, ("義項id", "對應義項id", "對應詞目id", "對應詞目漢字")),
    ("senseWordSynonyms", "義項tuì詞目近義", BY_SENSE, ("義項id", "對應詞目id", "對應詞目漢字")),
    ("senseWordAntonyms", "義項tuì詞目反義", BY_SENSE, ("義項id", "對應詞目id", "對應詞目漢字")),
)


def _entry(row, keys):
    return {key: row[key] for key in keys if row.get(key) not in (None, "")}


def _owner(row, keyed_by, sense_owner):
    if keyed_by == BY_WORD:
        return row["詞目id"]
    return sense_owner.get(row["義項id"])


def _resolved(row, sense_owner):
    if "對應義項id" not in row or "對應詞目id" in row:
        return row
    return {**row, "對應詞目id": sense_owner.get(row["對應義項id"])}


def group(rows, keyed_by, keys, sense_owner):
    grouped = {}
    for row in rows:
        owner = _owner(row, keyed_by, sense_owner)
        if owner is None:
            continue
        grouped.setdefault(owner, []).append(_entry(_resolved(row, sense_owner), keys))
    return grouped


def build(tables, sense_owner, categories):
    """Shape every headword's detail record. Pure — no sqlite, no ids invented."""
    grouped = {
        name: group(tables[table], keyed_by, keys, sense_owner)
        for name, table, keyed_by, keys in GROUPS
    }
    records = {}
    for name, _, _, _ in GROUPS:
        for owner, entries in grouped[name].items():
            records.setdefault(owner, {})[name] = entries
    for owner, category in categories.items():
        if owner in records:
            records[owner]["category"] = category
    return records
