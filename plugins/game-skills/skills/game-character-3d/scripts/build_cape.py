"""Blender: knee-length back cape for the deathknight, fitted around the processed hero (rest A-pose) and skinned to
the same armature, exported as its own skeletal mesh for Unreal (separate component, leader pose, own Chaos cloth).

blender -b --python build_cape.py -- --hero SK_Hero.fbx --tex T_HeroCape_BaseColor.png --out dir

Shape: a grid hanging from the back of the collar. Columns sweep an angle around the body axis measured from
straight behind (-X): +-40 deg at the top edge (between the pauldrons), widening to +-82 deg a quarter of the way
down, so the sides wrap the flanks behind the arms (concept dk3_cape_worn_front). Each vertex sits on the body's
outer hull in its direction (arms excluded), taken as the maximum over everything ABOVE it: a hanging cloth falls
straight down past a protrusion (pauldron, hips) instead of tucking back in. Slots: M_HeroCape_Cloth (render grid,
UV = the cape texture) and M_HeroCape_ClothSim (coarse welded proxy, Unreal builds the cloth from it, 4-12).
All vertices are weighted to Spine02; Unreal pins the top band and simulates the rest.
Writes <out>/SK_HeroCape.fbx, T_HeroCape_BaseColor.png, HeroCape.json."""
import argparse, json, math, shutil, sys
from pathlib import Path
import bpy, bmesh
import numpy as np

p = argparse.ArgumentParser()
p.add_argument('--hero', required=True); p.add_argument('--tex', required=True); p.add_argument('--out', required=True)
p.add_argument('--top', type=float, default=0.848, help='top edge height (fraction of the body height)')
p.add_argument('--bottom', type=float, default=0.27, help='hem height before the torn fringe (texture alpha)')
p.add_argument('--clear', type=float, default=0.018, help='gap to the body hull (fraction of height)')
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=a.hero, use_anim=False, ignore_leaf_bones=False)
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
body = next(o for o in bpy.context.scene.objects if o.type == 'MESH' and o.parent == arm)
arm.data.pose_position = 'REST'
bpy.context.view_layer.update()

# body hull points: main section only (no fur shells / sim proxies / tail), arms and hands excluded
skip_slots = {i for i, m in enumerate(body.data.materials) if m and m.name.split('.')[0].endswith(('_Fur', 'Sim', '_Tail'))}
armish = {g.index for g in body.vertex_groups if any(k in g.name for k in ('Upperarm', 'Forearm', 'Hand'))}
use = np.zeros(len(body.data.vertices), bool)
for poly in body.data.polygons:
    if poly.material_index not in skip_slots:
        use[list(poly.vertices)] = True
for v in body.data.vertices:
    if use[v.index] and v.groups:
        g = max(v.groups, key=lambda x: x.weight)
        if g.group in armish and g.weight > 0.35:
            use[v.index] = False
M = np.array(body.matrix_world)
P = np.array([v.co[:] for v in body.data.vertices])[use] @ M[:3, :3].T + M[:3, 3]
z0, z1 = P[:, 2].min(), P[:, 2].max(); H = z1 - z0
torso = P[(P[:, 2] > z0 + 0.55 * H) & (P[:, 2] < z0 + 0.8 * H)]
cx, cy = np.median(torso[:, 0]), np.median(torso[:, 1])
ang = np.arctan2(P[:, 1] - cy, -(P[:, 0] - cx))            # 0 = straight behind (-X), + = character's left (+Y)
rad = np.hypot(P[:, 0] - cx, P[:, 1] - cy)
print(f'CAPE body H={H:.4f} axis=({cx:.4f},{cy:.4f}) pts={len(P)}', flush=True)

NU, NV = 33, 41                                             # render grid (columns x rows)
zt, zb = z0 + a.top * H, z0 + a.bottom * H
# the texture's torn fringe hangs below the grid's cloth line: stretch the grid so the texture bottom is the hem tip
zb_tip = zb - 0.07 * H


def hull(theta, z, half=math.radians(6), dz=0.012):
    m = (np.abs(np.angle(np.exp(1j * (ang - theta)))) < half) & (P[:, 2] > z - dz * H) & (P[:, 2] < z + dz * H)
    return rad[m].max() if m.any() else 0.0


zs = np.linspace(zt, zb_tip, NV)
rows = []
for j, z in enumerate(zs):
    f = j / (NV - 1)
    tmax = math.radians(40 + (82 - 40) * min(1.0, f / 0.25))
    rows.append(np.linspace(-tmax, tmax, NU))
R = np.zeros((NV, NU))
for j in range(NV):
    for i in range(NU):
        R[j, i] = hull(rows[j][i], zs[j])
R = np.maximum.accumulate(R, axis=0)                        # hanging: never tuck back in below a protrusion
for _ in range(3):                                          # smooth across the columns (sector noise)
    R[:, 1:-1] = 0.25 * R[:, :-2] + 0.5 * R[:, 1:-1] + 0.25 * R[:, 2:]
R += a.clear * H
# flare the hem slightly outward (cloth hangs away from the legs; less pre-collision for the sim)
R *= (1 + 0.06 * np.linspace(0, 1, NV) ** 2)[:, None]
V = np.zeros((NV, NU, 3))
for j in range(NV):
    th = rows[j]
    V[j, :, 0] = cx - R[j] * np.cos(th)
    V[j, :, 1] = cy + R[j] * np.sin(th)
    V[j, :, 2] = zs[j]


def grid_mesh(name, V, uv_ok=True):
    nv, nu = V.shape[:2]
    me = bpy.data.meshes.new(name)
    faces = [(j * nu + i, j * nu + i + 1, (j + 1) * nu + i + 1, (j + 1) * nu + i) for j in range(nv - 1) for i in range(nu - 1)]
    me.from_pydata(V.reshape(-1, 3).tolist(), [], faces)
    me.update()
    uvl = me.uv_layers.new(name='UVMap')
    for poly in me.polygons:
        for li, vi in zip(poly.loop_indices, poly.vertices):
            j, i = divmod(vi, nu)
            uvl.data[li].uv = (i / (nu - 1), 1 - j / (nv - 1)) if uv_ok else (0.5, 0.5)
    for poly in me.polygons:
        poly.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


# render grid: 2x denser (bilinear resample of the fitted grid), sim proxy: every other row / column
def resample(V, k):
    nv, nu = V.shape[:2]
    jj = np.linspace(0, nv - 1, (nv - 1) * k + 1); ii = np.linspace(0, nu - 1, (nu - 1) * k + 1)
    j0 = np.clip(np.floor(jj).astype(int), 0, nv - 2); i0 = np.clip(np.floor(ii).astype(int), 0, nu - 2)
    fj = (jj - j0)[:, None, None]; fi = (ii - i0)[None, :, None]
    A = V[j0][:, i0]; B = V[j0][:, i0 + 1]; C = V[j0 + 1][:, i0]; D = V[j0 + 1][:, i0 + 1]
    return A * (1 - fj) * (1 - fi) + B * (1 - fj) * fi + C * fj * (1 - fi) + D * fj * fi


render = grid_mesh('render', resample(V, 2))
sim = grid_mesh('sim', V[::2, ::2], uv_ok=False)
mat_r = bpy.data.materials.new('M_HeroCape_Cloth'); mat_s = bpy.data.materials.new('M_HeroCape_ClothSim')
render.data.materials.append(mat_r); render.data.materials.append(mat_s)
sim.data.materials.append(mat_r); sim.data.materials.append(mat_s)
for poly in sim.data.polygons:
    poly.material_index = 1
for o in (render, sim):
    g = o.vertex_groups.new(name='Spine02')
    g.add(list(range(len(o.data.vertices))), 1.0, 'REPLACE')
bpy.ops.object.select_all(action='DESELECT')
render.select_set(True); sim.select_set(True); bpy.context.view_layer.objects.active = render
bpy.ops.object.join()
cape = bpy.context.view_layer.objects.active
cape.name = 'SK_HeroCape'; cape.data.name = 'SK_HeroCape'
cape.parent = arm
am = cape.modifiers.new('Armature', 'ARMATURE'); am.object = arm
# keep only the armature + cape
bpy.data.objects.remove(body, do_unlink=True)
arm.data.pose_position = 'POSE'
arm.animation_data_clear()
bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True); cape.select_set(True); bpy.context.view_layer.objects.active = arm
fbx = out / 'SK_HeroCape.fbx'
bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'ARMATURE', 'MESH'},
                         apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', add_leaf_bones=False,
                         bake_anim=False, path_mode='STRIP', mesh_smooth_type='OFF', use_tspace=True,
                         armature_nodetype='NULL')
shutil.copyfile(a.tex, out / 'T_HeroCape_BaseColor.png')
info = {'name': 'HeroCape', 'fbx': fbx.name, 'rest_height_m': round(float(H), 4), 'texture': 'T_HeroCape_BaseColor.png',
        'grid': [NU, NV], 'top': a.top, 'bottom': a.bottom, 'render_faces': (NU * 2 - 2) * (NV * 2 - 2),
        'sim_faces': len([p for p in cape.data.polygons if p.material_index == 1])}
(out / 'HeroCape.json').write_text(json.dumps(info, indent=1), encoding='utf-8')
bpy.ops.export_scene.gltf(filepath=str(out / 'cape_preview.glb'), use_selection=True, export_format='GLB')
print('CAPE_DONE', json.dumps(info), flush=True)
