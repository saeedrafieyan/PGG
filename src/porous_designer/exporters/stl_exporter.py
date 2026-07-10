"""STL mesh export."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import trimesh

from porous_designer.geometry.mesh import export_binary_stl


@dataclass
class STLExportResult:
    path: Path
    file_size_bytes: int
    sha256: str
    triangle_count: int


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export_stl(mesh: trimesh.Trimesh, path: str | Path) -> STLExportResult:
    out = export_binary_stl(mesh, path)
    return STLExportResult(
        path=out,
        file_size_bytes=out.stat().st_size,
        sha256=file_sha256(out),
        triangle_count=len(mesh.faces),
    )
