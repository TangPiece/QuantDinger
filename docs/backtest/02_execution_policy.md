# Execution Policy

## Problem

Research signals must not imply same-bar fills at the signal price unless explicitly configured.

Typical A-share daily workflow:

```text
T close  → signal_time / knowledge_time
T+1 open → execution_time / fill price (open)
```

Phase 2E [`signal/timeutil.py`](../../backend_api_python/app/services/research_data/signal/timeutil.py) used **calendar** next day (no exchange calendar). Phase 3B+ should align `ExecutionPolicy.execution_delay` with a real calendar while keeping the same contract fields.

## ExecutionPolicy fields

| Field | Meaning |
| --- | --- |
| `signal_time_rule` | When the signal is considered known (`close_of_signal_day`, …) |
| `execution_delay` | `T+0`, `T+1`, or `calendar_days:N` |
| `execution_price` | `open`, `close`, `vwap`, … |
| `execution_mode` | `market`, `limit`, `participation` |
| `participation_rate` | Optional volume participation cap |

## Preset: CN equity

`cn_equity_close_signal_next_open()`:

- `execution_delay = T+1`
- `execution_price = open`
- Aligns with 2E close → next open intent

## Preset: Qlib research relaxed

`research_qlib_relaxed()`:

- `T+0`, `close` fills — for fast research in 3B only; still serialized as the same contract.
