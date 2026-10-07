"""Blender: cover a texture artefact on one side of a (near-symmetric) character with the colour of the mirrored side.

blender -b --python fix_ghost.py -- <mesh.glb> <basecolor.png> <box json> [--res 4096]
box: {"y": [lo, hi] metres, "z": [lo, hi] fractions of height, "x_min": metres, "nx_min": normal x}
The mesh copy is mirrored across the model's Y centre and shows the atlas as emission; faces inside the box get the
mirrored colour by a selected-to-active EMIT bake, blended into the atlas with a soft edge. The original is kept as
<basecolor>.pre_ghost.png. (Deathknight head: Tripo projected a second small face from the side view onto the neck fur.)"""
import sys, json, shutil
from pathlib import Path
import bpy, bmesh
import numpy as np

args = sys.argv[sys.argv.index('--') + 1:]
glb, tex_path, box = args[0], Path(args[1]), json.loads(args[2])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
ob = [o for o in bpy.context.scene.objects if o.type == 'MESH'][0]
me = ob.data
V = np.array([ob.matrix_world @ v.co for v in me.vertices])
z0, H = V[:, 2].min(), V[:, 2].max() - V[:, 2].min()
yc = (V[:, 1].min() + V[:, 1].max()) / 2

bak = tex_path.with_suffix('.pre_ghost.png')
if not bak.exists():
    shutil.copy2(tex_path, bak)
atlas = bpy.data.images.load(str(bak))
W, Hh = atlas.size

# mirrored emission copy
src = ob.copy(); src.data = me.copy(); src.name = 'mirror'
bpy.context.collection.objects.link(src)
src.matrix_world = ob.matrix_world.copy()
for v in src.data.vertices:
    v.co.y = 2 * yc - v.co.y
bm = bmesh.new(); bm.from_mesh(src.data); bmesh.ops.reverse_faces(bm, faces=bm.faces[:]); bm.to_mesh(src.data); bm.free()
em = bpy.data.materials.new('emit'); em.use_nodes = True; nt = em.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = atlas
es = nt.nodes.new('ShaderNodeEmission'); outn = nt.nodes.new('ShaderNodeOutputMaterial')
nt.links.new(tn.outputs[0], es.inputs[0]); nt.links.new(es.outputs[0], outn.inputs[0])
src.data.materials.clear(); src.data.materials.append(em)

# target faces (inside the box) write into `baked`, the rest into a dummy image
baked = bpy.data.images.new('baked', W, Hh, alpha=True, float_buffer=True)
baked.pixels = np.zeros(W * Hh * 4, np.float32)
dummy = bpy.data.images.new('dummy', 64, 64, alpha=True)
def target_mat(name, img):
    m = bpy.data.materials.new(name); m.use_nodes = True
    t = m.node_tree.nodes.new('ShaderNodeTexImage'); t.image = img; m.node_tree.nodes.active = t
    return m
me.materials.clear(); me.materials.append(target_mat('other', dummy)); me.materials.append(target_mat('target', baked))
part_ok = None
if box.get('parts_npy'):                          # only faces of one assembled part (assemble_parts.py parts.npy)
    pn = np.load(box['parts_npy'])
    assert len(pn) == len(me.polygons), (len(pn), len(me.polygons))
    part_ok = pn == box['part']
n_t = 0
for p in me.polygons:
    if part_ok is not None and not part_ok[p.index]:
        p.material_index = 0
        continue
    c = ob.matrix_world @ p.center
    nrm = (ob.matrix_world.to_3x3() @ p.normal).normalized()
    inside = (box['y'][0] <= c.y <= box['y'][1] and z0 + box['z'][0] * H <= c.z <= z0 + box['z'][1] * H
              and c.x >= box.get('x_min', -1e9) and nrm.x >= box.get('nx_min', -1.0))
    p.material_index = 1 if inside else 0
    n_t += inside
print('GHOST_FACES', n_t, flush=True)

sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.samples = 1
sc.render.bake.use_selected_to_active = True
sc.render.bake.cage_extrusion = 0.01 * H
sc.render.bake.max_ray_distance = 0.03 * H
sc.render.bake.margin = 4
bpy.ops.object.select_all(action='DESELECT')
src.select_set(True); ob.select_set(True); bpy.context.view_layer.objects.active = ob
bpy.ops.object.bake(type='EMIT')
bk = np.array(baked.pixels[:], np.float32).reshape(Hh, W, 4).copy()
# second bake with a white emitter: the baked footprint (Cycles clears the rest of the image)
nt.links.remove(nt.links[0]); es.inputs[0].default_value = (1, 1, 1, 1)
baked.pixels = np.zeros(W * Hh * 4, np.float32)
bpy.ops.object.bake(type='EMIT')
mask = (np.array(baked.pixels[:], np.float32).reshape(Hh, W, 4)[..., 0] > 0.5).astype(np.float32)
px = np.array(atlas.pixels[:], np.float32).reshape(Hh, W, 4)
lin = np.clip(bk[..., :3], 0, 1)                  # float bake = linear emission; the byte atlas pixels are sRGB-encoded
bk[..., :3] = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
ys, xs = np.nonzero(mask)
out = px.copy()
if len(ys):
    k = max(3, W // 512) | 1                     # soft edge: box-blurred mask, kept inside the footprint
    y0, y1, x0, x1 = max(ys.min() - k, 0), min(ys.max() + k + 1, Hh), max(xs.min() - k, 0), min(xs.max() + k + 1, W)
    m = mask[y0:y1, x0:x1]
    for _ in range(2):
        c = np.pad(m, k // 2 + 1, mode='edge').cumsum(0).cumsum(1)
        m = (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k])[:y1 - y0, :x1 - x0] / (k * k)
    m = np.clip(m * mask[y0:y1, x0:x1], 0, 1)[..., None]
    out[y0:y1, x0:x1, :3] = px[y0:y1, x0:x1, :3] * (1 - m) + bk[y0:y1, x0:x1, :3] * m
res = bpy.data.images.new('out', W, Hh, alpha=False)
res.colorspace_settings.name = 'sRGB'
res.pixels = out.ravel()
res.filepath_raw = str(tex_path.resolve()); res.file_format = 'PNG'; res.save()
print('GHOST_FIXED texels', int(mask.sum()), flush=True)
