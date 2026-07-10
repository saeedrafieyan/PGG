import trimesh, numpy as np
m = trimesh.load(r"E:\Projects\Federica\federica_scaffold.stl")
print("in faces:", len(m.faces))
target = 700000
try:
    s = m.simplify_quadric_decimation(face_count=target)
except TypeError:
    s = m.simplify_quadric_decimation(target)
s.fix_normals()
print("out faces:", len(s.faces), "watertight:", s.is_watertight,
      "bbox:", np.round(s.bounds[1]-s.bounds[0],3))
s.export(r"E:\Projects\Federica\federica_scaffold_slim.stl")
print("wrote federica_scaffold_slim.stl")
