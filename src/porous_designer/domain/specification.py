"""Typed design specification — authoritative source of truth."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from porous_designer.domain.enums import (
    DomainShape,
    ExportFormat,
    GradingMode,
    OriginConvention,
    SkinMode,
    StructureFamily,
    TPMSVariant,
)

MESH_UNIT_FACTORS_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "um": 0.001, "in": 25.4}

_EXTENTS_CACHE: dict[tuple[str, float, str], list[float]] = {}


def _mesh_extents_mm(path: Path, units: str) -> list[float]:
    import trimesh

    key = (str(path.resolve()), path.stat().st_mtime, units)
    if key not in _EXTENTS_CACHE:
        mesh = trimesh.load(str(path), force="mesh")
        _EXTENTS_CACHE[key] = [float(e) * MESH_UNIT_FACTORS_TO_MM[units] for e in mesh.extents]
    return list(_EXTENTS_CACHE[key])


class DomainSpec(BaseModel):
    """Bounding domain definition.

    For a box: dimensions_mm = [X, Y, Z].
    For a cylinder: dimensions_mm = [diameter, height]; orientation along Z.
    For a sphere: dimensions_mm = [diameter].
    For a mesh: dimensions_mm = bounding-box extents [X, Y, Z] of the closed
    mesh after unit scaling (see ``DomainSpec.from_mesh_file``).
    """

    shape: DomainShape = Field(description="Bounding domain shape.")
    dimensions_mm: list[float] = Field(
        min_length=1,
        max_length=3,
        description="Box: [X,Y,Z] mm. Cylinder: [diameter, height] mm. Sphere: [diameter] mm. Mesh: bbox [X,Y,Z] mm.",
    )
    mesh_path: str | None = Field(default=None, description="Closed (watertight) mesh file used as the domain (STL/OBJ/PLY/OFF/GLB/3MF).")
    mesh_units: Literal["mm", "cm", "m", "um", "in"] = Field(default="mm", description="Length unit of the mesh file coordinates.")
    skin_thickness_mm: float | None = Field(default=None, gt=0, description="Optional solid outer skin of this thickness.")
    skin_mode: SkinMode = Field(default=SkinMode.ALL, description="all: skin on every boundary; lateral: box/cylinder side walls only (open ends along Z).")
    origin_convention: OriginConvention = Field(
        default=OriginConvention.CORNER_AT_ORIGIN,
        description="Whether the domain corner or center is at the origin.",
    )
    orientation: str = Field(
        default="z_up",
        description="Domain orientation convention (e.g. z_up for cylinder axis).",
    )

    @model_validator(mode="before")
    @classmethod
    def mesh_extents_from_file(cls, data: Any) -> Any:
        """For mesh domains the file is authoritative: extents are measured from it."""
        if isinstance(data, dict) and str(data.get("shape", "")) in ("mesh", "DomainShape.MESH") and data.get("mesh_path"):
            path = Path(str(data["mesh_path"]))
            if path.is_file():
                units = str(data.get("mesh_units") or "mm")
                data = {**data, "dimensions_mm": _mesh_extents_mm(path, units)}
        return data

    @field_validator("dimensions_mm")
    @classmethod
    def positive_dimensions(cls, v: list[float]) -> list[float]:
        if any(d <= 0 for d in v):
            raise ValueError("All domain dimensions must be positive.")
        return v

    @model_validator(mode="after")
    def shape_dimension_count(self) -> DomainSpec:
        if self.shape == DomainShape.BOX and len(self.dimensions_mm) != 3:
            raise ValueError("Box domain requires exactly 3 dimensions [X, Y, Z].")
        if self.shape == DomainShape.CYLINDER and len(self.dimensions_mm) != 2:
            raise ValueError("Cylinder domain requires [diameter, height].")
        if self.shape == DomainShape.SPHERE and len(self.dimensions_mm) != 1:
            raise ValueError("Sphere domain requires [diameter].")
        if self.shape == DomainShape.MESH:
            if not self.mesh_path:
                raise ValueError("Mesh domain requires mesh_path.")
            if len(self.dimensions_mm) != 3:
                raise ValueError("Mesh domain requires its bounding-box extents [X, Y, Z]; use DomainSpec.from_mesh_file().")
        if self.skin_mode == SkinMode.LATERAL and self.shape not in (DomainShape.BOX, DomainShape.CYLINDER):
            raise ValueError("Lateral skin is only defined for box and cylinder domains.")
        return self

    @property
    def mesh_scale_to_mm(self) -> float:
        return MESH_UNIT_FACTORS_TO_MM[self.mesh_units]

    @classmethod
    def from_mesh_file(cls, path: str | Path, units: str = "mm", **kwargs: Any) -> DomainSpec:
        """Domain from a closed mesh file; extents are measured after unit scaling."""
        extents = _mesh_extents_mm(Path(path), units)
        return cls(shape=DomainShape.MESH, dimensions_mm=extents, mesh_path=str(path), mesh_units=units, **kwargs)

    @property
    def volume_mm3(self) -> float:
        from porous_designer.geometry.domains import domain_volume

        return domain_volume(self)


class PoreDefinition(BaseModel):
    """How pore geometry is defined for the selected structure family."""

    definition_type: str = Field(
        default="spherical",
        description="spherical | tpms_implicit",
    )
    notes: str = Field(default="", description="Additional pore definition notes.")


class GradingSpec(BaseModel):
    """Linear variation of a quantity through the part.

    The normalised coordinate s in [0, 1] is:
    - linear: position along ``axis`` from the domain minimum to maximum,
    - radial: distance from the domain centre line parallel to ``axis``,
      divided by the largest such distance in the domain,
    - surface_distance: depth below the domain surface divided by
      ``depth_mm`` (clamped to 1).
    The value is ``start + (end - start) * s``.
    """

    mode: GradingMode = GradingMode.LINEAR
    axis: Literal["x", "y", "z"] = "z"
    start: float
    end: float
    depth_mm: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def depth_for_surface_mode(self) -> GradingSpec:
        if self.mode == GradingMode.SURFACE_DISTANCE and self.depth_mm is None:
            raise ValueError("surface_distance grading requires depth_mm.")
        return self


class StructureSpec(BaseModel):
    """Porous structure family and geometric parameters.

    Terminology (not interchangeable):
    - pore_diameter_mm: generating sphere diameter before clipping.
    - unit_cell_size_mm: spatial period (TPMS, strut lattices) or mean cell
      size (Voronoi foam).
    - lattice_spacing_mm: nearest-neighbor sphere-center spacing.
    - wall_thickness_mm: sheet thickness (sheet TPMS) or strut diameter
      (strut lattices, Voronoi foam); tuned to the porosity target if unset.
    - network_offset_mm: signed offset of the network-TPMS solid boundary
      from the minimal surface; tuned if unset.
    """

    family: StructureFamily
    pore_definition: PoreDefinition = Field(default_factory=PoreDefinition)
    pore_diameter_mm: float | None = Field(
        default=None,
        gt=0,
        description="Sphere pore diameter (mm) for lattice structures.",
    )
    unit_cell_size_mm: float | None = Field(
        default=None,
        gt=0,
        description="TPMS unit-cell size (mm). Controls spatial periodicity.",
    )
    lattice_spacing_mm: float | None = Field(
        default=None,
        gt=0,
        description="Nearest-neighbor sphere-center spacing (mm). Tuned if not set.",
    )
    tpms_level_set: float | None = Field(
        default=None,
        description="Legacy dimensionless TPMS level set (Phase 2B); not used by the implicit kernel.",
    )
    tpms_variant: TPMSVariant = Field(default=TPMSVariant.SHEET, description="Sheet or network TPMS.")
    wall_thickness_mm: float | None = Field(
        default=None,
        gt=0,
        description="Fixed sheet thickness / strut diameter (mm). When set, porosity is a result instead of a target.",
    )
    network_offset_mm: float | None = Field(default=None, description="Fixed network-TPMS offset (mm). Tuned if not set.")
    voronoi_randomness: float = Field(default=1.0, ge=0.0, le=1.0, description="Voronoi seed jitter: 0 regular grid, 1 fully random within cells.")
    cell_size_grading: GradingSpec | None = Field(
        default=None,
        description="Linear variation of the unit-cell size along an axis (TPMS and strut lattices).",
    )
    gradient: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional spatial gradient parameters.",
    )
    periodicity: bool = Field(
        default=True,
        description="Whether the lattice is periodically continued inside the domain.",
    )

    @model_validator(mode="after")
    def family_parameters(self) -> StructureSpec:
        if self.family.is_sphere_lattice and self.pore_diameter_mm is None:
            raise ValueError(f"{self.family.value} requires pore_diameter_mm.")
        if self.family.uses_unit_cell and self.unit_cell_size_mm is None:
            raise ValueError(f"{self.family.value} requires unit_cell_size_mm.")
        if self.cell_size_grading is not None:
            if not (self.family.is_tpms or self.family.is_strut_lattice):
                raise ValueError("Cell-size grading is supported for TPMS and strut lattices only.")
            if self.cell_size_grading.mode != GradingMode.LINEAR:
                raise ValueError("Cell-size grading supports linear mode only.")
            if min(self.cell_size_grading.start, self.cell_size_grading.end) <= 0:
                raise ValueError("Graded cell sizes must be positive.")
        return self

    @property
    def fixed_thickness(self) -> bool:
        """True when the geometry is fully prescribed and porosity is an outcome."""
        if self.family.is_tpms and self.tpms_variant == TPMSVariant.NETWORK:
            return self.network_offset_mm is not None
        return self.wall_thickness_mm is not None and not self.family.is_sphere_lattice


class PorosityTarget(BaseModel):
    """Target void fraction with optional range."""

    target: float = Field(ge=0.0, le=1.0, description="Primary porosity target (0–1).")
    tolerance: float = Field(
        default=0.02,
        ge=0.0,
        le=0.5,
        description="Acceptable deviation from target (absolute fraction).",
    )
    min_value: float | None = Field(default=None, ge=0.0, le=1.0)
    max_value: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def range_consistency(self) -> PorosityTarget:
        if self.min_value is not None and self.max_value is not None:
            if self.min_value > self.max_value:
                raise ValueError("min_value must be <= max_value.")
        return self


class TargetsSpec(BaseModel):
    porosity_target: PorosityTarget
    porosity_grading: GradingSpec | None = Field(
        default=None,
        description="Porosity varying through the part (start/end are fractions). The mean replaces porosity_target.target.",
    )
    pore_size_target_mm: float | None = Field(default=None, gt=0)
    throat_target_mm: float | None = Field(default=None, gt=0)
    wall_target_mm: float | None = Field(default=None, gt=0)


class ConstraintsSpec(BaseModel):
    require_open_pores: bool = Field(
        default=True,
        description="Require interconnected, boundary-connected pore network.",
    )
    require_single_solid_component: bool = Field(default=True)
    minimum_wall_thickness_mm: float | None = Field(default=None, gt=0)
    minimum_throat_size_mm: float | None = Field(default=None, gt=0)
    maximum_file_size_mb: float | None = Field(default=None, gt=0)
    allowed_dimension_tolerance_mm: float = Field(default=0.05, gt=0)


class ManufacturingSpec(BaseModel):
    process: str = Field(default="unknown")
    printer_profile: str = Field(default="generic_fdm")
    minimum_printable_feature_mm: float = Field(default=0.4, gt=0)
    preferred_orientation: str = Field(default="z_up")
    support_policy: str = Field(default="auto")


class GenerationSpec(BaseModel):
    preview_resolution_mm: float = Field(default=0.10, gt=0)
    final_resolution_mm: float = Field(default=0.04, gt=0)
    reference_resolution_mm: float = Field(default=0.03, gt=0)
    maximum_memory_gb: float = Field(default=16.0, gt=0)
    maximum_runtime_s: float = Field(default=600.0, gt=0)
    deterministic_seed: int = Field(default=42)
    compute_backend: Literal["auto", "cpu", "cuda"] = Field(default="auto", description="Field evaluation device; auto uses CUDA for large grids when available.")
    step_max_triangles: int = Field(default=20000, ge=1000, description="Faceted STEP is attempted only up to this many triangles (after decimation).")


class ExportSpec(BaseModel):
    formats: list[ExportFormat] = Field(default_factory=lambda: [ExportFormat.STL])
    output_directory: str = Field(default="runs")
    output_name: str = Field(default="scaffold")

    @field_validator("formats")
    @classmethod
    def at_least_one_format(cls, v: list[ExportFormat]) -> list[ExportFormat]:
        if not v:
            raise ValueError("At least one export format is required.")
        return v


class MetadataSpec(BaseModel):
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    created_by: str = Field(default="unknown")
    software_version: str = Field(default="0.1.0")
    notes: str = Field(default="")


class DesignSpecification(BaseModel):
    """Authoritative typed specification for porous structure generation."""

    schema_version: str = Field(default="1.0")
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_text: str = Field(default="")
    domain: DomainSpec
    structure: StructureSpec
    targets: TargetsSpec
    constraints: ConstraintsSpec = Field(default_factory=ConstraintsSpec)
    manufacturing: ManufacturingSpec = Field(default_factory=ManufacturingSpec)
    generation: GenerationSpec = Field(default_factory=GenerationSpec)
    export: ExportSpec = Field(default_factory=ExportSpec)
    metadata: MetadataSpec = Field(default_factory=MetadataSpec)

    @model_validator(mode="after")
    def grading_compatibility(self) -> DesignSpecification:
        grading = self.targets.porosity_grading
        if grading is not None:
            if self.structure.family.is_sphere_lattice:
                raise ValueError("Porosity grading is supported for TPMS, strut lattices, and Voronoi foam, not sphere-pore lattices.")
            if self.structure.fixed_thickness:
                raise ValueError("Porosity grading cannot be combined with a fixed wall thickness.")
            if not (0.0 < grading.start < 1.0 and 0.0 < grading.end < 1.0):
                raise ValueError("Graded porosity start/end must be fractions strictly between 0 and 1.")
        return self

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)

    @classmethod
    def from_yaml(cls, text: str) -> DesignSpecification:
        data = yaml.safe_load(text)
        return cls.model_validate(data)

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> DesignSpecification:
        """Load a YAML spec; a relative domain.mesh_path is taken relative to the file."""
        path = Path(path)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        domain = data.get("domain") if isinstance(data, dict) else None
        if isinstance(domain, dict) and domain.get("mesh_path"):
            mesh_path = Path(str(domain["mesh_path"]))
            if not mesh_path.is_absolute() and not mesh_path.exists() and (path.parent / mesh_path).exists():
                domain["mesh_path"] = str((path.parent / mesh_path).resolve())
        return cls.model_validate(data)

    def save_yaml(self, path: str | Path) -> None:
        Path(path).write_text(self.to_yaml(), encoding="utf-8")


# ---------------------------------------------------------------------------
# Legacy spec file adapter (porousgen key:value format)
# ---------------------------------------------------------------------------

_LATTICE_MAP = {
    "sc": StructureFamily.SC_SPHERICAL_PORES,
    "bcc": StructureFamily.BCC_SPHERICAL_PORES,
    "fcc": StructureFamily.FCC_SPHERICAL_PORES,
    "hcp": StructureFamily.HCP_SPHERICAL_PORES,
    "gyroid": StructureFamily.GYROID,
    "diamond": StructureFamily.DIAMOND,
    "primitive": StructureFamily.PRIMITIVE,
}


def _parse_box(s: str) -> list[float]:
    parts = [p for p in re.sub(r"[xX,]", " ", s).split() if p]
    if len(parts) != 3:
        raise ValueError(f"bounding_box needs 3 numbers, got: {s!r}")
    return [float(p) for p in parts]


def _parse_porosity(s: str) -> PorosityTarget:
    t = str(s).strip().replace("%", "")
    min_v = max_v = None
    if "-" in t and not t.startswith("-"):
        a, b = t.split("-", 1)
        min_v = float(a)
        max_v = float(b)
        if min_v > 1.0:
            min_v /= 100.0
        if max_v > 1.0:
            max_v /= 100.0
        target = (min_v + max_v) / 2.0
    else:
        target = float(t)
        if target > 1.0:
            target /= 100.0
    if not (0.0 < target < 1.0):
        raise ValueError(f"porosity must be within (0,1): got {target}")
    return PorosityTarget(target=target, min_value=min_v, max_value=max_v)


def _parse_formats(s: str) -> list[ExportFormat]:
    fmts = []
    for f in re.split(r"[,\s]+", s.strip()):
        f = f.lower()
        if f:
            fmts.append(ExportFormat(f))
    return fmts or [ExportFormat.STL]


def load_legacy_spec(path: str | Path) -> DesignSpecification:
    """Load porousgen-style key:value spec file into DesignSpecification."""
    spec: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            k, v = line.split(":", 1)
            spec[k.strip().lower()] = v.strip()

    lattice_key = spec.get("lattice", "hcp").lower()
    family = _LATTICE_MAP.get(lattice_key)
    if family is None:
        raise ValueError(f"Unknown lattice: {lattice_key}")

    pore = float(spec["pore_size"])
    porosity = _parse_porosity(spec["porosity"])

    structure = StructureSpec(
        family=family,
        pore_diameter_mm=pore if family.is_sphere_lattice else None,
        unit_cell_size_mm=pore if family.uses_unit_cell else None,
    )

    return DesignSpecification(
        source_text=Path(path).read_text(encoding="utf-8"),
        domain=DomainSpec(
            shape=DomainShape.BOX,
            dimensions_mm=_parse_box(spec["bounding_box"]),
        ),
        structure=structure,
        targets=TargetsSpec(porosity_target=porosity),
        generation=GenerationSpec(
            final_resolution_mm=float(spec.get("resolution", "0.04")),
        ),
        export=ExportSpec(
            formats=_parse_formats(spec.get("formats", "stl")),
            output_name=spec.get("output", "porous"),
        ),
    )
