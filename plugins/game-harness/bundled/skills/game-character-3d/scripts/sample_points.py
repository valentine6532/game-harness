"""Blender: area-weighted surface sample of a GLB -> npy (N x 3, Blender coords) for assemble_parts.py "body_pts".

blender -b --python sample_points.py -- <body generation.glb> <out.npy> [--n 300000] [--seed 0]

The whole-body Tripo generation is the frame every part is fitted to. Its GLB imports facing +X, left = +Y, centred
on the origin (heights are measured from the lowest point by assemble_parts.py).
"""
import sys
import bpy
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:]
glb, out = argv[0], argv[1]
n = int(argv[argv.index('--n') + 1]) if '--n' in argv else 300000
seed = int(argv[argv.index('--seed') + 1]) if '--seed' in argv else 0

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
tris = []
for o in bpy.context.scene.objects:
    if o.type != 'MESH':
        continue
    me = o.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    me.calc_loop_triangles()
    co = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3) @ np.array(o.matrix_world.to_3x3()).T + np.array(o.matrix_world.translation)
    idx = np.zeros(len(me.loop_triangles) * 3, np.int64); me.loop_triangles.foreach_get('vertices', idx)
    tris.append(co[idx.reshape(-1, 3)])
t = np.concatenate(tris)
area = 0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
rng = np.random.default_rng(seed)
pick = rng.choice(len(t), n, p=area / area.sum())
u, v = rng.random(n), rng.random(n)
flip = u + v > 1
u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
a, b, c = t[pick, 0], t[pick, 1], t[pick, 2]
pts = (a + (b - a) * u[:, None] + (c - a) * v[:, None]).astype(np.float32)
np.save(out, pts)
print('SAMPLE_POINTS', pts.shape, pts.min(0).round(4), pts.max(0).round(4))
