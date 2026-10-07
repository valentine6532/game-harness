"""Blender: render N frames of every action in a rigged FBX into one strip per action.

blender -b --python anim_frames.py -- --input model.fbx --out dir [--frames 5]
"""
import argparse, math, sys
from pathlib import Path

import bpy
from mathutils import Vector

p = argparse.ArgumentParser()
p.add_argument('--input', required=True)
p.add_argument('--out', required=True)
p.add_argument('--frames', type=int, default=5)
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=a.input)
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
for engine in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
    try:
        scene.render.engine = engine
        break
    except TypeError:
        pass
scene.render.resolution_x = scene.render.resolution_y = 360
world = bpy.data.worlds.new('W')
world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (0.45, 0.48, 0.52, 1)
scene.world = world
sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN'))
sun.data.energy = 3
sun.rotation_euler = (math.radians(40), 0, math.radians(40))
scene.collection.objects.link(sun)
cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam'))
cam.data.type = 'ORTHO'
scene.collection.objects.link(cam)
scene.camera = cam
for action in bpy.data.actions:
    arm.animation_data.action = action
    f0, f1 = (int(v) for v in action.frame_range)
    frames = [round(f0 + (f1 - f0) * i / max(a.frames - 1, 1)) for i in range(a.frames)]
    paths = []
    for i, f in enumerate(frames):
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        pts = []
        for o in scene.objects:
            if o.type == 'MESH':
                ev = o.evaluated_get(dg)
                pts += [ev.matrix_world @ v.co for v in ev.data.vertices]
        lo = Vector([min(v[k] for v in pts) for k in range(3)])
        hi = Vector([max(v[k] for v in pts) for k in range(3)])
        c = (lo + hi) / 2
        size = max(hi - lo) * 1.3
        cam.data.ortho_scale = max(size, 1.3)
        cam.location = c + Vector((1.2, -1.6, 0.8)).normalized() * 6
        cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
        path = out / f'{action.name.split("|")[-1]}_{i}.png'
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        paths.append(path)
    print('ACTION', action.name, f0, f1)
print('ANIM_FRAMES_DONE')
