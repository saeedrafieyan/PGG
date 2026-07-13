# Rendering Diagnostics

Phase 3A.3 moves detailed renderer diagnostics from the preview panel into the
main `Diagnostics` action.

## Tabs

The Diagnostics dialog contains:

- `Runtime`: Python, process, Qt, and package runtime information.
- `Rendering`: active preset, appearance settings, renderer features, system
  versions, OpenGL fields, and advanced extensions.

## Rendering Data

Rendering diagnostics are produced as a structured model with these groups:

- `appearance`: mesh color, background color, edge color, smooth shading, edge
  display, projection, opacity, axes, and bounding box settings.
- `features`: ambient-occlusion request and active method, anti-aliasing, depth
  peeling, fallback state, and rendering warning.
- `system`: VTK, PyVista, PyVistaQt, and Qt platform information.
- `opengl`: vendor, renderer, version, and extensions.
- `mesh`: loaded mesh path, filename, bounds, point/cell counts, normals, and
  display preparation timings when available.

The normal preview layout consumes only the compact status fields.

## OpenGL Extensions

OpenGL extensions are in a collapsed `OpenGL Extensions` section by default.
The section uses a read-only monospaced text area so long extension lists do not
resize the dialog.

## Actions

- `Copy Rendering Diagnostics` copies the complete rendering diagnostics text.
- `Save Diagnostics` writes runtime and rendering diagnostics to a text file.
- `Refresh` rebuilds the dialog from the current preview state.
- `Close` closes the dialog.

Refresh, copy, and save operations write compact structured GUI log events. The
complete extension list is not repeatedly logged on render, camera, or preset
changes.
