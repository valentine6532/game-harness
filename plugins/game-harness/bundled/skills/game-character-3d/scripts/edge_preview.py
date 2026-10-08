"""Preview for edge_axis.py (4-30): the real sword mesh on the hero at each strike, old roll vs grip.R.edge_axis.
Per strike: onion skin of the sword over strike..hit+1 from the quarter view, and the view from where the blade is
heading at the hit (a leading edge shows as a thin line, a leading flat as the full blade face).

blender -b -P edge_preview.py -- <SK_Hero.fbx> <Hero.json> <SM_Sword.fbx> <out dir>"""
import bpy, sys, json
from pathlib import Path
from mathutils import Vector, Matrix

fbx, js, sword_fbx, out = sys.argv[sys.argv.index('--') + 1:]
out = Path(out); out.mkdir(parents=True, exist_ok=True)
g = json.load(open(js, encoding='utf-8'))['grip']['R']
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
Wm = arm.matrix_world
H = (Wm @ arm.data.bones['Head'].head_local).z
old = set(scene.objects)
bpy.ops.import_scene.fbx(filepath=sword_fbx)
sword = next(o for o in scene.objects if o not in old and o.type == 'MESH')
sword.parent = None
sword.matrix_world = Matrix.Identity(4)
bpy.context.view_layer.update()
sword_scale = H / 1.5                          # weapon modelled for a 1.5 m hero (ue_build_plaza WEAPON_BASE_HEIGHT_M)

# rest-pose sword frame, as ue_build_plaza.grip_relative builds it (Blender +X fwd / +Y left / +Z up)
hr = Wm @ arm.data.bones['R_Hand'].matrix_local
hand_rest = Matrix.Translation(hr.translation) @ hr.to_3x3().normalized().to_4x4()
hloc = hr.translation
fore = Wm @ arm.data.bones['R_Forearm'].head_local
d = (hloc - fore).normalized()
grip = hloc + d * g['along_ratio'] * (hloc - fore).length + Vector(g['perp_m'])
z = Vector(g['hole_axis']).normalized()
x_old = (d - z * d.dot(z)).normalized()
y_new = Vector(g['edge_axis']); y_new = (y_new - z * y_new.dot(z)).normalized()


def frame(x, y):
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = grip
    return hand_rest.inverted() @ m @ Matrix.Scale(sword_scale, 4)


rel = {'before': frame(x_old, z.cross(x_old)), 'after': frame(y_new.cross(z), y_new)}

scene.render.engine = 'BLENDER_WORKBENCH'
sh = scene.display.shading
sh.light = 'STUDIO'
sh.color_type = 'OBJECT'
sh.show_cavity = True
sh.background_type = 'VIEWPORT'
sh.background_color = (0.13, 0.13, 0.15)
scene.render.resolution_x, scene.render.resolution_y = 420, 420
for o in scene.objects:
    if o.type == 'MESH':
        o.color = (0.55, 0.55, 0.55, 0.35)
cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam')); cam.data.type = 'ORTHO'
scene.collection.objects.link(cam); scene.camera = cam

WINS = {'onehand': [(26, 33), (56, 62), (86, 91)], 'power': [(38, 42)]}
copies = []


def place(tag, frames, hit):
    for c in copies:
        bpy.data.objects.remove(c)
    copies.clear()
    for f in frames:
        scene.frame_set(f)
        m = Wm @ arm.pose.bones['R_Hand'].matrix
        hm = Matrix.Translation(m.translation) @ m.to_3x3().normalized().to_4x4()
        c = sword.copy(); c.hide_render = False; scene.collection.objects.link(c)
        c.matrix_world = hm @ rel[tag]
        t = 1.0 if f == hit else 0.35 + 0.4 * (f - frames[0]) / max(1, hit - frames[0])
        c.color = (0.95 * t + 0.05, 0.25 * t, 0.1, 1)
        copies.append(c)
    scene.frame_set(hit)


sword.hide_render = True
for clip, wins in WINS.items():
    arm.animation_data.action = next(a for a in bpy.data.actions if a.name.endswith(clip))
    for wi, (k, h) in enumerate(wins):
        # blade-tip velocity at the hit decides the "incoming" camera
        tips = []
        for f in (h - 1, h):
            scene.frame_set(f)
            m = Wm @ arm.pose.bones['R_Hand'].matrix
            hm = Matrix.Translation(m.translation) @ m.to_3x3().normalized().to_4x4()
            tips.append(hm @ rel['before'] @ Vector((0, 0, 0.55)))
        v = (tips[1] - tips[0]).normalized()
        for tag in rel:
            place(tag, list(range(k - 1, h + 2)), h)
            scene.frame_set(h)
            hip = Wm @ arm.pose.bones['Hip'].head
            c = Vector((hip.x, hip.y, 0.5 * H))
            for vname, loc, look, scale in (('quarter', c + Vector((1.0, -1.25, 1.4)).normalized() * 8 * H, c, 1.9 * H),
                                            ('incoming', tips[1] + v * 4 * H, tips[1] - v * 0.2 * H, 1.1 * H)):
                cam.location = loc
                cam.rotation_euler = (look - loc).to_track_quat('-Z', 'Y').to_euler()
                cam.data.ortho_scale = scale
                scene.render.filepath = str(out / f'{clip}{wi}_{vname}_{tag}.png')
                bpy.ops.render.render(write_still=True)
print('EDGE_PREVIEW_DONE', flush=True)
