import trimesh, numpy as np, gmsh

# --- STL from the exact BREP: validate + re-export as compact binary ---
m = trimesh.load(r"E:\Projects\Federica\federica_scaffold_from_step.stl")
bbox = m.bounds
dims = bbox[1]-bbox[0]
vol = m.volume
box_vol = 8.0*14.0*8.0
por = (1.0 - vol/box_vol)*100
print("=== STL (from STEP BREP) ===")
print("faces:", len(m.faces))
print("watertight:", m.is_watertight)
print("bbox min:", np.round(bbox[0],4), "dims:", np.round(dims,4))
print(f"solid volume: {vol:.2f} mm^3  ->  porosity: {por:.2f}%")
m.export(r"E:\Projects\Federica\federica_scaffold.stl")  # overwrite with clean binary
print("re-exported compact binary -> federica_scaffold.stl")

# --- STEP: reimport in OCC to confirm it is a single valid solid ---
print("\n=== STEP reimport check ===")
gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 0)
gmsh.model.add("check")
gmsh.model.occ.importShapes(r"E:\Projects\Federica\federica_scaffold.step")
gmsh.model.occ.synchronize()
vols = gmsh.model.getEntities(3)
surfs = gmsh.model.getEntities(2)
xmin,ymin,zmin,xmax,ymax,zmax = gmsh.model.getBoundingBox(-1,-1)
print("solids:", len(vols), "| faces:", len(surfs))
print("bbox:", round(xmin,3),round(ymin,3),round(zmin,3),"->",round(xmax,3),round(ymax,3),round(zmax,3))
gmsh.finalize()
