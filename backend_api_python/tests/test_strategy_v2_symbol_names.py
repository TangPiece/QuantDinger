"""回测结果附加证券名称时，不改动权重字典的仓位 key。"""

import unittest
from unittest.mock import patch

from app.services.strategy_v2.storage import _normalize_backtest_result
from app.services.strategy_v2.symbol_labels import attach_symbol_names, display_symbol_code


class SymbolNameAttachmentTests(unittest.TestCase):
    def test_display_code_strips_market_venue_and_side(self):
        self.assertEqual(display_symbol_code("CNStock:688187.SH"), "688187.SH")
        self.assertEqual(display_symbol_code("688187::long"), "688187")
        self.assertEqual(display_symbol_code("Crypto:BTC/USDT@binance:spot"), "BTC/USDT")

    def test_named_symbol_is_attached_without_changing_weight_keys(self):
        weights = {"CNStock:688187": 0.9491, "CNStock:688187::long": 0.0}
        result = {
            "rebalanceRecords": [{
                "targetWeights": dict(weights),
                "actualWeights": {"688187": 0.9498},
            }],
            "closedTrades": [{"symbol": "CNStock:688187.SH"}],
            "attribution": {"symbols": [{"symbol": "688187"}]},
        }

        def lookup(pairs):
            self.assertIn(("CNStock", "688187.SH"), list(pairs))
            return {("CNStock", "688187.SH"): "时代电气"}

        attach_symbol_names(result, default_market="CNStock", lookup=lookup)

        self.assertEqual(result["rebalanceRecords"][0]["targetWeights"], weights)
        self.assertEqual(set(result["rebalanceRecords"][0]["actualWeights"]), {"688187"})
        self.assertEqual(result["symbolNames"]["688187"], "时代电气")
        self.assertEqual(result["symbolNames"]["688187.SH"], "时代电气")

    def test_missing_or_code_only_names_are_omitted(self):
        result = {
            "executions": [{"symbol": "Crypto:BTC/USDT@spot"}],
            "orderLedger": [{"symbol": "AAPL"}],
        }

        def lookup(_pairs):
            return {("Crypto", "BTC/USDT"): "BTC/USDT", ("USStock", "AAPL"): ""}

        attach_symbol_names(result, lookup=lookup)

        self.assertNotIn("symbolNames", result)
        self.assertEqual(result["executions"][0]["symbol"], "Crypto:BTC/USDT@spot")

    def test_history_normalize_attaches_names_for_saved_runs(self):
        result = {
            "initialCapital": 10000,
            "executionAssumptions": {
                "initialCapital": 10000,
                "startDate": "2025-01-01",
                "endDate": "2025-09-22",
                "leverageEnabled": False,
                "leverage": 1,
                "commission": 0.0005,
                "slippage": 0.0005,
            },
            "rebalanceRecords": [{
                "targetWeights": {"688187": 0.9491},
                "actualWeights": {"688187": 0.9498},
            }],
        }

        def lookup(pairs):
            self.assertIn(("CNStock", "688187"), list(pairs))
            return {("CNStock", "688187"): "时代电气"}

        with patch(
            "app.services.strategy_v2.symbol_labels._lookup_local_names",
            lookup,
        ):
            restored = _normalize_backtest_result(result, {
                "market": "CNStock",
                "initial_capital": 10000,
                "start_date": "2025-01-01",
                "end_date": "2025-09-22",
                "leverage": 1,
                "commission": 0.0005,
                "slippage": 0.0005,
            })

        self.assertEqual(restored["rebalanceRecords"][0]["targetWeights"], {"688187": 0.9491})
        self.assertEqual(restored["symbolNames"], {"688187": "时代电气"})


if __name__ == "__main__":
    unittest.main()
