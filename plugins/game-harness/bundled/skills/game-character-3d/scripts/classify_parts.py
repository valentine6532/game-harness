"""Blender: assign a material class to every part of a Tripo segmentation (mesh segment v2).

blender -b --python classify_parts.py -- --parts segment.glb --textured high.glb --out parts.json [--render prefix]

The segmented GLB has no textures, so each part's vertices are matched to the nearest vertex of the textured
generation mesh, whose base colour + metallic are sampled there. Per-part majority vote over:
metal (ORM metallic), cloth (saturated red), leather (warm brown), darkcloth (dark, low saturation), fur (rest).
Tail = fur part whose centre lies far behind the body. Whole parts get one class, so material edges follow the
modelled part boundaries instead of texel colour guesses (4-13).
"""
import argparse, json, sys
from collections import Counter
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector, kdtree

p = argparse.ArgumentParser()
p.add_argument('--parts', required=True)
p.add_argument('--textured', required=True)
p.add_argument('--out', required=True)
p.add_argument('--render')
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=a.textured)
src = [o for o in sc.objects if o.type == 'MESH']
before = set(sc.objects)
bpy.ops.import_scene.gltf(filepath=a.parts)
parts = [o for o in sc.objects if o not in before and o.type == 'MESH']


def image(prefix):
    img = next(i for i in bpy.data.images if i.name.startswith(prefix))
    w, h = img.size
    return np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4), w, h


col, cw, chh = image('Color')
orm, ow, oh = image('ORM')

# textured mesh: one sample per vertex (first loop's UV)
pts, uvs = [], []
for o in src:
    me = o.data
    uvl = me.uv_layers.active.data
    vuv = {}
    for li, loop in enumerate(me.loops):
        vuv.setdefault(loop.vertex_index, uvl[li].uv[:])
    for v in me.vertices:
        pts.append(o.matrix_world @ v.co)
        uvs.append(vuv.get(v.index, (0.0, 0.0)))
tree = kdtree.KDTree(len(pts))
for i, pt in enumerate(pts):
    tree.insert(pt, i)
tree.balance()
uvs = np.array(uvs, dtype=np.float32)


def classify(rgb, metal):
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    v = mx
    s = (mx - mn) / mx if mx > 1e-4 else 0.0
    d = max(mx - mn, 1e-4)
    hue = (((g - b) / d) % 6 if mx == r else ((b - r) / d + 2 if mx == g else (r - g) / d + 4)) / 6.0
    if metal > 0.45:
        return 'metal'
    if (hue < 0.035 or hue > 0.95) and s > 0.38 and v > 0.18:
        return 'cloth'
    if 0.02 <= hue < 0.14 and s > 0.38 and 0.08 < v < 0.6:
        return 'leather'
    if s < 0.38 and v < 0.16:
        return 'darkcloth'
    return 'fur'


allpts = np.array([o.matrix_world @ v.co for o in parts for v in o.data.vertices])
body_x = float(np.median(allpts[:, 0]))
height = float(allpts[:, 2].max() - allpts[:, 2].min())
result = {}
for o in parts:
    verts = o.data.vertices
    step = max(1, len(verts) // 400)
    votes = Counter()
    for v in list(verts)[::step]:
        _, idx, _ = tree.find(o.matrix_world @ v.co)
        u, vv = uvs[idx]
        x, y = min(cw - 1, int(u * cw)), min(chh - 1, int(vv * chh))
        rgb = col[y, x, :3]
        metal = orm[min(oh - 1, int(vv * oh)), min(ow - 1, int(u * ow)), 2]
        votes[classify(tuple(float(c) for c in rgb), float(metal))] += 1
    cls, n = votes.most_common(1)[0]
    centre = sum((o.matrix_world @ v.co for v in verts), Vector()) / max(len(verts), 1)
    tris = sum(len(pl.vertices) - 2 for pl in o.data.polygons)
    result[o.name] = {'class': cls, 'share': round(n / sum(votes.values()), 2), 'tris': tris,
                      'centre': [round(c, 3) for c in centre], 'votes': dict(votes)}

# tail: the largest fur part whose centre sits well behind the body (Tripo +X forward -> glTF import: -Y? use both)
fur_parts = [(k, v) for k, v in result.items() if v['class'] == 'fur']
if fur_parts:
    behind = max(fur_parts, key=lambda kv: (abs(kv[1]['centre'][0] - body_x) + abs(kv[1]['centre'][1])) * kv[1]['tris'] ** 0.25)
    result[behind[0]]['class'] = 'tail'
summary = Counter(v['class'] for v in result.values())
Path(a.out).write_text(json.dumps(result, indent=1), encoding='utf-8')
print('PARTS_CLASSIFIED', dict(summary), flush=True)

if a.render:
    colours = {'metal': (0.75, 0.78, 0.85), 'leather': (0.45, 0.25, 0.1), 'cloth': (0.8, 0.1, 0.1),
               'darkcloth': (0.15, 0.2, 0.35), 'fur': (0.9, 0.9, 0.6), 'tail': (0.2, 0.8, 0.3)}
    for o in src:
        o.hide_render = True
    mats = {}
    for k, c in colours.items():
        m = bpy.data.materials.new(k)
        m.use_nodes = True
        m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*c, 1)
        mats[k] = m
    for o in parts:
        o.data.materials.clear()
        o.data.materials.append(mats[result[o.name]['class']])
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = 500, 650
    w = bpy.data.worlds.new('W')
    sc.world = w
    cam = bpy.data.objects.new('C', bpy.data.cameras.new('C'))
    sc.collection.objects.link(cam)
    sc.camera = cam
    bb = [o.matrix_world @ Vector(c) for o in parts for c in o.bound_box]
    ctr = sum(bb, Vector()) / len(bb)
    for nm, dv in (('front', (0.3, -1, 0.1)), ('back', (-0.3, 1, 0.2)), ('side', (1, 0.2, 0.1))):
        dv = Vector(dv).normalized()
        cam.location = ctr + dv * height * 2.6
        cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = f'{a.render}_{nm}.png'
        bpy.ops.render.render(write_still=True)
