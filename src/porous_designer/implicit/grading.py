"""Spatial grading of porosity and cell size.

``normalized_coordinate`` maps every voxel to s in [0, 1] according to a
``GradingSpec`` (linear along an axis, radial from the centre line, or depth
below the domain surface). Graded quantities are ``start + (end - start) s``.

Cell-size grading warps the lattice coordinates along one axis. With the
cell size ``L(X_a)`` varying linearly along axis ``a`` the phase along that
axis is ``theta(X_a) = integral dX / L(X)``, and the other axes are scaled by
the local cell size around the domain centre, which keeps cells close to
cubic. The Jacobian of that map is returned so implicit-surface distances can
still be expressed in millimetres.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from porous_designer.domain.enums import GradingMode
from porous_designer.domain.specification import GradingSpec

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def normalized_coordinate(grading: GradingSpec, points: tuple[np.ndarray, np.ndarray, np.ndarray], extents: tuple[float, float, float], domain_sdf: np.ndarray | None) -> np.ndarray:
    a = AXIS_INDEX[grading.axis]
    if grading.mode == GradingMode.LINEAR:
        s = points[a] / max(extents[a], 1e-12)
    elif grading.mode == GradingMode.RADIAL:
        others = [i for i in range(3) if i != a]
        r2 = sum((points[i] - extents[i] / 2.0) ** 2 for i in others)
        r_max = np.sqrt(sum((extents[i] / 2.0) ** 2 for i in others))
        s = np.sqrt(r2) / max(r_max, 1e-12)
    else:
        if domain_sdf is None:
            raise ValueError("surface_distance grading needs the domain distance field.")
        s = -domain_sdf / float(grading.depth_mm)
    return np.clip(s, 0.0, 1.0).astype(np.float32)


def graded_value(grading: GradingSpec, s: np.ndarray) -> np.ndarray:
    return (grading.start + (grading.end - grading.start) * s).astype(np.float32)


@dataclass(frozen=True)
class CellWarp:
    """Linear cell-size variation along one axis (or uniform cells)."""

    base_cell_mm: float
    axis: int | None = None
    start_mm: float | None = None
    end_mm: float | None = None
    extent_mm: float | None = None
    centers_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @classmethod
    def from_spec(cls, unit_cell_mm: float, grading: GradingSpec | None, extents: tuple[float, float, float]) -> "CellWarp":
        if grading is None:
            return cls(base_cell_mm=unit_cell_mm)
        a = AXIS_INDEX[grading.axis]
        centers = tuple(e / 2.0 for e in extents)
        return cls(base_cell_mm=unit_cell_mm, axis=a, start_mm=float(grading.start), end_mm=float(grading.end), extent_mm=float(extents[a]), centers_mm=centers)  # type: ignore[arg-type]

    @property
    def uniform(self) -> bool:
        return self.axis is None

    def cell_size(self, ops, X):
        """Local cell size L at each point (array or scalar)."""
        if self.uniform:
            return self.base_cell_mm
        s = ops.clip(X[self.axis] / self.extent_mm, 0.0, 1.0)
        return self.start_mm + (self.end_mm - self.start_mm) * s

    def to_cell(self, ops, X):
        """Cell coordinates u (period 1) and the terms of the Jacobian dU/dX.

        Returns ``(u, L, shear)`` where ``shear[b] = du_b/dX_a`` for the
        warped axis ``a`` (None when cells are uniform).
        """
        if self.uniform:
            L = self.base_cell_mm
            return tuple(c / L for c in X), L, None
        a = self.axis
        L0, L1, E = self.start_mm, self.end_mm, self.extent_mm
        Xa = ops.clip(X[a], 0.0, E)
        L = L0 + (L1 - L0) * Xa / E
        if abs(L1 - L0) < 1e-12:
            theta = X[a] / L0
        else:
            theta = (E / (L1 - L0)) * ops.log(L / L0)
            # beyond the domain the phase continues linearly (never sampled for solid)
            theta = theta + (X[a] - Xa) / L
        dL = (L1 - L0) / E
        u = []
        shear = {}
        for b in range(3):
            if b == a:
                u.append(theta)
            else:
                rel = X[b] - self.centers_mm[b]
                u.append(rel / L)
                shear[b] = -rel * dL / (L * L)
        return tuple(u), L, shear
