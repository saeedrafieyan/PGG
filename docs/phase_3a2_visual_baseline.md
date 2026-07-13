# Phase 3A.2 Visual Baseline

Baseline captured before changing the renderer.

## Fixtures

| Fixture | Domain | Structure | Screenshot |
| --- | --- | --- | --- |
| Small SC | 4 x 4 x 4 mm | SC spherical pores | `docs/phase_3a2_before_sc.png` |
| Small gyroid | 4 x 4 x 4 mm | gyroid TPMS | `docs/phase_3a2_before_gyroid.png` |

## Baseline Renderer Configuration

The Phase 3A renderer used PyVistaQt defaults:

| Setting | Baseline |
| --- | --- |
| Mesh color | PyVista default pale blue |
| Background | white |
| Projection | PyVista default |
| Lighting | default renderer lighting |
| Smooth shading | not explicitly enabled |
| Actor properties | default `add_mesh` properties |
| Anti-aliasing | not explicitly configured |
| Depth peeling | not configured |
| Ambient occlusion | not configured |
| Camera reset | default reset, limited padding control |
| Clipping | controls existed but did not modify the rendered mesh |

## Baseline Image Metric

The gyroid baseline screenshot was bright and low contrast:

| Image | Size | Luminance std. dev. | Mean luminance |
| --- | ---: | ---: | ---: |
| `phase_3a2_before_gyroid.png` | 1320 x 798 | 21.39 | 242.43 |

This matches the observed pale-blue-on-white, flat-silhouette appearance.

## Normals

The gyroid preview STL loaded for the post-fix smoke reported:

- points: 1,764
- cells: 3,868
- bounds: `[-0.2, 3.8, -0.2, 3.8, -0.2, 3.8]`
- point normals in STL: false
- cell normals in STL: false

Phase 3A.2 therefore computes display normals on an in-memory copy only. The
validated STL is not overwritten or re-exported.
