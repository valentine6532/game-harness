"""Render the hero rest mesh with a checker texture through a given UV (old / new) from 3 sides (Workbench)."""
import sys
import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
fbx, uv_path, out_prefix = argv[0], argv[1], argv[2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
low = next(o for o in bpy.context.scene.objects if o.type == 'MESH' and o.parent == arm)
for o in list(bpy.context.scene.objects):
    if o is not low:
        bpy.data.objects.remove(o, do_unlink=True)
low.modifiers.clear()
me = low.data
me.uv_layers.active.data.foreach_set('uv', np.load(uv_path).astype(np.float32).ravel())

# checker: 32x32 cells, alternating two tones + a colour gradient so rotation / flips are visible too
N, C = 2048, 32
yy, xx = np.mgrid[0:N, 0:N]
cell = ((xx * C // N) + (yy * C // N)) % 2
px = np.zeros((N, N, 4), np.float32)
px[..., 0] = 0.25 + 0.6 * (xx / N)
px[..., 1] = 0.25 + 0.6 * (yy / N)
px[..., 2] = 0.55
px[..., :3] *= np.where(cell[..., None] == 1, 1.0, 0.35)
px[..., 3] = 1
img = bpy.data.images.new('checker', N, N)
img.pixels = px[::-1].ravel()
mat = bpy.data.materials.new('chk')
mat.use_nodes = True
nt = mat.node_tree
tn = nt.nodes.new('ShaderNodeTexImage')
tn.image = img
tn.interpolation = 'Closest'
nt.links.new(tn.outputs['Color'], nt.nodes['Principled BSDF'].inputs['Base Color'])
me.materials.clear()
me.materials.append(mat)
for p in me.polygons:
    p.use_smooth = True

sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'
sc.display.shading.color_type = 'TEXTURE'
sc.render.resolution_x, sc.render.resolution_y = 900, 1200
bb = [low.matrix_world @ Vector(c) for c in low.bound_box]
lo = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
hi = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
ctr, h = (lo + hi) / 2, hi.z - lo.z
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = 'ORTHO'
cam.data.ortho_scale = h * 1.08
for tag, d in (('front', Vector((1, 0, 0))), ('back', Vector((-1, 0, 0))), ('side', Vector((0, 1, 0)))):
    cam.location = ctr + d * h * 3
    cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = f'{out_prefix}_{tag}.png'
    bpy.ops.render.render(write_still=True)
print('CHECKER_DONE')
