"""LibraryEntry 索引 CRUD（内存 + 持久化）。"""

from __future__ import annotations

from typing import Iterable

from .protocol import FactorLibraryEntry


class LibraryCatalog:
    """进程内索引；runner 负责落盘。"""

    def __init__(self) -> None:
        self._by_id: dict[str, FactorLibraryEntry] = {}
        self._by_factor: dict[str, list[str]] = {}

    def upsert(self, entry: FactorLibraryEntry) -> None:
        self._by_id[entry.entry_id] = entry
        refs = self._by_factor.setdefault(entry.factor_ref, [])
        if entry.entry_id not in refs:
            refs.append(entry.entry_id)

    def get(self, entry_id: str) -> FactorLibraryEntry | None:
        return self._by_id.get(entry_id)

    def list_all(self) -> list[FactorLibraryEntry]:
        return list(self._by_id.values())

    def load_many(self, entries: Iterable[FactorLibraryEntry]) -> None:
        for e in entries:
            self.upsert(e)


__all__ = ["LibraryCatalog"]
