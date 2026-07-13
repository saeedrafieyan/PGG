# PGG - Porous Geometry Generation

**PGG, Porous Geometry Generation** generates deterministic porous-geometry STL
artifacts from structured specifications. The Phase 3A desktop GUI is a local
PySide6 application for internal research workflows; the command-line backend
remains the authoritative generation and validation engine.

Repository: [github.com/saeedrafieyan/PGG](https://github.com/saeedrafieyan/PGG)

## Requirements

- Python 3.12
- Core backend: `numpy`, `scipy`, `scikit-image`, `trimesh`, `gmsh`,
  `pydantic`, `PyYAML`, `structlog`
- GUI extra: `PySide6`, `pyvista`, `pyvistaqt`, `psutil`

Install editable development dependencies:

```powershell
pip install -e ".[gui,dev]"
```

## Usage

Structured CLI:

```powershell
porous-designer generate tests\fixtures\federica_regression.yaml --yaml --profile preview
porous-designer estimate tests\fixtures\federica_regression.yaml --yaml --profile final
```

GUI:

```powershell
porous-designer-gui
python -m porous_designer.gui.app
launch_pgg_gui.bat
```

Legacy scripts are preserved for comparison, but new development should use the
`porous_designer` package.

## Spec File Format

The modern backend uses structured YAML matching `DesignSpecification`.
Legacy `key: value` files are still loadable through the CLI adapter.

Legacy example:

```text
bounding_box: 8 x 14 x 8
lattice:      hcp
pore_size:    1.0
porosity:     75-80%
formats:      stl
resolution:   0.04
output:       sample
```

## How It Works

1. Pore centers or implicit TPMS fields are generated inside a box or cylinder.
2. Porosity tuning bisects the generator control parameter.
3. The solid voxel field is triangulated with marching cubes.
4. Validation records topology, porosity, connectivity, cleanup, resources, and
   provenance.
5. STL artifacts and reports are written under `runs/<run_id>/`.

## Notes And Limits

- Preview meshes are not final validation artifacts.
- STEP is disabled in the package pipeline until the Phase 0 negative-volume
  failure is resolved.
- Wall thickness and throat size are shown as unsupported in the Phase 3A GUI.
- Large final STLs are not loaded automatically by the GUI.
- LLM assistance, FEA, inverse design, cloud deployment, authentication, and
  arbitrary CAD code generation are not part of Phase 3A.

## Example

`tests/fixtures/federica_regression.yaml` reproduces the compact Federica HCP
regression fixture and writes run artifacts under `runs/<run_id>/`.
