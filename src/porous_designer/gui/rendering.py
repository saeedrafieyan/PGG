"""Display-only rendering presets for porous-structure previews."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from PySide6.QtCore import QSettings


@dataclass
class RenderingSettings:
    preset: str = "Scientific"
    mesh_color: str = "#9ca3af"
    background_color: str = "#111827"
    edge_color: str = "#111827"
    show_edges: bool = False
    edge_width: float = 0.6
    smooth_shading: bool = True
    perspective: bool = True
    ambient_occlusion: bool = True
    transparent_exterior: bool = False
    opacity: float = 1.0
    show_axes: bool = True
    show_bounding_box: bool = False


PRESETS: dict[str, RenderingSettings] = {
    "Scientific": RenderingSettings(),
    "High Contrast": RenderingSettings(
        preset="High Contrast",
        mesh_color="#d1d5db",
        background_color="#05070a",
        edge_color="#030712",
        ambient_occlusion=True,
    ),
    "Light Background": RenderingSettings(
        preset="Light Background",
        mesh_color="#5b6472",
        background_color="#f8fafc",
        edge_color="#1f2937",
        ambient_occlusion=False,
    ),
    "Wireframe": RenderingSettings(
        preset="Wireframe",
        mesh_color="#d1d5db",
        background_color="#111827",
        edge_color="#f9fafb",
        show_edges=True,
        edge_width=1.0,
        smooth_shading=False,
        opacity=0.08,
    ),
    "Surface + Edges": RenderingSettings(
        preset="Surface + Edges",
        mesh_color="#a7adb7",
        background_color="#111827",
        edge_color="#1f2937",
        show_edges=True,
        edge_width=0.35,
        smooth_shading=True,
    ),
}


def load_rendering_settings() -> RenderingSettings:
    q = QSettings()
    settings = PRESETS["Scientific"]
    data = RenderingSettings(**asdict(settings))
    for key, default in asdict(settings).items():
        value = q.value(f"rendering/{key}", default)
        if isinstance(default, bool):
            value = str(value).lower() in {"1", "true", "yes"}
        elif isinstance(default, float):
            value = float(value)
        setattr(data, key, value)
    return data


def save_rendering_settings(settings: RenderingSettings) -> None:
    q = QSettings()
    for key, value in asdict(settings).items():
        q.setValue(f"rendering/{key}", value)


def preset(name: str) -> RenderingSettings:
    return RenderingSettings(**asdict(PRESETS.get(name, PRESETS["Scientific"])))


def rendering_diagnostics(settings: RenderingSettings, capabilities: dict[str, Any]) -> str:
    rows = [
        ("Preset", settings.preset),
        ("Mesh color", settings.mesh_color),
        ("Background color", settings.background_color),
        ("Smooth shading", settings.smooth_shading),
        ("Edges", settings.show_edges),
        ("Perspective", settings.perspective),
        ("Ambient occlusion requested", settings.ambient_occlusion),
        ("Ambient occlusion active", capabilities.get("ambient_occlusion", False)),
        ("Anti-aliasing", capabilities.get("anti_aliasing", "unknown")),
        ("Depth peeling", capabilities.get("depth_peeling", False)),
        ("OpenGL renderer", capabilities.get("opengl_renderer", "unknown")),
        ("Fallback mode", capabilities.get("fallback", False)),
    ]
    return "\n".join(f"{k}: {v}" for k, v in rows)
