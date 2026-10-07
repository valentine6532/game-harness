"""Blender: faces of each part covered by another part (ray along the face normal hits a different part within 3 cm game)."""
import json
from pathlib import Path
import bpy, bmesh
import numpy as np
from mathutils.bvhtree import BVHTree
W = Path('D:/HarnessPrograming/diablo/workspace/deathknight/assembly/final')
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(W / 'Hero_low.glb'))
ob = [o for o in bpy.context.scene.objects if o.type == 'MESH'][0]
parts = np.load(W / 'parts.npy'); names = ['head', 'arm_r', 'arm_l', 'torso', 'legs']
bm = bmesh.new(); bm.from_mesh(ob.data); bm.transform(ob.matrix_world); bm.faces.ensure_lookup_table()
H = max(v.co.z for v in bm.verts) - min(v.co.z for v in bm.verts)
tree = BVHTree.FromBMesh(bm)
lim = 0.03 / 2.2 * H
res = {n: [0, 0] for n in names}
for f in bm.faces:
    n = names[parts[f.index]]; res[n][1] += 1
    c = f.calc_center_median(); nr = f.normal
    hit = tree.ray_cast(c + nr * 1e-4 * H, nr, lim)
    if hit[0] is not None and parts[hit[2]] != parts[f.index]:
        res[n][0] += 1
print('HIDDEN', json.dumps({k: {'covered': v[0], 'of': v[1], 'pct': round(100 * v[0] / v[1], 1)} for k, v in res.items()}), flush=True)
