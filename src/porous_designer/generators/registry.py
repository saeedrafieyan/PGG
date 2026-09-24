"""Generator registry for all porous structure families."""

from __future__ import annotations

from porous_designer.domain.enums import StructureFamily
from porous_designer.generators.base import PorousGenerator


def generator_registry() -> dict[StructureFamily, PorousGenerator]:
    return {family: PorousGenerator(family) for family in StructureFamily}


def get_generator(family: StructureFamily) -> PorousGenerator:
    registry = generator_registry()
    if family not in registry:
        raise ValueError(f"No generator registered for {family.value}")
    return registry[family]
