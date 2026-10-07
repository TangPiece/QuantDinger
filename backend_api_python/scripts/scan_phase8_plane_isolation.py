#!/usr/bin/env python3
"""AST + source scan: Phase 8 strategy lifecycle packages vs trading plane."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "app" / "services"

PHASE8_PACKAGES = (
    "strategy_registry",
    "strategy_candidate",
    "strategy_validation",
    "strategy_promotion",
    "live_performance_feedback",
    "strategy_monitoring",
    "strategy_guardrails",
    "production_research_feedback",
)

# Common forbidden identifier / attribute fragments (AST dump), unified from 8A–8H tests.
COMMON_FORBIDDEN_AST = (
    "submit_order",
    "oms_cycle.submit",
    "promote_to_live",
    "train_model",
    "mutate_version",
    "stop_live",
    "demote",
)

PACKAGE_FORBIDDEN_AST: dict[str, tuple[str, ...]] = {
    "strategy_registry": ("oms_cycle.submit", "promote_to_live"),
    "strategy_candidate": (
        "promote_to_shadow",
        "validate_gate",
        "link_governance_active",
    ),
    "strategy_validation": (
        "promote_to_shadow",
        "promote_to_live",
        "link_governance_active",
    ),
    "strategy_promotion": ("promote_to_live",),
    "live_performance_feedback": (),
    "strategy_monitoring": (),
    "strategy_guardrails": ("promote",),
    "production_research_feedback": ("promote",),
}

# Raw source substrings (imports / broker HTTP patterns), unified from 8H + phase 6/7 tests.
SOURCE_FORBIDDEN_SUBSTRINGS = (
    "live_trading",
    "trading_db",
    "broker_order",
    "pending_order",
    "psycopg",
    'request("post"',
    "request('post'",
    'request( "post"',
    "request( 'post'",
    '"post /v2/orders"',
    "'post /v2/orders'",
)


def _forbidden_for_package(pkg: str) -> tuple[str, ...]:
    extra = PACKAGE_FORBIDDEN_AST.get(pkg, ())
    seen: set[str] = set()
    out: list[str] = []
    for tok in (*COMMON_FORBIDDEN_AST, *extra):
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return tuple(out)


def scan_package(pkg: str) -> list[dict[str, Any]]:
    root = SERVICES / pkg
    violations: list[dict[str, Any]] = []
    if not root.is_dir():
        violations.append({"package": pkg, "file": str(root), "reason": "missing_package"})
        return violations

    forbidden_ast = _forbidden_for_package(pkg)
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(ROOT)
        text = py.read_text(encoding="utf-8")
        lower = text.lower()
        for frag in SOURCE_FORBIDDEN_SUBSTRINGS:
            if frag in lower:
                violations.append(
                    {
                        "package": pkg,
                        "file": str(rel),
                        "reason": "forbidden_source_substring",
                        "token": frag,
                    }
                )
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as exc:
            violations.append(
                {
                    "package": pkg,
                    "file": str(rel),
                    "reason": "syntax_error",
                    "detail": str(exc),
                }
            )
            continue
        blob = ast.dump(tree)
        for tok in forbidden_ast:
            if tok in blob:
                violations.append(
                    {
                        "package": pkg,
                        "file": str(rel),
                        "reason": "forbidden_ast_token",
                        "token": tok,
                    }
                )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.lower()
                    if any(
                        bad in mod
                        for bad in ("oms", "live_trading", "broker", "trading_db")
                    ):
                        violations.append(
                            {
                                "package": pkg,
                                "file": str(rel),
                                "reason": "forbidden_import",
                                "token": alias.name,
                            }
                        )
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").lower()
                if any(
                    bad in mod for bad in ("oms", "live_trading", "broker", "trading_db")
                ):
                    violations.append(
                        {
                            "package": pkg,
                            "file": str(rel),
                            "reason": "forbidden_import_from",
                            "token": node.module or "",
                        }
                    )
    return violations


def run_scan() -> dict[str, Any]:
    all_violations: list[dict[str, Any]] = []
    by_package: dict[str, int] = {}
    for pkg in PHASE8_PACKAGES:
        v = scan_package(pkg)
        by_package[pkg] = len(v)
        all_violations.extend(v)
    return {
        "phase": "8i",
        "packages": list(PHASE8_PACKAGES),
        "clean": len(all_violations) == 0,
        "violation_count": len(all_violations),
        "violations_by_package": by_package,
        "violations": all_violations,
    }


def main() -> int:
    summary = run_scan()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
