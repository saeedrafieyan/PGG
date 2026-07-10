# Phase 2B Report

## Implemented

- Unified `PorousGenerator` interface and registry.
- SC, BCC, FCC, HCP adapters.
- Gyroid, diamond, and primitive TPMS implicit generators.
- Box and cylinder domain masks.
- Resource estimation before voxel allocation.
- Cleanup safety reports with configurable hard limits.
- Optional validated mesh optimization profiles.
- Preview, final, and reference generation profiles.
- Resolution-sensitivity command producing JSON and CSV.
- CLI commands: `estimate`, `sensitivity`, `optimize-mesh`.
- Expanded unit and integration tests.

## Not Implemented

- GUI
- LLM agents
- STEP generation
- FEA
- inverse design
- cloud services

## Current Limitations

- Mesh optimization depends on optional trimesh simplification support and falls
  back to the master mesh if unavailable or invalid.
- Coarse cylinder meshes can show meaningful volume sensitivity because curved
  boundaries are voxel clipped.
- TPMS pore diameter and throat size are not measured.
- Sensitivity plots are represented as machine-readable CSV/JSON in Phase 2B;
  richer plotting can be added later.

## Federica Phase 2B Metrics

Measured final run for the compact Federica regression:

| Metric | Value |
| --- | ---: |
| Master mesh triangles | 7,006,676 |
| Optimized mesh triangles | not generated (`none` profile) |
| Triangle reduction | 0% |
| Master STL size | 350,333,884 bytes |
| Optimized STL size | not generated |
| Tuned spacing | 0.98828125 mm |
| Voxel porosity | 76.861% |
| Mesh porosity | 76.980% |
| Watertight | yes |
| Nonmanifold edges | 0 |
| Solid components | 1 |
| Pore components | 1 |
| Pore percolation | X, Y, and Z |
| STL SHA-256 | `f02a6fa92c433416e23ef2e9280a5acc3161fb06c557386b9d9b3a369ca7c05b` |
| Runtime | 83.86 s |
| Peak memory | 5,007.20 MB |
| Estimated peak memory | 3,297.81 MB |

Cleanup removed four one-voxel solid islands, total removed volume
`0.000256 mm3`, equal to about `0.000123%` of solid voxels. The cleanup is
recorded in the blackboard.

Coarse sensitivity run at `0.20 mm` and `0.16 mm` classified:

- control parameter: stable
- voxel porosity: stable
- mesh porosity: unstable
- triangle count: unstable

This confirms that coarse preview/sensitivity meshes should not be used for
final acceptance.

## Recommended Phase 2C

1. Add PNG plot generation for sensitivity reports.
2. Add approximate throat and wall-thickness measurements.
3. Add NPZ export for voxel/SDF fields.
4. Design STEP acceptance tests before re-enabling STEP.
