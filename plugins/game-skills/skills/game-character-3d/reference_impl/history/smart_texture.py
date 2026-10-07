"""Blender: "smart material" texturing pass on a baked game mesh (what Substance Painter smart materials do).

blender -b --python smart_texture.py -- --baked hero/baked --name Hero --high high.glb --scans ../hero_v2/scans --out dir [--res 2048]

Input: bake_highpoly.py output (low GLB + T_<Name>_BaseColor / _Normal (DirectX) / _ORM) and the high-poly GLB.
1. material classes per texel from the baked colour + metallic: metal, leather, cloth (scarf / tabard), dark cloth
   (trousers), fur (everything else)  -> T_<Name>_Classes.png (for review)
2. curvature from the HIGH-poly (Cycles pointiness, selected -> active)       -> edge wear on metal / leather
3. per-class scanned micro detail (Poly Haven CC0), box-projected in object space so the scale is the same on
   every UV island: normal + roughness + albedo luminance
4. edge wear (bright worn steel, lower roughness), cavity dirt from AO (darker, rougher)
5. everything is baked back to the same UVs: T_<Name>_BaseColor / _Normal (DirectX) / _ORM, low GLB copied
Why: the Tripo texture is one blended "paint" layer - every material has the same sheen and no micro structure,
so metal, leather, cloth and fur all read as the same clay (design/unreal_plaza_art_pipeline.md 4-7, 4-11).
"""
import argparse, colorsys, json, shutil, sys, time
from pathlib import Path

import bpy
import numpy as np

p = argparse.ArgumentParser()
p.add_argument('--baked', required=True)
p.add_argument('--name', required=True)
p.add_argument('--high', required=True)
p.add_argument('--scans', required=True)
p.add_argument('--out', required=True)
p.add_argument('--res', type=int, default=2048)
p.add_argument('--scan-scale', type=float, default=4.0, help='scan tiles per object unit (mesh is ~1 unit tall)')
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
baked = Path(a.baked).resolve()
out = Path(a.out).resolve()
scans = Path(a.scans).resolve()
out.mkdir(parents=True, exist_ok=True)
info = json.loads((baked / f'{a.name}_bake.json').read_text(encoding='utf-8'))
R = a.res
t0 = time.time()


def load_px(path, colorspace='Non-Color'):
    img = bpy.data.images.load(str(path))
    img.colorspace_settings.name = colorspace
    if img.size[0] != R:
        img.scale(R, R)
    return img, np.array(img.pixels[:], dtype=np.float32).reshape(R, R, 4)


def save_png(name, rgb, colorspace='Non-Color'):
    img = bpy.data.images.new(name, R, R, alpha=False)
    img.colorspace_settings.name = colorspace
    px = np.ones((R, R, 4), dtype=np.float32)
    px[..., :3] = np.clip(rgb, 0, 1)
    img.pixels = px.ravel()
    img.filepath_raw = str(out / f'{name}.png')
    img.file_format = 'PNG'
    img.save()
    return img


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
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
        scene.cycles.device = 'GPU'
        break
scene.cycles.samples = 16

bpy.ops.import_scene.gltf(filepath=str(baked / info['glb']))
low = next(o for o in scene.objects if o.type == 'MESH')
before = set(scene.objects)
bpy.ops.import_scene.gltf(filepath=a.high)
highs = [o for o in scene.objects if o not in before and o.type == 'MESH']
for o in scene.objects:
    o.select_set(o in highs)
bpy.context.view_layer.objects.active = highs[0]
if len(highs) > 1:
    bpy.ops.object.join()
high = bpy.context.view_layer.objects.active
bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
size = max(high.dimensions)

base_img, base = load_px(baked / info['textures']['BaseColor'], 'sRGB')
orm_img, orm = load_px(baked / info['textures']['ORM'])
nrm_img, nrm = load_px(baked / info['textures']['Normal'])

# ---------------------------------------------------------------- 1. material classes (texel space)
srgb = base[..., :3]                                  # byte images: .pixels holds the stored (sRGB) values
mx, mn = srgb.max(-1), srgb.min(-1)
v = mx
s = np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0)
r_, g_, b_ = srgb[..., 0], srgb[..., 1], srgb[..., 2]
hue = np.zeros_like(v)
d = np.maximum(mx - mn, 1e-4)
hue = np.where(mx == r_, ((g_ - b_) / d) % 6, np.where(mx == g_, (b_ - r_) / d + 2, (r_ - g_) / d + 4)) / 6.0
metal_src = orm[..., 2]
metal = np.clip((metal_src - 0.35) / 0.2, 0, 1)
red = ((hue < 0.035) | (hue > 0.95)) & (s > 0.38) & (v > 0.18)
brown = (hue >= 0.02) & (hue < 0.14) & (s > 0.38) & (v > 0.08) & (v < 0.6)   # warm-grey fur stays below s 0.35
dark = (s < 0.38) & (v < 0.16)                                                # trousers / gambeson: dark, low sat
cloth = red.astype(np.float32) * (1 - metal)
leather = brown.astype(np.float32) * (1 - metal) * (1 - cloth)
darkcloth = dark.astype(np.float32) * (1 - metal) * (1 - cloth) * (1 - leather)
fur = np.clip(1 - metal - cloth - leather - darkcloth, 0, 1)
classes = np.stack([metal, leather, cloth, darkcloth, fur], -1)


def blur(x, k=2):
    y = x.copy()
    for _ in range(k):
        y = (y + np.roll(y, 1, 0) + np.roll(y, -1, 0) + np.roll(y, 1, 1) + np.roll(y, -1, 1)) / 5
    return y


classes = blur(classes, 3)
classes /= np.maximum(classes.sum(-1, keepdims=True), 1e-4)
review = classes[..., 0:1] * [0.75, 0.78, 0.85] + classes[..., 1:2] * [0.45, 0.25, 0.1] + classes[..., 2:3] * [0.8, 0.1, 0.1] \
    + classes[..., 3:4] * [0.15, 0.2, 0.35] + classes[..., 4:5] * [0.9, 0.9, 0.6]
save_png(f'T_{a.name}_Classes', review, 'sRGB')
cls_img = bpy.data.images.new('cls1', R, R, alpha=True)
cls_img.colorspace_settings.name = 'Non-Color'
px = np.ones((R, R, 4), dtype=np.float32)
px[..., 0], px[..., 1], px[..., 2], px[..., 3] = classes[..., 0], classes[..., 1], classes[..., 2], classes[..., 3]
cls_img.pixels = px.ravel()
fractions = {k: round(float(classes[..., i].mean()), 3) for i, k in enumerate(('metal', 'leather', 'cloth', 'darkcloth', 'fur'))}
print('CLASSES', fractions, flush=True)

# ---------------------------------------------------------------- 2. curvature from the high-poly
bake = scene.render.bake
bake.margin = 16
bake.margin_type = 'EXTEND'


def emit_material(obj, build):
    m = bpy.data.materials.new('emit')
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    outp = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    nt.links.new(em.outputs[0], outp.inputs[0])
    build(nt, em)
    obj.data.materials.clear()
    obj.data.materials.append(m)
    return m


def curvature_nodes(nt, em):
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.42
    ramp.color_ramp.elements[1].position = 0.58
    nt.links.new(geo.outputs['Pointiness'], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], em.inputs[0])


emit_material(high, curvature_nodes)
target = bpy.data.images.new('curv', R, R, alpha=False, float_buffer=True)
target.colorspace_settings.name = 'Non-Color'
low_bake_mat = emit_material(low, lambda nt, em: None)
tnode = low_bake_mat.node_tree.nodes.new('ShaderNodeTexImage')
tnode.image = target
low_bake_mat.node_tree.nodes.active = tnode
for o in scene.objects:
    o.select_set(o in (high, low))
bpy.context.view_layer.objects.active = low
bake.use_selected_to_active = True
bake.cage_extrusion = size * 0.01
bake.max_ray_distance = size * 0.03
bpy.ops.object.bake(type='EMIT')
curv = np.array(target.pixels[:], dtype=np.float32).reshape(R, R, 4)[..., 0]
edge = np.clip((curv - 0.55) / 0.25, 0, 1)
save_png(f'T_{a.name}_Curvature', np.stack([curv] * 3, -1))
print('CURVATURE', round(float(curv.mean()), 3), 'edge frac', round(float((edge > 0.5).mean()), 3), flush=True)
high.hide_render = True
bake.use_selected_to_active = False

# ---------------------------------------------------------------- 3-4. smart material on the low mesh
edge_img = bpy.data.images.new('edge', R, R, alpha=False)
edge_img.colorspace_settings.name = 'Non-Color'
epx = np.ones((R, R, 4), dtype=np.float32)
epx[..., 0] = edge
epx[..., 1] = orm[..., 0]                              # AO
edge_img.pixels = epx.ravel()

SCANS = {'metal': 'rusty_metal_04', 'leather': 'brown_leather', 'cloth': 'poly_wool_herringbone',
         'darkcloth': 'rough_linen', 'fur': None}
# how much of each scan to use: (albedo luminance modulation, normal strength, roughness range lo, hi)
TUNE = {'metal': (0.35, 1.0, 0.22, 0.55), 'leather': (0.45, 0.9, 0.38, 0.7), 'cloth': (0.35, 0.8, 0.8, 0.95),
        'darkcloth': (0.35, 0.8, 0.82, 0.95), 'fur': (0.0, 0.0, 0.82, 0.95)}   # fur 0.6-0.8 caught blue sky sheen in UE

m = bpy.data.materials.new('smart')
m.use_nodes = True
nt = m.node_tree
N, L = nt.nodes, nt.links
for n in list(N):
    N.remove(n)
outp = N.new('ShaderNodeOutputMaterial')
bsdf = N.new('ShaderNodeBsdfPrincipled')
L.new(bsdf.outputs[0], outp.inputs[0])
uvmap = N.new('ShaderNodeUVMap')


def img_node(img, proj=None):
    t = N.new('ShaderNodeTexImage')
    t.image = img
    if proj:
        t.projection = 'BOX'
        t.projection_blend = 0.25
        L.new(proj.outputs[0], t.inputs['Vector'])
    else:
        L.new(uvmap.outputs[0], t.inputs['Vector'])
    return t


def math(op, a_, b_=None, clamp=False):
    n = N.new('ShaderNodeMath')
    n.operation = op
    n.use_clamp = clamp
    for i, x in enumerate((a_, b_)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        else:
            L.new(x, n.inputs[i])
    return n.outputs[0]


def mix_rgb(fac, c1, c2, blend='MIX'):
    n = N.new('ShaderNodeMix')
    n.data_type = 'RGBA'
    n.blend_type = blend
    for sock, x in ((0, fac), (6, c1), (7, c2)):
        if isinstance(x, (int, float)):
            n.inputs[sock].default_value = x
        elif isinstance(x, tuple):
            n.inputs[sock].default_value = x
        else:
            L.new(x, n.inputs[sock])
    return n.outputs[2]


tex_coord = N.new('ShaderNodeTexCoord')
mapping = N.new('ShaderNodeMapping')
mapping.inputs['Scale'].default_value = (a.scan_scale,) * 3
L.new(tex_coord.outputs['Object'], mapping.inputs['Vector'])
base_n = img_node(base_img)
orm_n = img_node(orm_img)
cls_n = img_node(cls_img)
edge_n = img_node(edge_img)
sep_cls = N.new('ShaderNodeSeparateColor')
L.new(cls_n.outputs['Color'], sep_cls.inputs[0])
masks = {'metal': sep_cls.outputs[0], 'leather': sep_cls.outputs[1], 'cloth': sep_cls.outputs[2],
         'darkcloth': cls_n.outputs['Alpha']}
fur_mask = math('SUBTRACT', 1.0, math('ADD', math('ADD', masks['metal'], masks['leather']), math('ADD', masks['cloth'], masks['darkcloth'])), clamp=True)
masks['fur'] = fur_mask
sep_e = N.new('ShaderNodeSeparateColor')
L.new(edge_n.outputs['Color'], sep_e.inputs[0])
edge_s, ao_s = sep_e.outputs[0], sep_e.outputs[1]

# baked normal (DirectX -> OpenGL for Blender)
nrm_n = img_node(nrm_img)
sep_n = N.new('ShaderNodeSeparateColor')
L.new(nrm_n.outputs['Color'], sep_n.inputs[0])
comb_n = N.new('ShaderNodeCombineColor')
L.new(sep_n.outputs[0], comb_n.inputs[0])
L.new(math('SUBTRACT', 1.0, sep_n.outputs[1]), comb_n.inputs[1])
L.new(sep_n.outputs[2], comb_n.inputs[2])
nmap_base = N.new('ShaderNodeNormalMap')
L.new(comb_n.outputs[0], nmap_base.inputs['Color'])
geo = N.new('ShaderNodeNewGeometry')

albedo_factor = None
rough_acc = None
n_acc = nmap_base.outputs[0]
for cls, scan in SCANS.items():
    lum_amt, n_str, r_lo, r_hi = TUNE[cls]
    msk = masks[cls]
    if scan:
        folder = scans / scan
        diff_img = bpy.data.images.load(str(folder / f'{scan}_diff_2k.jpg'))
        arm_img = bpy.data.images.load(str(folder / f'{scan}_arm_2k.jpg'))
        arm_img.colorspace_settings.name = 'Non-Color'
        nor_img = bpy.data.images.load(str(folder / f'{scan}_nor_gl_2k.png'))
        nor_img.colorspace_settings.name = 'Non-Color'
        dmean = float(np.array(diff_img.pixels[:]).reshape(-1, 4)[:, :3].mean())
        d_n = img_node(diff_img, mapping)
        a_n = img_node(arm_img, mapping)
        n_n = img_node(nor_img, mapping)
        bw = N.new('ShaderNodeRGBToBW')
        L.new(d_n.outputs['Color'], bw.inputs[0])
        lum_f = math('MULTIPLY', bw.outputs[0], 1.0 / max(dmean, 1e-3))
        f = math('ADD', math('MULTIPLY', math('SUBTRACT', lum_f, 1.0), lum_amt), 1.0)
        sep_a = N.new('ShaderNodeSeparateColor')
        L.new(a_n.outputs['Color'], sep_a.inputs[0])
        rough = math('ADD', math('MULTIPLY', sep_a.outputs[1], r_hi - r_lo), r_lo)
        nm = N.new('ShaderNodeNormalMap')
        nm.inputs['Strength'].default_value = n_str
        L.new(n_n.outputs['Color'], nm.inputs['Color'])
        # add the detail's deviation from the geometric normal onto the running normal, weighted by the class mask
        dev = N.new('ShaderNodeVectorMath')
        dev.operation = 'SUBTRACT'
        L.new(nm.outputs[0], dev.inputs[0])
        L.new(geo.outputs['Normal'], dev.inputs[1])
        sc = N.new('ShaderNodeVectorMath')
        sc.operation = 'SCALE'
        L.new(dev.outputs[0], sc.inputs[0])
        L.new(msk, sc.inputs['Scale'])
        add = N.new('ShaderNodeVectorMath')
        add.operation = 'ADD'
        L.new(n_acc, add.inputs[0])
        L.new(sc.outputs[0], add.inputs[1])
        n_acc = add.outputs[0]
    else:
        f = 1.0
        rough = (r_lo + r_hi) / 2
    fm = math('MULTIPLY', f if not isinstance(f, float) else f, msk) if not isinstance(f, float) else math('MULTIPLY', msk, f)
    albedo_factor = fm if albedo_factor is None else math('ADD', albedo_factor, fm)
    rm = math('MULTIPLY', rough, msk) if not isinstance(rough, float) else math('MULTIPLY', msk, rough)
    rough_acc = rm if rough_acc is None else math('ADD', rough_acc, rm)

norm = N.new('ShaderNodeVectorMath')
norm.operation = 'NORMALIZE'
L.new(n_acc, norm.inputs[0])

# albedo: guide colour x scan luminance; metal/leather edge wear brightens toward bare steel; cavity dirt darkens
albedo = mix_rgb(1.0, base_n.outputs['Color'], albedo_factor, 'MULTIPLY')
# metal: the generated texture paints steel dark grey (lit look); PBR steel reflectance is ~0.5-0.6 linear
metal_lin = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
mw = classes[..., 0]
metal_lum = float((metal_lin @ np.array([0.2126, 0.7152, 0.0722]) * mw).sum() / max(mw.sum(), 1.0))
metal_gain = float(np.clip(0.5 / max(metal_lum, 1e-3), 1.0, 5.0))
print('METAL_GAIN', round(metal_lum, 3), round(metal_gain, 2), flush=True)
albedo = mix_rgb(masks['metal'], albedo, mix_rgb(1.0, albedo, (metal_gain,) * 3 + (1.0,), 'MULTIPLY'))
wear = math('MULTIPLY', edge_s, math('ADD', masks['metal'], math('MULTIPLY', masks['leather'], 0.5)))
albedo = mix_rgb(math('MULTIPLY', wear, 0.65), albedo, (0.62, 0.62, 0.6, 1.0))
cavity = math('MULTIPLY', math('SUBTRACT', 1.0, ao_s, clamp=True), 0.6)
albedo = mix_rgb(cavity, albedo, (0.08, 0.065, 0.05, 1.0))
rough_final = math('ADD', math('MULTIPLY', wear, -0.25), rough_acc)
rough_final = math('ADD', math('MULTIPLY', cavity, 0.3), rough_final, clamp=True)
metal_final = math('ADD', math('MULTIPLY', masks['metal'], 0.9), math('MULTIPLY', wear, 0.3), clamp=True)
L.new(albedo, bsdf.inputs['Base Color'])
L.new(rough_final, bsdf.inputs['Roughness'])
L.new(metal_final, bsdf.inputs['Metallic'])
L.new(norm.outputs[0], bsdf.inputs['Normal'])
low.data.materials.clear()
low.data.materials.append(m)

# ---------------------------------------------------------------- 5. bake back to textures
target_n = N.new('ShaderNodeTexImage')
N.active = target_n
emission = N.new('ShaderNodeEmission')


def bake_emit(socket_src, name, colorspace='Non-Color'):
    img = bpy.data.images.new(name, R, R, alpha=False, float_buffer=True)
    img.colorspace_settings.name = colorspace
    target_n.image = img
    for l in list(outp.inputs[0].links):
        L.remove(l)
    L.new(socket_src, emission.inputs[0])
    L.new(emission.outputs[0], outp.inputs[0])
    for o in scene.objects:
        o.select_set(o == low)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.bake(type='EMIT')
    return np.array(img.pixels[:], dtype=np.float32).reshape(R, R, 4)[..., :3]


col = bake_emit(albedo, 'col', 'Non-Color')          # linear values
rgh = bake_emit(rough_final, 'rgh')[..., 0]
mtl = bake_emit(metal_final, 'mtl')[..., 0]
for l in list(outp.inputs[0].links):
    L.remove(l)
L.new(bsdf.outputs[0], outp.inputs[0])
nimg = bpy.data.images.new('nrm', R, R, alpha=False, float_buffer=True)
nimg.colorspace_settings.name = 'Non-Color'
target_n.image = nimg
bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT')
nb = np.array(nimg.pixels[:], dtype=np.float32).reshape(R, R, 4)[..., :3]
nb[..., 1] = 1.0 - nb[..., 1]                        # OpenGL -> DirectX

col_srgb = np.where(col <= 0.0031308, col * 12.92, 1.055 * np.power(np.clip(col, 0, 1), 1 / 2.4) - 0.055)
names = {'BaseColor': f'T_{a.name}_BaseColor', 'Normal': f'T_{a.name}_Normal', 'ORM': f'T_{a.name}_ORM'}
save_png(names['BaseColor'], col_srgb, 'sRGB')
save_png(names['Normal'], nb)
save_png(names['ORM'], np.stack([orm[..., 0], rgh, mtl], -1))
shutil.copyfile(baked / info['glb'], out / info['glb'])
new_info = dict(info)
new_info['textures'] = {k: f'{v}.png' for k, v in names.items()}
new_info['smart_texture'] = {'classes': fractions, 'scans': SCANS, 'tune': TUNE, 'scan_scale': a.scan_scale,
                             'seconds': round(time.time() - t0)}
(out / f'{a.name}_bake.json').write_text(json.dumps(new_info, indent=1), encoding='utf-8')
print('SMART_DONE', json.dumps(new_info['smart_texture']))
