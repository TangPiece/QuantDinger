"""进程内 Prometheus 风格 counter；禁止 symbol 作为 label。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

_FORBIDDEN_LABELS = frozenset({"symbol", "instrument", "instrument_key"})


def allowed_label_keys() -> frozenset[str]:
    return frozenset({"broker", "account", "strategy"})


def _normalize_labels(labels: Mapping[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (labels or {}).items():
        key = str(k).lower()
        if key in _FORBIDDEN_LABELS:
            continue
        if key not in allowed_label_keys():
            continue
        out[key] = str(v)
    return out


def increment_counter(
    registry: "MetricsRegistry",
    name: str,
    *,
    value: float = 1.0,
    labels: Mapping[str, str] | None = None,
) -> None:
    """递增 counter；非法 label 静默丢弃。"""
    registry.increment(name, value=value, labels=_normalize_labels(labels))


@dataclass
class MetricsRegistry:
    """简单 counter 存储 + 文本导出。"""

    _counters: dict[str, float] = field(default_factory=dict)

    def _key(self, name: str, labels: dict[str, str]) -> str:
        parts = [name] + [f'{k}="{labels[k]}"' for k in sorted(labels)]
        return "|".join(parts)

    def increment(
        self,
        name: str,
        *,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        lab = _normalize_labels(labels)
        k = self._key(name, lab)
        self._counters[k] = float(self._counters.get(k, 0.0) + value)

    def snapshot(self) -> dict[str, float]:
        return dict(self._counters)

    def prometheus_text(self) -> str:
        """导出为 comment 风格行（非完整 Prometheus 解析器）。"""
        lines: list[str] = []
        for k, v in sorted(self._counters.items()):
            lines.append(f"# TYPE {k.split('|', 1)[0]} counter")
            lines.append(f"{k.replace('|', '{', 1)} {v}" if "|" in k else f"{k} {v}")
        return "\n".join(lines)
