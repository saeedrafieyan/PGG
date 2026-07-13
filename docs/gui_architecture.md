# GUI Architecture

The Phase 3A GUI is a local PySide6 application. It does not contain an LLM
agentic layer and does not replace backend validation.

## Layers

| Layer | Responsibility |
| --- | --- |
| `gui.app` | Qt application entry point |
| `main_window` | Three-region desktop layout and dock tabs |
| `application_controller` | Coordinates UI events, workers, history, reports |
| `state_store` | GUI settings and current specification |
| `models/` | Qt table/state models |
| `panels/` | Domain-specific widgets |
| `workers/` | Background and process-backed execution |
| `reporting` | Deterministic HTML report generation |

## Backend Boundary

The GUI edits `DesignSpecification` and then calls existing deterministic
services:

- `estimate_resources`
- `generate_porous_stl`
- `run_resolution_sensitivity`
- `validate_standalone_stl`

The GUI does not duplicate scientific validation thresholds. Widget-level checks
only classify obvious field issues and unsupported measurements.

## Process Model

Final and preview generation use Windows-spawn-safe `ProcessWorker` jobs.
Worker targets are pure top-level functions that receive serializable payload
dictionaries plus result/event queues. Worker results are serialized
dictionaries containing artifact paths and metrics.

## 3D Viewer

`PreviewPanel` uses PyVistaQt when a display backend is available. In headless
test environments it falls back to a lightweight QLabel while preserving the
same load and screenshot API.

The application entry point does not force offscreen rendering in normal
interactive use.

Phase 3A.2 separates visualization settings from scientific specifications.
Rendering presets and colors are GUI preferences, not `DesignSpecification`
fields.

Phase 3A.3 separates normal preview status from deep renderer diagnostics.
`PreviewPanel` exposes a structured rendering diagnostics model for the
Diagnostics dialog while the normal preview layout displays only a compact
status row.

## Diagnostics

`DiagnosticsDialog` contains Runtime and Rendering tabs. Runtime diagnostics
come from `gui.diagnostics.runtime_diagnostics`; rendering diagnostics come
from `gui.rendering.rendering_diagnostics_model`.

OpenGL extensions are kept in a collapsed read-only text area so long capability
lists do not resize the main interface or the dialog.

## Agentic Request Interpretation

Phase 3B.1 adds a bounded agent-assisted layer. `AgenticRequestPanel` collects
natural-language requests and displays parsed fields and ambiguities.

`AgenticRequestOrchestrator` owns parsing, proposed specifications, approval
records, and audit files. The main window applies approved fields to existing
GUI panels and then calls the existing deterministic validation/estimate path.

External providers are disabled by default; automated tests use
`MockAgentProvider` or deterministic-only parsing.
