import numpy as np

# Bounding box (mm)
LX, LY, LZ = 8.0, 14.0, 8.0
R = 0.5          # pore radius (1 mm pore size)
VOX = 0.05       # voxel size for porosity estimate (mm)

def hcp_centers(a, margin):
    """Ideal HCP sphere centers covering the box +/- margin. a = nearest-neighbor dist."""
    c = a * np.sqrt(2.0/3.0)          # inter-layer spacing
    dy = a * np.sqrt(3.0)/2.0         # row spacing in a layer
    off = (a/2.0, a/(2.0*np.sqrt(3.0)))  # B-layer in-plane offset
    pts = []
    xs0, xs1 = -margin, LX + margin
    ys0, ys1 = -margin, LY + margin
    zs0, zs1 = -margin, LZ + margin
    kz = 0
    z = zs0
    while z <= zs1:
        ox, oy = (0.0, 0.0) if kz % 2 == 0 else off
        j = int(np.floor((ys0 - oy)/dy)) - 1
        y = oy + j*dy
        while y <= ys1:
            # row shift: alternate rows offset by a/2 for triangular lattice
            rx = ox + (a/2.0 if (j % 2) else 0.0)
            i = int(np.floor((xs0 - rx)/a)) - 1
            x = rx + i*a
            while x <= xs1:
                pts.append((x, y, z))
                i += 1; x = rx + i*a
            j += 1; y = oy + j*dy
        kz += 1; z = zs0 + kz*c
    return np.array(pts)

def porosity(a):
    nx = int(round(LX/VOX)); ny = int(round(LY/VOX)); nz = int(round(LZ/VOX))
    void = np.zeros((nx, ny, nz), dtype=bool)
    # voxel centers
    gx = (np.arange(nx)+0.5)*VOX
    gy = (np.arange(ny)+0.5)*VOX
    gz = (np.arange(nz)+0.5)*VOX
    centers = hcp_centers(a, margin=R+VOX)
    r2 = R*R
    rr = int(np.ceil(R/VOX))+1
    for (cx, cy, cz) in centers:
        ix = int(round(cx/VOX - 0.5)); iy = int(round(cy/VOX - 0.5)); iz = int(round(cz/VOX - 0.5))
        x0, x1 = max(0, ix-rr), min(nx, ix+rr+1)
        y0, y1 = max(0, iy-rr), min(ny, iy+rr+1)
        z0, z1 = max(0, iz-rr), min(nz, iz+rr+1)
        if x0>=x1 or y0>=y1 or z0>=z1: continue
        sx = gx[x0:x1]-cx; sy = gy[y0:y1]-cy; sz = gz[z0:z1]-cz
        d2 = sx[:,None,None]**2 + sy[None,:,None]**2 + sz[None,None,:]**2
        void[x0:x1, y0:y1, z0:z1] |= (d2 <= r2)
    return void.mean(), len(centers)

for a in [0.995, 0.990, 0.985, 0.980]:
    p, n = porosity(a)
    print(f"a={a:.3f} mm  ->  porosity={p*100:5.2f}%   n_spheres={n}")
