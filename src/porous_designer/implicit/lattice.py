"""Thickness-independent lattice distances.

For every implicit family the expensive part of the field does not depend on
wall thickness: it is a distance ``D`` (in cell units) from each point to the
lattice's skeleton - the minimal surface for TPMS, the strut axes for strut
lattices and Voronoi foam. The final lattice field in millimetres is then a
cheap expression of ``D``, the local cell size ``L`` and the (possibly
graded) normalised thickness ``tau``:

* sheet TPMS, struts, foam: ``L * (D - tau / 2)``   (D >= 0)
* network TPMS:            ``L * (D_signed - kappa)``

which is what makes porosity tuning fast and wall thickness physical.
"""

from __future__ import annotations

import math

import numpy as np

from porous_designer.domain.enums import StructureFamily, TPMSVariant
from porous_designer.implicit.grading import CellWarp
from porous_designer.implicit.struts import STRUT_KINDS, strut_distance
from porous_designer.implicit.tpms import SURFACES

TWO_PI = 2.0 * math.pi
_EPS = 1e-12


def lattice_kind(family: StructureFamily, variant: TPMSVariant) -> str:
    if family.is_tpms:
        return "tpms_network" if variant == TPMSVariant.NETWORK else "tpms_sheet"
    if family.is_strut_lattice:
        return "strut"
    if family.is_stochastic:
        return "voronoi"
    return "sphere"


def tpms_distance(ops, family: StructureFamily, warp: CellWarp, X, *, signed: bool):
    """Normalised distance to the TPMS surface and the local cell size."""
    u, L, shear = warp.to_cell(ops, X)
    f, gx, gy, gz = SURFACES[family](ops, *(TWO_PI * c for c in u))
    gu = [TWO_PI * gx, TWO_PI * gy, TWO_PI * gz]
    if shear is None:
        norm = ops.sqrt(gu[0] * gu[0] + gu[1] * gu[1] + gu[2] * gu[2]) / L
    else:
        a = warp.axis
        comps = []
        for i in range(3):
            if i == a:
                comp = gu[a] / L
                for b, s in shear.items():
                    comp = comp + gu[b] * s
            else:
                comp = gu[i] / L
            comps.append(comp)
        norm = ops.sqrt(comps[0] * comps[0] + comps[1] * comps[1] + comps[2] * comps[2])
    d_mm = f / (norm + _EPS)
    d_norm = d_mm / L
    return (d_norm if signed else ops.abs(d_norm)), L


def strut_lattice_distance(ops, family: StructureFamily, warp: CellWarp, X):
    u, L, _ = warp.to_cell(ops, X)
    return strut_distance(ops, STRUT_KINDS[family], *u), L


def periodic_cell_distance(family: StructureFamily, variant: TPMSVariant, n: int = 48) -> np.ndarray:
    """Normalised distance on one periodic unit cell (for calibration)."""
    from porous_designer.implicit.backend import NumpyOps

    ops = NumpyOps()
    c = (np.arange(n) + 0.5) / n
    X = np.meshgrid(c, c, c, indexing="ij")
    warp = CellWarp(base_cell_mm=1.0)
    kind = lattice_kind(family, variant)
    if kind in ("tpms_sheet", "tpms_network"):
        d, _ = tpms_distance(ops, family, warp, X, signed=kind == "tpms_network")
    elif kind == "strut":
        d, _ = strut_lattice_distance(ops, family, warp, X)
    else:
        raise ValueError(f"{family.value} has no periodic cell")
    return np.asarray(d, dtype=np.float32)
