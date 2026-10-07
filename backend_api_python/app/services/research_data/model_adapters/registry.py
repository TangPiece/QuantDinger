"""ModelAdapterRegistry：按 framework/algorithm 解析适配器。"""

from __future__ import annotations

from typing import Any, Callable

from .errors import ModelAdapterError
from .protocol import ModelAdapter


class ModelAdapterRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[..., ModelAdapter]] = {}

    def register(self, key: str, factory: Callable[..., ModelAdapter]) -> None:
        self._factories[str(key or "").strip().upper()] = factory

    def get(self, key: str, **kwargs: Any) -> ModelAdapter:
        k = str(key or "").strip().upper()
        if not k or k not in self._factories:
            raise ModelAdapterError(
                f"no adapter registered for: {key!r}",
                failure_class="CONFIG_ERROR",
                stage="PREPARING",
            )
        return self._factories[k](**kwargs)

    def resolve(
        self,
        *,
        framework: str = "",
        algorithm: str = "",
        **kwargs: Any,
    ) -> ModelAdapter:
        for candidate in (framework, algorithm, "LIGHTGBM"):
            k = str(candidate or "").strip().upper()
            if k in self._factories:
                return self._factories[k](**kwargs)
            # lightgbm ↔ LIGHTGBM
            if k == "LIGHTGBM" and "LIGHTGBM" in self._factories:
                return self._factories["LIGHTGBM"](**kwargs)
            if k.replace("-", "").replace("_", "") == "LIGHTGBM" and "LIGHTGBM" in self._factories:
                return self._factories["LIGHTGBM"](**kwargs)
        raise ModelAdapterError(
            f"no adapter for framework={framework!r} algorithm={algorithm!r}",
            failure_class="CONFIG_ERROR",
            stage="PREPARING",
        )

    def keys(self) -> list[str]:
        return sorted(self._factories)


_DEFAULT: ModelAdapterRegistry | None = None


def default_adapter_registry() -> ModelAdapterRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        from .qlib_model_adapter import QlibModelAdapter

        reg = ModelAdapterRegistry()
        reg.register("LIGHTGBM", lambda **kw: QlibModelAdapter(**kw))
        reg.register("QLIB", lambda **kw: QlibModelAdapter(**kw))
        _DEFAULT = reg
    return _DEFAULT


__all__ = ["ModelAdapterRegistry", "default_adapter_registry"]
