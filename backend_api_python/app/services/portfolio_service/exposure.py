"""Exposure：instrument / market / portfolio 三级。"""

from __future__ import annotations

from typing import Mapping

from .protocol import Exposure, Position


def _market_of(instrument_key: str) -> str:
    # CNStock:600000 → CNStock
    if ":" in instrument_key:
        return instrument_key.split(":", 1)[0]
    return "UNKNOWN"


def compute_exposure(
    positions: Mapping[str, Position],
    *,
    equity: float = 0.0,
) -> Exposure:
    """按市值汇总毛/净/多空敞口。"""
    inst: dict[str, float] = {}
    mkt: dict[str, float] = {}
    long_e = 0.0
    short_e = 0.0
    for key, pos in positions.items():
        mv = float(pos.market_value)
        if abs(mv) < 1e-12 and float(pos.quantity):
            # 无市值时跳过权重，仍记 0
            mv = 0.0
        inst[key] = mv
        mk = _market_of(key)
        mkt[mk] = float(mkt.get(mk, 0.0)) + mv
        if mv >= 0:
            long_e += mv
        else:
            short_e += abs(mv)
    gross = long_e + short_e
    net = long_e - short_e
    return Exposure(
        gross_exposure=gross,
        net_exposure=net,
        long_exposure=long_e,
        short_exposure=short_e,
        instrument_exposure=inst,
        market_exposure=mkt,
        portfolio_exposure=float(equity) if equity else gross,
    )
