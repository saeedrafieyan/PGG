"""Synthetic test domains ("phantoms") for mesh-domain generation.

These are *not* scans. They are closed, watertight shapes with a known,
reproducible geometry that stand in for a scanned defect while the
scan-to-domain pipeline is developed, so mesh-domain filling can be tested
end to end.

wound_cavity_phantom
    The volume that fills an open skin wound: flat on top (the surrounding
    skin surface, z = 0) and bowl-shaped below, with an irregular outline and
    an uneven wound bed. Clinically, such a volume comes from a 3D surface
    scan of the wound (structured-light, stereophotogrammetry or LiDAR),
    closed by fitting a surface over the surrounding intact skin.
"""

from __future__ import annotations

import numpy as np
import trimesh

from porous_designer.implicit.meshing import field_to_mesh


def wound_cavity_phantom(
    length_mm: float = 30.0,
    width_mm: float = 18.0,
    depth_mm: float = 6.0,
    *,
    irregularity: float = 0.15,
    wall_steepness: float = 0.4,
    seed: int = 0,
    voxel_mm: float | None = None,
) -> trimesh.Trimesh:
    """Closed mesh (mm) of a wound-cavity fill volume.

    The outline is an ellipse (length x width) whose radius is modulated by
    low-order harmonics; depth follows ``depth * (1 - u^2)^wall_steepness``
    (smaller exponent = steeper walls) with smooth random bumps in the bed.
    The top face lies at z = 0 and the part occupies z < 0.
    """
    if min(length_mm, width_mm, depth_mm) <= 0:
        raise ValueError("Phantom dimensions must be positive.")
    if not 0.0 <= irregularity < 0.5:
        raise ValueError("irregularity must be in [0, 0.5).")
    rng = np.random.default_rng(seed)
    a, b = length_mm / 2.0, width_mm / 2.0
    h = voxel_mm or min(a, b, depth_mm) / 30.0
    margin = 1.0 + 2.0 * irregularity
    xs = np.arange(-a * margin, a * margin + h, h)
    ys = np.arange(-b * margin, b * margin + h, h)
    zs = np.arange(-depth_mm * (1.0 + 2.0 * irregularity) - 2 * h, 2 * h, h)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")

    theta = np.arctan2(Y / b, X / a)
    outline = np.ones_like(theta)
    for k in range(2, 6):
        outline += irregularity * rng.uniform(0.3, 1.0) / (k - 1) * np.cos(k * theta + rng.uniform(0, 2 * np.pi))
    u = np.sqrt((X / a) ** 2 + (Y / b) ** 2) / outline

    bed = np.zeros_like(u)
    for _ in range(5):
        cx, cy = rng.uniform(-0.6, 0.6) * a, rng.uniform(-0.6, 0.6) * b
        s = rng.uniform(0.2, 0.4) * min(a, b)
        bed += rng.uniform(-1.0, 1.0) * np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2 * s * s))
    depth = depth_mm * np.clip(1.0 - u * u, 0.0, None) ** wall_steepness * (1.0 + irregularity * bed)

    # Negative inside: below the skin plane, above the wound bed, inside the outline.
    field = np.maximum.reduce([Z, -Z - depth, (u - 1.0) * min(a, b)]).astype(np.float32)
    result = field_to_mesh(field, h, origin_mm=0.0)
    mesh = result.mesh
    # field_to_mesh assumes the grid starts at origin; shift to the true corner.
    mesh.apply_translation([xs[0] - 0.5 * h, ys[0] - 0.5 * h, zs[0] - 0.5 * h])
    parts = mesh.split(only_watertight=False)
    if len(parts) > 1:
        mesh = max(parts, key=lambda m: abs(m.volume))
    if not mesh.is_watertight:
        raise RuntimeError("Phantom mesh is not watertight; use a smaller voxel_mm.")
    return mesh
