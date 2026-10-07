"""Phase 8C：OOS / 过拟合 / 成本 Gate（读 metrics 摘要，不重算回测）。"""

from __future__ import annotations

from ..bridge_from_candidate import ValidationEvidenceContext
from ..protocol import GateCheckResult, ValidationPolicyRules


def _f(metrics: dict, *keys: str, default: float = 0.0) -> float:
    for k in keys:
        if k in metrics and metrics[k] is not None:
            try:
                return float(metrics[k])
            except (TypeError, ValueError):
                continue
    return default


def run_oos_check(
    ctx: ValidationEvidenceContext,
    policy: ValidationPolicyRules,
) -> GateCheckResult:
    m = ctx.metrics
    oos = _f(m, "oos_sharpe", "test_sharpe", "sharpe_oos")
    if oos == 0.0 and "sharpe" in m:
        oos = _f(m, "sharpe")
    if oos < policy.min_oos_sharpe:
        return GateCheckResult(
            check="oos",
            status="FAIL",
            reason="oos sharpe below minimum",
            metrics={"oos_sharpe": oos, "min_oos_sharpe": policy.min_oos_sharpe},
        )
    turnover = _f(m, "turnover", "avg_turnover")
    if turnover > policy.max_turnover:
        return GateCheckResult(
            check="oos",
            status="FAIL",
            reason="turnover above policy",
            metrics={"turnover": turnover, "max_turnover": policy.max_turnover},
        )
    slip = _f(m, "slippage_bps", "avg_slippage_bps")
    if slip > policy.max_slippage_bps:
        return GateCheckResult(
            check="oos",
            status="FAIL",
            reason="slippage above policy",
            metrics={"slippage_bps": slip, "max_slippage_bps": policy.max_slippage_bps},
        )
    return GateCheckResult(
        check="oos",
        status="PASS",
        metrics={"oos_sharpe": oos, "turnover": turnover, "slippage_bps": slip},
    )


def run_overfit_check(
    ctx: ValidationEvidenceContext,
    policy: ValidationPolicyRules,
) -> GateCheckResult:
    m = ctx.metrics
    is_sh = _f(m, "is_sharpe", "train_sharpe", "sharpe_is")
    oos_sh = _f(m, "oos_sharpe", "test_sharpe", "sharpe_oos")
    if is_sh == 0.0 and oos_sh == 0.0:
        return GateCheckResult(
            check="overfit",
            status="SKIP",
            reason="is/oos sharpe not in metrics",
        )
    gap = is_sh - oos_sh
    if gap > policy.max_is_oos_sharpe_gap:
        return GateCheckResult(
            check="overfit",
            status="FAIL",
            reason="is-oos sharpe gap too large",
            metrics={
                "is_sharpe": is_sh,
                "oos_sharpe": oos_sh,
                "gap": gap,
                "max_gap": policy.max_is_oos_sharpe_gap,
            },
        )
    return GateCheckResult(
        check="overfit",
        status="PASS",
        metrics={"is_sharpe": is_sh, "oos_sharpe": oos_sh, "gap": gap},
    )


def run_cost_check(
    ctx: ValidationEvidenceContext,
    policy: ValidationPolicyRules,
) -> GateCheckResult:
    m = ctx.metrics
    net = _f(m, "net_sharpe", "sharpe_net")
    gross = _f(m, "gross_sharpe", "sharpe_gross")
    total_cost = _f(m, "total_cost", "cost")
    realism = str(m.get("realism") or ctx.candidate.metadata.get("realism") or "")
    if policy.require_net_backtest:
        if net == 0.0 and realism.upper() == "GROSS" and gross > 0:
            return GateCheckResult(
                check="cost",
                status="FAIL",
                reason="require_net_backtest but only GROSS metrics",
                metrics={"realism": realism, "gross_sharpe": gross},
            )
        if policy.require_net_backtest and total_cost <= 0 and net == 0.0 and gross > 0:
            return GateCheckResult(
                check="cost",
                status="FAIL",
                reason="missing total_cost / net sharpe",
                metrics={"gross_sharpe": gross},
            )
    if net > 0 and net < policy.min_oos_sharpe * 0.5:
        return GateCheckResult(
            check="cost",
            status="FAIL",
            reason="net sharpe too low after costs",
            metrics={"net_sharpe": net},
        )
    return GateCheckResult(
        check="cost",
        status="PASS",
        metrics={"net_sharpe": net, "gross_sharpe": gross, "total_cost": total_cost},
    )


__all__ = ["run_cost_check", "run_oos_check", "run_overfit_check"]
