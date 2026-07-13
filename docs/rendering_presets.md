# Rendering Presets

Phase 3A.2 adds five display-only rendering presets.

| Preset | Purpose |
| --- | --- |
| Scientific | neutral gray material, dark charcoal background, smooth shading |
| High Contrast | brighter geometry on a near-black background |
| Light Background | publication-friendly light background with gray geometry |
| Wireframe | topology inspection with visible mesh lines |
| Surface + Edges | shaded surface with subtle dark edges |

Appearance preferences are stored with GUI settings through `QSettings`. They
are not written into `DesignSpecification` and are not scientific geometry
parameters.

Changing presets does not reload or regenerate the STL.
