"""FactorSearchQuery 过滤。"""

from __future__ import annotations

from .protocol import FactorLibraryEntry, FactorSearchQuery


def matches_query(entry: FactorLibraryEntry, query: FactorSearchQuery) -> bool:
    if query.lifecycle and entry.lifecycle not in query.lifecycle:
        return False
    if query.category and entry.category not in query.category:
        return False
    tags = set(entry.tags or [])
    if query.tags_all and not all(t in tags for t in query.tags_all):
        return False
    if query.tags_any and not any(t in tags for t in query.tags_any):
        return False
    if query.factor_ref_prefix and not entry.factor_ref.startswith(query.factor_ref_prefix):
        return False
    if query.text:
        blob = " ".join(
            [
                entry.factor_ref,
                entry.entry_id,
                entry.category,
                " ".join(entry.tags),
                entry.candidate_id,
            ]
        ).lower()
        if query.text.lower() not in blob:
            return False
    return True


def search_entries(
    entries: list[FactorLibraryEntry],
    query: FactorSearchQuery,
) -> list[FactorLibraryEntry]:
    return [e for e in entries if matches_query(e, query)]


__all__ = ["matches_query", "search_entries"]
