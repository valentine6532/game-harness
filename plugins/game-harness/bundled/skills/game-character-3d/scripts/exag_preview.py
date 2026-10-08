"""Preview: current hero attack clips vs exaggerated variants, rendered from a quarter-view-like angle + side view.
blender -b -P exag_preview.py -- <SK_Hero.fbx> <Hero.json> <out dir> <variant specs step:crouch:lean ...>"""
import bpy, sys, json, math
from pathlib import Path
from mathutils import Vector, Matrix
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))   # exaggerate_attack.py next to this file
import exaggerate_attack as ex

fbx, js, out, *specs = sys.argv[sys.argv.index('--') + 1:]
out = Path(out); out.mkdir(parents=True, exist_ok=True)
g = json.load(open(js, encoding='utf-8'))['grip']['R']
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
Wm = arm.matrix_world
H = (Wm @ arm.data.bones['Head'].head_local).z
# sword proxy along the grip axis
hand_rest = (Wm @ arm.data.bones['R_Hand'].matrix_local).to_3x3().normalized()
axis_local = hand_rest.inverted() @ Vector(g['hole_axis']).normalized()
bpy.ops.mesh.primitive_cube_add(size=1)
sw = bpy.context.active_object
L = 0.45 * H
sw.scale = (0.012 * H, 0.03 * H, L)
bpy.ops.object.transform_apply(scale=True)
for v in sw.data.vertices:
    v.co.z += L / 2
sw.parent = arm
sw.parent_type = 'BONE'
sw.parent_bone = 'R_Hand'
bpy.context.view_layer.update()
# orient: bone-space Z of the sword -> axis_local in the hand's (rest) frame; parent bone space = bone tail, Y along bone
pb = arm.pose.bones['R_Hand']
arm.animation_data.action = None
for b in arm.pose.bones:
    b.matrix_basis = Matrix.Identity(4)
bpy.context.view_layer.update()
hand_w = Wm @ pb.matrix
q = Vector((0, 0, 1)).rotation_difference(hand_w.to_3x3().normalized() @ axis_local)
sw.matrix_world = Matrix.Translation(hand_w.translation) @ q.to_matrix().to_4x4()
mat = bpy.data.materials.new('Blade'); mat.diffuse_color = (0.9, 0.2, 0.1, 1)
sw.data.materials.append(mat)

scene.render.engine = 'BLENDER_WORKBENCH'
sh = scene.display.shading
sh.light = 'STUDIO'
sh.color_type = 'OBJECT'
sh.show_shadows = True
sh.show_cavity = True
sh.background_type = 'VIEWPORT'
sh.background_color = (0.12, 0.12, 0.14)
scene.render.resolution_x, scene.render.resolution_y = 300, 300
for o in scene.objects:
    if o.type == 'MESH':
        o.color = (0.72, 0.72, 0.7, 1)
sw.color = (0.95, 0.15, 0.1, 1)
bpy.ops.mesh.primitive_plane_add(size=40)
floor = bpy.context.active_object
floor.color = (0.32, 0.3, 0.27, 1)
cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam')); cam.data.type = 'ORTHO'
scene.collection.objects.link(cam); scene.camera = cam
cam.data.ortho_scale = 2.2 * H

WINS = {'onehand': [(16, 26, 34, 40), (45, 56, 63, 68), (75, 86, 92, 98)], 'power': [(18, 38, 42, 50)]}
base = {c: next(a for a in bpy.data.actions if a.name.endswith(c)) for c in WINS}
variants = [('cur', None)] + [(chr(65 + i), tuple(float(x) for x in sp.split(':'))) for i, sp in enumerate(specs)]
acts = {}
for name, prm in variants:
    for clip, wins in WINS.items():
        ac = base[clip].copy()
        ac.name = f'{name}_{clip}'
        if prm:
            travel = ex.apply(arm, ac, wins, step=prm[0], crouch=prm[1], lean=prm[2], log=lambda m: print(m, flush=True))
            print('TRAVEL', name, clip, {k: [round(v.x / H * 100), round(v.y / H * 100)] for k, v in travel.items()}, flush=True)
        acts[name, clip] = ac

views = {'quarter': (Vector((1.0, -1.25, 1.4)), -0.0), 'side': (Vector((0.0, -1.0, 0.12)), 0.0)}
for (name, clip), ac in acts.items():
    arm.animation_data.action = ac
    for wi, (s, k, h, e) in enumerate(WINS[clip]):
        frames = [s, k, (k + h) // 2, h, min(h + 2, e), e]
        scene.frame_set(s)
        c0 = Wm @ arm.pose.bones['Hip'].head
        for vname, (d, _) in views.items():
            for i, f in enumerate(frames):
                scene.frame_set(f)
                c = Vector((c0.x, c0.y, 0.45 * H))
                c.x += (Wm @ arm.pose.bones['Hip'].head).x * 0
                cam.location = c + d.normalized() * 8 * H
                cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
                scene.render.filepath = str(out / f'{name}_{clip}{wi}_{vname}_{i}.png')
                bpy.ops.render.render(write_still=True)
print('PREVIEW_DONE', flush=True)
