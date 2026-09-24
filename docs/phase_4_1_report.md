# Phase 4.1 — Implicit geometry kernel, new families, domains, grading, 3MF/STEP

Phase 4.1 replaces the voxel-sampling generators with a continuous implicit
field kernel and widens what AGE can design: 16 structure families, four
domain types (including imported closed meshes), porosity and cell-size
grading, solid skins, and three print/CAD formats. The agent layer and the GUI
now expose all of it. Scan-to-domain (turning a raw wound scan into a closed
domain) is still deferred; the mesh domain accepts any closed mesh, and a
synthetic wound phantom is provided for testing.

## 1. Kernel

Every structure is a float32 field `F(x)` in millimetres, negative inside
solid, on a regular grid with a one-voxel margin outside the domain:

    F = min( max(F_lattice, F_domain), F_skin )

* `F_domain` is the signed distance to the domain (exact for box, cylinder,
  sphere; for meshes see §3).
* `F_skin` is negative within `skin_thickness_mm` of the surface (all
  boundaries) or of the side wall only (`skin_mode: lateral`).
* The mesh is extracted with marching cubes **on the continuous field**, so
  surfaces are smooth, walls keep their thickness, and flat domain faces land
  exactly on their coordinates (bounding boxes match to < 1e-6 mm for
  resolved walls).

A thickness-independent base distance `D` (cell units) is computed once per
grid and cached; every trial thickness is then an array expression:

| kind | solid where | control |
|---|---|---|
| TPMS sheet | `L·(D − τ/2) ≤ 0`, `D = |f|/|∇f|` | `τ` = thickness / cell |
| TPMS network | `L·(D − κ) ≤ 0`, `D = f/|∇f|` | `κ` = offset / cell |
| strut lattice | `L·(D − τ/2) ≤ 0`, `D` = distance to strut axes | `τ` = diameter / cell |
| Voronoi foam | as struts, `D` = distance to Voronoi edges | `τ` |
| sphere pores | `r − dist(nearest centre) ≤ 0` is void | lattice spacing |

`L` is the (possibly graded) cell size. Analytic gradients of all seven TPMS
equations agree with central finite differences to < 1e-6 (tested at 400
random points each).

### Strut lattices without approximation

Cubic, BCC, octet and Kelvin lattices have full cubic (Oₕ) symmetry. Points
are folded into the fundamental region `0 ≤ z ≤ y ≤ x ≤ ½` of the cell, where
only the 1–2 strut segments that can be nearest are kept (pruned by the true
arg-min on random interior points). Distances equal a brute-force evaluation
over all edges to < 1e-7 cell (3000 random points per lattice).

### Voronoi foam

Seeds are jittered on a grid (`voronoi_randomness` 0 = regular, 1 = fully
random within each cell) with a fixed seed, so a given specification always
produces the same foam (identical SHA-256). Finite Voronoi edges from SciPy
are sampled densely and queried with a KD-tree.

### GPU backend

The same field code runs on NumPy or on PyTorch CUDA (`compute_backend:
auto|cpu|cuda`; `auto` uses CUDA from 2 M grid points when available). CPU
and CUDA fields agree to ~1e-5 cell near the surface with identical porosity;
CUDA is 3–4× faster for strut lattices and Lidinoid on an RTX 5070 Ti.

## 2. Porosity tuning that meets the target in the exported part

1. **Calibration.** For each periodic family, porosity versus `τ`/`κ` is
   tabulated once on a unit cell (Voronoi: on a 4×4×4 block). It gives tight
   bisection brackets and inverts graded targets.
2. **Partial-volume porosity.** Tuning uses the fraction of each voxel that
   is solid, not voxel-centre counting. Centre counting aliases badly when a
   lattice lines up with the grid (a Schwarz-P case read 36.8 % instead of
   45.2 % at 0.15 mm) and turns porosity into a staircase in the control
   parameter. For walls and struts the voxel fraction is the overlap of the
   voxel with the wall (`[d − h/2, d + h/2] ∩ [−t/2, t/2]`), which stays
   correct below one voxel; struts get an extra thin-direction factor.
   Across 0.3 → 0.0375 mm this estimator varies by ~1–3 % where centre counting
   varies by up to 25 %.
3. **Tuning grid → final grid.** Bisection on a coarse grid, then a
   refinement on the final grid in a ±5 % bracket.
4. **Mesh correction.** Marching cubes interpolates linearly and thins walls
   that span only a few voxels. The exported mesh is what gets printed, so
   when its porosity misses the target by more than max(¼ tolerance, 0.004),
   up to three secant steps on the control parameter re-mesh until it hits.
   The adjustment is logged.
5. **Printability gate.** If reaching the target needs walls/struts thinner
   than 0.75 voxel, the run stops as infeasible with the required thickness
   and what to change (config `generation.minimum_wall_voxels`).

Validation now treats the mesh (enclosed volume of the watertight part) as
the authoritative porosity. Voxel-centre porosity is a cross-check: moderate
disagreement is a **warning** with a resolution hint (e.g. "walls span 1.2
voxels; a final resolution of about 0.08 mm resolves them"); only a gross
difference (≥ 0.12, the signature of defects such as inverted cavity shells)
fails. Warnings no longer reject a part; any failed check still does.

## 3. Domains

| shape | dimensions | notes |
|---|---|---|
| box | [X, Y, Z] | |
| cylinder | [diameter, height] | axis Z |
| sphere | [diameter] | new |
| mesh | extents measured from the file | new: closed STL/OBJ/PLY/OFF/GLB/3MF |

Mesh domains: units `mm|cm|m|um|in`; the mesh is lightly repaired (merge,
degenerate faces, hole filling) and rejected with a clear message if it is
not closed. The signed distance is exact (point–triangle) within three voxels
of the surface, accurate to a small fraction of a voxel out to the skin
thickness / grading depth, and voxel-quantised beyond (only the sign matters
there). **The generated part keeps the coordinates of the source file**, so it
overlays the scan or CAD model it fills.

For curved and mesh domains a pore can sit exactly on the domain's extreme
point, making the porous part slightly smaller than its bounding box; that is
reported as a warning (oversize still fails). A skin restores the full size.

`porous-designer make-phantom out.stl` writes a synthetic wound-cavity fill
volume (flat skin plane, bowl-shaped irregular bed, irregular outline) for
testing. Real wounds would come from a 3D surface scan (structured light,
stereophotogrammetry, LiDAR) closed over the surrounding skin — that is the
deferred scan-to-domain phase.

## 4. Grading and skins

* **Porosity grading** (`targets.porosity_grading`): `linear` along an axis,
  `radial` from the centre line, or `surface_distance` from the surface over
  `depth_mm`. Local porosity is mapped to local `τ` through the calibration
  curve; a single shift is tuned so the mean matches. The per-band profile is
  validated (radial 85 → 55 % gyroid: interior bands within 0.006).
* **Cell-size grading** (`structure.cell_size_grading`, TPMS and struts,
  linear): coordinates are warped along one axis with the analytic Jacobian,
  so cells stay connected while their size changes.
* **Fixed thickness** (`structure.wall_thickness_mm` / `network_offset_mm`):
  geometry is prescribed and porosity is reported as a result.
* **Skin**: porosity targets the porous core; percolation is required only
  along axes the skin leaves open (lateral skin → Z).
* **Detached fragments** left by cutting the lattice with the boundary are
  removed if they total ≤ 2 % of the material; more means the design itself
  is disconnected and the run fails.

## 5. Exports

* **STL** (binary) — as before, plus the optional optimised copy.
* **3MF** — explicit `unit="millimeter"`, the preferred slicer format
  (PrusaSlicer, Cura, Bambu Studio, Chitubox, Lychee).
* **STEP** — faceted solid for CAD (planar faces sewn by OpenCASCADE via gmsh
  in a subprocess). The mesh is decimated towards `generation.step_max_triangles`
  (default 20 000): an aggressive quadric pass first, then repeated gentle
  passes if the aggressive one pinches thin walls into non-manifold edges; a
  closed result up to 1.5× the budget is accepted. The surface may move by at
  most max(voxel, dimension tolerance); the STEP is re-imported and its
  volume must match within 1 %. Otherwise STEP is skipped with a note. STEP
  is written for Final runs only. Example: the skinned I-WP cylinder
  (217 k triangles) exports as a 27.7 k-face solid, deviation 0.019 mm,
  volume identical, ~90 s.

## 6. Agent layer and GUI

* Terminology: I-WP, Neovius, Fischer–Koch S, Lidinoid, octet/Kelvin/BCC/
  cubic struts, Voronoi/stochastic/trabecular foam, sphere/ball domains,
  3MF. Plain "BCC" still means BCC spherical pores; "BCC struts/truss" means
  the strut lattice (longest match wins).
* "network gyroid", "sheet-based diamond" set `structure.tpms_variant`; the
  variant word must be adjacent to the family name ("pore network" does not
  count).
* Pore phrases ("spherical pores", "sphere diameter") are masked before
  domain-shape detection, so an HCP spherical-pore request is not read as a
  sphere domain.
* Grounded LLM schema: `sphere_diameter`, `tpms_variant`, formats
  `stl|3mf|step`; `mesh` is not a text-describable shape. Parser version
  `4.1.0-grounded` (invalidates cached extractions).
* STEP is no longer reported as unsupported.
* GUI: all 16 families, sheet/network, wall thickness, Voronoi randomness,
  cell-size grading; sphere and mesh domains (file picker, units, extents
  preview), skin thickness/mode; porosity grading; STL/3MF/STEP checkboxes,
  STEP triangle limit, compute backend.
* CLI: `porous-designer families`, `porous-designer make-phantom`.

## 7. Verification

* Unit: `tests/unit/test_implicit_phase_4_1.py` (46 tests: gradients,
  calibration, strut exactness, mesh SDF vs analytic sphere, sphere and mesh
  domains, phantom, grading, monotone control, skin, fixed thickness,
  watertightness sweep, closed cavities, fragments, 3MF, STEP, backend, CPU vs
  CUDA) and `tests/unit/test_agentic_phase_4_1.py` (23 tests: vocabulary,
  variants, masking, grounded sphere/variant/mesh).
* Integration: `tests/integration/test_phase_4_1_generation.py` (18 end-to-end
  runs: 5 TPMS, 4 strut lattices, Voronoi in a sphere with determinism,
  radial grading, cell grading, fixed thickness, lateral skin, wound phantom
  with skin, thin-wall infeasibility, all formats, CLI).
* The Federica HCP regression still passes unchanged in geometry.
* Existing tests that encoded "STEP unsupported" were updated to the new
  behaviour; Phase 2B generator tests run at 0.1 mm because 65 % diamond
  sheets at a 2 mm cell are ~0.15 mm thick, below one 0.2 mm voxel.

## 8. Known limits

* Sheet thickness uses the first-order distance `|f|/|∇f|`; it is less
  accurate for very thick walls (low porosity), which the tuner absorbs but
  the reported `wall_thickness_mm` is nominal.
* Wall-thickness and throat-size *measurement* is still not a validator.
* Sphere-pore lattices below the touching porosity have closed pores and
  correctly fail open-pore validation.
* STEP of large lattices is skipped by design (hundreds of thousands of
  faces); use 3MF/STL for printing.
