"""Qt-facing structured specification model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Signal
from pydantic import ValidationError

from porous_designer.domain.enums import DomainShape, StructureFamily
from porous_designer.domain.specification import (
    ConstraintsSpec,
    DesignSpecification,
    DomainSpec,
    ExportSpec,
    GenerationSpec,
    PorosityTarget,
    StructureSpec,
    TargetsSpec,
)


SPHERE_FAMILIES = {
    StructureFamily.SC_SPHERICAL_PORES,
    StructureFamily.BCC_SPHERICAL_PORES,
    StructureFamily.FCC_SPHERICAL_PORES,
    StructureFamily.HCP_SPHERICAL_PORES,
}
TPMS_FAMILIES = {StructureFamily.GYROID, StructureFamily.DIAMOND, StructureFamily.PRIMITIVE}


@dataclass
class FieldIssue:
    field: str
    status: str
    message: str


class SpecificationModel(QObject):
    """Converts form fields into the authoritative Pydantic model."""

    changed = Signal(object)
    validation_changed = Signal(list)

    def __init__(self, spec: DesignSpecification, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._spec = spec
        self._issues: list[FieldIssue] = []

    @property
    def specification(self) -> DesignSpecification:
        return self._spec

    @property
    def issues(self) -> list[FieldIssue]:
        return self._issues

    @property
    def has_invalid_fields(self) -> bool:
        return any(i.status == "invalid" for i in self._issues)

    def update_from_fields(self, data: dict[str, Any]) -> DesignSpecification | None:
        try:
            family = StructureFamily(data["family"])
            dims = (
                [data["box_x"], data["box_y"], data["box_z"]]
                if data["domain_shape"] == DomainShape.BOX.value
                else [data["cylinder_diameter"], data["cylinder_height"]]
            )
            structure = StructureSpec(
                family=family,
                pore_diameter_mm=data["pore_diameter"] if family in SPHERE_FAMILIES else None,
                unit_cell_size_mm=data["unit_cell_size"] if family in TPMS_FAMILIES else None,
                lattice_spacing_mm=data.get("lattice_spacing") or None,
                tpms_level_set=data.get("tpms_level_set") or None,
                periodicity=bool(data.get("periodicity", True)),
            )
            spec = DesignSpecification(
                source_text=data.get("source_text", ""),
                domain=DomainSpec(
                    shape=DomainShape(data["domain_shape"]),
                    dimensions_mm=[float(x) for x in dims],
                    orientation=data.get("axis", "z_up"),
                ),
                structure=structure,
                targets=TargetsSpec(
                    porosity_target=PorosityTarget(
                        target=float(data["porosity_target"]),
                        tolerance=float(data["porosity_tolerance"]),
                    ),
                    wall_target_mm=data.get("minimum_wall_thickness") or None,
                    throat_target_mm=data.get("minimum_throat_size") or None,
                ),
                constraints=ConstraintsSpec(
                    require_open_pores=bool(data.get("require_open_pores", True)),
                    require_single_solid_component=bool(data.get("require_single_solid_component", True)),
                    minimum_wall_thickness_mm=data.get("minimum_wall_thickness") or None,
                    minimum_throat_size_mm=data.get("minimum_throat_size") or None,
                    maximum_file_size_mb=data.get("maximum_file_size_mb") or None,
                ),
                generation=GenerationSpec(
                    preview_resolution_mm=float(data["preview_resolution"]),
                    final_resolution_mm=float(data["final_resolution"]),
                    reference_resolution_mm=float(data.get("reference_resolution") or data["final_resolution"]),
                    maximum_memory_gb=float(data["maximum_memory_gb"]),
                    maximum_runtime_s=float(data["maximum_runtime_s"]),
                ),
                export=ExportSpec(
                    output_directory=data["output_directory"],
                    output_name=data["output_name"],
                ),
            )
            self._spec = spec
            self._issues = self._soft_issues(spec)
            self.changed.emit(spec)
            self.validation_changed.emit(self._issues)
            return spec
        except (ValidationError, ValueError, TypeError) as exc:
            self._issues = [FieldIssue("specification", "invalid", str(exc))]
            self.validation_changed.emit(self._issues)
            return None

    def _soft_issues(self, spec: DesignSpecification) -> list[FieldIssue]:
        issues: list[FieldIssue] = []
        smallest = min(spec.domain.dimensions_mm)
        if spec.generation.final_resolution_mm > smallest / 40.0:
            issues.append(
                FieldIssue(
                    "final_resolution",
                    "warning",
                    "Final resolution is coarse for curved or implicit boundaries.",
                )
            )
        if spec.structure.family in SPHERE_FAMILIES and spec.structure.pore_diameter_mm:
            if spec.structure.pore_diameter_mm > smallest:
                issues.append(FieldIssue("pore_diameter", "invalid", "Pore diameter exceeds smallest domain dimension."))
            elif spec.structure.pore_diameter_mm > smallest / 2:
                issues.append(FieldIssue("pore_diameter", "warning", "Pore diameter is large relative to the sample."))
        if spec.structure.family in TPMS_FAMILIES and spec.structure.unit_cell_size_mm:
            cells = smallest / spec.structure.unit_cell_size_mm
            if cells < 2:
                issues.append(FieldIssue("unit_cell_size", "warning", "Fewer than two unit cells span the sample."))
        issues.append(FieldIssue("step_export", "unsupported", "STEP export is disabled in Phase 3A. STL only."))
        if spec.constraints.minimum_wall_thickness_mm:
            issues.append(FieldIssue("minimum_wall_thickness", "unsupported", "Wall-thickness validation is not yet available."))
        if spec.constraints.minimum_throat_size_mm:
            issues.append(FieldIssue("minimum_throat_size", "unsupported", "Throat-size validation is not yet available."))
        return issues
