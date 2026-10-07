"""Blender: numbers for the deathknight build review (assembled mesh + processed SK_Hero + cape + sword)."""
import sys, json
from pathlib import Path
import bpy, bmesh
import numpy as np
W = Path('D:/HarnessPrograming/diablo/workspace')
out = {}

def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    (bpy.ops.import_scene.fbx if path.suffix == '.fbx' else bpy.ops.import_scene.gltf)(filepath=str(path))
    return [o for o in bpy.context.scene.objects if o.type == 'MESH']

def uv_islands(bm, faces, uvl):
    """UV islands: faces connected through shared UV coordinates (glTF already split verts at seams)."""
    key = {}
    parent = {}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for f in faces:
        parent[f.index] = f.index
    for f in faces:
        for l in f.loops:
            k = (l.vert.index, round(l[uvl].uv.x, 5), round(l[uvl].uv.y, 5))
            if k in key:
                a, b = find(f.index), find(key[k])
                if a != b: parent[a] = b
            else:
                key[k] = f.index
    return len({find(f.index) for f in faces})

def coverage(faces, uvl, res=1024, box=(0, 0, 1, 1)):
    import math
    img = np.zeros((res, res), bool)
    x0, y0, x1, y1 = box
    for f in faces:
        uv = np.array([[l[uvl].uv.x, l[uvl].uv.y] for l in f.loops])
        uv = (uv - [x0, y0]) / [x1 - x0, y1 - y0] * res
        mn = np.floor(uv.min(0)).astype(int).clip(0, res - 1); mx = np.ceil(uv.max(0)).astype(int).clip(0, res - 1)
        if (mx - mn).max() > res: continue
        ys, xs = np.mgrid[mn[1]:mx[1] + 1, mn[0]:mx[0] + 1]
        P = np.stack([xs + 0.5, ys + 0.5], -1).reshape(-1, 2)
        a, b, c = uv[0], uv[1], uv[2]
        def cross(o, p, q): return (p[0] - o[0]) * (q[:, 1] - o[1]) - (p[1] - o[1]) * (q[:, 0] - o[0])
        d1, d2, d3 = cross(a, b, P), cross(b, c, P), cross(c, a, P)
        inside = ((d1 >= 0) & (d2 >= 0) & (d3 >= 0)) | ((d1 <= 0) & (d2 <= 0) & (d3 <= 0))
        img[ys.reshape(-1)[inside], xs.reshape(-1)[inside]] = True
    return float(img.mean())

# 1. assembled parts (before fur shells / sim proxies): per part tris, UV islands, cell usage, texel density
ms = load(W / 'deathknight/assembly/final/Hero_low.glb')
ob = ms[0]
parts = np.load(W / 'deathknight/assembly/final/parts.npy')
names = ['head', 'arm_r', 'arm_l', 'torso', 'legs']
cells = {'head': (0, 0), 'arm_r': (1, 0), 'arm_l': (1, 0), 'torso': (0, 1), 'legs': (1, 1)}
bm = bmesh.new(); bm.from_mesh(ob.data); bm.faces.ensure_lookup_table(); uvl = bm.loops.layers.uv.active
bm.verts.ensure_lookup_table()
H = max(v.co.z for v in bm.verts) - min(v.co.z for v in bm.verts)
cm_per_unit = 220.0 / H
rows = {}
for pi, n in enumerate(names):
    fs = [f for f in bm.faces if parts[f.index] == pi]
    cx, cy = cells[n]
    box = (cx * 0.5, cy * 0.5, cx * 0.5 + 0.5, cy * 0.5 + 0.5)
    area3d = sum(f.calc_area() for f in fs) * cm_per_unit ** 2
    area_uv = 0.0
    for f in fs:
        uv = [l[uvl].uv for l in f.loops]
        area_uv += abs((uv[1].x - uv[0].x) * (uv[2].y - uv[0].y) - (uv[2].x - uv[0].x) * (uv[1].y - uv[0].y)) / 2
    texels = area_uv * 4096 * 4096
    rows[n] = {'tris': len(fs), 'uv_islands': uv_islands(bm, fs, uvl), 'cell_usage': round(coverage(fs, uvl, 512, box), 3),
               'surface_m2_game': round(area3d / 1e4, 3), 'texel_per_cm': round((texels / max(area3d, 1e-9)) ** 0.5, 2)}
out['parts'] = rows
out['assembled_tris'] = len(bm.faces)

# 2. processed skeletal mesh: tris per material slot
ms = load(W / 'plaza_v2/export/characters/Hero/SK_Hero.fbx')
body = [o for o in ms][0]
slot = {}
for p in body.data.polygons:
    nm = body.data.materials[p.material_index].name if body.data.materials[p.material_index] else str(p.material_index)
    slot[nm] = slot.get(nm, 0) + len(p.vertices) - 2
out['sk_hero_slots_tris'] = slot
out['sk_hero_verts'] = len(body.data.vertices)
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
out['bones'] = len(arm.data.bones)
out['actions'] = sorted(a.name.split('|')[-1] for a in bpy.data.actions)

# 3. cape + sword
ms = load(W / 'plaza_v2/export/characters/HeroCape/SK_HeroCape.fbx')
cs = {}
for p in ms[0].data.polygons:
    nm = ms[0].data.materials[p.material_index].name
    cs[nm] = cs.get(nm, 0) + len(p.vertices) - 2
out['cape_slots_tris'] = cs
ms = load(W / 'plaza_v2/export/props/SM_Sword.fbx')
out['sword_tris'] = sum(len(p.vertices) - 2 for o in ms for p in o.data.polygons)
bm2 = bmesh.new(); bm2.from_mesh(ms[0].data); u2 = bm2.loops.layers.uv.active
out['sword_uv_islands'] = uv_islands(bm2, list(bm2.faces), u2)
out['sword_uv_usage'] = round(coverage(list(bm2.faces), u2, 512), 3)
print('REVIEW_STATS', json.dumps(out, ensure_ascii=False), flush=True)
