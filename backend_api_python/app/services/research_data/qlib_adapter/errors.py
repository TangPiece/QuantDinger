"""Qlib Adapter 错误类型。"""

from __future__ import annotations


class QlibAdapterError(RuntimeError):
    """Adapter 通用失败。"""


class QlibRuntimeError(QlibAdapterError):
    """QlibRuntime 未激活或 init 失败。"""


class UnsupportedFeatureError(QlibAdapterError, ValueError):
    """Feature 表达式不在 Phase 2A 白名单内。"""


class UnsupportedProcessorError(QlibAdapterError, ValueError):
    """Processor 步骤不在 Phase 2A 白名单内。"""


class VersionResolveError(QlibAdapterError):
    """VersionResolver 无法解析引用。"""
