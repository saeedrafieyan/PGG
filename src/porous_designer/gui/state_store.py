"""GUI-local settings and specification state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal

from porous_designer.domain.enums import DomainShape, ExportFormat, StructureFamily
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


@dataclass
class GuiSettings:
    default_output_folder: str = "runs"
    default_preview_resolution_mm: float = 0.20
    default_final_resolution_mm: float = 0.12
    maximum_memory_fraction: float = 0.75
    warning_memory_fraction: float = 0.50
    auto_open_output_folder: bool = False
    retain_rejected_candidate_meshes: bool = True
    ui_theme: str = "light"
    log_level: str = "INFO"


def default_specification(settings: GuiSettings | None = None) -> DesignSpecification:
    settings = settings or GuiSettings()
    return DesignSpecification(
        source_text="Created in PGG desktop GUI.",
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[4.0, 4.0, 4.0]),
        structure=StructureSpec(
            family=StructureFamily.SC_SPHERICAL_PORES,
            pore_diameter_mm=1.0,
        ),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.55, tolerance=0.08)),
        constraints=ConstraintsSpec(require_open_pores=True, require_single_solid_component=True),
        generation=GenerationSpec(
            preview_resolution_mm=settings.default_preview_resolution_mm,
            final_resolution_mm=settings.default_final_resolution_mm,
            maximum_memory_gb=16.0,
            maximum_runtime_s=600.0,
        ),
        export=ExportSpec(
            formats=[ExportFormat.STL],
            output_directory=settings.default_output_folder,
            output_name="pgg_scaffold",
        ),
    )


class StateStore(QObject):
    """Owns GUI-only settings separately from scientific run specifications."""

    specification_changed = Signal(object)
    settings_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = self._load_settings()
        self._specification = default_specification(self._settings)

    @property
    def settings(self) -> GuiSettings:
        return self._settings

    @property
    def specification(self) -> DesignSpecification:
        return self._specification

    def set_specification(self, spec: DesignSpecification) -> None:
        self._specification = spec
        self.specification_changed.emit(spec)

    def load_specification(self, path: str | Path) -> DesignSpecification:
        spec = DesignSpecification.from_yaml_file(path)
        self.set_specification(spec)
        return spec

    def save_specification(self, path: str | Path) -> None:
        self._specification.save_yaml(path)

    def update_settings(self, settings: GuiSettings) -> None:
        self._settings = settings
        q = QSettings()
        for key, value in settings.__dict__.items():
            q.setValue(key, value)
        self.settings_changed.emit(settings)

    def _load_settings(self) -> GuiSettings:
        q = QSettings()
        data = GuiSettings()
        for key, default in data.__dict__.items():
            value = q.value(key, default)
            if isinstance(default, bool):
                value = str(value).lower() in {"1", "true", "yes"}
            elif isinstance(default, float):
                value = float(value)
            setattr(data, key, value)
        return data
