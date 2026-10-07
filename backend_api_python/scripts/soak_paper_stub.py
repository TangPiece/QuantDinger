#!/usr/bin/env python3
"""Phase 6J：24h Paper Soak 入口桩（非合入门禁）。

仅打印建议步骤；真实 soak 由运维在 Paper 环境手动执行。
"""

from __future__ import annotations

print(
    """
QuantDinger Paper Soak (manual)

1. Deploy Paper stack (docker-compose / workers isolated from Research plane)
2. Run verify_phase6i_e2e.py + verify_phase6j_readiness.py (PRODUCTION_READY=true)
3. Start paper trading session with monitoring (6H) enabled
4. Observe for 24h: memory, CPU, DB growth, R2 growth, WS stability, error rate
5. Record results in docs/production/08_runbook.md incident template

This script does NOT run the soak gate automatically.
"""
)
