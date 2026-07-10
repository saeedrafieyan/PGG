# Resource Estimation

Before voxel allocation, Phase 2B estimates:

- grid shape
- voxel count
- base boolean array memory
- temporary array memory
- marching-cubes amplification
- estimated peak memory
- runtime class

The estimator compares peak memory with available system memory when it can be
detected. If available memory cannot be detected, the estimate is still saved but
not rejected solely for missing system data.

Configured thresholds:

- warning fraction: `resources.warning_memory_fraction`
- hard limit: `resources.maximum_memory_fraction`

The estimate is conservative and intended to prevent obvious unsafe runs, not to
predict exact peak memory.
