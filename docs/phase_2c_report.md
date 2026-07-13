# Phase 2C Report

Phase 2C closes validation gaps left by Phase 2B. It does not add GUI, LLM
agents, STEP export, FEA, inverse design, or cloud services.

## Implemented

- Federica mesh optimization validation with candidate STL retention.
- Bidirectional sampled surface-deviation checks for optimization candidates.
- Standalone `validate-optimization` CLI command.
- Determinism study command and JSON report.
- Preview-versus-final consistency command and JSON report.
- Final profile performance command and JSON report.
- Cylinder voxelization accuracy command and JSON report.
- Sensitivity rows now include deltas relative to the finest tested resolution.
- Expanded TPMS integration coverage across gyroid, diamond, and primitive
  families.

## Federica Findings

The accepted Federica output remains the unoptimized final master STL.

| Metric | Value |
| --- | ---: |
| Final resolution | 0.04 mm |
| Tuned spacing | 0.98828125 mm |
| Voxel porosity | 76.861% |
| Mesh porosity | 76.980% |
| Triangles | 7,006,676 |
| STL size | 350,333,884 bytes |
| Watertight | yes |
| Solid components | 1 |
| Pore components | 1 |
| Pore percolation | X, Y, and Z |
| STL SHA-256 | `f02a6fa92c433416e23ef2e9280a5acc3161fb06c557386b9d9b3a369ca7c05b` |

Conservative and balanced optimization candidates were both rejected. The
conservative candidate reduced triangles by 25%, but introduced nonmanifold
edges, degenerate faces, thousands of mesh shell components, and a maximum
sampled surface deviation above the configured limit. The balanced candidate
reduced triangles by 50%, but exceeded the surface-deviation limit by a wider
margin.

## Resolution Sensitivity

Federica was tested at 0.10, 0.06, and 0.04 mm. The 0.04 mm result is the
reference.

| Resolution | Spacing | Voxel porosity | Mesh porosity | Triangles |
| ---: | ---: | ---: | ---: | ---: |
| 0.10 mm | 0.98828125 | 76.710% | 77.626% | 1,031,710 |
| 0.06 mm | 0.98828125 | 76.907% | 77.345% | 3,010,240 |
| 0.04 mm | 0.98828125 | 76.861% | 76.980% | 7,006,676 |

Classification:

- control parameter: stable
- voxel porosity: stable
- mesh porosity: stable
- triangle count: unstable

This means the physical tuning result is stable for these resolutions, while
mesh density must be treated as resolution-dependent.

## Determinism

Two final Federica runs produced identical geometry metrics and identical STL
SHA-256 hashes. The study classifies the pipeline as numerically deterministic
because the tuning history CSV includes runtime columns, so the full text
history is not bitwise identical even when the generated geometry is.

## Performance

The profiled final Federica run took 63.21 s wall-clock generation time. Peak
memory was 5,007 MB. Marching cubes and validation remain the dominant runtime
costs; validation was retained rather than weakened.

## Phase 2C Status

Phase 2C is complete for command-line validation closure. The next development
phase can safely consume the deterministic master STL and validation reports as
the authoritative backend contract.
