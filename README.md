# PGG — Porous Geometry Generation

**Porous Structure Designer** — generate 3D porous structures (STL + STEP) from a plain-text specification or structured GUI fields.
Built for lab samples / scaffolds: give it a bounding box, a lattice type, a pore size and a target porosity, and it produces printable/CAD-ready files.

Repository: [github.com/saeedrafieyan/PGG](https://github.com/saeedrafieyan/PGG)

## Requirements
- Python 3 with `numpy`, `scikit-image`, `trimesh` (for STL) and `gmsh` (for STEP).
  All are already installed in this environment.

## Usage

From a spec file:
```
python porousgen.py sample_spec.txt
```

Or purely from the command line (flags override spec values):
```
python porousgen.py --box 8x14x8 --lattice hcp --pore 1 --porosity 75-80% --formats stl,step --out sample
```

## Spec file format
Human-readable `key: value` lines; `#` starts a comment.
```
bounding_box: 8 x 14 x 8      # mm (X Y Z)
lattice:      hcp             # sc | bcc | fcc | hcp | gyroid
pore_size:    1.0             # mm  (sphere diameter; for gyroid = unit-cell size)
porosity:     75-80%          # target void fraction (single value OR a range -> midpoint)
formats:      stl, step       # stl and/or step
resolution:   0.04            # voxel size for meshing / porosity (mm)
output:       sample          # output filename prefix
```

## How it works
1. **Pore lattice** — pore centers are placed on the chosen lattice
   (`sc`, `bcc`, `fcc`, `hcp`), parameterized by nearest-neighbour spacing.
2. **Porosity tuning** — the pore diameter is fixed by `pore_size`; the tool
   bisects the lattice spacing until the measured void fraction (from a voxel
   sampling of the block) matches the target porosity. For `gyroid` it instead
   tunes the level-set constant of the implicit TPMS surface.
3. **STL** — the solid voxel field is triangulated with marching cubes
   (watertight, exported as compact binary).
4. **STEP** — the block and pore spheres are rebuilt in OpenCASCADE (via gmsh)
   and boolean-cut into an exact B-rep solid.

## Notes & limits
- **Interconnection:** when the tuned spacing is smaller than the pore diameter,
  pores overlap → open, interconnected porosity (what you usually want for a
  scaffold). If porosity is low enough that spacing exceeds the pore diameter,
  pores are isolated (closed) — the tool prints a warning. Denser lattices
  (`fcc`, `hcp`) interconnect at lower porosity than `sc`/`bcc`.
- **Max porosity before overlap:** sc ≈48%, bcc ≈32%, fcc/hcp ≈26% *solid*
  fraction at the touching point (i.e. porosity ≈52/68/74% respectively);
  above that the pores must overlap.
- **STEP is for sphere lattices only.** Gyroid is an implicit surface, so it is
  exported as STL only.
- **STEP performance:** the boolean scales with pore count. Small pores in a
  large box → thousands of spheres → the cut can take minutes. gmsh may print
  `BOPAlgo_Alert...` warnings during the cut; these are non-fatal.
- STL is voxel-tessellated at `resolution`; smaller values = smoother surface +
  larger files. When both formats are requested, the STL is derived from the
  exact STEP B-rep instead.

## Example
`sample_spec.txt` reproduces the original 8×14×8 mm HCP sample with 1 mm pores at
75–80% porosity → `federica_scaffold.stl` + `federica_scaffold.step`.
