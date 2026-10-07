"""Blender: convert Tripo prop GLBs into Unreal-ready static mesh FBX + textures.

blender -b --python process_props.py -- --spec props.json --out export/props
spec: [{"name": "Cypress", "glb": "...", "height": 3.2},
       {"name": "Weapons", "glb": "...", "split": [{"name": "Sword", "length": 1.0, "grip": 0.13}, ...]}]
- single props: centred on X/Y, bottom at z=0, uniformly scaled to `height` metres
- split props: loose parts clustered along the row axis (gaps), each scaled so its longest side
  equals `length`, pivot at `grip` (fraction of height from the bottom; 0.5 = centre)
- "straighten": true -> straighten_blade() (a single-image blade bent in depth, 4-23)
- split item "handle": {"from": f0, "to": f1, "scale": s} -> thin_handle(): grip cross-section x s, pivot on it (4-26)
"""
import argparse, json, sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

p = argparse.ArgumentParser()
p.add_argument('--spec', required=True)
p.add_argument('--out', required=True)
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
OUT = Path(a.out).resolve()          # Blender Image.save() silently skips relative paths (4-23)
OUT.mkdir(parents=True, exist_ok=True)
specs = json.loads(Path(a.spec).read_text(encoding='utf-8'))
report = []


def texture_kind(n):
    """smart-low-poly GLBs name maps Color* / NormalGL* / ORM*; mesh-decimate GLBs (4-23 sword) *_BaseColor,
    *_Normal_Bake and a glTF metallic-roughness map (G rough, B metal, R unused)"""
    if n.startswith(('Color', 'NormalGL', 'ORM')):
        return next(k for k in ('Color', 'NormalGL', 'ORM') if n.startswith(k))
    if n.endswith('_BaseColor'):
        return 'Color'
    if 'Normal' in n:
        return 'NormalGL'
    if 'metallic' in n and 'roughness' in n:
        return 'MR'
    return None


def extract_textures(name):
    tex = {}
    for img in list(bpy.data.images):
        kind = texture_kind(img.name)
        if not kind or not img.size[0]:
            continue
        w, h = img.size
        px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
        if kind == 'NormalGL':
            px[..., 1] = 1.0 - px[..., 1]
        if kind == 'MR':
            px[..., 0] = 1.0                            # no AO in it -> ORM with R = 1
        role = {'Color': 'BaseColor', 'NormalGL': 'Normal', 'ORM': 'ORM', 'MR': 'ORM'}[kind]
        dst = bpy.data.images.new(f'T_{name}_{role}', w, h, alpha=False)
        dst.colorspace_settings.name = 'sRGB' if role == 'BaseColor' else 'Non-Color'
        dst.pixels = px.ravel()
        path = OUT / f'T_{name}_{role}.png'
        dst.filepath_raw = str(path)
        dst.file_format = 'PNG'
        dst.save()
        tex[role] = path.name
    return tex


def straighten_blade(ob, bins=80):
    """Single-image generations bend a thin blade in the depth the image does not show (4-23 sword: a sabre-like
    curve seen from the side). Blade = everything above the cross-guard (the widest slice in the lower half);
    per height slice, move the slice's mid-point (both horizontal axes) back onto the line at the guard."""
    me = ob.data
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    z0, z1 = co[:, 2].min(), co[:, 2].max()
    edges = np.linspace(z0, z1, bins + 1)
    k = np.clip(np.digitize(co[:, 2], edges) - 1, 0, bins - 1)
    width = np.array([np.ptp(co[k == b, :2], axis=0).max() if (k == b).any() else 0 for b in range(bins)])
    g = int(np.argmax(width[:bins // 2]))
    top = g + next((i for i in range(1, bins - g) if width[g + i] < 0.5 * width[g]), 1)   # first slice above the guard
    mid = np.full((bins, 2), np.nan)
    for b in range(top, bins):
        if (k == b).any():
            q = co[k == b, :2]
            mid[b] = (q.min(0) + q.max(0)) / 2
    idx = np.arange(top, bins)
    ok = ~np.isnan(mid[idx, 0])
    zc = (edges[:-1] + edges[1:]) / 2
    off = np.zeros((bins, 2))
    for ax in (0, 1):
        m = np.interp(idx, idx[ok], mid[idx[ok], ax])
        m = np.convolve(np.pad(m, 2, mode='edge'), np.ones(5) / 5, mode='valid')     # smooth, keep the length
        off[idx, ax] = m - m[0]
    blade = co[:, 2] >= edges[top]
    for ax in (0, 1):
        co[blade, ax] -= np.interp(co[blade, 2], zc[idx], off[idx, ax])
    me.vertices.foreach_set('co', co.ravel())
    me.update()
    print('STRAIGHTEN', ob.name, 'guard_z', round(float(zc[g]), 3), 'blade_from', round(float(edges[top]), 3),
          'max_offset', [round(float(abs(off[idx, ax]).max()), 4) for ax in (0, 1)], 'length', round(float(z1 - z0), 3))


def thin_handle(ob, lo_frac, hi_frac, scale, ramp=0.008):
    """Scale the grip's cross-section (height fractions lo..hi from the bottom) about the handle centreline, easing
    in/out over `ramp`; returns the centreline (x, y). 4-26: the generated handle was ~2.7x thicker than the hero's
    fist hole."""
    me = ob.data
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    z0, z1 = co[:, 2].min(), co[:, 2].max()
    f = (co[:, 2] - z0) / (z1 - z0)
    core = (f > lo_frac + ramp) & (f < hi_frac - ramp)
    q = co[core, :2]
    # per-slice centre (the generated grip is slightly bent: one common centre would kink it), smoothed
    edges = np.linspace(lo_frac, hi_frac, 21)
    zc = (edges[:-1] + edges[1:]) / 2
    cen = np.array([(lambda p: (p.min(0) + p.max(0)) / 2 if len(p) else [np.nan, np.nan])(co[(f >= e0) & (f < e1), :2])
                    for e0, e1 in zip(edges[:-1], edges[1:])])
    ok = ~np.isnan(cen[:, 0])
    cen = np.stack([np.convolve(np.pad(np.interp(zc, zc[ok], cen[ok, i]), 1, mode='edge'), np.ones(3) / 3, mode='valid')
                    for i in (0, 1)], 1)
    c_at = np.stack([np.interp(f, zc, cen[:, i]) for i in (0, 1)], 1)
    mid = cen[len(cen) // 2]
    w = np.clip(np.minimum(f - lo_frac, hi_frac - f) / ramp, 0, 1)
    w = w * w * (3 - 2 * w)                                  # smoothstep
    s = 1 - (1 - scale) * w
    co[:, :2] = c_at + (co[:, :2] - c_at) * s[:, None]
    me.vertices.foreach_set('co', co.ravel())
    me.update()
    print('THIN_HANDLE', ob.name, 'range', (lo_frac, hi_frac), 'scale', scale, 'width_before', np.round(np.ptp(q, 0), 4),
          'centreline_drift', np.round(np.ptp(cen, 0), 4))
    return mid


def world_bounds(ob):
    pts = [ob.matrix_world @ v.co for v in ob.data.vertices]
    lo = Vector([min(v[i] for v in pts) for i in range(3)])
    hi = Vector([max(v[i] for v in pts) for i in range(3)])
    return lo, hi


def finalize(ob, name, pivot, scale, mat_name):
    """Move `pivot` (world) to origin, scale, apply, single material, export FBX."""
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    me = ob.data
    me.transform(__import__('mathutils').Matrix.Translation(-pivot))
    me.transform(__import__('mathutils').Matrix.Scale(scale, 4))
    me.update()
    ob.name = me.name = f'SM_{name}'
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    me.materials.clear()
    me.materials.append(mat)
    for poly in me.polygons:
        poly.use_smooth = True
    bpy.ops.export_scene.fbx(filepath=str(OUT / f'SM_{name}.fbx'), use_selection=True, object_types={'MESH'},
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS',
                             path_mode='STRIP', mesh_smooth_type='FACE')
    lo, hi = world_bounds(ob)
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    return {'name': f'SM_{name}', 'triangles': tris, 'size_m': [round(v, 3) for v in (hi - lo)], 'material': mat_name}


for s in specs:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=s['glb'])
    tex = extract_textures(s['name'])
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    for o in bpy.context.view_layer.objects:
        o.select_set(o in meshes)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if s.get('straighten'):
        straighten_blade(ob)
    mat_name = f'M_{s["name"]}'
    if 'split' not in s:
        lo, hi = world_bounds(ob)
        pivot = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
        r = finalize(ob, s['name'], pivot, s['height'] / (hi.z - lo.z), mat_name)
        r['textures'] = tex
        report.append(r)
        continue
    # ---- split a prop sheet into loose parts, cluster along the widest horizontal axis
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode='OBJECT')
    parts = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    info = []
    for o in parts:
        l, h = world_bounds(o)
        info.append((o, l, h))
        lo = Vector([min(lo[i], l[i]) for i in range(3)])
        hi = Vector([max(hi[i], h[i]) for i in range(3)])
    axis = 0 if (hi.x - lo.x) > (hi.y - lo.y) else 1
    info.sort(key=lambda t: t[1][axis])
    clusters, cur, cur_hi = [], [], None
    gap = (hi[axis] - lo[axis]) * 0.02
    for o, l, h in info:
        if cur and l[axis] > cur_hi + gap:
            clusters.append(cur)
            cur, cur_hi = [], None
        cur.append(o)
        cur_hi = h[axis] if cur_hi is None else max(cur_hi, h[axis])
    clusters.append(cur)
    print('CLUSTERS', len(clusters), [len(c) for c in clusters])
    if len(clusters) != len(s['split']):
        raise SystemExit(f'expected {len(s["split"])} clusters, got {len(clusters)}')
    for cl, item in zip(clusters, s['split']):
        for o in bpy.context.view_layer.objects:
            o.select_set(o in cl)
        bpy.context.view_layer.objects.active = cl[0]
        if len(cl) > 1:
            bpy.ops.object.join()
        part = bpy.context.view_layer.objects.active
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        l, h = world_bounds(part)
        size = h - l
        pivot = Vector(((l.x + h.x) / 2, (l.y + h.y) / 2, l.z + size.z * item['grip']))
        if 'handle' in item:          # {"from": .., "to": .., "scale": ..}: thinner grip, pivot on its centreline
            hx, hy = thin_handle(part, item['handle']['from'], item['handle']['to'], item['handle']['scale'])
            pivot.x, pivot.y = hx, hy
        r = finalize(part, item['name'], pivot, item['length'] / max(size), mat_name)
        r['textures'] = tex
        r['grip_fraction'] = item['grip']
        report.append(r)
        bpy.data.objects.remove(part, do_unlink=True)

(OUT / 'props.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
print('PROPS_DONE', json.dumps([(r['name'], r['triangles'], r['size_m']) for r in report]))
