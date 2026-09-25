# AGE - Agentic Geometry Engineering

(formerly PGG - Porous Geometry Generation; the Python package is still `porous_designer`)

AGE turns a plain-language request into a printable porous part (STL / 3MF /
STEP). Every number it reports comes from deterministic tools, not from a
language model. The **Planner** reads the request and records where each value
came from. The **Designer** chooses what was left open and checks the printer
before anything is generated. The **Verifier** generates and measures the
part. The **Repairer** adjusts only the values the Designer chose. There are
two human checkpoints: approve the design, then approve the result.

Repository: [github.com/saeedrafieyan/PGG](https://github.com/saeedrafieyan/PGG)

## Requirements

- Python 3.12+ (3.14 tested)
- Core: `numpy`, `scipy`, `scikit-image`, `trimesh`, `gmsh`, `pydantic`, `PyYAML`, `structlog`
- GPU (optional, CUDA via PyTorch): used for large grids, permeability (LBM) and stiffness (FFT)
- Extras: `gui` (PySide6, pyvista), `web` (starlette, uvicorn), `llm` (httpx, keyring)

```powershell
pip install -e ".[gui,web,llm,dev]"
```

## Quick start

```powershell
# plain language -> verified design (two checkpoints in the terminal; --yes approves both)
porous-designer design "bone scaffold, 10 x 10 x 10 mm cube, gyroid, for my resin printer"

# desktop app: Describe -> Review -> Download   (--advanced for every parameter)
porous-designer-gui

# local web app and JSON API on http://127.0.0.1:8765
porous-designer serve
```

Structured specifications still work:

```powershell
porous-designer generate tests\fixtures\federica_regression.yaml --yaml
porous-designer estimate tests\fixtures\federica_regression.yaml --yaml --profile final
```

## Phase 4.1: structures, domains, formats

- **16 families**: sphere pores (SC, BCC, FCC, HCP); sheet or network TPMS
  (gyroid, diamond, primitive, I-WP, Neovius, Fischer-Koch S, Lidinoid); strut
  lattices (cubic, BCC, octet, Kelvin); stochastic Voronoi foam.
- **Domains**: box, cylinder, sphere, or any closed mesh (STL/OBJ/PLY/3MF), with
  an optional solid skin.
- **Grading** of porosity (linear, radial, from the surface) and cell size.
- **Exports**: STL, 3MF (for slicers), faceted STEP (for CAD).

See `docs/phase_4_1_report.md` and `examples/phase_4_1/`.

## Phase 4.2: measurements and printability

Every run is measured (`generation.metrology`: `basic` by default, `full` adds
physics):

- pore-size and wall-thickness distributions (continuous PSD / local thickness);
- throat size (largest sphere passing through), MIP-like intrusion curve,
  closed pores, surface area, curvature and geometric tortuosity;
- `full`: permeability from a lattice-Boltzmann solver (GPU) and the effective
  stiffness tensor from FFT homogenisation, both on the periodic unit cell.

Printer profiles for FDM, MSLA, DLP, tomographic and xolographic volumetric,
extrusion bioprinting, SLS and LPBF check walls, openings, drainage, islands,
overhangs, vial or build-volume fit and stray dose. A calibration coupon turns
measurements of your own printer into a profile:

```powershell
porous-designer printers
porous-designer make-coupon coupon_out --profile generic_msla
porous-designer calibrate --profile generic_msla --measurements coupon_out\generic_msla_measurements.csv --name my_resin_printer
```

See `docs/phase_4_2_report.md`.

## Phase 4.3: design agent

`porous-designer design "<request>" [--process sla] [--printer my_resin_printer] [--provider openrouter] [--yes]`

- **Planner**: the deterministic parser, or grounded OpenRouter extraction (every
  value must quote the request). Application words ("bone graft", "wound")
  add literature values with citations (`knowledge/data/applications.yaml`).
- **Designer**: measured structure-property tables of every family
  (`knowledge/data/property_tables.json`, `porous-designer build-property-tables`)
  predict walls, pores, openings, permeability and stiffness before
  generation. An infeasible request is explained with numbers and the nearest
  feasible alternatives (larger pores, lower porosity, another architecture,
  another printer).
- **Verifier / Repairer**: measured checks decide. Repairs are bounded (at most
  3 iterations), logged, and never change a value you stated.
- Every step is recorded in `agent_trace.json`, next to a `design_report.html`.

See `docs/phase_4_3_report.md`.

## Phase 4.4: simple interface

`services/design_session.py` is the one UI-independent flow (Describe -> Review ->
Download) behind the desktop window, the web page and the JSON API
(`api/server.py`). The desktop window has one text box, a process and printer
choice, a review card showing each value with its source, a 3D preview and download
buttons. **Advanced mode** opens the full engineering window. See
`docs/phase_4_4_report.md`.

## Phase 4.5: AGE-Bench

470 tiered prompts (explicit, partial, application/lay, constrained,
infeasible, out-of-scope, held-out paraphrases) with ground truth, a runner and
metrics. The metrics cover extraction accuracy, invented values, feasibility
detection, constraint satisfaction, property error, printability, iterations,
time and user effort. It compares AGE with its ablations and with LLM-only
baselines:

```powershell
porous-designer bench build
porous-designer bench run --system age --mode propose
porous-designer bench run --system age_llm:<free-model-id> --mode extract --per-tier 5
porous-designer bench run --system llm_direct:<free-model-id> --mode extract --per-tier 5
porous-designer bench report --by-tier
```

See `docs/phase_4_5_report.md`.

## Agent providers

External LLM access is off by default; everything works without a network.
OpenRouter (free models) is used for grounded extraction only. Store the key
once, in the OS credential store (it is never written to files or logs):

```
porous-designer credentials set
```

## How it works

1. The structure is a continuous signed field (TPMS, strut, Voronoi or sphere
   pores) combined with the domain's signed distance and an optional skin.
2. Porosity tuning finds the control parameter on a coarse grid, refines it on
   the final grid, and corrects it so the exported mesh meets the target.
3. Marching cubes triangulates the continuous field.
4. Validation and metrology measure topology, porosity, sizes, connectivity
   and printability. Physics runs on the periodic unit cell.
5. Artifacts and reports are written under `runs/<run_id>/`.

## Notes and limits

- Sizes are measured on voxels (about half a voxel of uncertainty). Permeability
  and stiffness are unit-cell (bulk) values.
- Printer profiles are generic until calibrated with the coupon. Printed parts
  need physical validation.
- STEP is a faceted solid and is skipped for very large lattices (use 3MF or STL).
- Scan-to-part, inverse design / optimisation, multi-material, degradation and
  deployment are outside the current scope. The agent says so when a request
  asks for them.

## Example

`tests/fixtures/federica_regression.yaml` reproduces the Federica HCP regression
fixture and writes run artifacts under `runs/<run_id>/`.
