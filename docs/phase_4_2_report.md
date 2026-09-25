# Phase 4.2 — Measured properties, printability rules, calibration coupon

Phase 4.2 makes AGE measure what it builds. Every Final run now reports pore,
throat and wall sizes, closed pores, drainage, tortuosity, surface area and
curvature. On request it also reports permeability and stiffness. The
measurements feed validation checks: the wall and throat minimums are no
longer "unsupported", but measured and enforced. A printer profile then turns
the measurements into process-specific printability rules. A printable
calibration coupon replaces the generic printer limits with measured ones.

## 1. Measurements (`porous_designer.metrology`)

`generation.metrology`: `none` | `basic` (default) | `full`. Preview runs are
never measured.

### On the part (as built, at the final resolution)

| quantity | method |
|---|---|
| pore-size distribution | morphological opening by spheres ("continuous PSD", Münch & Holzer 2008): the local size of a point is the largest inscribed sphere containing it; volume-weighted d05/d10/d50/d90 |
| wall/strut thickness distribution | the same on the solid ("local thickness", Hildebrand & Rüegsegger 1997) |
| percolation (critical throat) diameter | largest sphere that crosses the part between two reservoirs along each open axis (binary search over sphere sizes) |
| intrusion / drainage curve | spheres enter from the open faces and pass only openings as wide as themselves, as in mercury-intrusion porosimetry; gives the median throat size and the void fraction drainable through a given opening |
| closed pores | void components with no path to the outside (count, fraction, largest volume) |
| geometric tortuosity | shortest 26-connected void path between opposite faces ÷ thickness (`skimage.graph.MCP_Geometric`) |
| specific surface | mesh area ÷ domain volume, and ÷ solid volume |
| curvature | mean H and Gaussian K on the zero level set of the continuous field (central differences in a narrow band, away from the domain cut); saddle fraction (K < 0) |

Accuracy: voxel-centre distances are converted to boundary distances with a
half-voxel offset. Slabs of 4, 5, 10 and 11 voxels measure exactly within
±½ voxel. Sphere radii are snapped to the distance values that actually
occur, so no geometric-ladder quantisation is added. Grids above 4 M voxels
are measured on a central sub-volume, and the report says so.

### On the periodic representative volume element (RVE)

Effective properties need periodic boundaries. The design is therefore
re-evaluated on its own periodic cell (`metrology.rve`) rather than cut out
of the part:

* TPMS and struts: one unit cell, from the kernel's normalised distance, with
  40–112 voxels per cell chosen so thin walls span ≥ 6 voxels;
* sphere pores: the conventional cell (SC, BCC, FCC cubic; HCP
  orthorhombic a × √3a × 2c with four pores);
* Voronoi: a 3 × 3 × 3-cell periodic tessellation (seeds plus 26 images,
  and a periodic KD-tree);
* graded designs: RVEs at both ends of the grading.

RVE porosities match the calibration curves (gyroid 0.706 against 0.709). They
also match exact values: SC union of r = 0.55 spheres, 0.673 against 0.672
analytically; HCP packing fraction π/(3√2)·(d/s)³ within 0.01. The RVE gives
the headline pore and wall sizes, because it is free of boundary cuts and
resolved independently of the part's voxel size.

### Permeability (`full`): lattice Boltzmann

D3Q19, two-relaxation-time collision with Λ = 3/16, half-way bounce-back,
Guo body force and periodic boundaries. Darcy's law gives k = ν⟨u⟩/g. Only
fluid nodes are stored, and streaming with bounce-back is a single gather per
step on CUDA.

| verification | result |
|---|---|
| plane Poiseuille, H = 10 / 20 nodes | +0.6 % / +0.1 % vs H²/12 |
| square duct, a = 16 | +0.4 % vs a²/28.45 |
| τ⁺ = 1.0 vs 1.5 | 0.08 % difference (viscosity independent) |

Flow uses the full RVE: narrow windows control permeability, and coarsening
biased it by 14 %. The run has a 60 s budget per axis; a run that stops at the
budget is reported as a lower bound. Cubic lattices use one axis, HCP two
(x = y) and Voronoi or graded designs three. Example: a 2 mm sheet gyroid at
70 % porosity gives k ≈ 7 × 10⁻⁹ m²; a 1.5 mm-cell Voronoi foam at 75 % gives
1.5–1.7 × 10⁻⁸ m² (mild anisotropy).

### Stiffness (`full`): FFT homogenisation

A small-strain Galerkin FFT scheme solved with conjugate gradients (Zeman et
al. 2010; de Geus et al. 2017). The unknown is the displacement gradient, with
G(T) = (T·ξ)⊗ξ/|ξ|². The void has a stiffness ratio of 10⁻³. Six unit macro
strains give C*, and S* = C*⁻¹ gives E_i, G_ij, ν_ij and the Zener ratio.

| verification | result |
|---|---|
| dense solid | E = 1, ν = 0.3 exactly |
| laminate φ = 0.5, parallel | E∥ = 0.5005 (Voigt 0.5) |
| laminate, perpendicular | 0.0027 (Reuss ≈ 0.002) |
| sheet gyroid, ρ = 0.29 | E*/Es = 0.100 (literature ≈ 0.1) |

## 2. Validation checks from measurements

| check | rule |
|---|---|
| `minimum_wall_thickness` | 10th-percentile wall thickness (RVE) + ½ voxel ≥ `constraints.minimum_wall_thickness_mm` (fail otherwise) |
| `minimum_throat_size` | percolation diameter (part) + ½ voxel ≥ `constraints.minimum_throat_size_mm` (fail) |
| `pore_size_median` | within 20 % (or one voxel) of `targets.pore_size_target_mm` (warning) |
| `closed_pores` | ≤ 1 % of the void when open pores are required (warning) |

The 10th percentile is used because the 5th is dominated by voxel
staircases on diagonal struts: a 0.5 mm BCC strut shows a d05 of 0.28 mm
but a d10 of 0.48 mm. The deterministic parser now extracts "minimum wall
thickness 0.3 mm", "strut diameter 400 µm", "throat size 0.2 mm" and similar
phrases. A value stated without "minimum" or "at least" is marked for
confirmation.

## 3. Printability (`porous_designer.printability`)

Profiles are YAML files. The built-in generic ones cover FDM 0.4 mm, mSLA,
DLP, tomographic volumetric printing, xolography, extrusion bioprinting,
SLS and LPBF. User profiles live in `<AGE data root>/printers/` and take
precedence. `manufacturing.process` chooses the generic profile, and
`manufacturing.printer_profile` names a specific one. With process
`unknown`, no printability rules run.

| rule | processes |
|---|---|
| fits build volume / fits vial (bounding diagonal) | all / volumetric |
| min wall (measured) vs profile, and a robust-wall recommendation | all |
| smallest opening (percolation diameter) vs min hole | all |
| closed pores trap resin or powder | SLA, DLP, volumetric, SLS, LPBF |
| drainage / wash-out / powder removal: void reachable through throats ≥ `min_drain_throat_mm` (from the intrusion curve) ≥ 95 % | same |
| islands: layer regions not resting on the layer below (with the overhang allowance; specks < 4 voxels or one pixel ignored) | layered processes |
| overhang area fraction beyond the process limit | layered processes with a limit |
| stray-dose risk: fine pores inside thick parts | volumetric |
| pores vs extrusion width | FDM, bioprinting |
| mesh size (> 5 M triangles) | all |

Violations are warnings, so the part is still delivered. If
`manufacturing.enforce_printability` is set they become failures. Minimal
surfaces have K ≤ 0, so the height function on them has no local minima and
TPMS sheets produce no islands; the checks confirm this. Voronoi foams do
show islands from V-shaped nodes, which is a real printing issue.

## 4. Calibration coupon

```
porous-designer make-coupon out_dir --profile generic_msla
porous-designer calibrate --profile generic_msla --measurements out_dir\coupon_generic_msla_measurements.csv --name my_printer
```

The coupon has ladders of fins (walls), pins, tubes (vertical holes) and
slot pairs (gaps), spaced geometrically from 0.5× to 3× the profile's limits.
It also has three gyroid cubes with fixed walls, to weigh for porosity. Every
feature is an exact watertight primitive overlapping a base plate, and
slicers merge them. For vial printers every row is a separate coupon that
fits the vial. The measurement sheet takes `printed_ok` (and optionally
`measured_mm`) per feature. A limit is the smallest size that printed with
every larger size also printed, and the median measured − nominal is stored
as a bias. The result is a calibrated profile, selectable in the GUI and via
`manufacturing.printer_profile`.

## 5. Interfaces

* Run folder: `metrology.json` (all measurements and timings) and
  `printability.json`; the checks appear in `validation_report.json`.
* `GenerationResult.measurements` (headline values) and `.printability`.
* CLI: `generate` prints the measurements and printability issues;
  `printers`, `make-coupon`, `calibrate`.
* GUI: the manufacturing panel has a process list, profiles filtered by
  process (calibrated ones marked), limits and "fail the run on printability
  issues". The generation panel has a measurement level. The targets panel
  labels wall/throat minimums as measured.

## 6. Cost (RTX 5070 Ti, 6 mm parts at 0.06 mm)

| design | basic | full |
|---|---|---|
| gyroid, 1 M voxels | ≈ 13–22 s | ≈ 27 s |
| Voronoi foam | ≈ 30 s | ≈ 50 s |
| HCP spheres touching (0.09 mm windows) | ≈ 20 s | ≤ 3 min (flow budget) |

## 7. Limits

* Sizes carry about ±½ voxel. Small pores of round cross-section can be
  underestimated by up to one voxel because sphere centres sit on voxel
  centres. Refine the resolution for features under ~10 voxels.
* Permeability and stiffness are for the periodic cell, not the finite part
  with its boundary effects.
* Printer limits are generic until you calibrate with the coupon.
* Stray-dose closure in volumetric printing is a risk rule, not a light
  simulation.
