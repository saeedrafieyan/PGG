"""Best-effort faceted STEP export.

Lattices and minimal surfaces have no compact exact B-rep, so the STEP file
is a *faceted* solid: every triangle becomes a planar face, sewn into one
closed shell by OpenCASCADE (through gmsh). CAD tools open it as a solid
body, which is what is needed for boolean operations with other parts;
for printing, STL/3MF are smaller and equivalent.

Cost grows quickly with face count (about 7 s and 12 MB for 5k triangles),
so the mesh is decimated to ``max_triangles`` first, the surface deviation
of that decimation is reported, and export is skipped when the deviation
would exceed the allowed tolerance. The work runs in a subprocess because
OpenCASCADE writes directly to the console and can take minutes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

_WORKER = r"""
import json, sys
import gmsh, trimesh
src, dst = sys.argv[1], sys.argv[2]
mesh = trimesh.load(src, force="mesh")
gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 0)
gmsh.model.add("age")
occ = gmsh.model.occ
pts = [occ.addPoint(*map(float, v)) for v in mesh.vertices]
edges = {}
def line(a, b):
    key = (min(a, b), max(a, b))
    if key not in edges:
        edges[key] = occ.addLine(pts[key[0]], pts[key[1]])
    tag = edges[key]
    return tag if a == key[0] else -tag
faces = []
for a, b, c in mesh.faces:
    loop = occ.addCurveLoop([line(int(a), int(b)), line(int(b), int(c)), line(int(c), int(a))])
    faces.append(occ.addPlaneSurface([loop]))
shell = occ.addSurfaceLoop(faces, sewing=True)
occ.addVolume([shell])
occ.synchronize()
gmsh.write(dst)
gmsh.clear()
gmsh.model.add("check")
gmsh.merge(dst)
gmsh.model.occ.synchronize()
volumes = gmsh.model.getEntities(3)
volume = gmsh.model.occ.getMass(3, volumes[0][1]) if volumes else None
gmsh.finalize()
print("AGE_STEP_RESULT " + json.dumps({"volumes": len(volumes), "volume": volume}))
"""


@dataclass
class StepExportResult:
    status: str  # "exported" | "skipped" | "failed"
    path: Path | None = None
    message: str = ""
    triangle_count: int = 0
    decimation_deviation_mm: float | None = None
    step_volume_mm3: float | None = None
    mesh_volume_mm3: float | None = None
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "path": str(self.path) if self.path else None,
            "message": self.message,
            "triangle_count": self.triangle_count,
            "decimation_deviation_mm": self.decimation_deviation_mm,
            "step_volume_mm3": self.step_volume_mm3,
            "mesh_volume_mm3": self.mesh_volume_mm3,
        }


def _surface_deviation(reference: trimesh.Trimesh, candidate: trimesh.Trimesh, samples: int = 4000) -> float:
    pts, _ = trimesh.sample.sample_surface(candidate, samples, seed=0)
    _, dist, _ = trimesh.proximity.closest_point(reference, pts)
    return float(np.max(dist))


def _decimate_watertight(mesh: trimesh.Trimesh, max_triangles: int, *, slack: float = 1.5) -> trimesh.Trimesh | None:
    """Quadric decimation that keeps the mesh closed.

    Aggressive single-pass decimation reaches the limit but can pinch thin
    walls into non-manifold junctions; gentler passes stay manifold but stop
    early. Try aggressive first, then repeated gentle passes, and accept a
    closed result up to ``slack`` times the limit (STEP cost grows with faces,
    so the limit is a budget, not a hard format constraint).
    """
    import fast_simplification

    def simplify(src: trimesh.Trimesh, target: int, agg: int) -> trimesh.Trimesh:
        reduction = max(0.0, 1.0 - target / len(src.faces))
        verts, faces = fast_simplification.simplify(src.vertices, src.faces, target_reduction=reduction, agg=agg)
        return trimesh.Trimesh(verts, faces, process=True)

    for agg in (7, 5):
        candidate = simplify(mesh, max_triangles, agg)
        if candidate.is_watertight and len(candidate.faces) <= max_triangles:
            return candidate
    work = mesh
    for _ in range(8):
        candidate = simplify(work, max(max_triangles, len(work.faces) // 2), 3)
        if not candidate.is_watertight or len(candidate.faces) >= len(work.faces):
            break
        work = candidate
        if len(work.faces) <= max_triangles:
            break
    return work if work is not mesh and len(work.faces) <= slack * max_triangles else None


def export_faceted_step(
    mesh: trimesh.Trimesh,
    path: str | Path,
    *,
    max_triangles: int = 20000,
    max_deviation_mm: float = 0.05,
    timeout_s: float = 900.0,
) -> StepExportResult:
    out = Path(path)
    work = mesh
    deviation = 0.0
    if len(mesh.faces) > max_triangles:
        try:
            work = _decimate_watertight(mesh, max_triangles)
        except Exception as exc:
            return StepExportResult("failed", message=f"Decimation before STEP export failed: {exc}")
        if work is None:
            return StepExportResult("skipped", message="The part could not be reduced to the STEP triangle limit without breaking watertightness; use STL or 3MF.")
        deviation = _surface_deviation(mesh, work)
        if deviation > max_deviation_mm:
            return StepExportResult(
                "skipped",
                message=(
                    f"The part needs {len(mesh.faces)} triangles; reducing it to the STEP limit of {max_triangles} "
                    f"would move the surface by up to {deviation:.3f} mm (> {max_deviation_mm:.3f} mm). Use STL or 3MF, "
                    "or raise generation.step_max_triangles."
                ),
                triangle_count=len(work.faces),
                decimation_deviation_mm=deviation,
            )
    # Coincident vertices or sliver faces make OpenCASCADE refuse to build edges.
    work = work.copy()
    work.merge_vertices(digits_vertex=7)
    work.update_faces(work.nondegenerate_faces(height=1e-7))
    work.remove_unreferenced_vertices()
    if not work.is_watertight:
        return StepExportResult("skipped", message="The mesh is not watertight after cleaning; STEP needs a closed shell. Use STL or 3MF.", triangle_count=len(work.faces), decimation_deviation_mm=deviation)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "step_source.stl"
        work.export(src)
        try:
            proc = subprocess.run([sys.executable, "-c", _WORKER, str(src), str(out)], capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return StepExportResult("failed", message=f"STEP export exceeded {timeout_s:.0f} s.", triangle_count=len(work.faces), decimation_deviation_mm=deviation)
    line = next((l for l in proc.stdout.splitlines() if l.startswith("AGE_STEP_RESULT ")), None)
    if proc.returncode != 0 or line is None:
        tail = (proc.stderr or proc.stdout)[-400:]
        return StepExportResult("failed", message=f"STEP export failed: {tail.strip()}", triangle_count=len(work.faces), decimation_deviation_mm=deviation)
    info = json.loads(line.split(" ", 1)[1])
    step_volume = info.get("volume")
    mesh_volume = float(work.volume)
    ok = info.get("volumes") == 1 and step_volume is not None and abs(step_volume - mesh_volume) <= 0.01 * abs(mesh_volume)
    if not ok:
        return StepExportResult(
            "failed",
            path=out,
            message=f"STEP re-import check failed (volumes={info.get('volumes')}, STEP volume={step_volume}, mesh volume={mesh_volume:.4f}).",
            triangle_count=len(work.faces),
            decimation_deviation_mm=deviation,
            step_volume_mm3=step_volume,
            mesh_volume_mm3=mesh_volume,
        )
    return StepExportResult(
        "exported",
        path=out,
        message=f"Faceted STEP solid with {len(work.faces)} planar faces; re-import volume matches within 1%.",
        triangle_count=len(work.faces),
        decimation_deviation_mm=deviation,
        step_volume_mm3=step_volume,
        mesh_volume_mm3=mesh_volume,
    )
