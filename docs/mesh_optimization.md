# Mesh Optimization

Phase 2B adds optional mesh optimization profiles:

- `none`: default; preserves only the master mesh.
- `conservative`: attempts modest face-count reduction.
- `balanced`: attempts larger reduction, still gated by validation.

The pipeline always writes the unmodified master mesh first. An optimized mesh is
accepted only if it passes hard checks for watertightness, winding consistency,
positive volume, component count, bounding-box change, volume/porosity change,
degenerate faces, and deterministic sampled surface deviation.

If optimization is unavailable or fails validation, the master STL remains the
recommended output. Phase 2B does not use aggressive optimization by default.
