# GUI Validation Display

The validation panel displays backend validation reports in a table:

| Metric | Requested | Achieved | Tolerance | Status | Method |
| --- | --- | --- | --- | --- | --- |

Status values are textual and do not depend on color alone:

- PASS
- WARNING
- FAIL
- NOT AVAILABLE
- NOT REQUESTED

Selecting a row shows:

- detailed method
- explanation
- severity
- related artifacts guidance
- suggested user action

## Included Metrics

The table can display all backend validation checks, including:

- domain dimensions
- voxel porosity
- mesh porosity
- porosity disagreement
- watertightness
- winding consistency
- nonmanifold edges
- positive volume
- solid components
- pore components
- X/Y/Z percolation
- cleanup fraction
- triangle count
- output hash through run artifacts
- runtime and peak memory through run timing

Unsupported wall-thickness and throat-size measurements are marked unavailable.
