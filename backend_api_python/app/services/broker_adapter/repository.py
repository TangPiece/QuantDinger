"""Broker Registry 薄封装。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .writers import BrokerWriter


class BrokerRepository:
    def __init__(self, registry: ResearchRegistry, writer: BrokerWriter) -> None:
        self._registry = registry
        self._writer = writer
