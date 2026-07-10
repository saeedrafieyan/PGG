"""Generator registry for deterministic porous families."""

from __future__ import annotations

from porous_designer.domain.enums import StructureFamily
from porous_designer.generators.base import PorousGenerator
from porous_designer.generators.sphere_lattices import SphereLatticeGenerator
from porous_designer.generators.tpms import DiamondGenerator, GyroidGenerator, PrimitiveGenerator


def generator_registry() -> dict[StructureFamily, PorousGenerator]:
    return {
        StructureFamily.SC_SPHERICAL_PORES: SphereLatticeGenerator(StructureFamily.SC_SPHERICAL_PORES),
        StructureFamily.BCC_SPHERICAL_PORES: SphereLatticeGenerator(StructureFamily.BCC_SPHERICAL_PORES),
        StructureFamily.FCC_SPHERICAL_PORES: SphereLatticeGenerator(StructureFamily.FCC_SPHERICAL_PORES),
        StructureFamily.HCP_SPHERICAL_PORES: SphereLatticeGenerator(StructureFamily.HCP_SPHERICAL_PORES),
        StructureFamily.GYROID: GyroidGenerator(),
        StructureFamily.DIAMOND: DiamondGenerator(),
        StructureFamily.PRIMITIVE: PrimitiveGenerator(),
    }


def get_generator(family: StructureFamily) -> PorousGenerator:
    registry = generator_registry()
    if family not in registry:
        raise ValueError(f"No generator registered for {family.value}")
    return registry[family]
