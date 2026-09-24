# Phase 4.1 — how to test it yourself

All commands run from `E:\Projects\GG` in PowerShell. Outputs go to
`runs\phase_4_1\<run_id>\` (`geometry\` holds STL/3MF/STEP,
`validation_report.json` the checks, `blackboard.json` all metrics).

## A. Automated tests (≈ 6 min)

```powershell
python -m pytest tests -q -m "not live_provider"
```

Expected: `336 passed` (or more). Phase 4.1 only:

```powershell
python -m pytest tests\unit\test_implicit_phase_4_1.py tests\unit\test_agentic_phase_4_1.py tests\integration\test_phase_4_1_generation.py -q
```

## B. Command line — one example per feature

```powershell
porous-designer families
porous-designer make-phantom examples\phase_4_1\wound_phantom.stl
porous-designer generate examples\phase_4_1\01_network_gyroid_box.yaml
porous-designer generate examples\phase_4_1\02_octet_sphere.yaml
porous-designer generate examples\phase_4_1\03_voronoi_cylinder.yaml
porous-designer generate examples\phase_4_1\04_radial_graded_gyroid.yaml
porous-designer generate examples\phase_4_1\05_cell_graded_kelvin.yaml
porous-designer generate examples\phase_4_1\06_skinned_iwp_cylinder_step.yaml
porous-designer generate examples\phase_4_1\07_wound_phantom_fill.yaml
porous-designer generate examples\phase_4_1\08_fixed_wall_primitive.yaml
```

| # | feature | what to check (reference run) |
|---|---|---|
| 01 | network TPMS, 3MF | PASSED, mesh porosity ≈ 70 % (70.2), `kappa` control |
| 02 | strut lattice in a sphere | ≈ 80 % (80.3); round outline in the slicer |
| 03 | Voronoi foam | ≈ 75 % (75.2); rerun → identical STL SHA-256 in `checksums.json` |
| 04 | radial porosity grading | open centre, dense rim; `porosity_profile` in `blackboard.json` |
| 05 | cell-size grading | cells grow from bottom (1.5 mm) to top (3 mm) |
| 06 | lateral skin + STEP | solid side wall, open ends; `.step` opens in CAD as one solid (~90 s) |
| 07 | mesh domain (wound phantom) | part overlays `wound_phantom.stl` exactly (load both in a viewer) |
| 08 | fixed wall thickness | porosity reported as a result (≈ 69 %), not tuned |

Typical runtimes 7–50 s each on the reference machine.

## C. GUI (`start_gui.bat`)

Manual Design mode:

1. **Structure**: the family list has 16 entries. Pick *Neovius* → the TPMS
   variant box is active; set *network* → wall thickness greys out. Pick
   *Voronoi foam* → randomness is active, cell grading greys out. Pick
   *Octet truss* → tick *Grade the unit-cell size*.
2. **Domain**: choose *sphere* (diameter), or *mesh* → *Browse...* the
   phantom `examples\phase_4_1\wound_phantom.stl`; the extents line shows
   ~30.9 × 19.3 × 6.5 mm. Set *Solid skin* to 0.4 mm.
3. **Targets**: tick *Graded porosity*, choose *radial*, 0.85 → 0.55;
   the single target greys out.
4. **Generation**: tick *3MF* and *STEP*; choose compute *auto*/*cuda*.
   A STEP note appears in the issues list.
5. *Generate Preview*, then *Generate Final*; the result row lists the
   3MF/STEP status.

Agentic Design mode (deterministic parsing works offline; OpenRouter if
enabled) — try these requests and confirm the proposed fields:

* "Make a 10 x 10 x 5 mm network gyroid with a 2 mm unit cell and 70 % porosity, export STL, 3MF and STEP"
  → gyroid, `tpms_variant = network`, formats 3mf/step/stl, nothing "unsupported".
* "A 12 mm sphere filled with octet truss, 3 mm unit cell, 80 % porosity"
  → sphere domain `[12]`, `strut_octet`.
* "BCC spherical pores in a 10 x 10 x 10 mm box, 1 mm pore diameter"
  → box (not sphere), `bcc_spherical_pores`.
* "20 x 20 x 20 mm gyroid with an interconnected pore network, 60 % porosity"
  → no network variant (the word refers to the pores).

Live LLM check (uses free-tier requests):

```powershell
porous-designer evaluate-agent-provider --provider openrouter --limit 4
```

## D. Printing (optional)

Import a 3MF (e.g. 02 or 04) into your SLA slicer; the size must appear in
millimetres without scaling. Walls in these examples are 0.16–0.45 mm (07 is the thinnest); check
your resin's minimum feature before printing finer designs.
