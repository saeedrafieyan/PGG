# TPMS Validation

Phase 2C expands TPMS coverage for:

- gyroid
- diamond
- primitive

Each family is exercised at target porosities 35%, 60%, and 80%. The tests
verify that the final generator succeeds and that the measured mesh porosity is
within a practical tolerance for the compact integration fixture.

The test suite also covers an intentionally unreachable gyroid request at 99%
porosity with a very tight tolerance. That case must fail cleanly as
`INFEASIBLE`, not crash or produce a misleading accepted mesh.

## Scope

The current TPMS validation covers:

- implicit-field generation
- bisection tuning behavior
- mesh export through marching cubes
- final porosity measurement
- infeasible target reporting

It does not yet measure throat diameter, wall thickness, or anisotropic
transport properties.
