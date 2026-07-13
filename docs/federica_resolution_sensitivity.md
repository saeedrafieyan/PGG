# Federica Resolution Sensitivity

Phase 2C reran Federica at three final voxel resolutions and compared every row
to the finest successful result, 0.04 mm.

| Resolution | Spacing | Voxel porosity | Mesh porosity | Triangle count | Mesh porosity delta vs 0.04 mm | Triangle delta vs 0.04 mm |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.10 mm | 0.98828125 | 76.710% | 77.626% | 1,031,710 | +0.645% | -5,974,966 |
| 0.06 mm | 0.98828125 | 76.907% | 77.345% | 3,010,240 | +0.364% | -3,996,436 |
| 0.04 mm | 0.98828125 | 76.861% | 76.980% | 7,006,676 | 0.000% | 0 |

Classification thresholds:

| Metric | Threshold | Result |
| --- | ---: | --- |
| Control parameter | 0.01 mm | stable |
| Voxel porosity | 0.01 fraction | stable |
| Mesh porosity | 0.01 fraction | stable |
| Triangle count | 100,000 triangles | unstable |

## Interpretation

The bisection tuner rediscovers the same spacing at all three tested
resolutions. Voxel and mesh porosity remain within the acceptance threshold, so
the final porosity result is stable for this fixture. Triangle count is not
stable and should never be interpreted as a resolution-independent material
property.

The sensitivity command now writes `reference_resolution_mm`,
`classification_thresholds`, and each row's `delta_vs_finest` block to
`sensitivity.json`.
