# 05 — Domain & DataQuery Contracts

## Purpose

Define the semantic SSOT (field names, versions, query protocol) as copy-pasteable Python contracts.
**No runtime implementation in Phase 1.** Future code should live under something like
`backend_api_python/app/services/research_data/`.

Field names are English. Comments may be Chinese in implementation files later.

## Identity

```python
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional, Protocol, Sequence
from pydantic import BaseModel, Field


class AssetType(str, Enum):
    STOCK = "STOCK"
    ETF = "ETF"
    INDEX = "INDEX"
    FUND = "FUND"
    FUTURE = "FUTURE"
    OPTION = "OPTION"
    CRYPTO = "CRYPTO"
    FX = "FX"


class InstrumentKey(BaseModel):
    """Canonical research instrument identity: '{market}:{symbol}'."""

    market: str  # CNStock | HKStock | USStock | ...
    symbol: str

    def as_key(self) -> str:
        return f"{self.market}:{self.symbol}"


class PricePolicy(BaseModel):
    """How raw Canonical prices are adjusted at query time."""

    adjustment: Literal["none", "pre", "post"] = "none"
    return_type: Literal["price", "total"] = "price"
```

## Time

```python
class KnowledgeTime(BaseModel):
    """Backtest information cutoff. Prefer timezone-aware UTC datetimes."""

    value: datetime


# PIT rule (locked):
#   available_time <= knowledge_time
# then order by available_time DESC, revision DESC
```

## Definitions

```python
class FeatureDefinition(BaseModel):
    code: str
    version: str
    name: str
    expression: str
    frequency: str = "1d"
    dependencies: list[str] = Field(default_factory=list)
    backend: Literal["r2_factor", "d1_l2_factors", "computed"] = "r2_factor"
    online_supported: bool = False
    definition: dict[str, Any] = Field(default_factory=dict)
    # Phase 4A Factor Lab extensions (see docs/data/phase4/01_factor_definition.md):
    # description, factor_type, computation_engine, engine_version, universe,
    # information_policy, schema_version, factor_hash, price_policy, processor_ref


class LabelDefinition(BaseModel):
    code: str
    version: str
    name: str
    expression: str
    horizon: Optional[int] = None
    definition: dict[str, Any] = Field(default_factory=dict)


class ProcessorDefinition(BaseModel):
    code: str
    version: str
    pipeline: list[dict[str, Any]]


class DatasetDefinition(BaseModel):
    code: str
    version: str
    name: str
    frequency: str
    universe_code: str
    universe_version: str
    snapshot_id: str
    schema_version: str
    features: list[str]
    label: Optional[LabelDefinition] = None
    processor: Optional[str] = None  # code@version
    price_policy: PricePolicy = Field(default_factory=PricePolicy)
    pit: bool = True


class DataVersionRef(BaseModel):
    dataset_code: str
    version: str
    checksum: Optional[str] = None
    r2_uri: Optional[str] = None


class SnapshotRef(BaseModel):
    snapshot_id: str
    items: list[DataVersionRef] = Field(default_factory=list)


class ModelArtifact(BaseModel):
    model_code: str
    version: str
    engine: str
    dataset_ref: str  # code@version
    processor_ref: Optional[str] = None
    artifact_uri: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class ExperimentDefinition(BaseModel):
    experiment_id: str
    name: str
    dataset_ref: str
    snapshot_id: str
    dataset_hash: str
    model_version_ref: Optional[str] = None
    mlflow_run_id: Optional[str] = None
    parameters: dict[str, Any] = Field(default_factory=dict)
```

## Trading bridge (research domain; Phase 2E)

```python
class Signal(BaseModel):
    signal_id: str
    instrument_key: str
    trading_date: str
    direction: Literal["LONG", "SHORT", "FLAT"]
    score: float
    signal_time: datetime
    knowledge_time: datetime
    execution_time: datetime
    rank: Optional[int] = None
    confidence: Optional[float] = None
    target_weight: Optional[float] = None
    model_version: str = ""
    strategy_version: str = ""
    dataset_hash: str = ""
    bundle_hash: Optional[str] = None


class TargetPosition(BaseModel):
    instrument_key: str
    trading_date: str
    portfolio_id: str
    strategy_version: str
    dataset_hash: str
    timestamp: datetime
    target_weight: Optional[float] = None
    target_quantity: Optional[float] = None
    signal_id: Optional[str] = None


class OrderIntent(BaseModel):
    instrument_key: str
    side: Literal["BUY", "SELL"]
    quantity: float
    urgency: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"
    execution_algorithm: Literal["MARKET", "LIMIT", "TWAP", "VWAP", "POV", "CUSTOM"] = "MARKET"
    limit_price: Optional[float] = None
    signal_id: Optional[str] = None
    strategy_version: Optional[str] = None
    trading_date: Optional[str] = None
```

Research engines emit `Signal` / `TargetPosition`. `OrderIntent` is contract-only in Phase 2E (no Broker). Portfolio / risk / live execution stay in QuantDinger trading (Phase 3+).
## `dataset_hash` (locked)

```python
import hashlib
import json


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_dataset_hash(
    *,
    dataset_definition: dict[str, Any],
    dataset_version: str,
    snapshot_id: str,
    schema_version: str,
    processor_version: str,
    materializer_version: str,
    price_policy: dict[str, Any],
) -> str:
    """Stable hash for cache dirs and experiment reproducibility.

    Phase 1 does not include adapter_version. When a Qlib Adapter exists,
    fold its version into materializer_version or add an explicit field later.
    """
    payload = "|".join(
        [
            canonical_json(dataset_definition),
            dataset_version,
            snapshot_id,
            schema_version,
            processor_version,
            materializer_version,
            canonical_json(price_policy),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

`price_policy` **must** be in the hash so raw / pre / post adjustment cannot share a cache key.

## DataQuery protocol

`DataQuery` is the **only** research read surface. Future Qlib Adapter calls this — never R2 keys or PG tables directly from research jobs.

```python
Frame = Any  # pandas.DataFrame | pyarrow.Table — implementation choice


class DatasetHandle(BaseModel):
    definition: DatasetDefinition
    snapshot: SnapshotRef
    dataset_hash: str
    manifest_uri: str


class DataQuery(Protocol):
    def market(
        self,
        instrument_keys: Sequence[str],
        start: date,
        end: date,
        frequency: str,
        *,
        price_policy: PricePolicy,
        snapshot_id: Optional[str] = None,
    ) -> Frame:
        """Read Canonical market bars from R2 / local cache. Never live platform APIs."""

    def fundamental(
        self,
        instrument_keys: Sequence[str],
        metrics: Sequence[str],
        knowledge_time: datetime,
        *,
        snapshot_id: Optional[str] = None,
    ) -> Frame:
        """PIT fundamentals: available_time <= knowledge_time."""

    def universe(
        self,
        universe_code: str,
        knowledge_time: datetime,
        *,
        snapshot_id: Optional[str] = None,
        universe_version: Optional[str] = None,
    ) -> list[str]:
        """Historical membership from R2 universe snapshot; not live PG members."""

    def trading_status(
        self,
        instrument_keys: Sequence[str],
        trading_date: date,
        *,
        snapshot_id: Optional[str] = None,
    ) -> Frame: ...

    def corporate_actions(
        self,
        instrument_keys: Sequence[str],
        start: date,
        end: date,
        *,
        snapshot_id: Optional[str] = None,
    ) -> Frame: ...

    def dataset(self, dataset_ref: str) -> DatasetHandle:
        """Resolve code@version (+ bound snapshot) from D1 registry + R2 manifest."""

    def feature(
        self,
        feature_refs: Sequence[str],
        *,
        dataset_ref: str,
        knowledge_time: datetime,
    ) -> Frame:
        """Load feature values via Registry backend (r2_factor / d1_l2_factors / computed)."""
```

### Implementation mapping (for next phase)

| Method | Physical source |
| --- | --- |
| `market` | R2 `qd/canonical/market/` (+ local cache) |
| `fundamental` | R2 `qd/canonical/fundamental/pit/` |
| `universe` | R2 `qd/canonical/universe/` via snapshot |
| `trading_status` | R2 `qd/canonical/trading_status/` |
| `corporate_actions` | R2 `qd/canonical/corporate_action/` |
| `dataset` | D1 `qd_research.dataset` + R2 manifest |
| `feature` | Registry → R2 factor / D1 `l2_factors` / compute on Canonical |

Trading ops UIs may still read PostgreSQL directly. That path is **out of band** for research reproducibility.

## Feature DSL (Phase 1 minimal)

Store QuantDinger expressions, not raw Qlib expression dialect as the protocol.

Allowed starter ops:

```text
Ref(x, n)
Mean(x, n)
Std(x, n)
Rank(x)
ZScore(x)
x / Ref(x, n) - 1
```

Compilation to Qlib / Polars is Adapter responsibility (later).

## Serialization

- Registry rows: JSON TEXT in D1 with `schema_version`
- Large definitions: R2 JSON + digest in D1
- Wire format for APIs (future): same field names as Pydantic models above
