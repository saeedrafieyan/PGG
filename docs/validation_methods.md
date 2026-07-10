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
