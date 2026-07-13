# GUI User Guide

Launch PGG with:

```powershell
python -m porous_designer.gui.app
```

or on Windows:

```powershell
launch_pgg_gui.bat
```

For runtime diagnostics:

```powershell
python -m porous_designer.gui.app --debug-gui
launch_pgg_gui.bat --debug-gui
```

Debug logs are written under `logs/`. The toolbar `Diagnostics` action opens
runtime and rendering diagnostics, including GPU/OpenGL details.

## Basic Workflow

1. Set the output name and output folder.
2. Choose a box or cylinder domain.
3. Choose a structure family.
4. Enter the relevant geometric fields.
5. Set target porosity and tolerance.
6. Choose preview/final resolutions.
7. Click `Estimate`.
8. Click `Generate Preview`.
9. Inspect the preview mesh.
10. Click `Generate Final` when the estimate is acceptable.
11. Review validation results.
12. Export the HTML report.

## Rendering Presets

The preview panel includes:

- Scientific
- High Contrast
- Light Background
- Wireframe
- Surface + Edges

Use `Scientific` for normal inspection and `Light Background` for publication
screenshots. These settings affect display only.

## Preview Policy

Before a mesh is loaded, the preview status reads:

`No preview loaded`

After preview generation, the preview panel labels meshes with a compact status
row:

`PREVIEW | Not final validation | <preset> | <filename>`

When a final artifact is explicitly opened from run history, the status uses:

`FINAL ARTIFACT VIEW | Validation status: <status> | <filename>`

Preview metrics are approximate and cannot be accepted as final scientific
results.

## Rendering Diagnostics

Detailed renderer settings, OpenGL vendor/renderer/version, package versions,
and OpenGL extensions are available through `Diagnostics > Rendering`.

OpenGL extensions are collapsed by default. Use `Copy Rendering Diagnostics` or
`Save Diagnostics` when filing a rendering issue.

## Large Final Meshes

The GUI does not automatically load large final STLs. Use run history or output
folders to explicitly inspect final artifacts.

## Disabled Features

STEP, FEA, inverse design, cloud deployment, authentication, arbitrary CAD code
generation, and LLM assistance are disabled in Phase 3A.
