"""Phase 6E：Broker Adapter（停在 Paper / Fake / Alpaca Paper）。"""

from .errors import AdapterErrorCode, BrokerAdapterError
from .paper_adapter import PaperBrokerAdapter
from .protocol import ENGINE_VERSION, BrokerCapabilities
from .runner import BrokerAdapterService
from .simulated import SimulatedBrokerAdapter

__all__ = [
    "ENGINE_VERSION",
    "AdapterErrorCode",
    "BrokerAdapterError",
    "BrokerAdapterService",
    "BrokerCapabilities",
    "PaperBrokerAdapter",
    "SimulatedBrokerAdapter",
]
