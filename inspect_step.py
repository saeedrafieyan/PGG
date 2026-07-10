import gmsh, numpy as np
gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 0)
gmsh.model.add("c")
gmsh.model.occ.importShapes(r"E:\Projects\Federica\federica_scaffold.step")
gmsh.model.occ.synchronize()
vols = gmsh.model.getEntities(3)
print("num solids:", len(vols))
mass_tot = 0.0
outside = []
for (d,t) in vols:
    x0,y0,z0,x1,y1,z1 = gmsh.model.getBoundingBox(d,t)
    m = gmsh.model.occ.getMass(d,t)
    mass_tot += m
    if x0 < -1e-3 or y0 < -1e-3 or z0 < -1e-3 or x1 > 8.001 or y1 > 14.001 or z1 > 8.001:
        outside.append((t, round(x0,3),round(y0,3),round(z0,3),round(x1,3),round(y1,3),round(z1,3), round(m,4)))
print("total volume (mass):", round(mass_tot,3), "-> porosity", round((1-mass_tot/896)*100,2),"%")
print("solids extending outside box:", len(outside))
for o in outside[:20]:
    print("  tag",o[0],"bbox",o[1:7],"vol",o[7])
gmsh.finalize()
