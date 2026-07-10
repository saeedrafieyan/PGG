# Current System Audit — Federica Porous Geometry Project

**Audit date:** 2026-07-10  
**Auditor:** automated baseline run + manual code review  
**Branch:** `feature/agentic-porous-gui` (created from preserved baseline commit `7f2bf6c`)  
**Python:** 3.14.3 (Windows 10.0.26200)

---

## 1. Repository inventory

| File | Lines | Role | Status |
|------|-------|------|--------|
| `porousgen.py` | 330 | Unified CLI entry point: spec parsing, lattice generation, porosity tuning, STL/STEP export | **Primary reusable core** |
| `build_stl.py` | 71 | Hard-coded HCP STL generator (8×14×8, R=0.5, A=0.985) | **Obsolete** — superseded by `porousgen.py` |
| `build_step.py` | 67 | Hard-coded HCP STEP generator with gmsh boolean | **Obsolete** — superseded by `porousgen.py` |
| `tune_spacing.py` | 59 | Spacing sweep for HCP porosity at fixed R | **Obsolete** — logic absorbed into `porousgen.tune()` |
| `validate.py` | 31 | STL reload + gmsh STEP reimport smoke test | **Partially reusable** — insufficient for acceptance |
| `inspect_step.py` | 22 | STEP solid count, bbox, volume via gmsh | **Diagnostic only** |
| `check_step_extent.py` | 15 | Mesh node bbox from tessellated STEP | **Diagnostic only** |
| `parse_step_vertices.py` | 25 | STEP validation by parsing `VERTEX_POINT` coords | **Unsafe** — must not be used for acceptance |
| `slim_stl.py` | 14 | Quadric decimation to ~700k faces | **Utility** — not integrated |
| `sample_spec.txt` | 10 | Federica reference specification | **Reusable fixture** |
| `federica_scaffold.stl` | 78.98 MB | Reference STL output | **Baseline artifact** |
| `federica_scaffold.step` | 67.58 MB | Reference STEP output | **Baseline artifact (topology suspect)** |
| `step_log.txt` | 1.56 MB | gmsh boolean log from prior run | **Historical log** |
| `README.md` | 68 | Usage documentation | **Reusable** — needs expansion |

**Not present:** tests, `pyproject.toml`, dependency lock file, GUI, agent layer, typed schemas, run history, validation reports, cylinder domain, diamond/primitive TPMS.

---

## 2. Dependency baseline

Installed in audit environment (Python 3.14.3):

| Package | Version | Used by |
|---------|---------|---------|
| numpy | 2.4.4 | All geometry scripts |
| scikit-image | 0.26.0 | Marching cubes (`measure.marching_cubes`) |
| trimesh | 4.12.2 | STL I/O, mesh cleanup, watertight check |
| gmsh | 4.15.2 | OpenCASCADE boolean, STEP I/O, tessellation |
| scipy | 1.17.1 | Available but unused in current scripts |
| pydantic | 2.13.3 | Installed but unused |
| vtk | 9.6.1 | Installed but unused |
| pytest | 9.0.3 | Installed but no tests exist |

**Not installed:** PySide6, PyVistaQt, CadQuery, pythonOCC, structlog, pytest-qt, PyYAML.

**Python version note:** Environment runs Python 3.14.3. PySide6 6.11.1 publishes `cp310-abi3` wheels compatible with 3.14. Recommend documenting Python 3.11–3.14 support after install verification; prefer 3.12 for production stability.

---

## 3. Federica baseline run (2026-07-10)

Command: `python porousgen.py sample_spec.txt`

### 3.1 Inputs

```
bounding_box: 8 x 14 x 8 mm
lattice:      hcp
pore_size:    1.0 mm (sphere diameter)
porosity:     75-80% → midpoint 77.50%
formats:      stl, step
resolution:   0.04 mm
output:       federica_scaffold
```

### 3.2 Generation results

| Metric | Value |
|--------|-------|
| Total runtime | **238.2 s** (~4.0 min) |
| Tuned lattice spacing | **0.9858 mm** |
| Voxel porosity estimate (tuning grid) | 77.34% |
| Pore overlap status | Overlapping (open/interconnected) |
| Spheres in STEP boolean | 1,759 |
| STEP boolean time | 131.9 s |
| Surface mesh time (gmsh) | 48.0 s |

### 3.3 STL validation (trimesh, post-generation)

| Metric | Value |
|--------|-------|
| Triangle count | 1,579,606 |
| Vertex count | 776,551 |
| Watertight | **True** |
| Winding consistent | True |
| Bounding box dims | 8.0 × 14.0 × 8.0 mm |
| Solid volume | 209.03 mm³ |
| Porosity (mesh volume) | **76.67%** |
| Connected solid components | **1** |
| Euler number | −13,252 |
| File size | 78.98 MB |

### 3.4 STEP validation (gmsh OCC reimport)

| Metric | Value | Assessment |
|--------|-------|------------|
| Solid count | 1 | Appears single solid |
| Surface count | 2,096 | High complexity |
| Bounding box | [−0.5, −0.215, 0.0] → [8.387, 14.445, 8.0] | **Extends outside nominal box** |
| Volume (gmsh `getMass`) | **−172.64 mm³** | **Negative volume — invalid B-Rep orientation** |
| Implied porosity from STEP volume | 119.27% | Nonsense — confirms volume sign error |
| File size | 67.58 MB | Large |
| gmsh boolean warnings | Thousands of `BOPAlgo_AlertUnableToOrientTheShape` | Non-fatal to export, fatal to trust |

**Conclusion:** STL output is scientifically usable for the Federica case. STEP file exports but **fails rigorous B-Rep validation**. Current `validate.py` only checks solid count and bounding box — it does not detect negative volume or orientation failures.

### 3.5 HCP lattice verification

Nearest-neighbor distance check on tuned spacing (n=2,622 centers in padded domain):

- min/mean/max NN distance: 0.9858 / 0.9858 / 0.9858 mm  
- Expected: 0.9858 mm  
- **HCP stacking and spacing formula are numerically correct.**

---

## 4. Code reuse assessment

### 4.1 Reusable (migrate with minimal changes)

1. **Lattice center generators** (`centers_sc`, `centers_bcc`, `centers_fcc`, `centers_hcp`) — mathematically correct, deterministic ordering.
2. **Voxel solid grid builders** (`sphere_solid_grid`, `gyroid_solid_grid`) — core porosity engine.
3. **Bisection tuner** (`tune()`) — monotonic 1D search with tolerance; works for spacing and gyroid level-set.
4. **STL export pipeline** (`grid_to_stl`) — padding, marching cubes, trimesh cleanup.
5. **STEP boolean pipeline** (`build_step`) — gmsh OCC cut; needs validation hardening, not rewrite.
6. **Spec parsing** (`load_spec`, `parse_porosity`, `parse_box`) — simple key:value format; basis for `DesignSpecification` import.

### 4.2 Duplicated (consolidate)

- `hcp_centers()` is copy-pasted in `build_stl.py`, `build_step.py`, `tune_spacing.py` with identical logic to `porousgen.centers_hcp`.
- `intersects()` sphere-box test duplicated in `build_step.py` and `porousgen.build_step`.
- Hard-coded constants `LX=8, LY=14, LZ=8, R=0.5, A=0.985` in three legacy scripts.

### 4.3 Obsolete (preserve, do not extend)

- `build_stl.py`, `build_step.py`, `tune_spacing.py` — development scratch scripts with hard-coded paths to `E:\Projects\Federica\`.
- `parse_step_vertices.py` — validates STEP by vertex coordinate range only; explicitly disallowed by new acceptance rules.

### 4.4 Unsafe patterns

| Pattern | Location | Risk |
|---------|----------|------|
| STEP validity = solid count > 0 | `validate.py`, `inspect_step.py` | Declares invalid geometry valid |
| No connectivity analysis | All scripts | Cannot verify open/interconnected pores |
| No wall-thickness measurement | All scripts | Cannot enforce manufacturing constraints |
| Porosity from infinite-lattice intuition only in README | README | Boundary effects not quantified in output |
| Silent porosity range → midpoint | `parse_porosity()` | User not shown assumption |
| No reproducibility metadata | All scripts | No seeds, versions, or hashes recorded |
| gyroid only TPMS | `porousgen.py` | diamond, primitive not implemented |
| Box domain only | All scripts | Cylinder not supported |

### 4.5 Scientifically incomplete

- **Throat diameter:** never measured; overlap inferred from spacing < pore diameter.
- **Open vs closed porosity:** warning printed but not measured.
- **Pore connectivity:** not computed (no pore-phase labeling or percolation test).
- **Wall thickness:** not computed.
- **Resolution uncertainty:** porosity reported to 0.01% regardless of 0.04 mm voxel size.
- **STEP vs STL consistency:** when both requested, STL comes from STEP tessellation — porosity differs (76.67% mesh vs 77.34% voxel estimate).

---

## 5. Architecture gaps vs target application

| Requirement | Current state |
|-------------|---------------|
| Typed `DesignSpecification` | Plain dict from text file |
| User approval gate | None — runs immediately |
| Feasibility check | None |
| Ambiguity detection | None — `hcp` assumed, range → midpoint silently |
| Agentic layer | None |
| GUI | None |
| Background workers | None |
| Validation report | Console print only |
| Repair loops | None |
| Run history / provenance | None |
| Federica regression test | Manual only |
| CLI + GUI entry points | CLI only via `porousgen.py` |

---

## 6. Performance baseline (Federica, this workstation)

| Stage | Time |
|-------|------|
| Porosity tuning (voxel, coarse grid) | < 5 s (embedded in total) |
| STEP boolean (1,759 spheres) | 131.9 s |
| STEP → STL tessellation | 48.0 s |
| **Total** | **238.2 s** |

Memory: not instrumented; peak likely driven by 200×350×200 voxel grid (~14M voxels) and 1.58M triangle mesh.

---

## 7. Recommended migration strategy

1. **Extract** lattice, voxel, tuning, and export modules from `porousgen.py` into `porous_designer/generators/` and `porous_designer/geometry/` without changing algorithms initially.
2. **Wrap** spec parsing in Pydantic `DesignSpecification`; keep legacy `sample_spec.txt` import path.
3. **Replace** `validate.py` with multi-check `ValidationReport` including STEP orientation/volume sign checks.
4. **Do not delete** original scripts; mark deprecated in README.
5. **Add** Federica regression test that re-discovers spacing via tuner (no hard-coded 0.985).
6. **Defer** STEP repair until BRepCheck-based validation is implemented in Phase 3.

---

## 8. Unresolved risks

1. STEP negative volume may be gmsh `getMass` orientation issue vs true invalid solid — requires `BRepCheck_Analyzer` or equivalent.
2. Python 3.14 is bleeding-edge; CI should target 3.12 as primary.
3. Large STL (79 MB, 1.58M faces) may stress GUI preview — need decimation for display mesh.
4. No `.gitignore` — `__pycache__` was committed in baseline (fix in Phase 1).
