"""3MF export with explicit millimetre units.

3MF is the preferred format for printing: it is compact (zipped XML), states
its unit, and is read natively by current slicers (PrusaSlicer, Cura,
Bambu Studio, Chitubox, Lychee). The writer produces the minimal core
specification package: content types, relationships, and one mesh object.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import trimesh

from porous_designer.exporters.stl_exporter import file_sha256

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""


@dataclass
class ThreeMFExportResult:
    path: Path
    file_size_bytes: int
    sha256: str
    triangle_count: int


def _model_xml(mesh: trimesh.Trimesh, title: str) -> str:
    verts = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    vertex_lines = "\n".join(f'<vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in verts)
    triangle_lines = "\n".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
        f'<metadata name="Title">{escape(title)}</metadata>\n'
        '<metadata name="Application">AGE - Agentic Geometry Engineering</metadata>\n'
        '<resources>\n<object id="1" type="model">\n<mesh>\n<vertices>\n'
        f"{vertex_lines}\n</vertices>\n<triangles>\n{triangle_lines}\n</triangles>\n"
        "</mesh>\n</object>\n</resources>\n"
        '<build>\n<item objectid="1"/>\n</build>\n</model>\n'
    )


def export_3mf(mesh: trimesh.Trimesh, path: str | Path, *, title: str = "AGE porous structure") -> ThreeMFExportResult:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", _model_xml(mesh, title))
    return ThreeMFExportResult(path=out, file_size_bytes=out.stat().st_size, sha256=file_sha256(out), triangle_count=len(mesh.faces))
