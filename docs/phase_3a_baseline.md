# Phase 3A Baseline

Recorded before Phase 3A GUI implementation.

| Item | Baseline |
| --- | --- |
| Branch | `feature/agentic-porous-gui` |
| Latest commit | `56d628b Validate deterministic pipeline Phase 2C` |
| Working tree | clean before Phase 3A edits |
| CLI entry point | `porous-designer = porous_designer.cli:main` |
| Existing GUI entry point | `porous-designer-gui = porous_designer.gui.app:main` |
| Existing GUI state | placeholder message box only |

## Tests Run

| Command | Result |
| --- | --- |
| `python -m pytest tests/unit -q -p no:cacheprovider` | 39 passed |
| `python -m pytest tests/integration/test_phase_2b_generators.py -q -p no:cacheprovider` | 6 passed |
| `python -m porous_designer.cli generate tests/fixtures/federica_regression.yaml --yaml --profile preview` | preview run completed |

## Preview Smoke Result

| Metric | Value |
| --- | ---: |
| Run ID | `08f9e2b6-16d4-4c96-a5ca-5ab3fe8d785a` |
| Status | failed final acceptance, preview artifact produced |
| Lattice spacing | 0.9883 mm |
| Tuning-grid porosity | 76.71% |
| Final voxel porosity | 76.71% |
| Final mesh porosity | 77.63% |
| Triangles | 1,031,710 |
| Watertight | true |
| Solid components | 5 |
| Preview STL | `runs/08f9e2b6-16d4-4c96-a5ca-5ab3fe8d785a/geometry/federica_scaffold.preview.stl` |
| Total runtime | 14.3 s |
| Peak memory | 726.8 MB |

The preview command returns a generated preview STL but is not final acceptance.
The cleanup policy rejected the preview cleanup fraction, which is expected for
preview-only inspection and is surfaced as a warning.

## Existing Run Directory Format

Run directories live under `runs/<run_id>/` and contain:

- `approved_specification.yaml`
- `blackboard.json`
- `checksums.json`
- `environment.json`
- `timing.json`
- `tuning_history.csv`
- `validation_report.json`
- `geometry/*.stl`

The run directory remains the authoritative artifact store. Phase 3A run
history must store only metadata and paths.

## Dependency Check

The project already declares GUI optional dependencies in `pyproject.toml` and
`environment.yml`. The local bundled runtime initially lacked PySide6, PyVista,
PyVistaQt, and pytest-qt; they were installed into the runtime for Phase 3A
development and verification.

## Validation Thresholds

No existing validation thresholds were changed for Phase 3A baseline setup.
