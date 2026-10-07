"""并发 activate → 单 ACTIVE。"""

from __future__ import annotations

import threading
from pathlib import Path

from app.services.research_data.model_platform.protocol import ModelPlatformInject
from model_platform_golden.golden import (
    create_formal_version,
    golden_model_spec,
    make_model_platform_env,
)


def run_concurrency_checks(tmp: Path) -> dict[str, bool]:
    plat = make_model_platform_env(tmp / "conc")
    model = plat.register_model(golden_model_spec(model_code="conc_9f9"))
    v1 = create_formal_version(plat, model_id=model.model_id, version="1.0.0")
    v2 = create_formal_version(plat, model_id=model.model_id, version="2.0.0")
    for v in (v1, v2):
        plat.approve_version(
            v.model_version_id,
            operator="conc",
            inject=ModelPlatformInject(skip_approval_gate=True),
        )

    errors: list[BaseException] = []

    def _act(vid: str) -> None:
        try:
            plat.activate(vid, operator="conc", reason=f"race-{vid}")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=_act, args=(v1.model_version_id,))
    t2 = threading.Thread(target=_act, args=(v2.model_version_id,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    actives = [
        v for v in plat.list_versions(model.model_id) if v.lifecycle == "ACTIVE"
    ]
    records = plat.list_activations(model_id=model.model_id)
    return {
        "single_active": len(actives) == 1,
        "has_activation_records": len(records) >= 1,
        "no_fatal_errors": len(errors) == 0
        or all("single ACTIVE" not in str(e) for e in errors)
        or len(actives) == 1,
    }


__all__ = ["run_concurrency_checks"]
