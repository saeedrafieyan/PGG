# Windows Multiprocessing

Windows uses spawn semantics for Python multiprocessing. Phase 3A.1 follows
these rules:

- GUI modules must be import-safe.
- `QApplication` is created only inside `gui.app.main`.
- `MainWindow` is created only inside `gui.app.main` or explicit tests/scripts.
- `multiprocessing.freeze_support()` is called in the GUI entry point.
- Worker process targets are top-level functions.
- Worker payloads are serializable dictionaries.
- Workers do not receive Qt objects, VTK objects, PyVista widgets, meshes,
  NumPy arrays, open file handles, or controller references.

The child process returns only compact data:

- artifact paths
- scalar metrics
- warnings
- structured errors
- run identifiers

Unexpected exits are detected by the parent process and reported through the GUI
instead of leaving the UI busy indefinitely.
