# PGG - Porous Geometry Generation

**PGG, Porous Geometry Generation** is evolving toward an **Agentic
Porous-Material Design System**. It generates deterministic porous-geometry STL
artifacts from structured specifications and now includes a human-supervised
agent-assisted request interpretation workflow. The command-line backend remains
the authoritative generation and validation engine.

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

Debug GUI launch:

```powershell
python -m porous_designer.gui.app --debug-gui
launch_pgg_gui.bat --debug-gui
```

Legacy scripts are preserved for comparison, but new development should use the
`porous_designer` package.

## Agent-Assisted Requests

The GUI has separate `Manual Design` and `Agentic Design` modes. Manual Design
lets users enter engineering parameters directly. Agentic Design can parse
natural-language requests into proposed typed fields, show confidence/evidence, detect
ambiguities, and require field-by-field human approval before applying anything
to the active specification.

External agent access is disabled by default. Deterministic-only parsing works
without network credentials.

Phase 3B.1.2 adds provider activation controls for optional OpenAI and Gemini
structured request interpretation. No external LLM is required to use PGG, and
external access must be explicitly enabled in the GUI provider settings.

Provider settings persist across dialog reopen and application restart. Raw API
keys are never stored in QSettings and are never repopulated into the password
field; credential availability is shown separately. The Agentic Request panel
shows call mode, provider, model, credential status, last decision, and last
execution.

Phase 3B.1.3 separates workflow authority: manual fields are hidden while
Agentic Design is active, approved agentic specifications are shown read-only,
and stale agentic approvals block preview/final generation.

Phase 3B.2 adds a bounded Engineering Strategy Agent. After a human-approved
agentic specification, the GUI can generate a reviewable strategy plan with
deterministic tools, validation gates, unsupported-request notes, risks, and
user checkpoints. Agentic Preview and Final require an approved non-stale plan,
but every execution step still requires an explicit user click.

Phase 3B.3 connects approved strategy-plan steps to guarded deterministic
execution. Users can run plan steps one at a time, see precondition results,
step status, structured observations, validation gates, and next-action
recommendations. This is still not autonomous multi-step execution.

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
- Preview rendering presets are display-only and do not alter exported STL
  geometry or validation metrics.
- Renderer and OpenGL details are available from the GUI `Diagnostics` action;
  the normal preview panel shows only a compact preview/final status row.
- FEA, inverse design, cloud deployment, autonomous multi-step execution,
  bounded repair, STEP generation, material optimization, and arbitrary CAD code
  generation are not part of Phase 3B.3.

## Example

`tests/fixtures/federica_regression.yaml` reproduces the compact Federica HCP
regression fixture and writes run artifacts under `runs/<run_id>/`.
