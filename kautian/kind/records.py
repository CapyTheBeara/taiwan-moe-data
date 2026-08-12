"""Detail-kind classification: which of full/bound/named/none an id resolves
to when the word-details modal decides what icon to show. Pure — no IO.

Mirrors `resolveKind` in taigi-ear's `src/features/compose/useWordDetailKind.ts`
exactly: an id whose 詞目類型 is not one of the three entry-less labels is
`full` regardless of anything else — that is every 主詞目, every 附錄, and every
id with no 詞目 row at all. Among the entry-less ids, a record surviving into
concised/v3/ speaks for the headword already: `bound` for 單字不成詞者, `full`
for the other two labels. Only when concised is silent does kautian/rel/v1/ get
to add anything — `named` if some other headword names it, `none` if it is a
genuine dead end.
"""

FULL, BOUND, NAMED, NONE = 0, 1, 2, 3
KINDS = ("full", "bound", "named", "none")

BOUND_LABEL = "單字不成詞者"
ENTRYLESS_TYPES = (BOUND_LABEL, "近反義詞不單列詞目者", "臺華共同詞")


def classify(label, concised_live, relations_live):
    """The four-way call for one id, given its 詞目類型 and sibling liveness."""
    if label not in ENTRYLESS_TYPES:
        return FULL
    if concised_live:
        return BOUND if label == BOUND_LABEL else FULL
    return NAMED if relations_live else NONE


def build(types, concised_live, relations_live, max_id):
    """One kind byte per id, 0..max_id. An id absent from `types` is `full`.

    `types` is {詞目id: 詞目類型}. `concised_live` and `relations_live` are
    id-keyed containers (sets or anything supporting `in`) of the ids with a
    non-empty record in the matching sibling container.
    """
    return bytes(
        classify(types.get(word_id), word_id in concised_live, word_id in relations_live)
        for word_id in range(max_id + 1)
    )
