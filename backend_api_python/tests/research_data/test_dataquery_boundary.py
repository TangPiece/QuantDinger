"""DataQuery 边界：禁止 Source/PG market/D1 fact/Level2；仅经 CanonicalRepository。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RD = ROOT / "app" / "services" / "research_data"


def _imports_of(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
                names.add(node.module)
    return names


def test_data_query_and_repo_forbid_source_imports():
    """禁止真实依赖入口（AST import），而非文档字符串里的 backend 名。"""
    banned_modules = {
        "app.data_sources",
        "app.data_sources.factory",
        "app.data_sources.cn_stock",
        "app.services.level2_ingest",
        "app.services.universe_service",
        "psycopg2",
        "psycopg",
    }
    banned_names = {"CNStockDataSource", "DataSourceFactory", "UniverseService"}
    for rel in ("data_query.py", "canonical_repository.py"):
        tree = ast.parse((RD / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in banned_modules
                    assert alias.name.split(".")[0] not in {"psycopg2", "psycopg"}
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert mod not in banned_modules
                for alias in node.names:
                    assert alias.name not in banned_names


def test_data_query_uses_canonical_repository_symbol():
    text = (RD / "data_query.py").read_text(encoding="utf-8")
    assert "CanonicalRepository" in text
    assert "from .canonical_repository import CanonicalRepository" in text


def test_ingest_may_use_source_but_not_imported_by_data_query():
    # ingest 允许 Source；DataQuery 顶层 import 不得触及 ingest
    dq_imports = _imports_of(RD / "data_query.py")
    assert "ingest" not in dq_imports
    assert "app.services.research_data.ingest" not in " ".join(dq_imports)


def test_market_does_not_touch_requests(seeded_research, monkeypatch):
    query = seeded_research["query"]

    def boom(*_a, **_k):
        raise AssertionError("DataQuery must not call requests")

    monkeypatch.setattr("requests.get", boom)
    monkeypatch.setattr("requests.post", boom)
    from datetime import date

    df = query.market(["CNStock:000001"], date(2024, 5, 1), date(2024, 5, 1))
    assert len(df) == 1
