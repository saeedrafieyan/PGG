"""Resolution-sensitivity worker."""

from __future__ import annotations

from porous_designer.domain.specification import DesignSpecification
from porous_designer.gui.workers.base_worker import ProcessWorker
from porous_designer.services.sensitivity_service import run_resolution_sensitivity


def run_sensitivity(spec_data: dict, resolutions: list[float]) -> dict:
    spec = DesignSpecification.model_validate(spec_data)
    result = run_resolution_sensitivity(spec, resolutions=resolutions)
    return {
        "output_dir": str(result.output_dir),
        "rows": result.rows,
        "status": result.status,
        "reference_resolution_mm": result.reference_resolution_mm,
    }


class SensitivityWorker(ProcessWorker):
    def __init__(self, spec: DesignSpecification, resolutions: list[float], parent=None) -> None:
        super().__init__(run_sensitivity, (spec.model_dump(mode="json"), resolutions), parent)
