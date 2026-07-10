"""Unified deterministic porous-generator interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np

from porous_designer.domain.enums import DomainShape, ExportFormat, StructureFamily
from porous_designer.domain.specification import DesignSpecification
from porous_designer.geometry.domains import DomainGrid


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


class PorousGenerator(ABC):
    family: StructureFamily
    control_parameter: str
    monotonic_decreasing: bool = True
    parameter_definitions: tuple[ParameterDefinition, ...] = ()
    known_limitations: tuple[str, ...] = ()

    def validate_specification(self, spec: DesignSpecification) -> None:
        if spec.structure.family != self.family:
            raise ValueError(f"{self.family.value} cannot handle {spec.structure.family.value}")

    def supported_domains(self) -> tuple[DomainShape, ...]:
        return (DomainShape.BOX, DomainShape.CYLINDER)

    def supported_exports(self) -> tuple[ExportFormat, ...]:
        return (ExportFormat.STL,)

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

    @abstractmethod
    def default_search_interval(self, spec: DesignSpecification) -> tuple[float, float]:
        """Return the deterministic tuning interval."""

    @abstractmethod
    def generate_voxels(
        self,
        spec: DesignSpecification,
        domain_grid: DomainGrid,
        control_parameter: float,
    ) -> GeneratedField:
        """Generate a boolean solid grid, clipped to ``domain_grid.mask``."""
