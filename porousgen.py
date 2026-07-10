#!/usr/bin/env python
"""
porousgen - generate porous-material geometries from a plain-text spec.

Usage:
    python porousgen.py spec.txt
    python porousgen.py --box 8x14x8 --pore 1 --porosity 75-80% --lattice hcp --formats stl,step --out sample

A spec file is human-readable "key: value" lines, e.g.:

    bounding_box: 8 x 14 x 8      # mm
    lattice:      hcp             # sc | bcc | fcc | hcp | gyroid
    pore_size:    1.0             # mm  (sphere diameter, or gyroid unit-cell size)
    porosity:     75-80%          # target void fraction (single value or range)
    formats:      stl, step       # stl and/or step  (step: sphere lattices only)
    resolution:   0.04            # voxel size for meshing/porosity (mm)
    output:       sample          # output file prefix

CLI flags override spec-file values. Lines starting with # are comments.
"""
import argparse, os, sys, math, time
import numpy as np

# --------------------------------------------------------------------------
# Spec parsing
# --------------------------------------------------------------------------
def parse_number(s):
    return float(str(s).strip())

def parse_box(s):
    parts = [p for p in str(s).replace('x', ' ').replace('X', ' ').replace(',', ' ').split() if p]
    if len(parts) != 3:
        raise ValueError(f"bounding_box needs 3 numbers, got: {s!r}")
    return tuple(float(p) for p in parts)

def parse_porosity(s):
    """Accept '0.77', '77%', '75-80', '75-80%'. Range -> midpoint."""
    t = str(s).strip().replace('%', '')
    if '-' in t and not t.startswith('-'):
        a, b = t.split('-')
        val = (float(a) + float(b)) / 2.0
    else:
        val = float(t)
    if val > 1.0:          # given as a percentage
        val /= 100.0
    if not (0.0 < val < 1.0):
        raise ValueError(f"porosity must be within (0,1): got {val}")
    return val

def parse_formats(s):
    return [f.strip().lower() for f in str(s).replace(',', ' ').split() if f.strip()]

def strip_comment(line):
    # drop trailing "# comment" but keep '#' only if at line start already handled
    return line.split('#', 1)[0]

def load_spec(path):
    spec = {}
    with open(path, 'r', encoding='utf-8') as fh:
        for raw in fh:
            line = strip_comment(raw).strip()
            if not line or ':' not in line:
                continue
            k, v = line.split(':', 1)
            spec[k.strip().lower()] = v.strip()
    return spec

# --------------------------------------------------------------------------
# Lattice pore-center generators (nearest-neighbour spacing = s)
# --------------------------------------------------------------------------
def _grid_range(lo, hi, step, phase=0.0):
    i0 = math.floor((lo - phase) / step) - 1
    i1 = math.ceil((hi - phase) / step) + 1
    return [phase + i * step for i in range(i0, i1 + 1)]

def centers_sc(box, s, margin):
    xs = _grid_range(-margin, box[0] + margin, s)
    ys = _grid_range(-margin, box[1] + margin, s)
    zs = _grid_range(-margin, box[2] + margin, s)
    return np.array([(x, y, z) for x in xs for y in ys for z in zs])

def _cell_lattice(box, a, basis, margin):
    """Tile a cubic conventional cell (edge a) with fractional basis points."""
    xs = _grid_range(-margin, box[0] + margin, a)
    ys = _grid_range(-margin, box[1] + margin, a)
    zs = _grid_range(-margin, box[2] + margin, a)
    pts = []
    for x in xs:
        for y in ys:
            for z in zs:
                for (bx, by, bz) in basis:
                    pts.append((x + bx * a, y + by * a, z + bz * a))
    return np.array(pts)

def centers_bcc(box, s, margin):
    a = 2.0 * s / math.sqrt(3.0)                     # nn along body diagonal
    return _cell_lattice(box, a, [(0, 0, 0), (0.5, 0.5, 0.5)], margin)

def centers_fcc(box, s, margin):
    a = s * math.sqrt(2.0)                            # nn across face
    basis = [(0, 0, 0), (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5)]
    return _cell_lattice(box, a, basis, margin)

def centers_hcp(box, s, margin):
    a = s
    c = a * math.sqrt(2.0 / 3.0)
    dy = a * math.sqrt(3.0) / 2.0
    off = (a / 2.0, a / (2.0 * math.sqrt(3.0)))
    LX, LY, LZ = box
    pts = []
    z0, z1 = -margin, LZ + margin
    y0, y1 = -margin, LY + margin
    x0, x1 = -margin, LX + margin
    kz = 0; z = z0
    while z <= z1:
        ox, oy = (0.0, 0.0) if kz % 2 == 0 else off
        j = int(math.floor((y0 - oy) / dy)) - 1
        y = oy + j * dy
        while y <= y1:
            rx = ox + (a / 2.0 if (j % 2) else 0.0)
            i = int(math.floor((x0 - rx) / a)) - 1
            x = rx + i * a
            while x <= x1:
                pts.append((x, y, z)); i += 1; x = rx + i * a
            j += 1; y = oy + j * dy
        kz += 1; z = z0 + kz * c
    return np.array(pts)

LATTICES = {'sc': centers_sc, 'bcc': centers_bcc, 'fcc': centers_fcc, 'hcp': centers_hcp}

# --------------------------------------------------------------------------
# Solid voxel grid (True = solid material)
# --------------------------------------------------------------------------
def sphere_solid_grid(box, vox, radius, spacing, lattice):
    nx = int(round(box[0] / vox)); ny = int(round(box[1] / vox)); nz = int(round(box[2] / vox))
    grid = np.ones((nx, ny, nz), dtype=bool)
    gx = (np.arange(nx) + 0.5) * vox
    gy = (np.arange(ny) + 0.5) * vox
    gz = (np.arange(nz) + 0.5) * vox
    centers = LATTICES[lattice](box, spacing, margin=radius)
    r2 = radius * radius
    rr = int(np.ceil(radius / vox)) + 1
    for cx, cy, cz in centers:
        ix = int(round(cx / vox - 0.5)); iy = int(round(cy / vox - 0.5)); iz = int(round(cz / vox - 0.5))
        x0, x1 = max(0, ix - rr), min(nx, ix + rr + 1)
        y0, y1 = max(0, iy - rr), min(ny, iy + rr + 1)
        z0, z1 = max(0, iz - rr), min(nz, iz + rr + 1)
        if x0 >= x1 or y0 >= y1 or z0 >= z1:
            continue
        sx = gx[x0:x1] - cx; sy = gy[y0:y1] - cy; sz = gz[z0:z1] - cz
        d2 = sx[:, None, None] ** 2 + sy[None, :, None] ** 2 + sz[None, None, :] ** 2
        grid[x0:x1, y0:y1, z0:z1] &= (d2 > r2)
    return grid

def gyroid_solid_grid(box, vox, cell, level):
    nx = int(round(box[0] / vox)); ny = int(round(box[1] / vox)); nz = int(round(box[2] / vox))
    gx = (np.arange(nx) + 0.5) * vox
    gy = (np.arange(ny) + 0.5) * vox
    gz = (np.arange(nz) + 0.5) * vox
    k = 2.0 * math.pi / cell
    X = gx[:, None, None] * k; Y = gy[None, :, None] * k; Z = gz[None, None, :] * k
    g = (np.sin(X) * np.cos(Y) + np.sin(Y) * np.cos(Z) + np.sin(Z) * np.cos(X))
    return g > level      # solid where g exceeds the level-set constant

# --------------------------------------------------------------------------
# Porosity tuning (bisection)
# --------------------------------------------------------------------------
def tune(target, eval_fn, lo, hi, decreasing, tol=0.003, iters=40):
    """Find param in [lo,hi] so eval_fn(param) == target. `decreasing`:
    porosity decreases as param grows (True for sphere spacing)."""
    best = None
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        p = eval_fn(mid)
        best = (mid, p)
        if abs(p - target) <= tol:
            break
        too_porous = p > target
        if (too_porous and decreasing) or (not too_porous and not decreasing):
            lo = mid
        else:
            hi = mid
    return best

# --------------------------------------------------------------------------
# Mesh export
# --------------------------------------------------------------------------
def grid_to_stl(grid, vox, out_path):
    from skimage import measure
    import trimesh
    pad = 2
    f = np.zeros((np.array(grid.shape) + 2 * pad), dtype=np.float32)
    f[pad:-pad, pad:-pad, pad:-pad] = grid.astype(np.float32)
    verts, faces, normals, _ = measure.marching_cubes(f, level=0.5, spacing=(vox, vox, vox))
    verts -= pad * vox
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, vertex_normals=normals, process=True)
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals()
    mesh.export(out_path)
    return mesh.is_watertight, len(mesh.faces), mesh.volume

def build_step(box, radius, spacing, lattice, out_step, out_stl=None, mesh_size=None):
    import gmsh
    def intersects(c):
        dx = max(0.0, -c[0], c[0] - box[0])
        dy = max(0.0, -c[1], c[1] - box[1])
        dz = max(0.0, -c[2], c[2] - box[2])
        return dx * dx + dy * dy + dz * dz < radius * radius
    centers = [tuple(c) for c in LATTICES[lattice](box, spacing, margin=radius) if intersects(c)]
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.option.setNumber("Geometry.OCCParallel", 1)
    gmsh.model.add("porous")
    b = gmsh.model.occ.addBox(0, 0, 0, box[0], box[1], box[2])
    tools = [(3, gmsh.model.occ.addSphere(cx, cy, cz, radius)) for cx, cy, cz in centers]
    print(f"    [step] cutting {len(tools)} spheres from block ...", flush=True)
    t0 = time.time()
    gmsh.model.occ.cut([(3, b)], tools, removeObject=True, removeTool=True)
    gmsh.model.occ.synchronize()
    print(f"    [step] boolean done in {time.time()-t0:.1f}s", flush=True)
    gmsh.write(out_step)
    if out_stl:
        ms = mesh_size or max(box) / 60.0
        gmsh.option.setNumber("Mesh.MeshSizeMin", ms * 0.5)
        gmsh.option.setNumber("Mesh.MeshSizeMax", ms)
        gmsh.model.mesh.generate(2)
        tmp = out_stl + ".ascii.stl"
        gmsh.write(tmp)
        gmsh.finalize()
        import trimesh
        m = trimesh.load(tmp)
        m.export(out_stl)              # compact binary
        os.remove(tmp)
        return m.is_watertight, len(m.faces), m.volume
    gmsh.finalize()
    return None

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Generate porous-material STL/STEP from a text spec.")
    ap.add_argument("spec", nargs="?", help="path to a text spec file")
    ap.add_argument("--box", help="bounding box, e.g. 8x14x8 (mm)")
    ap.add_argument("--lattice", help="sc | bcc | fcc | hcp | gyroid")
    ap.add_argument("--pore", help="pore size (mm): sphere diameter, or gyroid cell size")
    ap.add_argument("--porosity", help="target void fraction, e.g. 0.77 or 75-80%%")
    ap.add_argument("--formats", help="stl,step")
    ap.add_argument("--resolution", help="voxel size for meshing (mm)")
    ap.add_argument("--out", help="output file prefix")
    args = ap.parse_args()

    spec = load_spec(args.spec) if args.spec else {}
    def get(key, cli, default=None, required=False):
        if cli is not None:
            return cli
        for k in (key, key.replace('_', '')):
            if k in spec:
                return spec[k]
        if required:
            sys.exit(f"error: missing required parameter '{key}'")
        return default

    box       = parse_box(get('bounding_box', args.box, required=True))
    lattice   = get('lattice', args.lattice, 'hcp').lower()
    pore      = parse_number(get('pore_size', args.pore, required=True))
    porosity  = parse_porosity(get('porosity', args.porosity, required=True))
    formats   = parse_formats(get('formats', args.formats, 'stl'))
    vox       = parse_number(get('resolution', args.resolution, min(box) / 160.0))
    out       = get('output', args.out, 'porous')

    tune_vox = max(vox, min(box) / 80.0)     # coarser grid for fast tuning

    print("=" * 60)
    print("porousgen")
    print("=" * 60)
    print(f"  bounding box : {box[0]} x {box[1]} x {box[2]} mm")
    print(f"  lattice      : {lattice}")
    print(f"  pore size    : {pore} mm")
    print(f"  porosity tgt : {porosity*100:.2f}%")
    print(f"  formats      : {', '.join(formats)}")
    print(f"  resolution   : {vox} mm")
    print("-" * 60)

    if lattice == 'gyroid':
        # tune level-set constant c: porosity(solid=g>c) INCREASES with c
        eval_fn = lambda c: 1.0 - gyroid_solid_grid(box, tune_vox, pore, c).mean()
        c, pest = tune(porosity, eval_fn, lo=-1.5, hi=1.5, decreasing=False)
        print(f"  tuned level-set c = {c:+.4f}  (est. porosity {pest*100:.2f}%)")
        grid = gyroid_solid_grid(box, vox, pore, c)
        por = 1.0 - grid.mean()
        if 'step' in formats:
            print("  ! STEP is not supported for gyroid (implicit TPMS); writing STL only.")
        wt, nf, vol = grid_to_stl(grid, vox, f"{out}.stl")
        print(f"  STL: {out}.stl  faces={nf}  watertight={wt}  porosity={ (1-vol/(box[0]*box[1]*box[2]))*100:.2f}%")
    else:
        if lattice not in LATTICES:
            sys.exit(f"error: unknown lattice '{lattice}' (choose sc|bcc|fcc|hcp|gyroid)")
        radius = pore / 2.0
        eval_fn = lambda s: 1.0 - sphere_solid_grid(box, tune_vox, radius, s, lattice).mean()
        # porosity DECREASES as spacing grows
        s, pest = tune(porosity, eval_fn, lo=0.5 * pore, hi=3.0 * pore, decreasing=True)
        overlap = "overlapping (open/interconnected)" if s < pore else "isolated (closed pores)"
        print(f"  tuned spacing = {s:.4f} mm  (est. porosity {pest*100:.2f}%)  -> pores {overlap}")
        if s >= pore:
            print("  ! pores do NOT overlap at this porosity -> closed porosity. "
                  "Use a denser lattice (fcc/hcp) or higher porosity for interconnection.")
        want_step = 'step' in formats
        want_stl  = 'stl' in formats
        if want_step:
            res = build_step(box, radius, s, lattice, f"{out}.step",
                             out_stl=(f"{out}.stl" if want_stl else None), mesh_size=vox * 3)
            print(f"  STEP: {out}.step")
            if res:
                wt, nf, vol = res
                print(f"  STL:  {out}.stl  faces={nf}  watertight={wt}  "
                      f"porosity={(1-vol/(box[0]*box[1]*box[2]))*100:.2f}%")
        elif want_stl:
            grid = sphere_solid_grid(box, vox, radius, s, lattice)
            wt, nf, vol = grid_to_stl(grid, vox, f"{out}.stl")
            print(f"  STL:  {out}.stl  faces={nf}  watertight={wt}  "
                  f"porosity={(1-vol/(box[0]*box[1]*box[2]))*100:.2f}%")
    print("=" * 60)
    print("done.")

if __name__ == "__main__":
    main()
