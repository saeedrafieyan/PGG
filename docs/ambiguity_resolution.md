# Ambiguity Resolution

Phase 3B.1 detects ambiguous design language before approval.

Implemented deterministic ambiguity rules include:

- `hexagonal`: HCP spherical-pore centers, hexagonal channels, or honeycomb
  solid cells
- `pore size`: generating sphere diameter, equivalent pore diameter, throat
  diameter, or maximum inscribed pore diameter
- `cell size`: TPMS unit-cell size, lattice spacing, or biological cell size
- `interconnected`: unspecified connectivity direction
- porosity range: midpoint, lower bound, upper bound, or user-selected target
- STEP/STP: requested but unsupported in accepted production output
- missing domain dimensions
- missing structure family
- missing final/manufacturing resolution
- unsupported wall/throat constraints

Mandatory ambiguities must be resolved before the user can approve a resolved
specification.
