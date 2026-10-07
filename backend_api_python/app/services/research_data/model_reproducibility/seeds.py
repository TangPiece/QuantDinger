"""SeedBundle 记录（不强制应用全局 RNG；训练侧自行消费）。"""

from __future__ import annotations

from .protocol import SeedBundle


def build_seed_bundle(master_seed: int = 0, *, torch: bool = False) -> SeedBundle:
    seed = int(master_seed or 0)
    data: dict = {
        "master_seed": seed,
        "python_seed": seed,
        "numpy_seed": seed,
        "qlib_seed": seed,
        "framework_seed": seed,
        "model_seed": seed,
    }
    if torch:
        data["torch_seed"] = seed
        data["torch_cuda_seed"] = seed
    return SeedBundle.model_validate(data)


def seed_match(a: SeedBundle, b: SeedBundle) -> bool:
    return (
        a.master_seed == b.master_seed
        and a.python_seed == b.python_seed
        and a.numpy_seed == b.numpy_seed
        and a.qlib_seed == b.qlib_seed
        and a.framework_seed == b.framework_seed
        and a.model_seed == b.model_seed
    )


__all__ = ["build_seed_bundle", "seed_match"]
