# Phase 8F — Strategy Monitoring & Alerting

## 目标

把 8E 的事后 Drift 分析升级为**持续运行的策略监控引擎**：Metrics → Rules → Health → Alert → Notification / Governance 事件。

```text
Trading Runtime / Fake inject / 8E·Risk·Recon bridges
  → Monitoring Engine (collect + evaluate)
  → MonitoringMetric + StrategyHealth
  → AlertEngine (dedupe / cooldown / lifecycle)
  → NotificationDispatcher | GovernanceReviewEvent
  ✕ mutate StrategyVersion / auto demote / stop LIVE
```

## 边界

**做（P0）**

- 包 `backend_api_python/app/services/strategy_monitoring/`
- `MonitoringMetric` + `StrategyHealth`（WORST-priority 聚合，**禁止**加权平均）
- 硬规则：`RECONCILIATION` / `RISK` breach / `MARKET_DATA` stale 为 CRITICAL → overall ≥ CRITICAL
- Collectors + 只读桥接 8E `latest_drift_scalars` / RiskPolicy / Recon inject
- `AlertRule`（`default_monitor_v1`）+ FSM + dedupe `(strategy_code, rule_id, fingerprint)`
- `NotificationDispatcher`：Recording/Fake 通道
- `GovernanceBridge`：`REVIEW_REQUIRED` 事件 only
- Dashboard Query API（Service，无 Flask 路由）
- D1 `0036` + R2 `qd/registry/strategy_monitoring/{strategy_code}/...`

**不做**

```text
❌ Auto demote / stop LIVE / pause（→ 8G）
❌ Mutate StrategyVersion / Model / Dataset / RiskPolicy
❌ 替换 8E / ops_service / reconciliation 实现
❌ 真实邮件/Telegram/Slack 发送
❌ Flask/Vue Dashboard UI
❌ 加权 Health Score
❌ OMS submit
```

## 包结构

```text
strategy_monitoring/
  protocol.py              # ENGINE_VERSION=qd_strategy_monitoring@1
  identity.py / pin.py / policy.py / policy_presets.py
  fsm.py / health.py
  collectors/              # performance, risk, execution, market_data, ...
  bridges/                 # bridge_from_feedback, risk_policy, reconciliation
  alert_engine.py / notification.py / governance_bridge.py
  dashboard.py / writers.py / artifact_store.py / runner.py
```

## Service API

`StrategyMonitoringService(store, registry, *, feedback=None, risk=None, reconciliation=None)`：

- `collect_and_evaluate(strategy_code, *, inject=None, session_id="")` → `StrategyHealth`
- `get_health` / `list_metrics` / `list_alerts`
- `ack_alert` / `investigate_alert` / `resolve_alert`
- `get_dashboard` / `list_notifications` / `list_governance_events`
- `get_performance` / `get_risk` / `get_execution` / `get_drift` / `get_reconciliation`

文档 REST 形状（未来 HTTP）：

- `GET /strategies/{strategy_code}/monitoring/health`
- `GET /strategies/{strategy_code}/monitoring/metrics`
- `GET /strategies/{strategy_code}/monitoring/alerts`
- `GET /strategies/{strategy_code}/monitoring/dashboard`

## 存储

- D1：`workers/qd-research-d1/migrations/0036_strategy_monitoring.sql`
  - `strategy_monitor_metric` / `strategy_health_snapshot`
  - `strategy_alert_rule` / `strategy_alert`
  - `strategy_notification_dispatch` / `strategy_governance_event`
- R2：`qd/registry/strategy_monitoring/{strategy_code}/health|metrics|alerts/{id}.json`

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8f_strategy_monitoring.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8f_strategy_monitoring.py -q --confcutdir=tests/research_data
```

8E verify 仍应绿：

```bash
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8e_performance_feedback.py
```
