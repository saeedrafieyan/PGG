"""Array backends for field evaluation (NumPy on CPU, PyTorch on CUDA).

Field code is written once against the small ``ArrayOps`` surface below, so
the same equations run on either device. Results always come back as NumPy
``float32`` arrays.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

# Grids smaller than this are evaluated on the CPU even in "auto" mode; the
# transfer overhead dominates for small problems.
AUTO_CUDA_MIN_POINTS = 2_000_000


class NumpyOps:
    name = "numpy"
    device = "cpu"

    def asarray(self, a: Any):
        return np.asarray(a, dtype=np.float32)

    def to_numpy(self, a) -> np.ndarray:
        return np.asarray(a, dtype=np.float32)

    sin = staticmethod(np.sin)
    cos = staticmethod(np.cos)
    sqrt = staticmethod(np.sqrt)
    abs = staticmethod(np.abs)
    maximum = staticmethod(np.maximum)
    minimum = staticmethod(np.minimum)
    where = staticmethod(np.where)
    floor = staticmethod(np.floor)
    log = staticmethod(np.log)

    def clip(self, a, lo, hi):
        return np.clip(a, lo, hi)

    def sort_desc_last(self, a):
        return -np.sort(-a, axis=-1)

    def stack_last(self, arrays):
        return np.stack(arrays, axis=-1)

    def full_like(self, a, value):
        return np.full_like(a, value, dtype=np.float32)


class TorchOps:
    name = "torch"

    def __init__(self, device: str = "cuda") -> None:
        import torch

        self.torch = torch
        self.device = device

    def asarray(self, a: Any):
        return self.torch.as_tensor(np.asarray(a, dtype=np.float32), device=self.device)

    def to_numpy(self, a) -> np.ndarray:
        if isinstance(a, self.torch.Tensor):
            return a.detach().to("cpu").numpy().astype(np.float32, copy=False)
        return np.asarray(a, dtype=np.float32)

    def sin(self, a):
        return self.torch.sin(a)

    def cos(self, a):
        return self.torch.cos(a)

    def sqrt(self, a):
        return self.torch.sqrt(a)

    def abs(self, a):
        return self.torch.abs(a)

    def maximum(self, a, b):
        return self.torch.maximum(self._t(a), self._t(b))

    def minimum(self, a, b):
        return self.torch.minimum(self._t(a), self._t(b))

    def where(self, c, a, b):
        return self.torch.where(c, self._t(a), self._t(b))

    def floor(self, a):
        return self.torch.floor(a)

    def log(self, a):
        return self.torch.log(a)

    def clip(self, a, lo, hi):
        return self.torch.clamp(a, lo, hi)

    def sort_desc_last(self, a):
        return self.torch.sort(a, dim=-1, descending=True).values

    def stack_last(self, arrays):
        return self.torch.stack(arrays, dim=-1)

    def full_like(self, a, value):
        return self.torch.full_like(a, float(value))

    def _t(self, a):
        if isinstance(a, self.torch.Tensor):
            return a
        return self.torch.as_tensor(a, dtype=self.torch.float32, device=self.device)


@dataclass(frozen=True)
class BackendChoice:
    ops: Any
    reason: str

    @property
    def name(self) -> str:
        return self.ops.name


def cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def select_backend(requested: str = "auto", point_count: int = 0) -> BackendChoice:
    """Pick the evaluation backend; never fails, falls back to NumPy."""
    if requested == "cpu":
        return BackendChoice(NumpyOps(), "cpu requested")
    if requested == "cuda":
        if cuda_available():
            return BackendChoice(TorchOps("cuda"), "cuda requested")
        return BackendChoice(NumpyOps(), "cuda requested but unavailable; using cpu")
    if point_count >= AUTO_CUDA_MIN_POINTS and cuda_available():
        return BackendChoice(TorchOps("cuda"), f"auto: {point_count} points on cuda")
    return BackendChoice(NumpyOps(), "auto: cpu")
