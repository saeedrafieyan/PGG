import re, numpy as np
txt = open(r"E:\Projects\Federica\federica_scaffold.step","r",errors="ignore").read()
# collapse to one entity per ; (STEP entities can span lines)
entities = txt.split(';')
cart = {}
vert_refs = []
cp_re = re.compile(r"#(\d+)\s*=\s*CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(([^)]*)\)")
vp_re = re.compile(r"#(\d+)\s*=\s*VERTEX_POINT\s*\(\s*'[^']*'\s*,\s*#(\d+)")
for e in entities:
    m = cp_re.search(e)
    if m:
        try:
            xyz = [float(v) for v in m.group(2).split(',')]
            if len(xyz)==3: cart[int(m.group(1))] = xyz
        except: pass
    m = vp_re.search(e)
    if m:
        vert_refs.append(int(m.group(2)))
allcp = np.array(list(cart.values()))
vcoords = np.array([cart[r] for r in vert_refs if r in cart])
print("total CARTESIAN_POINTs:", len(allcp), " | VERTEX_POINTs:", len(vcoords))
print("ALL cartesian point range:  min", np.round(allcp.min(0),3), " max", np.round(allcp.max(0),3))
if len(vcoords):
    print("VERTEX (real trim pts) range: min", np.round(vcoords.min(0),3), " max", np.round(vcoords.max(0),3))
