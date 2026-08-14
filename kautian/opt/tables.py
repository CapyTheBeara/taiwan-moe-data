"""
tables.py — what each kautian.db column is, and how it is reconstructed.

The database denormalises heavily: a relation row carries a copy of both
headwords' 漢字 and both senses' 解說, an example carries an audio filename
composed from ids it already holds, and every romanised column restates a
reading that its 漢字 mostly determines. None of that is content — it is a join
or a format string — so this module names each column's plan and the encoder
stores only what a plan cannot rebuild.

A `derived` plan is never trusted blind. The encoder runs the rule over the real
rows, compares, and stores an exception list for the rows where the rule is
wrong, so losslessness does not depend on the rule being right. The rules here
hold for 96–100% of rows; the remainder ride in the exception column.

Every rule reads only columns that precede it in its table's column order, plus
tables decoded earlier. That is what lets the decoder resolve a derived column
during its single forward pass instead of deferring it — which it must, because
a `tailo` column is decoded against a 漢字 column that is itself derived.
"""

from kautian.opt import tailo

INT = "int"
DELTA = "delta"
TEXT = "text"
ENUM = "enum"
TAGSET = "tagset"
TAILO = "tailo"
DERIVED = "derived"

ACCENTS = (
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

TAGS = ("詞目", "例句", "又唸作", "合音唸作", "俗唸作", "詞彙比較", "名", "姓", "釋義")


def _index_by(context, table, key, value):
    keys = context[table][key]
    values = context[table][value]
    return dict(zip(keys, values))


def headword_hanji(context, rows, id_column):
    lookup = _index_by(context, "詞目", "詞目id", "漢字")
    return [lookup.get(word_id) for word_id in rows[id_column]]


def sense_gloss(context, rows, id_column):
    lookup = _index_by(context, "義項", "義項id", "解說")
    return [lookup.get(sense_id) for sense_id in rows[id_column]]


def sense_headword_hanji(context, rows, id_column):
    owner = _index_by(context, "義項", "義項id", "詞目id")
    hanji = _index_by(context, "詞目", "詞目id", "漢字")
    return [hanji.get(owner.get(sense_id)) for sense_id in rows[id_column]]


def headword_audio(context, rows, id_column):
    return [f"{word_id}(1)" for word_id in rows[id_column]]


def example_order(context, rows, _):
    """例句順序 restarts at 1 for every (詞目id, 義項id) run in table order."""
    orders = []
    previous = None
    counter = 0
    for word_id, sense_id in zip(rows["詞目id"], rows["義項id"]):
        key = (word_id, sense_id)
        counter = counter + 1 if key == previous else 1
        previous = key
        orders.append(counter)
    return orders


def example_audio(context, rows, _):
    """音檔檔名 is {詞目id}-{position of 義項id within the word}-{例句順序}."""
    positions = {}
    seen = {}
    for word_id, sense_id in zip(context["義項"]["詞目id"], context["義項"]["義項id"]):
        seen.setdefault(word_id, [])
        if sense_id not in seen[word_id]:
            seen[word_id].append(sense_id)
            positions[(word_id, sense_id)] = len(seen[word_id])
    orders = example_order(context, rows, None)
    return [
        f"{word_id}-{positions.get((word_id, sense_id))}-{order}"
        for word_id, sense_id, order in zip(rows["詞目id"], rows["義項id"], orders)
    ]


RULES = {
    "headword_hanji": headword_hanji,
    "sense_gloss": sense_gloss,
    "sense_headword_hanji": sense_headword_hanji,
    "headword_audio": headword_audio,
    "example_order": example_order,
    "example_audio": example_audio,
}


def derived(rule, *arguments):
    return (DERIVED, rule, arguments)


def tailo_of(hanji_column):
    return (TAILO, hanji_column)


PLAN = {
    "詞目": {
        "詞目id": (DELTA,),
        "詞目類型": (ENUM,),
        "漢字": (TEXT,),
        "羅馬字": (TEXT,),
        "分類": (ENUM,),
        "羅馬字音檔檔名": derived("headword_audio", "詞目id"),
    },
    "義項": {
        "詞目id": (DELTA,),
        "義項id": (DELTA,),
        "詞性": (ENUM,),
        "解說": (TEXT,),
    },
    "例句": {
        "詞目id": (DELTA,),
        "義項id": (DELTA,),
        "例句順序": derived("example_order", None),
        "漢字": (TEXT,),
        "羅馬字": tailo_of("漢字"),
        "華語": (TEXT,),
        "音檔檔名": derived("example_audio", None),
    },
    "又唸作": {"詞目id": (DELTA,), "漢字": derived("headword_hanji", "詞目id"), "羅馬字": tailo_of("漢字")},
    "合音唸作": {"詞目id": (DELTA,), "漢字": derived("headword_hanji", "詞目id"), "羅馬字": tailo_of("漢字")},
    "俗唸作": {"詞目id": (DELTA,), "漢字": derived("headword_hanji", "詞目id"), "羅馬字": tailo_of("漢字")},
    "語音差異": dict(
        [("詞目id", (DELTA,)), ("漢字", derived("headword_hanji", "詞目id"))]
        + [(accent, (TEXT,)) for accent in ACCENTS]
    ),
    "詞彙比較": {
        "華語詞目id": (DELTA,),
        "華語詞目": (TEXT,),
        "腔": (ENUM,),
        "漢字": (TEXT,),
        "羅馬字": tailo_of("漢字"),
    },
    "名": {"漢字": (TEXT,), "羅馬字": tailo_of("漢字"), "建議順序": (INT,), "類型": (ENUM,)},
    "姓": {"漢字": (TEXT,), "羅馬字": tailo_of("漢字"), "建議順序": (INT,), "類型": (ENUM,)},
    "異用字": {"詞目id": (DELTA,), "漢字": derived("headword_hanji", "詞目id"), "異用字": (TEXT,)},
    "義項tuì義項近義": {
        "義項id": (INT,),
        "詞目漢字": derived("sense_headword_hanji", "義項id"),
        "解說": derived("sense_gloss", "義項id"),
        "對應義項id": (INT,),
        "對應詞目漢字": derived("sense_headword_hanji", "對應義項id"),
        "對應解說": derived("sense_gloss", "對應義項id"),
    },
    "義項tuì詞目近義": {
        "義項id": (INT,),
        "詞目漢字": derived("sense_headword_hanji", "義項id"),
        "解說": derived("sense_gloss", "義項id"),
        "對應詞目id": (INT,),
        "對應詞目漢字": derived("headword_hanji", "對應詞目id"),
    },
    "詞目tuì詞目近義": {
        "詞目id": (INT,),
        "詞目漢字": derived("headword_hanji", "詞目id"),
        "對應詞目id": (INT,),
        "對應詞目漢字": derived("headword_hanji", "對應詞目id"),
    },
    "羅馬字清單": {"羅馬字": (TEXT,), "來源": (TAGSET,)},
    "漢字羅馬字對應": {"漢字": (TEXT,), "羅馬字": tailo_of("漢字"), "來源": (TAGSET,)},
}

PLAN["義項tuì義項反義"] = PLAN["義項tuì義項近義"]
PLAN["義項tuì詞目反義"] = PLAN["義項tuì詞目近義"]
PLAN["詞目tuì詞目反義"] = PLAN["詞目tuì詞目近義"]

MODEL_SOURCE = ("詞目", "漢字", "羅馬字")
