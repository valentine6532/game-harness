"""Blender: fit separately generated Tripo parts onto the whole-body Tripo model and merge them into one textured mesh.

blender -b --python assemble_parts.py -- <config.json>

config: {"body_pts": npy (N x 3 sample of the body generation GLB, Blender coords, faces +X, left = +Y),
         "out": dir, "name": "DK", "atlas": 4096,
         "parts": [{"name", "glb", "quad": [col, row] (2x2 atlas cell), "mirror": false,
                    "region": {"z": [lo, hi], "y": [lo, hi]}   (fractions of body height from the feet; y in metres),
                    "init": "top" | "bottom" | "axis",  "trim": {"below_z": f, "above_z": f} (optional, body-height fractions),
                    "share_uv_with": "<part name>" (mirrored copy uses the same atlas cell),
                    "normal_dx": png (optional re-baked DirectX normal map replacing the decimate's 1K one)}]}
Fit = similarity transform: coarse scale search anchored at the region top/bottom (or the principal axis for arms),
then trimmed ICP (body region -> part nearest points, Umeyama). The part may be larger than the region (hidden neck,
arm stub); only body->part distances drive the fit.
Writes <out>/<name>_low.glb, T_<name>_{BaseColor,Normal(DirectX),ORM}.png, <name>_bake.json (process_character --baked),
<out>/fit.json (per-part scale, mean distance) and <out>/parts.npy (per-face part index of the merged mesh)."""
import sys, json, math
from pathlib import Path
import bpy, bmesh
import numpy as np
from mathutils import kdtree, Matrix

cfg = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf-8'))
out = Path(cfg['out']); out.mkdir(parents=True, exist_ok=True)
name = cfg['name']; A = cfg.get('atlas', 4096); cell = A // 2
body = np.load(cfg['body_pts']).astype(np.float64)
z0, z1 = body[:, 2].min(), body[:, 2].max(); H = z1 - z0
rng = np.random.default_rng(0)


def region(r):
    m = (body[:, 2] >= z0 + r['z'][0] * H) & (body[:, 2] <= z0 + r['z'][1] * H)
    if 'y' in r:
        m &= (body[:, 1] >= r['y'][0]) & (body[:, 1] <= r['y'][1])
    q = body[m]
    return q[rng.choice(len(q), min(len(q), 12000), replace=False)]


def kd(pts):
    t = kdtree.KDTree(len(pts))
    for i, p in enumerate(pts):
        t.insert(p, i)
    t.balance()
    return t


def umeyama(src, dst):
    ms, md = src.mean(0), dst.mean(0)
    a, b = src - ms, dst - md
    U, S, Vt = np.linalg.svd(b.T @ a / len(src))
    D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ D @ Vt
    s = np.trace(np.diag(S) @ D) / (a ** 2).sum(1).mean()
    return s, R, md - s * R @ ms


def q2p(q, pts, keep=0.85):
    """nearest part point for every region point, trimmed to the closest `keep` fraction."""
    t = kd(pts)
    res = [t.find(p) for p in q]
    d = np.array([r[2] for r in res]); idx = np.array([r[1] for r in res])
    k = d <= np.quantile(d, keep)
    return q[k], idx[k], float(d[k].mean())


def rot_between(a, b):
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    v = np.cross(a, b); c = float(a @ b)
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1 + c)


def fit(P, Q, init):
    """similarity (s, R, t) with s R P + t ~ Q."""
    if init == 'axis':
        cq = Q.mean(0); _, _, vt = np.linalg.svd(Q - cq); d = vt[0]
        if d[2] > 0:
            d = -d                                         # shoulder -> fist, pointing down
        R0 = rot_between(np.array([0, 0, -1.0]), d)
        ext_q = (Q - cq) @ d
        base_s = (ext_q.max() - ext_q.min()) / (P[:, 2].max() - P[:, 2].min())
        perp = lambda v: v - d * (v @ d)
        def place(s):
            X = (P @ R0.T) * s
            shift = d * ((cq @ d + ext_q.max()) - (X @ d).max()) + perp(cq) - perp(X.mean(0))
            return X + shift
        R_init = R0
    else:
        base_s = (Q[:, 1].max() - Q[:, 1].min()) / (P[:, 1].max() - P[:, 1].min())
        def place(s):
            X = P * s
            off = np.array([Q[:, 0].mean() - X[:, 0].mean(), Q[:, 1].mean() - X[:, 1].mean(), 0.0])
            off[2] = (Q[:, 2].max() - X[:, 2].max()) if init == 'top' else (Q[:, 2].min() - X[:, 2].min())
            return X + off
        R_init = np.eye(3)
    best = None
    for f in np.linspace(0.6, 1.6, 21):
        X = place(base_s * f)
        _, _, e = q2p(Q, X[rng.choice(len(X), min(len(X), 20000), replace=False)])
        if best is None or e < best[0]:
            best = (e, f)
    X = place(base_s * best[1])
    # total transform so far: X = s0 R_init P + t0 (recover it by least squares on the exact mapping)
    s_tot, R_tot, t_tot = umeyama(P, X)
    for it in range(40):
        Xs = s_tot * P @ R_tot.T + t_tot
        sub = rng.choice(len(P), min(len(P), 20000), replace=False)
        qa, j, e = q2p(Q, Xs[sub])
        pid = sub[j]
        s, R, tt = umeyama(P[pid], qa)
        moved = np.abs(s - s_tot) / s_tot + np.linalg.norm(R - R_tot) + np.linalg.norm(tt - t_tot) / H
        s_tot, R_tot, t_tot = s, R, tt
        if moved < 1e-4:
            break
    Xs = s_tot * P @ R_tot.T + t_tot
    _, _, e = q2p(Q, Xs[rng.choice(len(P), min(len(P), 20000), replace=False)], keep=0.95)
    print(f'FIT scale_search={best[1]:.2f} icp_iters={it + 1} scale={s_tot:.4f} mean_dist={e:.4f} ({e / H * 100:.2f}% of height)', flush=True)
    return s_tot, R_tot, t_tot, e


def import_part(glb):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    for o in new:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    for o in bpy.context.view_layer.objects:
        o.select_set(o in meshes)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.parent = None
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return ob


def part_images(ob):
    """(basecolor, normal, metallicRoughness) images of the glTF material."""
    base = nrm = mr = None
    for m in ob.data.materials:
        if not m or not m.use_nodes:
            continue
        for l in m.node_tree.links:
            n = l.from_node
            if n.type != 'TEX_IMAGE' or not n.image:
                continue
            if l.to_node.type == 'BSDF_PRINCIPLED' and l.to_socket.name == 'Base Color':
                base = n.image
            elif l.to_node.type == 'NORMAL_MAP':
                nrm = n.image
            elif l.to_node.type in ('SEPARATE_COLOR', 'SEPRGB', 'SEPARATE_RGB'):
                mr = n.image
    return base, nrm, mr


def img_px(img, size):
    if img is None:
        return None
    im = img.copy()
    if im.size[0] != size or im.size[1] != size:
        im.scale(size, size)
    px = np.array(im.pixels[:], dtype=np.float32).reshape(size, size, 4)
    bpy.data.images.remove(im)
    return px


bpy.ops.wm.read_factory_settings(use_empty=True)
atlas = {'BaseColor': np.zeros((A, A, 4), np.float32), 'Normal': np.zeros((A, A, 4), np.float32), 'ORM': np.zeros((A, A, 4), np.float32)}
atlas['Normal'][..., :] = (0.5, 0.5, 1.0, 1.0); atlas['ORM'][..., :] = (1.0, 0.8, 0.0, 1.0); atlas['BaseColor'][..., 3] = 1
objs, fits, filled = [], {}, set()
for pi, part in enumerate(cfg['parts']):
    ob = import_part(part['glb'])
    ob.name = part['name']
    me = ob.data
    V = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get('co', V); V = V.reshape(-1, 3)
    if part.get('mirror'):
        V[:, 1] *= -1
    Q = region(part['region'])
    s, R, t, e = fit(V, Q, part['init'])
    V = s * V @ R.T + t
    me.vertices.foreach_set('co', V.ravel())
    if part.get('mirror'):
        bm = bmesh.new(); bm.from_mesh(me)
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:], flip_multires=False)
        bm.to_mesh(me); bm.free()
    trim = part.get('trim', {})
    if trim:
        bm = bmesh.new(); bm.from_mesh(me)
        dead = []
        for f in bm.faces:
            zs = [v.co.z for v in f.verts]
            if ('below_z' in trim and max(zs) < z0 + trim['below_z'] * H) or ('above_z' in trim and min(zs) > z0 + trim['above_z'] * H):
                dead.append(f)
        bmesh.ops.delete(bm, geom=dead, context='FACES')
        bm.to_mesh(me); bm.free()
    me.update()
    # atlas cell: this part's own textures (or the source part's cell for a mirrored copy)
    src = part.get('share_uv_with', part['name'])
    qi = next(p for p in cfg['parts'] if p['name'] == src)['quad']
    uv = np.zeros(len(me.loops) * 2); me.uv_layers.active.data.foreach_get('uv', uv); uv = uv.reshape(-1, 2)
    uv = np.clip(uv, 0, 1) * 0.5 + np.array([qi[0] * 0.5, qi[1] * 0.5])
    me.uv_layers.active.data.foreach_set('uv', uv.ravel())
    if src not in filled:
        base, nrm, mr = part_images(ob)
        r0, c0 = qi[1] * cell, qi[0] * cell
        b = img_px(base, cell); n = img_px(nrm, cell); m = img_px(mr, cell)
        if part.get('normal_dx'):          # re-baked from the part's high-poly (bake_normal_onto.py, DirectX) -> OpenGL here
            n = img_px(bpy.data.images.load(part['normal_dx']), cell); n[..., 1] = 1.0 - n[..., 1]
        atlas['BaseColor'][r0:r0 + cell, c0:c0 + cell] = b
        if n is not None:
            atlas['Normal'][r0:r0 + cell, c0:c0 + cell] = n
        if m is not None:
            orm = np.ones_like(m); orm[..., 1] = m[..., 1]; orm[..., 2] = m[..., 2]
            atlas['ORM'][r0:r0 + cell, c0:c0 + cell] = orm
        filled.add(src)
        print(f'TEX {src} base={base and base.size[:]} normal={nrm and nrm.size[:]} mr={mr and mr.size[:]}', flush=True)
    me.materials.clear()
    ob['part_index'] = pi
    fits[part['name']] = {'scale': round(float(s), 5), 'mean_dist': round(float(e), 5), 'mean_dist_of_height': round(float(e / H), 5),
                          'faces': len(me.polygons)}
    objs.append(ob)

# merge (face order = part order), one material
part_of_face = np.concatenate([np.full(len(o.data.polygons), o['part_index'], np.int32) for o in objs])
for o in bpy.context.view_layer.objects:
    o.select_set(o in objs)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.object.join()
merged = bpy.context.view_layer.objects.active
merged.name = f'{name}_low'
mat = bpy.data.materials.new(f'M_{name}'); merged.data.materials.append(mat)
for p in merged.data.polygons:
    p.use_smooth = True
np.save(out / 'parts.npy', part_of_face)

# coarse classes for process_character --parts/--parts-json: head = fur (the crown is re-labelled metal there by its
# texture), tail = fur of the legs piece behind the legs (cfg "tail": {"part", "x_below" m, "z_below" height fraction}),
# the rest = armour (metal)
tail = cfg.get('tail')
names = [p['name'] for p in cfg['parts']]
cls = []
for poly, pi in zip(merged.data.polygons, part_of_face):
    c = poly.center
    if names[pi] == 'head':
        cls.append('fur')
    elif tail and names[pi] == tail['part'] and c.x < tail['x_below'] and c.z < z0 + tail['z_below'] * H:
        cls.append('tail')
    else:
        cls.append('metal')
cls = np.array(cls)
np.save(out / 'classes.npy', cls)
print('CLASSES', {k: int((cls == k).sum()) for k in ('fur', 'tail', 'metal')}, flush=True)
seg_objs = []
for k in ('fur', 'tail', 'metal'):
    if not (cls == k).any():
        continue
    o = merged.copy(); o.data = merged.data.copy(); o.name = k
    bpy.context.collection.objects.link(o)
    bm = bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if cls[f.index] != k], context='FACES')
    bm.to_mesh(o.data); bm.free()
    seg_objs.append(o)
bpy.ops.object.select_all(action='DESELECT')
for o in seg_objs:
    o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str((out / f'{name}_parts.glb').resolve()), use_selection=True, export_format='GLB', export_materials='NONE')
(out / f'{name}_parts.json').write_text(json.dumps({k: {'class': k} for k in ('fur', 'tail', 'metal')}, indent=1), encoding='utf-8')
for o in seg_objs:
    bpy.data.objects.remove(o, do_unlink=True)

tex = {}
for role, px in atlas.items():
    px = px.copy()
    if role == 'Normal':
        px[..., 1] = 1.0 - px[..., 1]          # glTF / Blender OpenGL -> Unreal DirectX
    img = bpy.data.images.new(f'T_{name}_{role}', A, A, alpha=False)
    img.colorspace_settings.name = 'sRGB' if role == 'BaseColor' else 'Non-Color'
    img.pixels = px.ravel()
    path = (out / f'T_{name}_{role}.png').resolve()
    img.filepath_raw = str(path); img.file_format = 'PNG'; img.save()
    assert path.exists(), path
    tex[role] = path.name
# preview material for the GLB (process_character only reads the mesh + UV)
mat.use_nodes = True
tn = mat.node_tree.nodes.new('ShaderNodeTexImage'); tn.image = bpy.data.images[f'T_{name}_BaseColor']
mat.node_tree.links.new(tn.outputs[0], mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
bpy.ops.object.select_all(action='DESELECT'); merged.select_set(True)
glb = (out / f'{name}_low.glb').resolve()
bpy.ops.export_scene.gltf(filepath=str(glb), use_selection=True, export_format='GLB')
info = {'glb': glb.name, 'textures': tex, 'res': A, 'parts': fits, 'low_tris': sum(len(p.vertices) - 2 for p in merged.data.polygons)}
(out / f'{name}_bake.json').write_text(json.dumps(info, indent=1), encoding='utf-8')
(out / 'fit.json').write_text(json.dumps(fits, indent=1), encoding='utf-8')
print('ASSEMBLE_DONE', json.dumps(info))
