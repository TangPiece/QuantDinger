"""factor_hash：定义可追溯内容指纹。"""

from __future__ import annotations

import hashlib

from app.services.research_data.contracts import FeatureDefinition, PricePolicy
from app.services.research_data.hashing import canonical_json

from .version import FACTOR_LAB_CONTRACT_VERSION


def compute_factor_hash(feature: FeatureDefinition) -> str:
    """对 Factor/Feature 定义做内容寻址 hash。

    覆盖：expression、schema、dependencies、processor、price_policy、engine 等。
    """
    pp = feature.price_policy
    if pp is None:
        pp_dump = PricePolicy().model_dump(mode="json")
    else:
        pp_dump = pp.model_dump(mode="json")
    deps = sorted(str(d) for d in (feature.dependencies or []))
    payload = {
        "code": feature.code,
        "version": feature.version,
        "expression": feature.expression,
        "schema_version": feature.schema_version,
        "dependencies": deps,
        "processor_ref": feature.processor_ref or "",
        "price_policy": pp_dump,
        "computation_engine": feature.computation_engine,
        "engine_version": feature.engine_version or "",
        "factor_type": feature.factor_type,
        "frequency": feature.frequency,
        "information_policy": feature.information_policy,
        "contract_version": FACTOR_LAB_CONTRACT_VERSION,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
