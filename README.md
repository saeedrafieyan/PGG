# AGE - Agentic Geometry Engineering

(formerly PGG - Porous Geometry Generation; the Python package is still `porous_designer`)

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

## Phase 4.1: structures, domains, formats

- **16 families**: sphere pores (SC, BCC, FCC, HCP); sheet or network TPMS
  (gyroid, diamond, primitive, I-WP, Neovius, Fischer-Koch S, Lidinoid); strut
  lattices (cubic, BCC, octet, Kelvin); stochastic Voronoi foam.
- **Domains**: box, cylinder, sphere, or any closed mesh file (STL/OBJ/PLY/3MF,
  with units); optional solid skin on all boundaries or the side wall only.
- **Grading**: porosity (linear, radial, from the surface) and unit-cell size.
- **Exports**: STL, 3MF (millimetres, for slicers), faceted STEP (for CAD).
- The exported mesh is tuned to hit the porosity target; CUDA is used for
  large grids when available.

```powershell
porous-designer families
porous-designer generate examples\phase_4_1\02_octet_sphere.yaml --yaml
porous-designer make-phantom examples\phase_4_1\wound_phantom.stl
porous-designer generate examples\phase_4_1\07_wound_phantom_fill.yaml --yaml
```

See `docs/phase_4_1_report.md` and the example specs in `examples/phase_4_1/`.

## Agent-Assisted Requests

The GUI has separate `Manual Design` and `Agentic Design` modes. Manual Design
lets users enter engineering parameters directly. Agentic Design can parse
natural-language requests into proposed typed fields, show confidence/evidence, detect
ambiguities, and require field-by-field human approval before applying anything
to the active specification.

External agent access is disabled by default. Deterministic-only parsing works
without network credentials.

Phase 4.0 replaces the OpenAI/Gemini providers with a single OpenRouter
provider (free models by default) and evidence-grounded extraction: the model
must quote the request for every value, and code verifies each quote, number,
and unit before anything is proposed. See `docs/phase_4_0_report.md`. No
external LLM is required, and external access must be explicitly enabled in the
GUI provider settings. Store the key once with:

```
porous-designer credentials set
```

Run the live faithfulness benchmark (12 cases, uses free-tier requests) with
`porous-designer evaluate-agent-provider --provider openrouter`.

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

1. The structure is a continuous signed field (TPMS, strut, Voronoi, or sphere
   pores) composed with the domain's signed distance and an optional skin.
2. Porosity tuning bisects the control parameter (wall thickness, strut
   diameter, network offset, or lattice spacing) on a coarse grid, refines it
   on the final grid, and corrects it so the exported mesh meets the target.
3. The continuous field is triangulated with marching cubes (smooth surfaces).
4. Validation records topology, porosity, connectivity, cleanup, resources, and
   provenance.
5. STL/3MF/STEP artifacts and reports are written under `runs/<run_id>/`.

## Notes And Limits

- Preview meshes are not final validation artifacts.
- STEP is a faceted solid, written for Final runs when the part can be reduced
  to `generation.step_max_triangles` within tolerance; the STEP is re-imported
  and its volume checked. Large lattices skip STEP; use 3MF or STL.
- Wall-thickness and throat-size minima are recorded but not yet measured.
- Large final STLs are not loaded automatically by the GUI.
- Preview rendering presets are display-only and do not alter exported STL
  geometry or validation metrics.
- Renderer and OpenGL details are available from the GUI `Diagnostics` action;
  the normal preview panel shows only a compact preview/final status row.
- FEA, inverse design, cloud deployment, autonomous multi-step execution,
  scan-to-domain processing, material optimization, and arbitrary CAD code
  generation are not part of Phase 4.1.

## Example

`tests/fixtures/federica_regression.yaml` reproduces the compact Federica HCP
regression fixture and writes run artifacts under `runs/<run_id>/`.
