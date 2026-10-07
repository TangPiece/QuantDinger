"""Phase 8C：稳定性 Gate — 多窗口 metrics 通过比例。"""

from __future__ import annotations

from ..bridge_from_candidate import ValidationEvidenceContext
from ..protocol import GateCheckResult, ValidationPolicyRules


def run_stability_check(
    ctx: ValidationEvidenceContext,
    policy: ValidationPolicyRules,
) -> GateCheckResult:
    windows = list(ctx.stability_windows or [])
    if not windows:
        listed = ctx.metrics.get("stability_windows")
        if isinstance(listed, list):
            windows = [w for w in listed if isinstance(w, dict)]
    if not windows:
        return GateCheckResult(
            check="stability",
            status="SKIP",
            reason="no stability windows",
        )
    passed = 0
    for w in windows:
        sh = w.get("sharpe") or w.get("oos_sharpe")
        try:
            if float(sh) >= policy.min_oos_sharpe:
                passed += 1
        except (TypeError, ValueError):
            continue
    ratio = passed / len(windows) if windows else 0.0
    if ratio < policy.stability_min_windows_pass:
        return GateCheckResult(
            check="stability",
            status="FAIL",
            reason="stability window pass ratio below policy",
            metrics={
                "pass_ratio": ratio,
                "min_ratio": policy.stability_min_windows_pass,
                "n_windows": len(windows),
            },
        )
    return GateCheckResult(
        check="stability",
        status="PASS",
        metrics={"pass_ratio": ratio, "n_windows": len(windows)},
    )


__all__ = ["run_stability_check"]
