# Numerical Sensitivity

Phase 2B adds:

```powershell
porous-designer sensitivity <spec> --resolutions 0.10,0.06,0.04
```

The command runs the deterministic generator at selected resolutions and writes:

- `sensitivity.json`
- `sensitivity.csv`

It compares tuned control parameter, voxel porosity, mesh porosity, component
counts, pore percolation, triangle count, runtime, peak memory, and STL hash.
Phase 2C also records the finest successful resolution as
`reference_resolution_mm` and adds a `delta_vs_finest` block to each row.

Metrics are classified as:

- `stable`: variation is within a configured tolerance.
- `converging`: latest two resolutions are close even if coarse values differ.
- `unstable`: latest values still materially change.

Preview or sensitivity metrics are not final acceptance metrics.
