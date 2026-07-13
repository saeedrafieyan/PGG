# Validation Methods

Phase 2B validation records:

- bounding-box dimensions
- positive enclosed volume
- watertightness
- winding consistency
- mesh shell component count
- degenerate triangle count
- nonmanifold edge count
- voxel porosity
- STL mesh-volume porosity
- porosity-method disagreement
- solid voxel components
- pore voxel components
- pore boundary fraction
- X/Y/Z pore percolation

Material connectivity is validated on the voxel solid phase. Mesh shell count is
recorded for transparency but is not treated as the material-connectivity source
of truth for porous solids.

Cylinder and TPMS results can be resolution-sensitive because voxel clipping
approximates curved and implicit boundaries. Sensitivity analysis should be used
before treating connectivity or porosity as robust.

## Phase 2C Additions

Mesh optimization validation now records bidirectional sampled surface
deviation:

- master-to-candidate distance summary
- candidate-to-master distance summary
- combined bidirectional summary
- maximum sampled deviation used as a hard acceptance check

The standalone optimization validator also checks that candidate meshes preserve
watertightness, winding consistency, positive volume, component count,
bounding-box dimensions, volume-derived porosity, nonmanifold edge count, and
degenerate-face count.

Preview metrics are explicitly labeled as approximate or unavailable. Preview
geometry is not a final acceptance artifact.

Determinism reports compare generated geometry metrics, cleanup reports,
connectivity, validation hashes, and STL SHA-256 hashes across repeated final
runs.
