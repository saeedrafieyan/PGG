import numpy as np
import gmsh, time, sys

LX, LY, LZ = 8.0, 14.0, 8.0
R = 0.5
A = 0.985

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

# keep only spheres that actually intersect the box
def intersects(c):
    dx = max(0.0, max(-c[0], c[0]-LX))
    dy = max(0.0, max(-c[1], c[1]-LY))
    dz = max(0.0, max(-c[2], c[2]-LZ))
    return dx*dx+dy*dy+dz*dz < R*R

centers = [tuple(c) for c in hcp_centers(A, margin=R) if intersects(c)]
print(f"spheres intersecting box: {len(centers)}", flush=True)

gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 1)
gmsh.option.setNumber("Geometry.OCCParallel", 1)
gmsh.model.add("scaffold")

box = gmsh.model.occ.addBox(0, 0, 0, LX, LY, LZ)
tools = [(3, gmsh.model.occ.addSphere(cx, cy, cz, R)) for (cx, cy, cz) in centers]
print(f"created {len(tools)} spheres, starting boolean cut...", flush=True)
t0 = time.time()
out, _ = gmsh.model.occ.cut([(3, box)], tools, removeObject=True, removeTool=True)
gmsh.model.occ.synchronize()
print(f"boolean cut done in {time.time()-t0:.1f}s, result vols: {len(out)}", flush=True)

gmsh.write(r"E:\Projects\Federica\federica_scaffold.step")
print("wrote federica_scaffold.step", flush=True)

# also emit a matching STL from the same BREP
gmsh.option.setNumber("Mesh.MeshSizeMin", 0.08)
gmsh.option.setNumber("Mesh.MeshSizeMax", 0.20)
t0 = time.time()
gmsh.model.mesh.generate(2)
print(f"surface mesh in {time.time()-t0:.1f}s", flush=True)
gmsh.write(r"E:\Projects\Federica\federica_scaffold_from_step.stl")
print("wrote federica_scaffold_from_step.stl", flush=True)
gmsh.finalize()
print("DONE", flush=True)
