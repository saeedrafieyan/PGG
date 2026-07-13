# Phase 3A.1 Reproduction

The reported Windows symptom was:

- clicking `Estimate` could result in a blank white or unresponsive GUI
- clicking `Generate Preview` could result in the same behavior

## Environment

| Item | Observation |
| --- | --- |
| Branch | `feature/agentic-porous-gui` |
| Baseline commit | `21ef12a Implement local desktop GUI Phase 3A` |
| Test command | `python -X faulthandler scripts/windows_gui_smoke.py` |
| Debug log | `logs/gui_debug_20260713_120251.log` |
| Screenshot | `docs/phase_3a1_windows_smoke.png` |

## Reproduction Steps

1. Launch the GUI on Windows with diagnostics enabled.
2. Use a 2.5 x 2.5 x 2.5 mm SC spherical-pore fixture.
3. Trigger `Estimate`.
4. Trigger `Generate Preview`.
5. Wait for child-process completion.
6. Verify the generated STL is loaded into the embedded preview panel.

The automated interactive smoke script performs these same actions without
forcing `QT_QPA_PLATFORM=offscreen`, so it exercises the PyVistaQt path.

## Observed Behavior After Fix

| Check | Result |
| --- | --- |
| Blank new top-level window | not observed |
| Main window blank | not observed |
| Main window unresponsive | not observed |
| Resource panel populated | yes |
| Child process starts | yes, PID `76640` |
| Child process exits | yes, exit code `0` |
| Python traceback | none from application code |
| Qt/VTK/faulthandler output | one non-terminating Windows COM/RPC faulthandler line was printed while inside Qt event loop |
| Worker completion callback | yes |
| Preview STL produced | yes |
| Preview actor added | yes, actor count `2` |

## Process IDs

| Process | PID | Parent PID |
| --- | ---: | ---: |
| GUI process | 56164 | 64444 |
| Preview worker process | 76640 | 56164 |

## Important Log Events

- `estimate_clicked`
- `estimate_completed`
- `worker_process_started`
- `child_process_entry`
- `preview_complete`
- `worker_result_received`
- `preview_mesh_actor_created`
- `worker_process_exited`
- `worker_finished`

The debug log confirms that preview generation ran outside the GUI process and
that mesh loading/rendering happened back on the GUI thread.
