#!/usr/bin/env python3
"""Scan Phase 9F model packages for Strategy LIVE / OMS leakage。"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "app" / "services" / "research_data"

PHASE9F_PACKAGES = (
    "model_platform",
    "model_adapters",
    "model_evaluation",
    "model_reproducibility",
)

FORBIDDEN_AST = (
    "auto_live",
    "promote_strategy",
    "promote_to_live",
    "submit_order",
    "oms_cycle",
)

SOURCE_FORBIDDEN = (
    "live_trading",
    "trading_db",
    "broker_order",
    "pending_order",
)


def scan_package(pkg: str) -> list[dict[str, Any]]:
    root = SERVICES / pkg
    violations: list[dict[str, Any]] = []
    if not root.is_dir():
        return [{"package": pkg, "file": str(root), "reason": "missing_package"}]
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(ROOT)
        text = py.read_text(encoding="utf-8")
        lower = text.lower()
        for frag in SOURCE_FORBIDDEN:
            if frag in lower:
                violations.append(
                    {
                        "package": pkg,
                        "file": str(rel),
                        "reason": f"source:{frag}",
                    }
                )
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            violations.append(
                {"package": pkg, "file": str(rel), "reason": f"syntax:{exc}"}
            )
            continue
        dumped = ast.dump(tree)
        for tok in FORBIDDEN_AST:
            if tok in dumped:
                # allow string docs mentioning boundaries
                if f"'{tok}'" in text or f'"{tok}"' in text:
                    # still flag if appears as Name/Attribute in AST dump as bare id
                    if f"Name(id='{tok}'" in dumped or f"attr='{tok}'" in dumped:
                        violations.append(
                            {
                                "package": pkg,
                                "file": str(rel),
                                "reason": f"ast:{tok}",
                            }
                        )
                elif f"Name(id='{tok}'" in dumped or f"attr='{tok}'" in dumped:
                    violations.append(
                        {
                            "package": pkg,
                            "file": str(rel),
                            "reason": f"ast:{tok}",
                        }
                    )
    return violations


def run_scan() -> dict[str, Any]:
    all_v: list[dict[str, Any]] = []
    for pkg in PHASE9F_PACKAGES:
        all_v.extend(scan_package(pkg))
    return {"clean": len(all_v) == 0, "violations": all_v}


def main() -> int:
    result = run_scan()
    print(json.dumps(result, indent=2))
    return 0 if result["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
