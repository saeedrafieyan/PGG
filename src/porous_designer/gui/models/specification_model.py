"""Qt-facing structured specification model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Signal
from pydantic import ValidationError

from porous_designer.domain.enums import DomainShape, ExportFormat, SkinMode, StructureFamily, TPMSVariant
from porous_designer.domain.specification import (
    ConstraintsSpec,
    DesignSpecification,
    DomainSpec,
    ExportSpec,
    GenerationSpec,
    GradingSpec,
    PorosityTarget,
    StructureSpec,
    TargetsSpec,
)
from porous_designer.paths import resolve_output_directory


SPHERE_FAMILIES = {
    StructureFamily.SC_SPHERICAL_PORES,
    StructureFamily.BCC_SPHERICAL_PORES,
    StructureFamily.FCC_SPHERICAL_PORES,
    StructureFamily.HCP_SPHERICAL_PORES,
}
TPMS_FAMILIES = {family for family in StructureFamily if family.is_tpms}
UNIT_CELL_FAMILIES = {family for family in StructureFamily if family.uses_unit_cell}


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
            shape = DomainShape(data["domain_shape"])
            skin = {
                "skin_thickness_mm": data.get("skin_thickness") or None,
                "skin_mode": SkinMode(data.get("skin_mode") or "all"),
                "orientation": data.get("axis", "z_up"),
            }
            if shape == DomainShape.MESH:
                if not data.get("mesh_path"):
                    raise ValueError("Choose a closed mesh file for the mesh domain.")
                domain = DomainSpec.from_mesh_file(data["mesh_path"], units=data.get("mesh_units") or "mm", **skin)
            else:
                dims = {
                    DomainShape.BOX: lambda: [data["box_x"], data["box_y"], data["box_z"]],
                    DomainShape.CYLINDER: lambda: [data["cylinder_diameter"], data["cylinder_height"]],
                    DomainShape.SPHERE: lambda: [data["sphere_diameter"]],
                }[shape]()
                domain = DomainSpec(shape=shape, dimensions_mm=[float(x) for x in dims], **skin)
            cell_grading = data.get("cell_size_grading")
            structure = StructureSpec(
                family=family,
                pore_diameter_mm=data["pore_diameter"] if family in SPHERE_FAMILIES else None,
                unit_cell_size_mm=data["unit_cell_size"] if family in UNIT_CELL_FAMILIES else None,
                lattice_spacing_mm=(data.get("lattice_spacing") or None) if family in SPHERE_FAMILIES else None,
                tpms_level_set=data.get("tpms_level_set") or None,
                tpms_variant=TPMSVariant(data.get("tpms_variant") or "sheet"),
                wall_thickness_mm=(data.get("wall_thickness") or None) if family in UNIT_CELL_FAMILIES else None,
                voronoi_randomness=float(data.get("voronoi_randomness", 1.0)),
                cell_size_grading=GradingSpec(**cell_grading) if cell_grading else None,
                periodicity=bool(data.get("periodicity", True)),
            )
            porosity_grading = data.get("porosity_grading")
            formats = data.get("export_formats") or [ExportFormat.STL.value]
            spec = DesignSpecification(
                source_text=data.get("source_text", ""),
                domain=domain,
                structure=structure,
                targets=TargetsSpec(
                    porosity_target=PorosityTarget(
                        target=float(data["porosity_target"]),
                        tolerance=float(data["porosity_tolerance"]),
                    ),
                    porosity_grading=GradingSpec(**porosity_grading) if porosity_grading else None,
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
                    compute_backend=data.get("compute_backend") or "auto",
                    step_max_triangles=int(data.get("step_max_triangles") or 20000),
                ),
                export=ExportSpec(
                    output_directory=resolve_output_directory(data["output_directory"]),
                    output_name=data["output_name"],
                    formats=[ExportFormat(f) for f in formats],
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
        if spec.structure.family in UNIT_CELL_FAMILIES and spec.structure.unit_cell_size_mm:
            cells = smallest / spec.structure.unit_cell_size_mm
            if cells < 2:
                issues.append(FieldIssue("unit_cell_size", "warning", "Fewer than two unit cells span the sample."))
        if ExportFormat.STEP in spec.export.formats:
            issues.append(
                FieldIssue(
                    "step_export",
                    "warning",
                    f"STEP is a faceted solid; it is skipped (with a note) if the part cannot be reduced to {spec.generation.step_max_triangles} triangles within 0.05 mm.",
                )
            )
        if spec.domain.skin_thickness_mm and spec.domain.skin_mode == SkinMode.ALL and spec.constraints.require_open_pores:
            issues.append(FieldIssue("skin", "warning", "A skin on every boundary closes all pores; open-pore validation will fail. Use a lateral skin or untick 'Require pore percolation'."))
        if spec.constraints.minimum_wall_thickness_mm:
            issues.append(FieldIssue("minimum_wall_thickness", "unsupported", "Wall-thickness validation is not yet available."))
        if spec.constraints.minimum_throat_size_mm:
            issues.append(FieldIssue("minimum_throat_size", "unsupported", "Throat-size validation is not yet available."))
        return issues
