# Performance Profile

Phase 2C adds:

```powershell
porous-designer profile <spec> --profile final
```

The command writes `profile.json` alongside the run artifacts.

## Federica Final Profile

| Stage | Time |
| --- | ---: |
| Tuning | 5.72 s |
| Voxel generation | 1.32 s |
| Marching cubes | 32.21 s |
| Validation | 23.25 s |
| Export | 0.70 s |
| Total generation | 63.21 s |
| Wall clock | 63.26 s |
| Peak memory | 5,007 MB |

Resource estimate:

| Metric | Value |
| --- | ---: |
| Grid | 200 x 350 x 200 |
| Voxels | 14,000,000 |
| Base memory estimate | 13.35 MB |
| Temporary memory estimate | 80.11 MB |
| Marching-cubes estimate | 3,204.35 MB |
| Estimated peak | 3,297.81 MB |
| Feasibility status | feasible |
| Runtime class | moderate |

## Interpretation

Marching cubes and validation dominate runtime. Phase 2C keeps validation in the
critical path because the rejected optimization candidates show why topology and
surface checks are necessary.
