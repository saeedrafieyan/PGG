import numpy as np
from skimage import measure
import trimesh

LX, LY, LZ = 8.0, 14.0, 8.0
R = 0.5
A = 0.985          # chosen HCP nearest-neighbor spacing -> 77.5% porosity
VOX = 0.04         # voxel size for STL surface (mm)

def hcp_centers(a, margin):
    c = a * np.sqrt(2.0/3.0)
    dy = a * np.sqrt(3.0)/2.0
    off = (a/2.0, a/(2.0*np.sqrt(3.0)))
    pts = []
    xs0, xs1 = -margin, LX + margin
    ys0, ys1 = -margin, LY + margin
    zs0, zs1 = -margin, LZ + margin
    kz = 0; z = zs0
    while z <= zs1:
        ox, oy = (0.0, 0.0) if kz % 2 == 0 else off
        j = int(np.floor((ys0 - oy)/dy)) - 1
        y = oy + j*dy
        while y <= ys1:
            rx = ox + (a/2.0 if (j % 2) else 0.0)
            i = int(np.floor((xs0 - rx)/a)) - 1
            x = rx + i*a
            while x <= xs1:
                pts.append((x, y, z)); i += 1; x = rx + i*a
            j += 1; y = oy + j*dy
        kz += 1; z = zs0 + kz*c
    return np.array(pts)

nx = int(round(LX/VOX)); ny = int(round(LY/VOX)); nz = int(round(LZ/VOX))
PAD = 2
# solid field: start all solid inside box, carve pores. Padding stays 0 (empty) to cap faces.
field = np.zeros((nx+2*PAD, ny+2*PAD, nz+2*PAD), dtype=np.float32)
field[PAD:PAD+nx, PAD:PAD+ny, PAD:PAD+nz] = 1.0

gx = (np.arange(nx)+0.5)*VOX
gy = (np.arange(ny)+0.5)*VOX
gz = (np.arange(nz)+0.5)*VOX
centers = hcp_centers(A, margin=R+VOX)
r2 = R*R
rr = int(np.ceil(R/VOX))+1
for (cx, cy, cz) in centers:
    ix = int(round(cx/VOX-0.5)); iy = int(round(cy/VOX-0.5)); iz = int(round(cz/VOX-0.5))
    x0,x1 = max(0,ix-rr), min(nx,ix+rr+1)
    y0,y1 = max(0,iy-rr), min(ny,iy+rr+1)
    z0,z1 = max(0,iz-rr), min(nz,iz+rr+1)
    if x0>=x1 or y0>=y1 or z0>=z1: continue
    sx=gx[x0:x1]-cx; sy=gy[y0:y1]-cy; sz=gz[z0:z1]-cz
    d2 = sx[:,None,None]**2 + sy[None,:,None]**2 + sz[None,None,:]**2
    mask = d2 <= r2
    sub = field[PAD+x0:PAD+x1, PAD+y0:PAD+y1, PAD+z0:PAD+z1]
    sub[mask] = 0.0

por = 1.0 - field[PAD:PAD+nx,PAD:PAD+ny,PAD:PAD+nz].mean()
print(f"voxel porosity = {por*100:.2f}%")

verts, faces, normals, _ = measure.marching_cubes(field, level=0.5, spacing=(VOX,VOX,VOX))
verts -= PAD*VOX  # shift so box corner at origin
mesh = trimesh.Trimesh(vertices=verts, faces=faces, vertex_normals=normals, process=True)
mesh.update_faces(mesh.unique_faces())
mesh.update_faces(mesh.nondegenerate_faces())
mesh.remove_unreferenced_vertices()
mesh.fix_normals()
print("watertight:", mesh.is_watertight, "| faces:", len(mesh.faces),
      "| bbox:", np.round(mesh.bounds[1]-mesh.bounds[0],3))
mesh.export(r"E:\Projects\Federica\federica_scaffold.stl")
print("wrote federica_scaffold.stl")
