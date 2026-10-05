# 06 — Research Consistency

## Goal

Define what “same data / same experiment” means across:

```text
Source → Canonical → Snapshot → DuckDB → Qlib (derived) → (future) Production Backtest
```

Phase 1 implements these as **documented rules and future CI cases**. No requirement that research PnL equals production PnL yet.

## Layers

| Layer | Must be consistent on | SSOT |
| --- | --- | --- |
| Ingestion | Normalize + validate before publish | Job logs + checksums |
| Canonical | Fact values + schemas | R2 `qd/canonical/` |
| Snapshot | Exact file set for an experiment | D1 snapshot + R2 manifest |
| Research query | `DataQuery` results under fixed snapshot / hash | Contract |
| Qlib cache | Deterministic rematerialization from Canonical | Local derived |
| Production backtest | Real exchange rules (later phase) | QuantDinger engine |

## Data consistency checklist

### OHLCV

- Raw Canonical bars are the only research market facts.
- `price_policy` applied only in Query/Materializer; never silently rewrite Canonical files.
- Same `snapshot_id` + `price_policy` ⇒ identical adjusted series (within documented float epsilon).

### Calendar / status

- Trading dates must align with exchange calendar used at ingest.
- Suspended / limit-up / limit-down flags come from Canonical `trading_status` for the same snapshot.

### Corporate actions

- Adjustment inputs from Canonical `corporate_action` for the bound snapshot only.

### Universe

- Research membership for date `T` comes from universe **snapshot** intervals.
- Editing PG `qd_universe_members` after snapshot export must **not** change historical research results.
- CI case: mutate PG membership, re-run `DataQuery.universe` for old `snapshot_id` → unchanged.

### PIT fundamentals

- Selection: `available_time <= knowledge_time`, then latest `available_time`, `revision` DESC.
- `publish_time` alone is insufficient.
- CI case: restatement with later `available_time` must be invisible before that cutoff.

## Research consistency checklist

An experiment is reproducible when these are fixed and recorded:

```text
snapshot_id
dataset_version
dataset_definition (canonical JSON)
schema_version
processor_version
materializer_version
price_policy
dataset_hash
feature versions
label version
random seeds (models)
```

Same `dataset_hash` must address the same Qlib cache directory content (after rematerialization).

## Leakage tests (P0)

### Fundamental leakage

```text
Given knowledge_time = T
Assert every fundamental input row satisfies available_time <= T
```

Any violation ⇒ FAIL.

### Universe leakage

```text
Given backtest date = T and snapshot S
Assert membership == snapshot S as-of T
Assert membership is independent of live PG state
```

### Feature leakage

```text
Feature windows may only use market bars with trading_date <= T
(and PIT inputs obey available_time <= knowledge_time derived for T)
```

### API bypass leakage

```text
Research DataQuery implementation must not call live QuantDinger market APIs
when snapshot_id / Canonical paths are configured
```

## Cross-engine consistency (Phase 1 scope)

| Comparison | Phase 1 requirement |
| --- | --- |
| DuckDB vs direct Parquet read | Values equal (epsilon for float ops) |
| Canonical vs rematerialized Qlib features (later) | Document epsilon; not required until Materializer exists |
| Qlib research backtest vs QuantDinger production backtest | **Out of scope** (Differential Test in later phase) |

## Suggested future test layout

```text
backend_api_python/tests/research_data/
  test_pit_leakage.py
  test_universe_snapshot_stability.py
  test_dataset_hash_price_policy.py
  test_dataquery_no_live_api.py
```

## Operator invariants

1. Publish to Canonical is append/versioned; do not mutate historical partitions in place.
2. Bad publish ⇒ new `data_version` / snapshot, not silent overwrite of checksummed paths used by old experiments.
3. Local cache eviction is always safe.
4. Hot `l2_factors` updates do not rewrite historical R2 research factor sets unless a new `factor_set@version` is published.
