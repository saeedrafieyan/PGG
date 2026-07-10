"""Typed design specification — authoritative source of truth."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from porous_designer.domain.enums import (
    DomainShape,
    ExportFormat,
    OriginConvention,
    StructureFamily,
)


class DomainSpec(BaseModel):
    """Bounding domain definition.

    For a box: dimensions_mm = [X, Y, Z].
    For a cylinder: dimensions_mm = [diameter, height]; orientation along Z.
    """

    shape: DomainShape = Field(description="Bounding domain shape.")
    dimensions_mm: list[float] = Field(
        min_length=2,
        max_length=3,
        description="Box: [X,Y,Z] mm. Cylinder: [diameter, height] mm.",
    )
    origin_convention: OriginConvention = Field(
        default=OriginConvention.CORNER_AT_ORIGIN,
        description="Whether the domain corner or center is at the origin.",
    )
    orientation: str = Field(
        default="z_up",
        description="Domain orientation convention (e.g. z_up for cylinder axis).",
    )

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
        return self

    @property
    def volume_mm3(self) -> float:
        if self.shape == DomainShape.BOX:
            return self.dimensions_mm[0] * self.dimensions_mm[1] * self.dimensions_mm[2]
        import math

        r = self.dimensions_mm[0] / 2.0
        return math.pi * r * r * self.dimensions_mm[1]


class PoreDefinition(BaseModel):
    """How pore geometry is defined for the selected structure family."""

    definition_type: str = Field(
        default="spherical",
        description="spherical | tpms_implicit",
    )
    notes: str = Field(default="", description="Additional pore definition notes.")


class StructureSpec(BaseModel):
    """Porous structure family and geometric parameters.

    Terminology (not interchangeable):
    - pore_diameter_mm: generating sphere diameter before clipping.
    - unit_cell_size_mm: TPMS spatial periodicity.
    - lattice_spacing_mm: nearest-neighbor sphere-center spacing.
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
        description="TPMS level-set / thickness parameter. Tuned if not set.",
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
        if self.family.is_tpms and self.unit_cell_size_mm is None:
            raise ValueError(f"{self.family.value} requires unit_cell_size_mm.")
        return self


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
    maximum_memory_gb: float = Field(default=16.0, gt=0)
    maximum_runtime_s: float = Field(default=600.0, gt=0)
    deterministic_seed: int = Field(default=42)


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
    def export_step_compatibility(self) -> DesignSpecification:
        if ExportFormat.STEP in self.export.formats and not self.structure.family.supports_step:
            raise ValueError(
                f"STEP export is not supported for {self.structure.family.value}. "
                "Use STL for TPMS structures."
            )
        return self

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)

    @classmethod
    def from_yaml(cls, text: str) -> DesignSpecification:
        data = yaml.safe_load(text)
        return cls.model_validate(data)

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> DesignSpecification:
        return cls.from_yaml(Path(path).read_text(encoding="utf-8"))

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
        unit_cell_size_mm=pore if family.is_tpms else None,
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
