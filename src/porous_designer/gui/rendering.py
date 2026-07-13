"""Display-only rendering presets for porous-structure previews."""

from __future__ import annotations

import os
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


def parse_opengl_capabilities(report: str) -> dict[str, Any]:
    """Extract stable fields from VTK's free-form OpenGL capability report."""
    data: dict[str, Any] = {"vendor": "", "renderer": "", "version": "", "extensions": []}
    extensions: list[str] = []
    in_extensions = False
    for raw_line in str(report or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if "vendor" in lower and not data["vendor"]:
            data["vendor"] = line.split(":", 1)[-1].strip() if ":" in line else line
        elif "renderer" in lower and not data["renderer"]:
            data["renderer"] = line.split(":", 1)[-1].strip() if ":" in line else line
        elif "version" in lower and "opengl" in lower and not data["version"]:
            data["version"] = line.split(":", 1)[-1].strip() if ":" in line else line
        if "extension" in lower:
            in_extensions = True
            if ":" in line:
                tail = line.split(":", 1)[1].strip()
                extensions.extend(token for token in tail.replace(",", " ").split() if token.startswith("GL_"))
            continue
        if in_extensions:
            extensions.extend(token for token in line.replace(",", " ").split() if token.startswith("GL_"))
    data["extensions"] = sorted(dict.fromkeys(extensions))
    return data


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in ("pyvista", "pyvistaqt", "vtk"):
        try:
            mod = __import__(package)
            versions[package] = str(getattr(mod, "__version__", "unknown"))
        except Exception as exc:
            versions[package] = f"unavailable: {exc}"
    return versions


def rendering_diagnostics_model(settings: RenderingSettings, capabilities: dict[str, Any]) -> dict[str, Any]:
    opengl = dict(capabilities.get("opengl") or {})
    if not opengl and capabilities.get("opengl_renderer"):
        opengl = parse_opengl_capabilities(str(capabilities.get("opengl_renderer")))
    versions = package_versions()
    return {
        "preset": settings.preset,
        "appearance": {
            "mesh_color": settings.mesh_color,
            "background_color": settings.background_color,
            "edge_color": settings.edge_color,
            "smooth_shading": settings.smooth_shading,
            "edges": settings.show_edges,
            "perspective": settings.perspective,
            "opacity": settings.opacity,
            "edge_width": settings.edge_width,
            "bounding_box": settings.show_bounding_box,
            "axes": settings.show_axes,
            "transparent_exterior": settings.transparent_exterior,
        },
        "features": {
            "ambient_occlusion_requested": settings.ambient_occlusion,
            "ambient_occlusion_active": capabilities.get("ambient_occlusion", False),
            "anti_aliasing": capabilities.get("anti_aliasing", "unknown"),
            "depth_peeling": capabilities.get("depth_peeling", False),
            "fallback": capabilities.get("fallback", False),
            "warning": capabilities.get("warning", ""),
        },
        "system": {
            "vtk_version": versions.get("vtk", "unknown"),
            "pyvista_version": versions.get("pyvista", "unknown"),
            "pyvistaqt_version": versions.get("pyvistaqt", "unknown"),
            "qt_platform_plugin": os.environ.get("QT_QPA_PLATFORM", "system default"),
        },
        "opengl": {
            "vendor": opengl.get("vendor", ""),
            "renderer": opengl.get("renderer", ""),
            "version": opengl.get("version", ""),
            "extensions": opengl.get("extensions", []),
        },
        "mesh": dict(capabilities.get("mesh") or {}),
    }


def rendering_diagnostics_text(model: dict[str, Any]) -> str:
    rows: list[str] = ["[General]", f"Active preset: {model.get('preset', '')}"]
    appearance = model.get("appearance", {})
    rows.extend(f"{key.replace('_', ' ').title()}: {value}" for key, value in appearance.items())
    rows.append("")
    rows.append("[Rendering capabilities]")
    features = model.get("features", {})
    rows.extend(f"{key.replace('_', ' ').title()}: {value}" for key, value in features.items() if value != "")
    rows.append("")
    rows.append("[System]")
    system = model.get("system", {})
    opengl = model.get("opengl", {})
    for key in ("vendor", "renderer", "version"):
        value = opengl.get(key, "")
        if value:
            rows.append(f"OpenGL {key}: {value}")
    rows.extend(f"{key.replace('_', ' ').title()}: {value}" for key, value in system.items() if value != "")
    extensions = opengl.get("extensions") or []
    rows.append("")
    rows.append(f"[OpenGL extensions] {len(extensions)} entries")
    rows.extend(str(item) for item in extensions)
    return "\n".join(rows)
