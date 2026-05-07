"""Classification d'intent — pivot pour décider si décomposer.

Types d'intents :
  - extract     : champ unique, une seule retrieval (cas dominant, Type 1)
  - compare     : deux concepts à confronter
  - aggregate   : liste exhaustive ou ranking
  - conditional : « si X, alors Y »
  - open        : open-ended, possiblement multi-passages
"""

from __future__ import annotations

INTENTS = ("extract", "compare", "aggregate", "conditional", "open")

_COMPARE_KW = (
    "compare", "consistent", "matches", "match between", "differ", "difference between",
    "vs ", "versus", "cohérent", "cohérence", "écart entre",
)
_AGGREGATE_KW = (
    "list all", "rank ", "ranked", "every ", "all of the", "all the ",
    "lister tous", "lister toutes", "classer ",
)
_CONDITIONAL_KW = (
    "and if so", "and if yes", "if so,", "if yes,",
    "et si oui", "le cas échéant",
)
_OPEN_KW = (
    "explain ", "summarize", "summary", "overview",
    "expliquer", "résumer", "résumé", "synthèse",
)


def classify_intent(question: str) -> str:
    q = question.lower()
    if any(kw in q for kw in _COMPARE_KW):
        return "compare"
    if any(kw in q for kw in _AGGREGATE_KW):
        return "aggregate"
    if any(kw in q for kw in _CONDITIONAL_KW):
        return "conditional"
    if any(kw in q for kw in _OPEN_KW):
        return "open"
    return "extract"
