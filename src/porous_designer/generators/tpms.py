"""Implicit TPMS generators.

Equations use ``x = 2*pi*X/unit_cell_size`` and likewise for Y/Z.

- Gyroid:   sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x)
- Primitive: cos(x) + cos(y) + cos(z)
- Diamond: sin(x)sin(y)sin(z) + sin(x)cos(y)cos(z)
           + cos(x)sin(y)cos(z) + cos(x)cos(y)sin(z)

The control parameter is a dimensionless sheet half-thickness around the zero
level set: solid where ``abs(phi) <= level_set``. Increasing the level set
increases solid fraction and therefore decreases porosity.
"""

from __future__ import annotations

import math

import numpy as np

from porous_designer.domain.enums import StructureFamily
from porous_designer.domain.specification import DesignSpecification
from porous_designer.generators.base import GeneratedField, ParameterDefinition, PorousGenerator
from porous_designer.geometry.domains import DomainGrid, unit_cells_per_axis


class TPMSGenerator(PorousGenerator):
    control_parameter = "tpms_level_set"
    monotonic_decreasing = True
    parameter_definitions = (
        ParameterDefinition(
            "unit_cell_size_mm",
            "mm",
            "Spatial periodicity of the implicit TPMS field.",
        ),
        ParameterDefinition(
            "tpms_level_set",
            "dimensionless",
            "Half-thickness around the zero implicit surface; larger means more solid.",
        ),
    )
    known_limitations = (
        "No exact pore diameter is reported for TPMS structures in Phase 2B.",
        "STEP export is unsupported for implicit TPMS structures.",
        "Boundary truncation can affect connectivity in small specimens.",
    )

    def default_search_interval(self, spec: DesignSpecification) -> tuple[float, float]:
        return (0.02, 1.25)

    def _field(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def generate_voxels(
        self,
        spec: DesignSpecification,
        domain_grid: DomainGrid,
        control_parameter: float,
    ) -> GeneratedField:
        unit = spec.structure.unit_cell_size_mm
        if unit is None:
            raise ValueError(f"{self.family.value} requires unit_cell_size_mm")
        nx, ny, nz = domain_grid.grid_shape
        voxel = domain_grid.voxel_mm
        gx = (np.arange(nx) + 0.5) * voxel
        gy = (np.arange(ny) + 0.5) * voxel
        gz = (np.arange(nz) + 0.5) * voxel
        k = 2.0 * math.pi / unit
        field = self._field(gx[:, None, None] * k, gy[None, :, None] * k, gz[None, None, :] * k)
        solid = (np.abs(field) <= control_parameter) & domain_grid.mask
        return GeneratedField(
            solid_grid=solid,
            control_parameter=control_parameter,
            generator_metrics={
                "unit_cells_per_axis": unit_cells_per_axis(spec.domain, unit),
                "boundary_truncation": True,
                "implicit_equation": self.__class__.__name__,
            },
        )


class GyroidGenerator(TPMSGenerator):
    family = StructureFamily.GYROID

    def _field(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
        return np.sin(x) * np.cos(y) + np.sin(y) * np.cos(z) + np.sin(z) * np.cos(x)


class PrimitiveGenerator(TPMSGenerator):
    family = StructureFamily.PRIMITIVE

    def _field(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
        return np.cos(x) + np.cos(y) + np.cos(z)


class DiamondGenerator(TPMSGenerator):
    family = StructureFamily.DIAMOND

    def _field(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
        return (
            np.sin(x) * np.sin(y) * np.sin(z)
            + np.sin(x) * np.cos(y) * np.cos(z)
            + np.cos(x) * np.sin(y) * np.cos(z)
            + np.cos(x) * np.cos(y) * np.sin(z)
        )
