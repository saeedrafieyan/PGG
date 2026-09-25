# Phase 4.3: design agent (Planner, Designer, Verifier, Repairer)

## Principle

A language model may help read the request, but **every number AGE reports
comes from deterministic tools**. Each value in the design intent records its
source:

- `user`: quoted from the request;
- `knowledge_base`: a cited literature value;
- `designer`: chosen by the agent, with a reason;
- `default`: flagged for confirmation.

A value the user stated is never changed silently. There are two human
checkpoints: approve the proposed design (before any geometry is generated)
and approve the verified result.

```
request ──► Planner ──► DesignIntent (value + source + reason + citations)
                            │
                            ▼
                        Designer ──► feasibility vs printer ──► infeasible: numbers + nearest alternatives
                            │                                     (nothing is generated)
                            ▼
                 [checkpoint 1: approve design]
                            │
                            ▼
              Verifier: generate + Phase 4.2 measurements + printability
                            │ failed checks
                            ▼
              Repairer: bounded rules, designer-chosen values only (<= 3 iterations)
                            │
                            ▼
                 [checkpoint 2: approve result]  ──► STL / 3MF / report / agent_trace.json
```

## Components

### Planner (`agentic/design_agent.py: DesignAgent.plan`)

- **Extraction**:
  - the Phase 3 deterministic parser, or the Phase 4.0 grounded OpenRouter
    extraction (every value must quote the request and is checked by code);
  - an extra evidence-quoting pass for the process (FDM, resin/SLA, DLP,
    volumetric, xolography, bioprinting, SLS, LPBF), permeability (m², mm²,
    darcy) and relative stiffness ("E*/Es 0.1", "10 % of the solid
    stiffness").
- **Parser fixes found while building AGE-Bench**:
  - "N mm cube";
  - "diameter X and height Y" in either order;
  - porosity ranges written "between 60 % and 70 %" or "60 to 70 %";
  - "cell size of";
  - "BCC lattice" now means struts;
  - the value for "pores" can no longer be taken from a neighbouring
    quantity (e.g. "0.3 mm pores, walls of at least 1 mm" used to give 1 mm
    pores).
- **Applications** (`knowledge/data/applications.yaml`, `knowledge/applications.py`):
  - bone, collagen bone culture and skin/wound presets, with aliases, ranges,
    typical values and citations: Hulbert 1970, Karageorgiou & Kaplan 2005,
    Murphy 2010, Yannas 1989, Gibson & Ashby, Rumpler 2008, Gibson 1985;
  - the longest matching alias wins;
  - presets only fill values the user did not state.
- **Out-of-scope detection**: scan-to-part, inverse design / optimisation,
  multi-material, degradation, electrical properties and drug release are
  reported in the proposal ("not supported: ...") instead of being quietly
  ignored.

### Designer

- **Property tables** (`knowledge/property_tables.py`, `knowledge/data/property_tables.json`):
  - every family (23 architecture/variant combinations) is measured on its
    periodic unit cell at 12 porosities (sphere packings: 10 spacing ratios);
  - the tools are the Phase 4.2 metrology chain: wall d10 and d50, pore d10
    and d50, throat (percolation diameter), surface area, permeability (LBM)
    and E*/Es (FFT);
  - lengths are stored per cell size, so any design is predicted in closed
    form, for example wall = w(φ)·L and k = κ(φ)·L²;
  - building the tables took about 40 min on the RTX 5070 Ti
    (`porous-designer build-property-tables`).
- **Choice** (`knowledge/feasibility.py`):
  - candidates are ordered by preference: self-supporting TPMS first on layer
    printers, extrusion-friendly struts for bioprinting, the application's
    preferred families, and the stiffest at a given porosity when stiffness
    is a target;
  - the cell size comes from the pore target, the permeability target, or
    else the smallest cell meeting the printer's minimum wall and hole with
    25 % margin;
  - the margin is capped so that at least two cells fit across the part;
  - resolution is chosen so the thinnest wall or opening spans at least 4
    voxels, within a memory budget.
- **Porosity policy**:
  - a stated single value is used as is;
  - a stated range, a default or a literature value moves to the nearest
    porosity the architecture can reach with open pores. Spherical pores
    only interconnect above about 55 % (SC), 72 % (BCC) and 78 % (FCC/HCP)
    porosity.
- **Feasibility**:
  - the part must fit the printer (vial or build volume);
  - walls must be at least the larger of the user's and the printer's
    minimum, and openings at least the larger minimum hole or throat;
  - the median pore must be within 20 % of its target;
  - at least two cells must fit across the part;
  - the porosity must lie inside the tabulated range;
  - permeability must be within 0.7–1.4× its target and stiffness within
    20 %.
- **Infeasible requests**:
  - the explanation gives the numbers, e.g. "at 85 % porosity a gyroid wall
    of 0.45 mm needs pores of at least 3.6 mm";
  - the nearest feasible alternatives change one thing each: larger pores,
    lower porosity, another architecture, or another printer (limited to the
    application's usual processes).
- **Literature values are guidance, not user values**:
  - if the typical literature pore size cannot be printed, the designer
    picks the printable design whose pores are closest to it, says so, and
    asks for confirmation;
  - if that fails, it tries the low end of the cited porosity range.

### Verifier

`generate_porous_stl` followed by the Phase 4.2 measurements (`metrology =
full` when permeability or stiffness is a target) and the printability rules.
The validation report is the only judge of pass or fail. Permeability and
stiffness targets add their own checks (0.7–1.4× and 0.8–1.25×).

### Repairer

Bounded, logged rules, at most 3 iterations:

| failed check | repair (designer-chosen values only) |
|---|---|
| walls below the user / printer minimum | enlarge the cell by the measured shortfall (or lower a free porosity by 5 %) |
| openings / drainage | enlarge the cell |
| median pore off target | scale the cell by target / measured |
| unsupported islands (lattices on layer printers) | switch to a sheet gyroid (self-supporting) |
| walls thinner than the voxel | refine the resolution |
| permeability off target | scale the cell by √(target / measured) |
| stiffness off target | invert the table with the measured model error |

If the fix would change a value the user stated, the Repairer does not apply
it. The agent stops with `needs_user` and states the conflict, for example
"walls 0.27 mm below 0.3 mm; the fix is a larger cell size, which the request
fixed at 2.2 mm".

## Structure-property tables at 70 % porosity (per unit cell size L)

| architecture | porosity range | wall d10 / L | median pore / L | opening / L | S·L | k / L² | E*/Es |
|---|---|---|---|---|---|---|---|
| sc_spherical_pores | 0.56-0.95 | 0.178 | 0.976 | 0.459 | 2.98 | 5.23e-03 | 0.155 |
| bcc_spherical_pores (at 83%) | 0.72-0.94 | 0.073 | 0.979 | 0.353 | 3.36 | 4.81e-03 | 0.060 |
| fcc_spherical_pores (at 86%) | 0.78-0.94 | 0.069 | 0.959 | 0.298 | 3.37 | 5.18e-03 | 0.011 |
| hcp_spherical_pores (at 86%) | 0.78-0.94 | 0.054 | 0.924 | 0.324 | 3.26 | 5.72e-03 | 0.019 |
| gyroid:sheet | 0.35-0.90 | 0.092 | 0.328 | 0.325 | 6.22 | 1.69e-03 | 0.100 |
| gyroid:network | 0.35-0.90 | 0.287 | 0.569 | 0.542 | 3.01 | 6.11e-03 | 0.068 |
| diamond:sheet | 0.35-0.90 | 0.083 | 0.342 | 0.236 | 7.66 | 1.03e-03 | 0.118 |
| diamond:network | 0.35-0.90 | 0.246 | 0.505 | 0.417 | 3.67 | 3.93e-03 | 0.060 |
| primitive:sheet | 0.35-0.90 | 0.122 | 0.710 | 0.315 | 4.77 | 2.10e-03 | 0.078 |
| primitive:network | 0.35-0.90 | 0.328 | 1.000 | 0.637 | 2.26 | 1.02e-02 | 0.142 |
| iwp:sheet | 0.35-0.90 | 0.083 | 0.317 | 0.232 | 6.59 | 1.15e-03 | 0.114 |
| iwp:network | 0.35-0.90 | 0.236 | 0.596 | 0.398 | 3.23 | 4.74e-03 | 0.141 |
| neovius:sheet | 0.35-0.90 | 0.073 | 0.688 | 0.073 | 6.22 | 1.95e-04 | 0.138 |
| neovius:network | 0.35-0.90 | 0.082 | 0.948 | 0.284 | 2.89 | 3.63e-03 | 0.060 |
| fischer_koch_s:sheet | 0.35-0.91 | 0.049 | 0.200 | 0.145 | 10.54 | 5.24e-04 | 0.094 |
| fischer_koch_s:network | 0.35-0.90 | 0.134 | 0.343 | 0.278 | 5.14 | 2.03e-03 | 0.070 |
| lidinoid:sheet | 0.35-0.90 | 0.049 | 0.176 | 0.161 | 11.94 | 4.53e-04 | 0.054 |
| lidinoid:network | 0.35-0.90 | 0.114 | 0.272 | 0.236 | 5.86 | 1.59e-03 | 0.022 |
| strut_cubic | 0.35-0.89 | 0.369 | 0.986 | 0.569 | 2.12 | 8.73e-03 | 0.151 |
| strut_bcc | 0.35-0.89 | 0.251 | 0.520 | 0.406 | 3.86 | 4.13e-03 | 0.029 |
| strut_octet | 0.35-0.89 | 0.157 | 0.516 | 0.193 | 5.63 | 1.52e-03 | 0.069 |
| strut_kelvin | 0.35-0.90 | 0.229 | 0.776 | 0.330 | 3.81 | 3.30e-03 | 0.101 |
| voronoi_foam | 0.35-0.89 | 0.274 | 0.791 | 0.526 | 2.83 | 6.39e-03 | 0.069 |

(Sphere packings: lengths per pore diameter; E*/Es is the smallest of the
three directional moduli; permeability is along z.)

These tables drive the design decisions. At 70 % porosity a sheet gyroid's
walls are 0.09 L, so the 0.3 mm resin minimum needs L ≈ 3.3 mm and pores
of about 1.1 mm. A network gyroid reaches the same wall thickness at
L ≈ 1.05 mm with 0.6 mm pores, which is why the agent picks it for a resin
bone scaffold.

## Example (real run)

`porous-designer design "bone scaffold, 10 x 10 x 10 mm cube, for my resin printer" --yes`

The agent recorded:

- **Part size** (10 x 10 x 10 mm) and **process** (SLA): from the request.
- **Porosity** 70 %: from the knowledge base, typical for trabecular bone
  (Karageorgiou & Kaplan 2005).
- **Pore size** 0.74 mm: chosen by the designer. The typical literature value
  of 0.5 mm cannot be printed on the generic MSLA; 0.74 mm is the closest
  printable size and is inside the cited 0.3–0.8 mm range (Hulbert 1970;
  Karageorgiou 2005). Marked for confirmation.
- **Architecture**: network gyroid (designer), with the cell size and
  resolution derived from it.
- **Notes**: match the host bone stiffness (Gibson 1985); concave surfaces
  favour tissue growth (Rumpler 2008).

Generation followed; the verified result is in `design_report.html` and
`agent_trace.json`.

## Tests

- `tests/unit/test_design_agent_phase_4_3.py` (9) uses synthetic tables and a
  fake generator:
  - provenance, and knowledge never overriding user values;
  - printer limits, infeasibility with alternatives, literature relaxation;
  - the repair loop enlarges a designer-chosen cell and never changes a user
    cell;
  - checkpoint rejection generates nothing;
  - a stiffness target selects the porosity.
- `tests/integration/test_design_agent_kernel_phase_4_3.py` (3) uses the real tables
  and kernel:
  - table monotonicity;
  - a resin gyroid scaffold is generated and verified, and the measured
    wall d10 agrees with the table prediction;
  - an infeasible FDM request is refused before generation.

## Limitations

- Tables are measured at one resolution (48 voxels per cell). Voronoi values
  are one seed (42) at randomness 1.0.
- Prediction assumes the periodic structure dominates. Skins, small parts and
  graded designs deviate, and the Verifier measures that deviation.
- The knowledge base is small (three applications, eight references) and is
  meant to be extended by domain experts; every entry carries its source.
