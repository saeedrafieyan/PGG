"""Tests for porosity bisection solver."""

import pytest

from porous_designer.tuning.porosity_solver import bisection_solve, check_monotonicity


def test_monotonic_decreasing():
    fn = lambda s: 0.95 - 0.2 * s  # decreasing in s
    assert check_monotonicity(fn, 0.5, 2.0, decreasing=True)


def test_bisection_converges():
    fn = lambda s: 0.8 - 0.1 * (s - 1.0)  # porosity decreases with spacing
    result = bisection_solve(0.77, fn, 0.5, 1.5, decreasing=True, tolerance=0.001)
    assert result.reachable
    assert result.converged
    assert result.estimated_porosity == pytest.approx(0.77, abs=0.01)
    assert len(result.iterations) >= 1


def test_unreachable_target():
    fn = lambda s: 0.5  # constant — target 0.8 unreachable
    result = bisection_solve(0.8, fn, 0.5, 1.5, decreasing=True)
    assert not result.reachable
    assert not result.converged


def test_iterations_recorded():
    fn = lambda s: 0.9 - 0.2 * s
    result = bisection_solve(0.5, fn, 0.5, 2.0, decreasing=True, tolerance=0.01, max_iterations=20)
    assert len(result.iterations) >= 1
    for it in result.iterations:
        assert it.runtime_s >= 0
