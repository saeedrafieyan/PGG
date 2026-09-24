"""Porosity as a function of normalised thickness, per family.

Computed once on a periodic unit cell (or a representative block for
Voronoi foam) and cached. Used to

* bracket the tuning interval tightly,
* turn a graded porosity target into a local thickness field
  ``tau(x) = g^-1(p(x))``, and
* report the achievable porosity range before any geometry is generated.

The parameter is ``tau = t / L`` for sheets and struts (t = sheet thickness
or strut diameter) and ``kappa = c / L`` for network TPMS (c = offset).
Porosity decreases monotonically with the parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from porous_designer.domain.enums import StructureFamily, TPMSVariant
from porous_designer.implicit.lattice import lattice_kind, periodic_cell_distance


@dataclass(frozen=True)
class CalibrationCurve:
    family: StructureFamily
    variant: TPMSVariant
    parameter_name: str
    parameters: np.ndarray  # increasing
    porosity: np.ndarray  # non-increasing

    @property
    def porosity_range(self) -> tuple[float, float]:
        return float(self.porosity.min()), float(self.porosity.max())

    def porosity_at(self, parameter) -> np.ndarray:
        return np.interp(parameter, self.parameters, self.porosity)

    def parameter_for(self, porosity) -> np.ndarray:
        """Inverse map; porosity outside the reachable range is clamped."""
        p = np.asarray(porosity, dtype=np.float64)
        # np.interp needs increasing x: porosity is non-increasing in the parameter.
        x = self.porosity[::-1]
        y = self.parameters[::-1]
        x, idx = np.unique(x, return_index=True)
        return np.interp(p, x, y[idx]).astype(np.float32)


def _monotone(porosity: np.ndarray) -> np.ndarray:
    return np.minimum.accumulate(porosity)


@lru_cache(maxsize=None)
def periodic_calibration(family: StructureFamily, variant: TPMSVariant) -> CalibrationCurve:
    kind = lattice_kind(family, variant)
    d = periodic_cell_distance(family, variant).ravel()
    if kind == "tpms_network":
        params = np.linspace(-0.6, 0.6, 121)
        porosity = np.array([(d > k).mean() for k in params])
        name = "kappa"
    else:
        params = np.linspace(0.0, 1.2, 241)
        porosity = np.array([(d > t / 2.0).mean() for t in params])
        name = "tau"
    return CalibrationCurve(family, variant, name, params, _monotone(porosity))


@lru_cache(maxsize=32)
def voronoi_calibration(randomness: float, seed: int) -> CalibrationCurve:
    """Porosity vs normalised strut diameter on a 4x4x4-cell block (interior 2x2x2)."""
    from porous_designer.implicit.stochastic import voronoi_edge_distance, voronoi_network

    cells = 4
    n_per_cell = 24
    network = voronoi_network((float(cells),) * 3, 1.0, randomness, seed, sample_step_mm=1.0 / (2 * n_per_cell))
    c = (np.arange(2 * n_per_cell) + 0.5) / n_per_cell + 1.0  # interior [1, 3]
    pts = np.stack(np.meshgrid(c, c, c, indexing="ij"), axis=-1).reshape(-1, 3)
    d = voronoi_edge_distance(pts, network, reach_mm=0.8)
    params = np.linspace(0.0, 1.2, 241)
    porosity = np.array([(d > t / 2.0).mean() for t in params])
    return CalibrationCurve(StructureFamily.VORONOI_FOAM, TPMSVariant.SHEET, "tau", params, _monotone(porosity))


def calibration_for(family: StructureFamily, variant: TPMSVariant, *, randomness: float = 1.0, seed: int = 42) -> CalibrationCurve:
    if family.is_stochastic:
        return voronoi_calibration(round(float(randomness), 3), int(seed))
    return periodic_calibration(family, variant)
