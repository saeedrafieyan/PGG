# Structure Families

## Sphere-Pore Lattices

Supported deterministic sphere-pore lattices:

- SC
- BCC
- FCC
- HCP

Control parameter: `lattice_spacing_mm`, the nearest-neighbor sphere-center
spacing. The generating sphere diameter is `pore_diameter_mm`.

For cylinder domains, closed-pore requests filter centers so carved spheres are
fully inside the cylinder. Open-pore requests may allow boundary intersection.

## TPMS

Supported implicit TPMS families:

- gyroid
- diamond
- primitive

Control parameter: `tpms_level_set`, a dimensionless half-thickness around the
zero implicit surface. Spatial periodicity is controlled by
`unit_cell_size_mm`.

Phase 2B does not report TPMS pore diameter because equivalent pore metrics are
not explicitly measured yet. STEP export is unsupported for TPMS.
