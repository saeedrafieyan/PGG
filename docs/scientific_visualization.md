# Scientific Visualization

Phase 3A.2 visualization is display-only.

The GUI may compute display normals on an in-memory PyVista mesh:

```python
display_mesh = loaded_mesh.extract_surface().triangulate()
display_mesh = display_mesh.compute_normals(
    point_normals=True,
    cell_normals=True,
    consistent_normals=True,
    auto_orient_normals=True,
    inplace=False,
)
```

The validated STL is not modified, overwritten, or re-exported.

## Depth Cues

Depth perception is improved through:

- neutral surface colors
- darker scientific background
- smooth normals
- key/fill/rim lighting
- specular highlights
- perspective projection
- optional ambient occlusion
- optional transparent exterior mode

These improve inspection only. They do not imply any geometric change.
