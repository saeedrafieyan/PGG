# Visual Regression Testing

Exact pixel matching is avoided because PyVista/VTK rendering can vary by GPU,
driver, and Qt platform plugin.

Phase 3A.2 uses robust checks:

- screenshot is not uniformly white
- screenshot is not uniformly blue
- luminance standard deviation exceeds a minimum
- multiple sampled color bands are present
- actor count is stable
- repeated preset changes do not create duplicate actors
- background and foreground colors differ

The real Windows smoke helper is:

```powershell
python scripts\windows_gui_visual_smoke.py --family gyroid --preset Scientific
```

Offscreen CI tests still verify preset state, screenshot sidecar creation, and
worker behavior. GPU-specific ambient-occlusion assertions are intentionally not
required in offscreen tests.
