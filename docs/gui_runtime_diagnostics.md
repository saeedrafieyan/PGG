# GUI Runtime Diagnostics

Phase 3A.1 adds debug GUI logging.

Launch with:

```powershell
python -m porous_designer.gui.app --debug-gui
launch_pgg_gui.bat --debug-gui
```

Logs are written to:

`logs/gui_debug_<timestamp>.log`

Each log line is JSON with:

- timestamp
- process ID
- parent process ID
- thread ID
- event name
- worker type
- child process ID
- child exit code
- run ID when available

The main toolbar also includes `Diagnostics`, which displays:

- Python version
- Qt version
- PySide6 version
- VTK version
- PyVista version
- PyVistaQt version
- Qt platform plugin
- multiprocessing start method
- process ID
- QApplication/top-level widget state
- debug log path

Do not log meshes, large arrays, full specifications, or VTK objects.
