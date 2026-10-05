"""Materializer 边界：禁止 Source/PG/R2 SDK/HTTP。"""

from __future__ import annotations

import ast
from pathlib import Path

RD = Path(__file__).resolve().parents[2] / "app" / "services" / "research_data"
MAT = RD / "qlib_materializer"


def test_materializer_package_forbids_banned_imports():
    banned_modules = {
        "app.data_sources",
        "app.data_sources.factory",
        "app.data_sources.cn_stock",
        "app.services.level2_ingest",
        "app.services.universe",
        "requests",
        "psycopg2",
        "psycopg",
        "boto3",
    }
    banned_names = {"CNStockDataSource", "DataSourceFactory", "UniverseService"}
    for path in MAT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in banned_modules, path.name
                    assert alias.name.split(".")[0] not in {"psycopg2", "psycopg", "boto3", "requests"}
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert mod not in banned_modules, f"{path.name} imports {mod}"
                for alias in node.names:
                    assert alias.name not in banned_names


def test_materializer_uses_data_query_only_for_reads():
    text = (MAT / "qlib_materializer.py").read_text(encoding="utf-8")
    assert "DataQuery" in text
    assert "self._query.market" in text
    assert "self._query.universe" in text
    assert "self._query.dataset" in text
