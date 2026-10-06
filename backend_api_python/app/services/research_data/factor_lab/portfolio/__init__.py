"""Phase 4I：Factor Portfolio。"""

from app.services.research_data.contracts import FactorPortfolioSummary

from .hash import compute_portfolio_hash
from .orchestrator import (
    FactorPortfolioError,
    FactorPortfolioService,
    PortfolioResult,
)
from .protocol import PORTFOLIO_VERSION, PortfolioSpec

__all__ = [
    "PORTFOLIO_VERSION",
    "FactorPortfolioError",
    "FactorPortfolioService",
    "FactorPortfolioSummary",
    "PortfolioResult",
    "PortfolioSpec",
    "compute_portfolio_hash",
]
