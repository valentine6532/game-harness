"""Blender: high-poly Tripo model -> game mesh with baked maps (the standard high -> low workflow).

blender -b --python bake_highpoly.py -- --glb high.glb --name Hero --tris 30000 --res 2048 --out dir

- decimates a copy of the high-poly mesh to --tris, smooth-by-angle shading
- keeps Tripo's high-detail UV atlas (few hundred islands) through decimation and re-packs it with padding
- Cycles bakes from the high-poly (selected -> active): tangent normal, AO, base colour, roughness, metallic
- writes <dir>/<Name>_low.glb (static mesh with UVs) and T_<Name>_BaseColor / _Normal (DirectX green) / _ORM .png
Why: Tripo's low-poly outputs (P1 / smart_low_poly) carried an almost flat normal map, no AO and thousands of
tiny UV islands -> characters read as blurry clay in game (design/unreal_plaza_art_pipeline.md 4-7).
"""
import argparse, json, sys, time
from pathlib import Path

import bpy
import numpy as np

p = argparse.ArgumentParser()
p.add_argument('--glb', required=True)
p.add_argument('--name', required=True)
p.add_argument('--tris', type=int, default=30000)
p.add_argument('--res', type=int, default=2048)
p.add_argument('--samples', type=int, default=64)
p.add_argument('--ao-strength', type=float, default=0.6, help='0 = no AO, 1 = full baked AO')
p.add_argument('--out', required=True)
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = Path(a.out).resolve()   # Blender resolves relative image paths against its own folder
out.mkdir(parents=True, exist_ok=True)
t0 = time.time()

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=a.glb)
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for o in bpy.context.scene.objects:
    o.select_set(o in meshes)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
high = bpy.context.view_layer.objects.active
bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
high.name = 'High'
high_tris = sum(len(pl.vertices) - 2 for pl in high.data.polygons)
size = max(high.dimensions)

# ---------------------------------------------------------------- low-poly: decimate a copy
low = high.copy()
low.data = high.data.copy()
low.name = f'{a.name}_low'
bpy.context.collection.objects.link(low)
mod = low.modifiers.new('Decimate', 'DECIMATE')
mod.ratio = min(1.0, a.tris / max(high_tris, 1))
mod.use_collapse_triangulate = True
for o in bpy.context.scene.objects:
    o.select_set(o == low)
bpy.context.view_layer.objects.active = low
bpy.ops.object.modifier_apply(modifier=mod.name)
bpy.ops.object.shade_smooth_by_angle(angle=np.radians(45))
low_tris = sum(len(pl.vertices) - 2 for pl in low.data.polygons)

# UVs: Tripo's high-detail atlas (~500 islands) survives collapse decimation; re-pack with padding so mips
# do not bleed. (Smart UV Project on a decimated triangle soup gave ~8,500 islands - worse than P1.)
while len(low.data.uv_layers) > 1:
    low.data.uv_layers.remove(low.data.uv_layers[-1])
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.select_all(action='SELECT')
bpy.ops.uv.pack_islands(margin=0.004, rotate=True)
bpy.ops.object.mode_set(mode='OBJECT')

# ---------------------------------------------------------------- bake setup
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = a.samples
scene.cycles.device = 'CPU'
prefs = bpy.context.preferences.addons['cycles'].preferences
for backend in ('OPTIX', 'CUDA', 'HIP'):
    try:
        prefs.compute_device_type = backend
        prefs.get_devices()
    except Exception:
        continue
    gpus = [d for d in prefs.devices if d.type != 'CPU']
    if gpus:
        for d in prefs.devices:
            d.use = d.type != 'CPU'
        scene.cycles.device = 'GPU'
        break
print('BAKE_DEVICE', scene.cycles.device, prefs.compute_device_type, flush=True)
bake = scene.render.bake
bake.use_selected_to_active = True
bake.use_cage = False
bake.cage_extrusion = size * 0.01
bake.max_ray_distance = size * 0.03
bake.margin = 16
bake.margin_type = 'EXTEND'

low.data.materials.clear()
mat = bpy.data.materials.new(f'M_{a.name}_bake')
mat.use_nodes = True
low.data.materials.append(mat)
nodes = mat.node_tree.nodes
tex_node = nodes.new('ShaderNodeTexImage')
nodes.active = tex_node


def new_image(name, color_space):
    img = bpy.data.images.new(name, a.res, a.res, alpha=False, float_buffer=True)
    img.colorspace_settings.name = color_space
    return img


def run_bake(kind, img, **kw):
    tex_node.image = img
    for o in bpy.context.scene.objects:
        o.select_set(o in (high, low))
    bpy.context.view_layer.objects.active = low
    s = time.time()
    bpy.ops.object.bake(type=kind, **kw)
    print(f'BAKE {kind} {time.time() - s:.0f}s', flush=True)
    return np.array(img.pixels[:], dtype=np.float32).reshape(a.res, a.res, 4)


# high-poly material: glTF import -> Principled BSDF with texture links
high_mats = [m for m in high.data.materials if m and m.use_nodes]


def principled(m):
    return next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def rewire_emission(socket_name):
    """Route one Principled input (texture link or value) into Emission so EMIT bakes it verbatim."""
    saved = []
    for m in high_mats:
        bsdf = principled(m)
        links = m.node_tree.links
        src = bsdf.inputs[socket_name]
        em_col, em_str = bsdf.inputs['Emission Color'], bsdf.inputs['Emission Strength']
        saved.append((m, [l for l in em_col.links], tuple(em_col.default_value), em_str.default_value))
        for l in list(em_col.links):
            links.remove(l)
        if src.links:
            from_sock = src.links[0].from_socket
            links.new(from_sock, em_col)
        else:
            v = src.default_value
            em_col.default_value = (v, v, v, 1.0) if isinstance(v, float) else tuple(v)
        em_str.default_value = 1.0
    return saved


def restore_emission(saved):
    for m, _links, col, strength in saved:
        bsdf = principled(m)
        for l in list(bsdf.inputs['Emission Color'].links):
            m.node_tree.links.remove(l)
        bsdf.inputs['Emission Color'].default_value = col
        bsdf.inputs['Emission Strength'].default_value = strength


res = {}
res['normal'] = run_bake('NORMAL', new_image('N', 'Non-Color'), normal_space='TANGENT')
res['color'] = run_bake('DIFFUSE', new_image('C', 'sRGB'), pass_filter={'COLOR'})
saved = rewire_emission('Roughness')
res['rough'] = run_bake('EMIT', new_image('R', 'Non-Color'))
restore_emission(saved)
saved = rewire_emission('Metallic')
res['metal'] = run_bake('EMIT', new_image('M', 'Non-Color'))
restore_emission(saved)
scene.cycles.samples = max(a.samples, 128)
scene.world = scene.world or bpy.data.worlds.new('W')
scene.world.light_settings.distance = size * 0.12      # local occlusion (folds, straps), not whole-body shadowing
res['ao'] = run_bake('AO', new_image('AO', 'Non-Color'))


def save(name, rgb, srgb):
    img = bpy.data.images.new(name, a.res, a.res, alpha=False)
    img.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
    px = np.ones((a.res, a.res, 4), dtype=np.float32)
    px[..., :3] = np.clip(rgb, 0.0, 1.0)
    img.pixels = px.ravel()
    path = out / f'{name}.png'
    img.filepath_raw = str(path)
    img.file_format = 'PNG'
    img.save()
    return path.name


n = res['normal'][..., :3].copy()
# rays that missed / hit the far side of thin parts (scarf, ears) leave near-horizontal normals -> white
# specular specks in game. Fade anything tilted more than ~70 deg back toward flat.
tilt = np.clip((n[..., 2] - 0.35) / 0.2, 0.0, 1.0)[..., None]
n = n * tilt + np.array([0.5, 0.5, 1.0], dtype=np.float32) * (1.0 - tilt)
bad_normals = float((tilt < 1.0).mean())
n[..., 1] = 1.0 - n[..., 1]                     # Blender bakes OpenGL (+Y) -> Unreal DirectX
color = res['color'][..., :3]
ao = 1.0 - a.ao_strength * (1.0 - res['ao'][..., 0])   # full-strength AO made the fur read near-black in game
orm = np.stack([ao, res['rough'][..., 0], res['metal'][..., 0]], axis=-1)
tex = {'BaseColor': save(f'T_{a.name}_BaseColor', color, True),
       'Normal': save(f'T_{a.name}_Normal', n, False),
       'ORM': save(f'T_{a.name}_ORM', orm, False)}

# low mesh with UVs only (materials are assigned in Unreal)
for o in bpy.context.scene.objects:
    o.select_set(o == low)
low.data.materials.clear()
glb = out / f'{a.name}_low.glb'
bpy.ops.export_scene.gltf(filepath=str(glb), use_selection=True, export_format='GLB', export_materials='NONE')
import bmesh
from bpy_extras import bmesh_utils
_bm = bmesh.new(); _bm.from_mesh(low.data)
uv_islands = len(bmesh_utils.bmesh_linked_uv_islands(_bm, _bm.loops.layers.uv.active)); _bm.free()
stats = {'uv_islands': uv_islands, 'high_tris': high_tris, 'low_tris': low_tris, 'res': a.res, 'textures': tex, 'glb': glb.name,
         'normal_std': round(float(n[..., :2].std()), 4), 'normal_texels_flattened': round(bad_normals, 4), 'ao_strength': a.ao_strength, 'ao_mean': round(float(ao.mean()), 4),
         'seconds': round(time.time() - t0)}
(out / f'{a.name}_bake.json').write_text(json.dumps(stats, indent=1), encoding='utf-8')
print('BAKE_DONE', json.dumps(stats))
