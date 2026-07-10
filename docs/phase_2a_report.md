# Phase 2A Deterministic STL Pipeline Report

## Scope Completed

Phase 2A implements a deterministic box-domain, spherical-pore STL pipeline for
SC, BCC, FCC, and HCP lattices. It does not implement GUI, LLM agents, TPMS,
cylinder domains, STEP repair, FEA, or inverse design.

Implemented components:

- Lattice center generation with documented coordinate conventions.
- Voxel/SDF solid-grid construction for sphere-pore lattices.
- Deterministic porosity bisection with monotonicity and reachability checks.
- Marching-cubes mesh generation and binary STL export.
- Geometry, mesh, porosity, and connectivity validation.
- CLI commands: `generate`, `validate`, and `inspect-run`.
- Compact Federica regression fixture and deterministic repeat test.
- Provenance outputs: approved specification, blackboard, tuning history,
  timing, checksums, environment, and validation report.

## STEP Status

STEP acceptance remains disabled in Phase 2A. The legacy Federica STEP fixture is
recorded as failed because reimport produced negative B-Rep volume and a bounding
box outside the nominal domain. The deterministic pipeline exports STL only.

## Federica Regression Metrics

Measured with `tests/fixtures/federica_regression.yaml` using final resolution
`0.04 mm`.

| Metric | Value |
| --- | ---: |
| Tuned lattice spacing | 0.98828125 mm |
| Tuning-grid porosity | 76.71% |
| Final voxel porosity | 76.86% |
| Final mesh porosity | 76.98% |
| Voxel/mesh porosity difference | 0.12 percentage points |
| Triangle count | 7,006,676 |
| STL size | 350,333,884 bytes |
| Watertight | yes |
| Enclosed solid volume | 206.2552 mm3 |
| Solid voxel components | 1 |
| Pore voxel components | 1 |
| Pore percolation | X, Y, and Z |
| Removed voxelization islands | 4 one-voxel solid islands |
| STEP status | disabled_phase_2a |

## Runtime Breakdown

Latest passing full Federica regression:

| Stage | Time |
| --- | ---: |
| Tuning | 5.29 s |
| Voxel generation | 1.11 s |
| Marching cubes | 33.25 s |
| Validation | 12.28 s |
| Export | 0.73 s |
| Total | 52.68 s |
| Peak memory | 4,979.63 MB |

Main bottleneck: marching cubes, followed by validation on the large final mesh.

## Determinism

The deterministic repeat test verifies identical tuned spacing, voxel porosity,
mesh porosity, triangle count, and STL SHA-256 for repeated runs with the same
specification, seed, resolution, and dependency environment.

The latest recorded Federica STL SHA-256 was:

`f02a6fa92c433416e23ef2e9280a5acc3161fb06c557386b9d9b3a369ca7c05b`

## Comparison With Original Baseline

| Metric | Original porousgen baseline | Phase 2A |
| --- | ---: | ---: |
| Runtime | 238.2 s | 52.68 s |
| Tuned spacing | 0.9858 mm | 0.98828125 mm |
| Mesh/STL porosity | 76.67% | 76.98% |
| Triangles | 1,579,606 | 7,006,676 |
| Watertight | yes | yes |
| Solid components | 1 | 1 by voxel material connectivity |
| STEP | generated but failed validation | disabled |

Phase 2A intentionally does not decimate the STL because decimation has not yet
been proven to preserve porosity, watertightness, connectivity, and dimensions.

## Commands To Reproduce

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
C:\Users\Z32\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests/unit -q -p no:cacheprovider
C:\Users\Z32\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests/integration -q -p no:cacheprovider
C:\Users\Z32\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m porous_designer.cli generate tests/fixtures/federica_regression.yaml --yaml
```

## Remaining Limitations

- STEP generation is intentionally disabled pending a dedicated STEP phase.
- Final STL output is large at strict `0.04 mm` resolution.
- Mesh shell component count is recorded for transparency, but material
  connectivity is validated on the voxel solid phase.
- Tiny disconnected solid voxel islands are removed deterministically before
  meshing and recorded in provenance.
- No GUI, LLM parsing, TPMS, cylinder domain, repair policy, or HTML report is
  included in Phase 2A.

## Recommended Phase 2B

1. Add a deterministic preview artifact path with PNG cross-sections.
2. Add NPZ export of the final voxel/SDF representation.
3. Introduce bounded repair policy objects around the current small-island
   cleanup and porosity retuning behavior.
4. Split slow regression tests from quick smoke tests in CI.
5. Begin STEP backend design only after defining exact acceptance checks for
   B-Rep volume, bounding box, and topology.
