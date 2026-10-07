"""Factor compute engines (DuckDB optional at import time)."""

from .level2_engine import Level2FactorEngine
from .polars_engine import PolarsFactorEngine
from .qlib_engine import QlibFactorEngine
from .quantdinger_engine import QuantDingerFactorEngine


def __getattr__(name: str):
    if name == "DuckDBFactorEngine":
        from .duckdb_engine import DuckDBFactorEngine

        return DuckDBFactorEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DuckDBFactorEngine",
    "Level2FactorEngine",
    "PolarsFactorEngine",
    "QlibFactorEngine",
    "QuantDingerFactorEngine",
]
