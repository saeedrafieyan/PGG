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

Debug logs are written under `logs/`.

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

The preview panel permanently labels preview meshes as:

`Preview only, not final validation`

Preview metrics are approximate and cannot be accepted as final scientific
results.

## Large Final Meshes

The GUI does not automatically load large final STLs. Use run history or output
folders to explicitly inspect final artifacts.

## Disabled Features

STEP, FEA, inverse design, cloud deployment, authentication, arbitrary CAD code
generation, and LLM assistance are disabled in Phase 3A.
