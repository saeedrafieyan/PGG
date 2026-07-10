import numpy as np

from porous_designer.geometry.voxel import remove_small_solid_components, voxel_porosity


def test_cleanup_removes_tiny_internal_component():
    grid = np.zeros((5, 5, 5), dtype=bool)
    grid[2:4, 2:4, 2:4] = True
    grid[0, 0, 0] = True
    cleaned, report = remove_small_solid_components(
        grid,
        min_voxels=2,
        max_removed_solid_fraction=0.2,
        reject_boundary_touching=False,
    )
    assert report.accepted
    assert report.removed_component_count == 1
    assert report.removed_voxel_count == 1
    assert not cleaned[0, 0, 0]


def test_cleanup_rejects_boundary_touching_component():
    grid = np.zeros((5, 5, 5), dtype=bool)
    grid[2:4, 2:4, 2:4] = True
    grid[0, 0, 0] = True
    cleaned, report = remove_small_solid_components(grid, min_voxels=2)
    assert not report.accepted
    assert report.removed_touched_boundary
    assert cleaned[0, 0, 0]


def test_cleanup_rejects_large_removed_fraction():
    grid = np.zeros((5, 5, 5), dtype=bool)
    grid[1:3, 1:3, 1:3] = True
    grid[4, 4, 4] = True
    cleaned, report = remove_small_solid_components(
        grid,
        min_voxels=2,
        max_removed_solid_fraction=0.01,
        reject_boundary_touching=False,
    )
    assert not report.accepted
    assert "fraction" in report.reason
