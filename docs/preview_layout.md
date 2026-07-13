# Preview Layout

Phase 3A.3 keeps the preview panel focused on geometry inspection.

## Normal Layout

The center panel now contains:

1. primary rendering controls
2. display and section controls
3. one compact preview-status row
4. the PyVistaQt viewport

The verbose renderer diagnostics block was removed from the normal layout. The
viewport receives the released vertical space, and the status row remains
fixed-height.

## Compact Status

Before a mesh is loaded, the status reads:

```text
No preview loaded
```

For preview meshes, the status format is:

```text
PREVIEW | Not final validation | <preset> | <filename>
```

For explicitly opened final artifacts, the status format is:

```text
FINAL ARTIFACT VIEW | Validation status: <status> | <filename>
```

The status does not show GPU, OpenGL, or extension information.

## Toolbar Cleanup

Controls are grouped into three rows:

- rendering preset, colors, appearance reset, and camera views
- display toggles such as smooth shading, edges, axes, perspective, ambient
  occlusion, transparency, opacity, and edge width
- clipping, slicing, screenshots, screenshot scale, and transparent PNG export

Button labels use complete text such as `Reset Appearance` and
`Transparent Exterior`.

## Screenshots

The screenshot action captures only the renderer output. Toolbars, status
labels, validation tables, and diagnostics widgets are outside the renderer and
are not included in default viewport screenshots.
