"""Signed distance fields (mm, negative inside) for part domains.

Analytic fields for box, cylinder, and sphere. Closed triangle meshes are
handled on the voxel grid:

1. sign: the mesh surface is densely sampled and rasterised into a shell of
   voxels, the enclosed region is filled, and shell voxels are classified by
   the normal of the nearest triangle;
2. magnitude: exact point-to-triangle distance to the triangles around the
   nearest surface sample, inside a narrow band; outside the band the
   magnitude is clamped (only the sign matters there).

All domains occupy ``[0, extent]`` on each axis; meshes are translated so
their bounding-box minimum sits at the origin.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from porous_designer.domain.enums import DomainShape, SkinMode
from porous_designer.domain.specification import DomainSpec


@dataclass(frozen=True)
class GridGeometry:
    """Voxel-centre grid covering ``[0, bounds]`` plus one voxel of margin.

    Voxel ``i`` is centred at ``origin + (i + 0.5) * voxel`` with
    ``origin = -margin * voxel``. The margin layer lies outside the domain,
    so the zero crossing of the domain distance field (the part's outer
    faces) is interpolated exactly by marching cubes. Inside the domain the
    voxel centres are the same as a grid starting at 0.
    """

    voxel_mm: float
    shape: tuple[int, int, int]
    bounds_mm: tuple[float, float, float]
    margin: int = 1

    @classmethod
    def covering(cls, bounds_mm: tuple[float, float, float], voxel_mm: float, margin: int = 1) -> "GridGeometry":
        shape = tuple(max(1, int(np.ceil(round(b / voxel_mm, 9)))) + 2 * margin for b in bounds_mm)
        return cls(voxel_mm=voxel_mm, shape=shape, bounds_mm=tuple(float(b) for b in bounds_mm), margin=margin)  # type: ignore[arg-type]

    @property
    def origin_mm(self) -> float:
        return -self.margin * self.voxel_mm

    def axis(self, i: int) -> np.ndarray:
        return (self.origin_mm + (np.arange(self.shape[i]) + 0.5) * self.voxel_mm).astype(np.float64)

    def slab_points(self, x0: int, x1: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        xs = self.axis(0)[x0:x1]
        return np.meshgrid(xs, self.axis(1), self.axis(2), indexing="ij")

    @property
    def point_count(self) -> int:
        return int(self.shape[0] * self.shape[1] * self.shape[2])


def domain_extents(domain: DomainSpec) -> tuple[float, float, float]:
    if domain.shape == DomainShape.BOX:
        return tuple(float(d) for d in domain.dimensions_mm)  # type: ignore[return-value]
    if domain.shape == DomainShape.CYLINDER:
        d, h = domain.dimensions_mm
        return (float(d), float(d), float(h))
    if domain.shape == DomainShape.SPHERE:
        d = float(domain.dimensions_mm[0])
        return (d, d, d)
    return tuple(float(d) for d in domain.dimensions_mm)  # type: ignore[return-value]


def box_sdf(x, y, z, extents) -> np.ndarray:
    qs = [np.abs(c - e / 2.0) - e / 2.0 for c, e in zip((x, y, z), extents)]
    outside = np.sqrt(sum(np.maximum(q, 0.0) ** 2 for q in qs))
    inside = np.minimum(np.maximum(np.maximum(qs[0], qs[1]), qs[2]), 0.0)
    return outside + inside


def _combine_2d(a, b):
    outside = np.sqrt(np.maximum(a, 0.0) ** 2 + np.maximum(b, 0.0) ** 2)
    return outside + np.minimum(np.maximum(a, b), 0.0)


def cylinder_sdf(x, y, z, diameter: float, height: float) -> np.ndarray:
    r = diameter / 2.0
    radial = np.sqrt((x - r) ** 2 + (y - r) ** 2) - r
    axial = np.abs(z - height / 2.0) - height / 2.0
    return _combine_2d(radial, axial)


def sphere_sdf(x, y, z, diameter: float) -> np.ndarray:
    r = diameter / 2.0
    return np.sqrt((x - r) ** 2 + (y - r) ** 2 + (z - r) ** 2) - r


def lateral_sdf(domain: DomainSpec, x, y, z) -> np.ndarray:
    """Distance to the side walls only (used for skins open along Z)."""
    if domain.shape == DomainShape.BOX:
        lx, ly, _ = domain.dimensions_mm
        return _combine_2d(np.abs(x - lx / 2) - lx / 2, np.abs(y - ly / 2) - ly / 2)
    if domain.shape == DomainShape.CYLINDER:
        r = domain.dimensions_mm[0] / 2.0
        return np.sqrt((x - r) ** 2 + (y - r) ** 2) - r
    raise ValueError("Lateral distance is only defined for box and cylinder domains.")


# ---------------------------------------------------------------------------
# Meshes
# ---------------------------------------------------------------------------


class DomainMeshError(ValueError):
    pass


def load_domain_mesh(domain: DomainSpec):
    """Load, scale to mm, repair lightly, check closure, translate to origin."""
    import trimesh

    if not domain.mesh_path:
        raise DomainMeshError("Mesh domain has no mesh_path.")
    path = Path(domain.mesh_path)
    if not path.exists():
        raise DomainMeshError(f"Domain mesh not found: {path}")
    mesh = trimesh.load(str(path), force="mesh")
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise DomainMeshError(f"{path.name} does not contain a triangle mesh.")
    mesh = mesh.copy()
    mesh.apply_scale(domain.mesh_scale_to_mm)
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
    if not mesh.is_watertight:
        raise DomainMeshError(
            f"{path.name} is not a closed surface (not watertight), so its inside is undefined. "
            "Close the mesh (e.g. cap an open scan) before using it as a domain."
        )
    trimesh.repair.fix_normals(mesh)
    if mesh.volume < 0:
        mesh.invert()
    # Work in a corner-at-origin frame; the source placement is kept so the
    # generated part can be put back where the scan/CAD model sits.
    mesh.metadata["age_source_min_mm"] = [float(v) for v in mesh.bounds[0]]
    mesh.apply_translation(-mesh.bounds[0])
    return mesh


def _point_triangle_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Vectorised exact distance from points p (N,3) to triangles (N,3) each."""
    ab, ac, ap = b - a, c - a, p - a
    d1 = np.einsum("ij,ij->i", ab, ap)
    d2 = np.einsum("ij,ij->i", ac, ap)
    bp = p - b
    d3 = np.einsum("ij,ij->i", ab, bp)
    d4 = np.einsum("ij,ij->i", ac, bp)
    cp = p - c
    d5 = np.einsum("ij,ij->i", ab, cp)
    d6 = np.einsum("ij,ij->i", ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    denom = va + vb + vc
    denom = np.where(np.abs(denom) < 1e-30, 1e-30, denom)
    v = vb / denom
    w = vc / denom
    closest = a + ab * v[:, None] + ac * w[:, None]
    # Regions outside the face: fall back to edges/vertices.
    candidates = [closest]
    for e0, e1 in ((a, b), (b, c), (c, a)):
        e = e1 - e0
        t = np.clip(np.einsum("ij,ij->i", p - e0, e) / np.maximum(np.einsum("ij,ij->i", e, e), 1e-30), 0.0, 1.0)
        candidates.append(e0 + e * t[:, None])
    inside_face = (va >= 0) & (vb >= 0) & (vc >= 0)
    dists = np.stack([np.linalg.norm(p - q, axis=1) for q in candidates], axis=1)
    face_d = np.where(inside_face, dists[:, 0], np.inf)
    return np.minimum(face_d, dists[:, 1:].min(axis=1))


def mesh_sdf_grid(mesh, grid: GridGeometry, *, band_voxels: float = 3.0, exact_depth_mm: float = 0.0) -> np.ndarray:
    """Signed distance of every grid voxel centre to a closed mesh.

    Exact (point-triangle) within ``band_voxels`` of the surface. Out to
    ``exact_depth_mm`` (skin thickness, surface-grading depth) distances are
    taken to dense surface samples, accurate to a small fraction of a voxel.
    Beyond that only the sign and a voxel-quantised magnitude are kept, which
    is all the lattice composition needs.
    """
    import trimesh

    h = grid.voxel_mm
    dense = mesh
    max_edge = h / 3.0
    if dense.edges_unique_length.max() > max_edge:
        verts, faces = trimesh.remesh.subdivide_to_size(dense.vertices, dense.faces, max_edge=max_edge, max_iter=20)
        dense = trimesh.Trimesh(verts, faces, process=False)
    samples = np.vstack([dense.vertices, dense.triangles_center])
    sample_faces = np.concatenate([np.full(len(dense.vertices), -1), np.arange(len(dense.faces))])
    # 1. shell voxels + fill -> inside
    idx = np.floor((samples - grid.origin_mm) / h).astype(np.int64)
    valid = np.all((idx >= 0) & (idx < np.array(grid.shape)), axis=1)
    shell = np.zeros(grid.shape, dtype=bool)
    shell[tuple(idx[valid].T)] = True
    filled = ndimage.binary_fill_holes(shell)
    inside = filled & ~shell
    # 2. band distances and signs
    tree = cKDTree(samples)
    vertex_faces = dense.vertex_faces  # (V, k) padded with -1
    # Far field: voxel-accurate Euclidean distance (needed for thick skins and
    # depth-based grading); the band below is overwritten with exact values.
    inside_depth = ndimage.distance_transform_edt(filled).astype(np.float32) * h
    outside_depth = ndimage.distance_transform_edt(~filled).astype(np.float32) * h
    sdf = np.where(inside, -inside_depth, outside_depth).astype(np.float32)
    del inside_depth, outside_depth
    # The dilated band reaches band_voxels in city-block distance only, so
    # sample-accurate distances always extend a voxel beyond it.
    exact_depth_mm = max(exact_depth_mm, (band_voxels + 1.0) * h)
    if exact_depth_mm > 0:
        mid = np.argwhere(np.abs(sdf) <= exact_depth_mm + 2.0 * h)
        for start in range(0, len(mid), 1_000_000):
            chunk = mid[start : start + 1_000_000]
            dist, _ = tree.query(grid.origin_mm + (chunk + 0.5) * h, k=1, workers=-1)
            sign = np.where(inside[tuple(chunk.T)], -1.0, 1.0)
            sdf[tuple(chunk.T)] = (sign * dist).astype(np.float32)
    shell_or_near = ndimage.binary_dilation(shell, iterations=int(np.ceil(band_voxels)))
    band_idx = np.argwhere(shell_or_near)
    tri = dense.triangles
    normals = dense.face_normals
    for start in range(0, len(band_idx), 400_000):
        chunk = band_idx[start : start + 400_000]
        pts = grid.origin_mm + (chunk + 0.5) * h
        _, nearest = tree.query(pts, k=1, workers=-1)
        # candidate faces: faces around the nearest vertex, or the face whose centre was nearest
        cand = np.full((len(pts), vertex_faces.shape[1] + 1), -1, dtype=np.int64)
        is_vertex = nearest < len(dense.vertices)
        cand[is_vertex, : vertex_faces.shape[1]] = vertex_faces[nearest[is_vertex]]
        cand[~is_vertex, 0] = sample_faces[nearest[~is_vertex]]
        best = np.full(len(pts), np.inf)
        best_face = np.zeros(len(pts), dtype=np.int64)
        for k in range(cand.shape[1]):
            faces_k = cand[:, k]
            ok = faces_k >= 0
            if not ok.any():
                continue
            d = np.full(len(pts), np.inf)
            t = tri[faces_k[ok]]
            d[ok] = _point_triangle_distance(pts[ok], t[:, 0], t[:, 1], t[:, 2])
            better = d < best
            best = np.where(better, d, best)
            best_face = np.where(better, faces_k, best_face)
        in_shell = shell[tuple(chunk.T)]
        # Sign: fill result away from the surface; nearest-face normal on the shell.
        centroid_dir = pts - tri[best_face].mean(axis=1)
        normal_inside = np.einsum("ij,ij->i", centroid_dir, normals[best_face]) < 0
        is_inside = np.where(in_shell, normal_inside, inside[tuple(chunk.T)])
        magnitude = np.minimum(best, (band_voxels + 1.0) * h)
        sdf[tuple(chunk.T)] = np.where(is_inside, -magnitude, magnitude).astype(np.float32)
    return sdf


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def domain_sdf_grid(domain: DomainSpec, grid: GridGeometry, *, mesh=None, exact_depth_mm: float | None = None) -> np.ndarray:
    """Full-grid signed distance (float32) for any supported domain.

    ``exact_depth_mm`` is how deep below the surface distances must be
    accurate for mesh domains; by default the skin thickness.
    """
    if domain.shape == DomainShape.MESH:
        mesh = mesh if mesh is not None else load_domain_mesh(domain)
        depth = exact_depth_mm if exact_depth_mm is not None else (domain.skin_thickness_mm or 0.0)
        return mesh_sdf_grid(mesh, grid, exact_depth_mm=depth)
    out = np.empty(grid.shape, dtype=np.float32)
    step = max(1, 4_000_000 // max(1, grid.shape[1] * grid.shape[2]))
    for x0 in range(0, grid.shape[0], step):
        x1 = min(grid.shape[0], x0 + step)
        x, y, z = grid.slab_points(x0, x1)
        if domain.shape == DomainShape.BOX:
            out[x0:x1] = box_sdf(x, y, z, domain.dimensions_mm)
        elif domain.shape == DomainShape.CYLINDER:
            out[x0:x1] = cylinder_sdf(x, y, z, *domain.dimensions_mm)
        else:
            out[x0:x1] = sphere_sdf(x, y, z, domain.dimensions_mm[0])
    return out


def skin_region_sdf(domain: DomainSpec, grid: GridGeometry, domain_sdf: np.ndarray) -> np.ndarray | None:
    """Field that is negative inside the solid skin, or None without a skin."""
    t = domain.skin_thickness_mm
    if not t:
        return None
    if domain.skin_mode == SkinMode.LATERAL:
        wall = np.empty(grid.shape, dtype=np.float32)
        step = max(1, 4_000_000 // max(1, grid.shape[1] * grid.shape[2]))
        for x0 in range(0, grid.shape[0], step):
            x1 = min(grid.shape[0], x0 + step)
            x, y, z = grid.slab_points(x0, x1)
            wall[x0:x1] = lateral_sdf(domain, x, y, z)
        # inside the domain AND within t of the side wall
        return np.maximum(domain_sdf, -wall - t).astype(np.float32)
    return np.maximum(domain_sdf, -domain_sdf - t).astype(np.float32)
