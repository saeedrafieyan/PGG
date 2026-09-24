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

## TPMS (Phase 4.1)

Implicit families: gyroid, diamond (Schwarz D), primitive (Schwarz P), I-WP,
Neovius, Fischer-Koch S, Lidinoid. Each comes as a **sheet** (solid within
`t/2` of the minimal surface, `|f|/|grad f| <= t/2`) or a **network** (solid on
one side, `f/|grad f| <= c`). Spatial period: `unit_cell_size_mm`.

Control parameter: `tau = wall_thickness / cell` (sheet) or
`kappa = network_offset / cell` (network), tuned to the porosity target unless
`wall_thickness_mm` / `network_offset_mm` is fixed. The legacy
`tpms_level_set` is ignored by the implicit kernel.

## Strut lattices (Phase 4.1)

`strut_cubic`, `strut_bcc`, `strut_octet`, `strut_kelvin`: cylindrical struts
of diameter `tau * cell` along the lattice edges, exact distances via cubic
symmetry folding.

## Voronoi foam (Phase 4.1)

`voronoi_foam`: struts along the edges of a Voronoi tessellation of jittered
seeds; `unit_cell_size_mm` is the mean seed spacing, `voronoi_randomness`
(0-1) the jitter, and `generation.deterministic_seed` fixes the foam.

## Grading

Porosity grading (`targets.porosity_grading`: linear / radial /
surface_distance) for all non-sphere families; cell-size grading
(`structure.cell_size_grading`, linear) for TPMS and strut lattices.

See `docs/phase_4_1_report.md` for the method and verification.
