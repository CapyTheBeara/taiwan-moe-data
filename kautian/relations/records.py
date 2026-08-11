"""Relation edges to the inbound-relation records. Pure — no sqlite, no IO."""

SYNONYM_OF = "synonymOf"
ANTONYM_OF = "antonymOf"
GROUPS = (SYNONYM_OF, ANTONYM_OF)


def build(edges, eligible):
    """One record per eligible headword some other headword names.

    edges is (group, 詞目id, 漢字, 對應詞目id) tuples — the naming headword and
    the headword it names. Only the named end is indexed, and only when it is
    one of the entry-less types: a headword with 義項 of its own already answers
    for itself, and a record for it would be bytes nothing reads.

    A headword that names the same target through several 義項 yields one entry,
    and a headword that names itself yields none — the dictionary has a handful
    of both, and neither says anything to a reader.
    """
    seen = {}
    for group, word_id, hanji, target in edges:
        if target not in eligible or target == word_id or not hanji:
            continue
        seen.setdefault(target, {}).setdefault(group, {}).setdefault(word_id, hanji)

    records = {}
    for target, groups in seen.items():
        record = {}
        for group in GROUPS:
            named_by = groups.get(group)
            if not named_by:
                continue
            record[group] = [
                {"詞目id": word_id, "漢字": named_by[word_id]}
                for word_id in sorted(named_by)
            ]
        if record:
            records[target] = record
    return records
