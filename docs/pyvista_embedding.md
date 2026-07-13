# PyVistaQt Embedding

The normal GUI uses `pyvistaqt.QtInteractor(parent=preview_panel)`.

Rules:

- create the renderer only in the main GUI process
- create the renderer only on the Qt GUI thread
- insert the renderer into the preview panel layout
- never use `BackgroundPlotter` for the embedded preview
- never call `Plotter.show(interactive=True)` from the GUI workflow
- load preview STL files on the GUI thread after worker completion
- compute display normals on an in-memory copy when STL normals are missing
- clear existing actors before loading a new preview
- call `add_mesh`, `reset_camera`, and `render`
- log actor counts and render failures

`QT_QPA_PLATFORM=offscreen` is used only for automated tests. The production
entry point no longer forces `PYVISTA_OFF_SCREEN=true`.

Phase 3A.2 adds rendering presets, a three-light scene rig, defensive ambient
occlusion/depth-peeling feature detection, and screenshot metadata sidecars.
