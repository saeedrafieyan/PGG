# Background Execution

Phase 3A.1 uses Qt signals plus Windows-spawn-safe process-backed workers.

## Worker Types

- `PreviewWorker`: preview generation in a child process.
- `GenerationWorker`: final generation in a child process.
- `SensitivityWorker`: sensitivity analysis in a child process.
- `ValidationWorker`: standalone STL validation in a child process.
- `EstimateWorker`: lightweight resource estimation.

## Progress

The existing backend does not expose fine-grained progress callbacks. The GUI
therefore uses named stages and indeterminate progress while generation is
running. It does not fake exact percentages.

## Cancellation

Cancellation terminates the active child process and emits a structured
cancellation message. Unexpected child exits and timeouts are also surfaced as
structured GUI errors. Completed validated artifacts are left untouched. Logs
and the last valid run artifacts remain in the run directory.

## Memory Behavior

PyVista/VTK can retain mesh memory until actors are cleared and Python releases
objects. Phase 3A loads preview meshes by default and avoids automatically
loading Federica-scale final STLs.
