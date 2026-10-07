"""Blender: orthographic review renders of a raw Tripo GLB with its own materials (Eevee).
blender -b --python review_glb.py -- <glb> <out prefix> [--zoom name:cx,cz,size ...]   (cx/cz/size as fractions of height, views front/left/back/right)"""
import sys, math, bpy
from mathutils import Vector
args = sys.argv[sys.argv.index('--') + 1:]
glb, out = args[0], args[1]
zooms = [z.split(':') for z in args[3:] if ':' in z and not z.startswith('--') and not z.endswith('.png')] if len(args) > 2 and args[2] == '--zoom' else []
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
for g in glb.split(','):          # several GLBs separated by , are rendered together (e.g. body + assembled parts)
    bpy.ops.import_scene.gltf(filepath=g)
ms = [o for o in sc.objects if o.type == 'MESH']
if '--tex' in args:              # show this BaseColor PNG instead of the texture packed in the GLB
    img = bpy.data.images.load(args[args.index('--tex') + 1])
    for o in ms:
        for m in o.data.materials:
            for n in m.node_tree.nodes:
                if n.type == 'TEX_IMAGE' and any(l.to_socket.name == 'Base Color' for l in n.outputs[0].links):
                    n.image = img
if '--objcolor' in args:          # flat colour per object (class / part check)
    pal = {'fur': (0.9, 0.7, 0.2, 1), 'tail': (0.9, 0.1, 0.1, 1), 'metal': (0.4, 0.45, 0.6, 1)}
    for i, o in enumerate(ms):
        m = bpy.data.materials.new(o.name); m.use_nodes = True
        m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = pal.get(o.name, (0.3 + 0.2 * (i % 3), 0.5, 0.4, 1))
        o.data.materials.clear(); o.data.materials.append(m)
nf = sum(len(o.data.polygons) for o in ms)
bb = [o.matrix_world @ Vector(v) for o in ms for v in o.bound_box]
lo = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb))); hi = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
ctr = (lo + hi) / 2; h = hi.z - lo.z
print(f'REVIEW meshes={len(ms)} faces={nf} size={tuple(round(x,3) for x in hi-lo)}')
sc.render.engine = 'BLENDER_EEVEE'
w = bpy.data.worlds.new('W'); w.use_nodes = True; bg = w.node_tree.nodes['Background']; bg.inputs[0].default_value = (0.8, 0.8, 0.8, 1); bg.inputs[1].default_value = 1.0; sc.world = w
sun = bpy.data.objects.new('S', bpy.data.lights.new('S', 'SUN')); sun.data.energy = 2.5; sun.rotation_euler = (math.radians(45), 0, math.radians(-30)); sc.collection.objects.link(sun)
sc.view_settings.view_transform = 'Standard'
cam = bpy.data.objects.new('C', bpy.data.cameras.new('C')); cam.data.type = 'ORTHO'; sc.collection.objects.link(cam); sc.camera = cam
dirs = {'front': Vector((1, 0, 0)), 'left': Vector((0, 1, 0)), 'back': Vector((-1, 0, 0)), 'right': Vector((0, -1, 0))}  # Tripo GLB faces +X in Blender
def shot(view, tgt, size, fn, res):
    d = dirs[view]; cam.location = tgt + d * h * 3; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    cam.data.ortho_scale = size; cam.data.clip_end = h * 10
    sc.render.resolution_x = res[0]; sc.render.resolution_y = res[1]; sc.render.filepath = fn; bpy.ops.render.render(write_still=True)
for v in dirs:
    shot(v, ctr, h * 1.05, f'{out}_{v}.png', (600, 900))
for name, spec in zooms:  # cy = lateral offset (+ = character's left, +Y), cz = height, as fractions of h
    cy, cz, size = map(float, spec.split(','))
    tgt = Vector((ctr.x, ctr.y + cy * h, lo.z + cz * h))
    for v in dirs:
        shot(v, tgt, size * h, f'{out}_{name}_{v}.png', (600, 600))
