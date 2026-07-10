"""Deterministic bounded porosity tuning via bisection."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np


@dataclass
class TuningIteration:
    iteration: int
    parameter_mm: float
    estimated_porosity: float
    residual: float
    runtime_s: float


@dataclass
class TuningResult:
    parameter_mm: float
    estimated_porosity: float
    converged: bool
    reachable: bool
    monotonic: bool
    iterations: list[TuningIteration] = field(default_factory=list)
    message: str = ""


def check_monotonicity(
    eval_fn: Callable[[float], float],
    lo: float,
    hi: float,
    *,
    decreasing: bool,
    samples: int = 8,
) -> bool:
    """Verify porosity vs parameter is monotonic on [lo, hi]."""
    params = np.linspace(lo, hi, samples)
    values = [eval_fn(float(p)) for p in params]
    diffs = np.diff(values)
    if decreasing:
        return bool(np.all(diffs <= 1e-6))
    return bool(np.all(diffs >= -1e-6))


def bisection_solve(
    target_porosity: float,
    eval_fn: Callable[[float], float],
    lo: float,
    hi: float,
    *,
    decreasing: bool = True,
    tolerance: float = 0.003,
    max_iterations: int = 40,
) -> TuningResult:
    """Find parameter in [lo, hi] such that eval_fn(param) ≈ target_porosity.

    For sphere lattices, porosity *decreases* as lattice spacing increases.
    """
    iterations: list[TuningIteration] = []
    monotonic = check_monotonicity(eval_fn, lo, hi, decreasing=decreasing)

    p_lo = eval_fn(lo)
    p_hi = eval_fn(hi)
    if decreasing:
        reachable = p_hi <= target_porosity <= p_lo
    else:
        reachable = p_lo <= target_porosity <= p_hi

    if not reachable:
        return TuningResult(
            parameter_mm=0.5 * (lo + hi),
            estimated_porosity=eval_fn(0.5 * (lo + hi)),
            converged=False,
            reachable=False,
            monotonic=monotonic,
            message="Target porosity outside achievable range on search interval.",
        )

    best_param = 0.5 * (lo + hi)
    best_porosity = eval_fn(best_param)
    converged = False

    for i in range(max_iterations):
        t0 = time.perf_counter()
        mid = 0.5 * (lo + hi)
        porosity = eval_fn(mid)
        dt = time.perf_counter() - t0
        residual = porosity - target_porosity
        iterations.append(
            TuningIteration(
                iteration=i,
                parameter_mm=mid,
                estimated_porosity=porosity,
                residual=residual,
                runtime_s=dt,
            )
        )
        best_param = mid
        best_porosity = porosity
        if abs(residual) <= tolerance:
            converged = True
            break
        too_porous = porosity > target_porosity
        if (too_porous and decreasing) or (not too_porous and not decreasing):
            lo = mid
        else:
            hi = mid

    msg = "Converged within tolerance." if converged else (
        f"Did not converge within {max_iterations} iterations (tolerance={tolerance})."
    )
    return TuningResult(
        parameter_mm=best_param,
        estimated_porosity=best_porosity,
        converged=converged,
        reachable=True,
        monotonic=monotonic,
        iterations=iterations,
        message=msg,
    )
