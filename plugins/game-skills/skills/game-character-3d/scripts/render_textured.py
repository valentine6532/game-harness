"""Blender: turntable-style review renders of a baked game mesh with its T_<Name>_* textures (Eevee).
blender -b --python render_textured.py -- --dir baked_dir --name Hero --out prefix [--views front,back,left]"""
import argparse, math, os, sys, json
import bpy
from mathutils import Vector
p = argparse.ArgumentParser()
p.add_argument('--dir', required=True); p.add_argument('--name', required=True); p.add_argument('--out', required=True)
p.add_argument('--views', default='front,back,side'); p.add_argument('--res', type=int, default=700)
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
D = os.path.abspath(a.dir)
info = json.load(open(f'{D}/{a.name}_bake.json', encoding='utf-8'))
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=f'{D}/{info["glb"]}')
low = [o for o in sc.objects if o.type == 'MESH'][0]
m = bpy.data.materials.new('B'); m.use_nodes = True; nt = m.node_tree; b = nt.nodes['Principled BSDF']
def tex(f, cs):
    n = nt.nodes.new('ShaderNodeTexImage'); n.image = bpy.data.images.load(f'{D}/{f}'); n.image.colorspace_settings.name = cs; return n
c = tex(info['textures']['BaseColor'], 'sRGB'); nt.links.new(c.outputs[0], b.inputs['Base Color'])
o = tex(info['textures']['ORM'], 'Non-Color'); sp = nt.nodes.new('ShaderNodeSeparateColor'); nt.links.new(o.outputs[0], sp.inputs[0])
nt.links.new(sp.outputs[1], b.inputs['Roughness']); nt.links.new(sp.outputs[2], b.inputs['Metallic'])
n = tex(info['textures']['Normal'], 'Non-Color'); s2 = nt.nodes.new('ShaderNodeSeparateColor'); nt.links.new(n.outputs[0], s2.inputs[0])
inv = nt.nodes.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1; nt.links.new(s2.outputs[1], inv.inputs[1])
cc = nt.nodes.new('ShaderNodeCombineColor'); nt.links.new(s2.outputs[0], cc.inputs[0]); nt.links.new(inv.outputs[0], cc.inputs[1]); nt.links.new(s2.outputs[2], cc.inputs[2])
nm = nt.nodes.new('ShaderNodeNormalMap'); nt.links.new(cc.outputs[0], nm.inputs['Color']); nt.links.new(nm.outputs[0], b.inputs['Normal'])
low.data.materials.clear(); low.data.materials.append(m)
sc.render.engine = 'BLENDER_EEVEE'; sc.render.resolution_x = a.res; sc.render.resolution_y = int(a.res * 1.3)
w = bpy.data.worlds.new('W'); w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (0.55, 0.6, 0.7, 1); w.node_tree.nodes['Background'].inputs[1].default_value = 0.8; sc.world = w
sun = bpy.data.objects.new('S', bpy.data.lights.new('S', 'SUN')); sun.data.energy = 4.5; sun.data.angle = 0.05
sun.rotation_euler = (math.radians(50), 0, math.radians(150)); sc.collection.objects.link(sun)
cam = bpy.data.objects.new('C', bpy.data.cameras.new('C')); cam.data.lens = 70; sc.collection.objects.link(cam); sc.camera = cam
bb = [low.matrix_world @ Vector(v) for v in low.bound_box]; ctr = sum(bb, Vector()) / 8; h = max(v.z for v in bb) - min(v.z for v in bb)
dirs = {'front': (1, 0.3, 0.15), 'back': (-1, -0.3, 0.3), 'side': (0.2, -1, 0.15), 'face': (1, 0.25, 0.1)}
for v in a.views.split(','):
    d = Vector(dirs[v]).normalized(); dist = h * (1.2 if v == 'face' else 3.2)
    tgt = ctr + Vector((0, 0, h * 0.33)) if v == 'face' else ctr
    cam.location = tgt + d * dist; cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = f'{a.out}_{v}.png'; bpy.ops.render.render(write_still=True)
