"""QlibRuntime：封装进程级 qlib.init，禁止业务散落直调。

Qlib 存在全局状态；切换 provider_uri 会重新 init。
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .errors import QlibRuntimeError


class QlibRuntime:
    """进程内唯一推荐的 Qlib 初始化入口。"""

    def __init__(self) -> None:
        self._provider_uri: str | None = None
        self._region: str = "cn"
        self._active: bool = False

    @property
    def is_active(self) -> bool:
        """当前进程是否已成功 activate。"""
        return self._active

    @property
    def provider_uri(self) -> str | None:
        return self._provider_uri

    def activate(
        self,
        provider_uri: str | Path,
        *,
        region: str = "cn",
        kernels: int = 1,
        force: bool = False,
    ) -> None:
        """初始化 / 切换 Qlib LocalProvider。

        Args:
            provider_uri: Materializer 产出的 cache 目录
            region: Qlib region（默认 cn）
            kernels: 并行核数；测试建议 1
            force: 即使 uri 相同也重新 init
        """
        try:
            import qlib
        except ImportError as exc:
            raise QlibRuntimeError("pyqlib is required for QlibRuntime") from exc

        uri = str(Path(provider_uri).resolve())
        if (
            not force
            and self._active
            and self._provider_uri == uri
            and self._region == region
        ):
            return

        try:
            qlib.init(
                provider_uri=uri,
                region=region,
                expression_cache=None,
                dataset_cache=None,
                kernels=kernels,
            )
        except Exception as exc:
            self._active = False
            self._provider_uri = None
            raise QlibRuntimeError(f"qlib.init failed: {exc}") from exc

        self._provider_uri = uri
        self._region = region
        self._active = True

    def require_active(self) -> None:
        """未 activate 时抛错，供 Adapter 其它组件调用前检查。"""
        if not self._active or not self._provider_uri:
            raise QlibRuntimeError("QlibRuntime is not active; call activate() first")

    @contextmanager
    def session(
        self,
        provider_uri: str | Path,
        *,
        region: str = "cn",
        kernels: int = 1,
    ) -> Iterator["QlibRuntime"]:
        """上下文内激活指定 provider；退出不关闭全局状态（Qlib 无干净 teardown）。"""
        self.activate(provider_uri, region=region, kernels=kernels)
        yield self


# 模块级默认实例：Research Job 共用
default_runtime = QlibRuntime()
