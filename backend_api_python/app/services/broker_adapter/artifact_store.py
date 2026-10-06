"""Artifact 别名：与 raw_store 对齐。"""

from .raw_store import BrokerRawStore

BrokerArtifactStore = BrokerRawStore

__all__ = ["BrokerArtifactStore", "BrokerRawStore"]
