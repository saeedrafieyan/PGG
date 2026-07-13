# Federica Mesh Optimization

Phase 2C tested optional mesh reduction on the Federica final master mesh:

`runs/_test_integration_prev/d5162ab3-6ad3-4a18-9409-b0ac26f8ad28/geometry/federica_scaffold_master.stl`

The master mesh is the only accepted output.

## Master Mesh

| Metric | Value |
| --- | ---: |
| Triangles | 7,006,676 |
| STL size | 350,333,884 bytes |
| Watertight | yes |
| Winding consistent | yes |
| Nonmanifold edges | 0 |
| Degenerate faces | 0 |
| Mesh shell components | 88 |
| Solid material components | 1 |
| Volume | 206.255204 mm3 |
| Porosity | 76.980446% |

Mesh shell count is recorded for transparency. Material connectivity is derived
from the voxel solid phase, where the final accepted scaffold has one connected
solid component.

## Conservative Candidate

| Metric | Value |
| --- | ---: |
| Accepted | no |
| Triangles | 5,255,006 |
| STL size | 262,750,384 bytes |
| Triangle reduction | 25.0% |
| Volume change fraction | 0.000001 |
| Porosity change | 0.000000 |
| Bounding-box change | 0.001045 mm |
| Max sampled surface deviation | 0.048112 mm |
| Optimization runtime | 21.59 s |
| Peak optimization memory | 3,414 MB |

Rejection reasons:

- candidate is not watertight
- nonmanifold edges were introduced
- degenerate faces were introduced
- mesh shell component count changed from 88 to 3,613
- sampled surface deviation exceeded the 0.04 mm conservative threshold

## Balanced Candidate

| Metric | Value |
| --- | ---: |
| Accepted | no |
| Triangles | 3,503,338 |
| STL size | 175,166,984 bytes |
| Triangle reduction | 50.0% |
| Volume change fraction | 0.000001 |
| Bounding-box change | 0.001587 mm |
| Max sampled surface deviation | 0.090270 mm |
| Optimization runtime | 16.92 s |
| Peak optimization memory | 1,848 MB |

The balanced candidate failed the same acceptance policy more strongly on
surface deviation. It is useful only as a rejected validation artifact.

## Conclusion

No optimized Federica STL is recommended. The conservative reduction preserves
global volume and porosity well, but local topology and surface fidelity fail
the current hard checks.
