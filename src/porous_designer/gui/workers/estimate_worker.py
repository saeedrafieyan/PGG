"""Resource-estimation worker."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from porous_designer.domain.specification import DesignSpecification
from porous_designer.services.resource_estimation import estimate_resources


class EstimateWorker(QObject):
    result = Signal(dict)
    error = Signal(dict)

    def __init__(self, spec: DesignSpecification, profile: str = "final", parent=None) -> None:
        super().__init__(parent)
        self.spec = spec
        self.profile = profile

    @Slot()
    def run(self) -> None:
        try:
            resolution = (
                self.spec.generation.preview_resolution_mm
                if self.profile == "preview"
                else self.spec.generation.final_resolution_mm
            )
            self.result.emit(estimate_resources(self.spec, resolution).to_dict())
        except Exception as exc:
            self.error.emit({"message": str(exc), "technical_details": repr(exc)})
