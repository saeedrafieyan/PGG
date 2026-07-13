# Cylinder Accuracy

Phase 2C adds:

```powershell
porous-designer cylinder-accuracy --diameter 8 --height 14 --resolutions 0.40,0.20,0.10,0.05
```

The command compares analytic cylinder volume against the voxelized domain mask.

Analytic volume for diameter 8 mm and height 14 mm:

`703.716754 mm3`

| Resolution | Grid | Voxelized volume | Volume error |
| ---: | --- | ---: | ---: |
| 0.40 mm | 20 x 20 x 35 | 707.840000 mm3 | 0.586% |
| 0.20 mm | 40 x 40 x 70 | 707.840000 mm3 | 0.586% |
| 0.10 mm | 80 x 80 x 140 | 703.360000 mm3 | 0.051% |
| 0.05 mm | 160 x 160 x 280 | 703.780000 mm3 | 0.009% |

## Recommendation

Use at least 40 voxels across the smallest cylinder dimension for dimensional
screening, then run a resolution-sensitivity study before accepting final
porosity or connectivity metrics. For this 8 mm diameter cylinder, that implies
0.20 mm or finer as a starting point; 0.10 mm and 0.05 mm substantially improve
volume accuracy.
