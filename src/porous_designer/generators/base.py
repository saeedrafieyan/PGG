"""Unified porous-generator interface on top of the implicit field kernel.

A generator describes one structure family (its parameters, supported
domains and exports, and limitations) and produces a ``GeneratedField`` for a
given control parameter from a prepared ``FieldModel``. The heavy lifting is
in ``porous_designer.implicit``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from porous_designer.domain.enums import DomainShape, ExportFormat, StructureFamily
from porous_designer.domain.specification import DesignSpecification


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    units: str
    meaning: str


@dataclass
class GeneratedField:
    solid_grid: np.ndarray
    control_parameter: float
    generator_metrics: dict[str, Any]
    field: np.ndarray | None = None


_SPHERE_PARAMETERS = (
    ParameterDefinition("pore_diameter_mm", "mm", "Generating sphere diameter before clipping and overlap."),
    ParameterDefinition("lattice_spacing_mm", "mm", "Nearest-neighbour sphere-centre spacing, tuned to reach the porosity target."),
)
_TPMS_PARAMETERS = (
    ParameterDefinition("unit_cell_size_mm", "mm", "Spatial period of the minimal surface."),
    ParameterDefinition("tpms_variant", "-", "sheet (solid shell around the surface) or network (solid on one side)."),
    ParameterDefinition("wall_thickness_mm", "mm", "Physical sheet thickness; tuned to the porosity target unless fixed."),
    ParameterDefinition("network_offset_mm", "mm", "Network variant: offset of the solid boundary from the surface; tuned unless fixed."),
)
_STRUT_PARAMETERS = (
    ParameterDefinition("unit_cell_size_mm", "mm", "Edge length of the cubic unit cell."),
    ParameterDefinition("wall_thickness_mm", "mm", "Strut diameter; tuned to the porosity target unless fixed."),
)
_VORONOI_PARAMETERS = (
    ParameterDefinition("unit_cell_size_mm", "mm", "Mean cell size (seed spacing)."),
    ParameterDefinition("voronoi_randomness", "-", "Seed jitter: 0 regular, 1 fully random within each cell."),
    ParameterDefinition("wall_thickness_mm", "mm", "Strut diameter; tuned to the porosity target unless fixed."),
)


class PorousGenerator:
    """Descriptor and field adapter for one structure family."""

    def __init__(self, family: StructureFamily) -> None:
        self.family = family
        if family.is_sphere_lattice:
            self.control_parameter = "lattice_spacing_mm"
            self.parameter_definitions = _SPHERE_PARAMETERS
            self.known_limitations = (
                "Throat size is not explicitly measured yet.",
                "Porosity grading is not supported for sphere-pore lattices.",
            )
        elif family.is_tpms:
            self.control_parameter = "tau (sheet thickness / cell) or kappa (network offset / cell)"
            self.parameter_definitions = _TPMS_PARAMETERS
            self.known_limitations = (
                "Wall thickness uses the first-order distance |f|/|grad f|; accuracy decreases for very thick walls.",
                "Boundary truncation can affect connectivity in small specimens.",
            )
        elif family.is_strut_lattice:
            self.control_parameter = "tau (strut diameter / cell)"
            self.parameter_definitions = _STRUT_PARAMETERS
            self.known_limitations = ("Under cell-size grading strut diameters are approximate (warped coordinates).",)
        else:
            self.control_parameter = "tau (strut diameter / cell)"
            self.parameter_definitions = _VORONOI_PARAMETERS
            self.known_limitations = (
                "Cell-size grading is not supported for Voronoi foam.",
                "Stochastic: geometry depends on generation.deterministic_seed.",
            )

    @property
    def monotonic_decreasing(self) -> bool:
        return True

    def validate_specification(self, spec: DesignSpecification) -> None:
        if spec.structure.family != self.family:
            raise ValueError(f"{self.family.value} cannot handle {spec.structure.family.value}")

    def supported_domains(self) -> tuple[DomainShape, ...]:
        return (DomainShape.BOX, DomainShape.CYLINDER, DomainShape.SPHERE, DomainShape.MESH)

    def supported_exports(self) -> tuple[ExportFormat, ...]:
        return (ExportFormat.STL, ExportFormat.THREE_MF, ExportFormat.STEP)

    def describe_parameters(self) -> dict[str, Any]:
        return {
            "family": self.family.value,
            "control_parameter": self.control_parameter,
            "monotonic_decreasing": self.monotonic_decreasing,
            "parameters": [p.__dict__ for p in self.parameter_definitions],
            "supported_domains": [d.value for d in self.supported_domains()],
            "supported_exports": [e.value for e in self.supported_exports()],
            "known_limitations": list(self.known_limitations),
        }

    def generate_field(self, model, control_parameter: float) -> GeneratedField:
        field = model.field(control_parameter)
        solid = (field <= 0.0) & model.inside
        metrics: dict[str, Any] = {"lattice_kind": model.kind, "backend": model.backend_reason}
        if model.kind == "sphere":
            metrics["sphere_center_count"] = model.sphere_center_count()
        else:
            metrics.update(model.thickness_summary(control_parameter))
            unit = model.spec.structure.unit_cell_size_mm
            metrics["unit_cells_per_axis"] = [round(b / unit, 3) for b in model.grid.bounds_mm] if unit else None
        return GeneratedField(solid_grid=solid, control_parameter=control_parameter, generator_metrics=metrics, field=field)
