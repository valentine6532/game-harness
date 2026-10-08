"""Blender: import a model (glb/fbx), report stats, render review views (textured + wireframe).

blender -b --python inspect_render.py -- --input model.glb --out review_dir [--size 700]
Writes stats.json and <view>.png / <view>_wire.png. Forward axis is detected from the file
(Tripo GLB faces +X after glTF import -> Blender -Y? we render from 4 sides so it does not matter).
"""
import argparse, json, math, sys
from pathlib import Path

import bpy
from mathutils import Vector

p = argparse.ArgumentParser()
p.add_argument('--input', required=True)
p.add_argument('--out', required=True)
p.add_argument('--size', type=int, default=700)
p.add_argument('--no-wire', action='store_true')
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
src = Path(a.input)
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
if src.suffix.lower() in ('.glb', '.gltf'):
    bpy.ops.import_scene.gltf(filepath=str(src))
else:
    bpy.ops.import_scene.fbx(filepath=str(src))
scene = bpy.context.scene
meshes = [o for o in scene.objects if o.type == 'MESH']
deps = bpy.context.evaluated_depsgraph_get()
tris = 0
for o in meshes:
    me = o.evaluated_get(deps).to_mesh()
    me.calc_loop_triangles()
    tris += len(me.loop_triangles)
    o.evaluated_get(deps).to_mesh_clear()
mats = sorted({s.material.name for o in meshes for s in o.material_slots if s.material})
imgs = [{'name': i.name, 'size': list(i.size)} for i in bpy.data.images if i.size[0]]
arms = [o for o in scene.objects if o.type == 'ARMATURE']
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector([min(v[i] for v in pts) for i in range(3)])
hi = Vector([max(v[i] for v in pts) for i in range(3)])
stats = {
    'input': str(src), 'meshes': len(meshes), 'triangles': tris, 'materials': mats, 'images': imgs,
    'armatures': [{'name': o.name, 'bones': len(o.data.bones)} for o in arms],
    'actions': [ac.name for ac in bpy.data.actions],
    'bbox_min': list(lo), 'bbox_max': list(hi), 'dimensions': list(hi - lo),
}
(out / 'stats.json').write_text(json.dumps(stats, indent=1), encoding='utf-8')
print('STATS', json.dumps(stats))

center = (lo + hi) / 2
size = max(hi - lo)
for engine in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
    try:
        scene.render.engine = engine
        break
    except TypeError:
        pass
scene.render.resolution_x = scene.render.resolution_y = a.size
scene.view_settings.view_transform = 'Standard'
world = bpy.data.worlds.new('W')
world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (0.42, 0.45, 0.5, 1)
world.node_tree.nodes['Background'].inputs[1].default_value = 1.0
scene.world = world
sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN'))
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(45), 0, math.radians(30))
scene.collection.objects.link(sun)
cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam'))
cam.data.type = 'ORTHO'
cam.data.ortho_scale = size * 1.15
cam.data.clip_end = size * 30
scene.collection.objects.link(cam)
scene.camera = cam
views = {'front_x': (1, 0, 0), 'back_x': (-1, 0, 0), 'front_y': (0, -1, 0), 'back_y': (0, 1, 0),
         'quarter': (0.8, -0.8, 0.9)}
for name, d in views.items():
    cam.location = center + Vector(d).normalized() * size * 4
    cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sun.rotation_euler = cam.rotation_euler
    scene.render.filepath = str(out / f'{name}.png')
    bpy.ops.render.render(write_still=True)

if not a.no_wire:
    # wireframe overlay via Freestyle-free approach: wireframe modifier on a copy, dark material
    wm = bpy.data.materials.new('Wire')
    wm.use_nodes = True
    wm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.02, 0.02, 0.02, 1)
    for o in meshes:
        c = o.copy()
        c.data = o.data.copy()
        scene.collection.objects.link(c)
        c.data.materials.clear()
        c.data.materials.append(wm)
        m = c.modifiers.new('wf', 'WIREFRAME')
        m.thickness = size * 0.0012
        m.use_replace = True
    for name in ('front_x', 'front_y', 'quarter'):
        d = views[name]
        cam.location = center + Vector(d).normalized() * size * 4
        cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sun.rotation_euler = cam.rotation_euler
        scene.render.filepath = str(out / f'{name}_wire.png')
        bpy.ops.render.render(write_still=True)
print('INSPECT_DONE', out)
