# Determinism

Phase 2C adds:

```powershell
porous-designer determinism <spec> --runs 2
```

The command reruns the final deterministic pipeline and writes
`determinism.json`.

## Federica Result

Classification: `numerically deterministic`

Two final Federica runs produced the same:

- tuned spacing: `0.98828125 mm`
- voxel porosity: `0.7686122857142857`
- mesh porosity: `0.7698044226190477`
- triangle count: `7,006,676`
- solid components: `1`
- pore components: `1`
- X/Y/Z pore percolation: `true`
- cleanup report
- STL SHA-256:
  `f02a6fa92c433416e23ef2e9280a5acc3161fb06c557386b9d9b3a369ca7c05b`

The classification is not `bitwise deterministic` because the tuning history
CSV includes runtime measurements. The generated geometry and acceptance metrics
were identical.

## Policy

Runtime and memory columns are diagnostic, not acceptance criteria. Geometry,
porosity, connectivity, cleanup, and STL hash are the deterministic contract for
later GUI or agent layers.
