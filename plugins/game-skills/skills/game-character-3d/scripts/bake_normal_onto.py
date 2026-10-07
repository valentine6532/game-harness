"""Blender: bake only a tangent-space normal map from a high-poly onto an existing low-poly with its own UVs.

blender -b --python bake_normal_onto.py -- --high high.glb --low retopo.fbx --out T_Hero_Normal.png [--res 4096]

Used for the Tripo quad retopology (its transferred normal map is only 1K). Colour / roughness / metallic stay
Tripo's; only the normal is re-baked (4-14). The low mesh is shaded like the game export (custom normals
cleared, smooth) so the tangent basis matches Unreal (FBX normals + MikkTSpace tangents). Near-horizontal
normals from rays that missed thin parts are faded back to flat. Output is DirectX (green flipped).
"""
import argparse, sys, time
from pathlib import Path

import bpy
import numpy as np

p = argparse.ArgumentParser()
p.add_argument('--high', required=True)
p.add_argument('--low', required=True)
p.add_argument('--out', required=True)
p.add_argument('--res', type=int, default=4096)
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
t0 = time.time()

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=a.high)
highs = [o for o in sc.objects if o.type == 'MESH']
before = set(sc.objects)
(bpy.ops.import_scene.gltf if a.low.lower().endswith('.glb') else bpy.ops.import_scene.fbx)(filepath=a.low)   # glb: Tripo decimate output
low = next(o for o in sc.objects if o not in before and o.type == 'MESH')

# the two files use different axes / origins: fit the high-poly onto the low by bounds (4 yaw turns, nearest error)
from mathutils import Matrix, Vector, kdtree
lp = np.array([low.matrix_world @ v.co for v in low.data.vertices])
tree = kdtree.KDTree(len(lp))
for i, x in enumerate(lp):
    tree.insert(x, i)
tree.balance()
hp = np.array([o.matrix_world @ v.co for o in highs for v in list(o.data.vertices)[::50]])
llo, lhi = lp.min(0), lp.max(0)
best = None
for k in range(4):
    rz = np.array(Matrix.Rotation(k * np.pi / 2, 3, 'Z'))
    q = hp @ rz.T
    lo, hi = q.min(0), q.max(0)
    s = (lhi[2] - llo[2]) / max(hi[2] - lo[2], 1e-6)
    off = (llo + lhi) / 2 - s * (lo + hi) / 2
    off[2] = llo[2] - s * lo[2]
    err = float(np.mean([tree.find(x)[2] for x in (q * s + off)[::20]]))
    if best is None or err < best[0]:
        best = (err, k, s, off)
err, k, s, off = best
fit = Matrix.Translation(Vector(off)) @ Matrix.Scale(s, 4) @ Matrix.Rotation(k * np.pi / 2, 4, 'Z')
for o in highs:
    o.matrix_world = fit @ o.matrix_world
size = float(max(lhi - llo))
print(f'NORMAL_FIT yaw={k * 90} scale={s:.4f} mean_dist={err / size * 100:.3f}%', flush=True)

# low: game shading
bpy.ops.object.select_all(action='DESELECT')
low.select_set(True)
bpy.context.view_layer.objects.active = low
low.modifiers.clear()
if low.data.has_custom_normals:
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
for poly in low.data.polygons:
    poly.use_smooth = True
low.data.materials.clear()
m = bpy.data.materials.new('bake')
m.use_nodes = True
tn = m.node_tree.nodes.new('ShaderNodeTexImage')
img = bpy.data.images.new('nrm', a.res, a.res, alpha=False, float_buffer=True)
img.colorspace_settings.name = 'Non-Color'
tn.image = img
m.node_tree.nodes.active = tn
low.data.materials.append(m)

sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
prefs = bpy.context.preferences.addons['cycles'].preferences
for backend in ('OPTIX', 'CUDA'):
    try:
        prefs.compute_device_type = backend
        prefs.get_devices()
    except Exception:
        continue
    if any(d.type != 'CPU' for d in prefs.devices):
        for d in prefs.devices:
            d.use = d.type != 'CPU'
        sc.cycles.device = 'GPU'
        break
sc.cycles.samples = 16
bk = sc.render.bake
bk.use_selected_to_active = True
bk.use_cage = False
bk.cage_extrusion = size * 0.008
bk.max_ray_distance = size * 0.025
bk.margin = 16
bk.margin_type = 'EXTEND'
bpy.ops.object.select_all(action='DESELECT')
for o in highs:
    o.select_set(True)
low.select_set(True)
bpy.context.view_layer.objects.active = low
bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT')

n = np.array(img.pixels[:], dtype=np.float32).reshape(a.res, a.res, 4)[..., :3].copy()
tilt = np.clip((n[..., 2] - 0.35) / 0.2, 0.0, 1.0)[..., None]
n = n * tilt + np.array([0.5, 0.5, 1.0], dtype=np.float32) * (1.0 - tilt)
n[..., 1] = 1.0 - n[..., 1]                             # OpenGL -> DirectX
outimg = bpy.data.images.new('out', a.res, a.res, alpha=False)
outimg.colorspace_settings.name = 'Non-Color'
px = np.ones((a.res, a.res, 4), dtype=np.float32)
px[..., :3] = np.clip(n, 0, 1)
outimg.pixels = px.ravel()
outimg.filepath_raw = str(Path(a.out).resolve())
outimg.file_format = 'PNG'
outimg.save()
print('NORMAL_DONE', round(float(n[..., :2].std()), 4), 'flattened', round(float((tilt < 1).mean()), 4), f'{time.time() - t0:.0f}s', flush=True)
