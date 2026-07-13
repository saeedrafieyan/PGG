"""Final generation worker entry points."""

from __future__ import annotations

from porous_designer.domain.specification import DesignSpecification
from porous_designer.services.generation_service import GenerationProfile, generate_porous_stl
from porous_designer.services.mesh_optimization import OptimizationProfile

from porous_designer.gui.workers.base_worker import ProcessWorker, result_payload_from_generation


def run_final_generation(spec_data: dict) -> dict:
    spec = DesignSpecification.model_validate(spec_data)
    result = generate_porous_stl(
        spec,
        profile=GenerationProfile.FINAL,
        optimization_profile=OptimizationProfile.NONE,
    )
    return result_payload_from_generation(result)


class GenerationWorker(ProcessWorker):
    def __init__(self, spec: DesignSpecification, parent=None) -> None:
        super().__init__(run_final_generation, (spec.model_dump(mode="json"),), parent)
