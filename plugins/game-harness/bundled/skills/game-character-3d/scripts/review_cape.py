"""Blender: hero + cape FBX together, textured, orthographic front/left/back/right (rest pose)."""
import sys, math, bpy
from mathutils import Vector
hero_fbx, hero_tex, cape_fbx, cape_tex, out = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
def load(fbx, tex, alpha):
    before = set(sc.objects)
    bpy.ops.import_scene.fbx(filepath=fbx, use_anim=False)
    new = [o for o in sc.objects if o not in before]
    img = bpy.data.images.load(tex)
    for o in new:
        if o.type == 'ARMATURE':
            o.data.pose_position = 'REST'
        if o.type != 'MESH':
            continue
        m = bpy.data.materials.new('m'); m.use_nodes = True; nt = m.node_tree; b = nt.nodes['Principled BSDF']
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = img
        nt.links.new(t.outputs[0], b.inputs['Base Color'])
        if alpha:
            nt.links.new(t.outputs[1], b.inputs['Alpha'])
        b.inputs['Roughness'].default_value = 0.8
        for i in range(len(o.data.materials)):
            o.data.materials[i] = m
        for poly in o.data.polygons:        # hide sim proxies / fur shells in the preview
            if poly.material_index > 0 and not alpha:
                poly.hide = True
        if alpha:
            import bmesh
            bm = bmesh.new(); bm.from_mesh(o.data)
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index == 1], context='FACES')
            bm.to_mesh(o.data); bm.free()
    return [o for o in new if o.type == 'MESH']
hm = load(hero_fbx, hero_tex, False)
for o in hm:      # drop fur shells / sim / tail slots (index >= 1) for a clean silhouette
    import bmesh
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index >= 1 and 'Fur' in (o.data.materials[f.material_index].name if False else 'Fur')], context='FACES')
    bm.to_mesh(o.data); bm.free()
load(cape_fbx, cape_tex, True)
bpy.context.view_layer.update()
ms = [o for o in sc.objects if o.type == 'MESH']
bb = [o.matrix_world @ Vector(c) for o in ms for c in o.bound_box]
lo = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb))); hi = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
ctr = (lo + hi) / 2; h = hi.z - lo.z
sc.render.engine = 'BLENDER_EEVEE'; sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new('W'); w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (0.8, 0.8, 0.8, 1); sc.world = w
sun = bpy.data.objects.new('S', bpy.data.lights.new('S', 'SUN')); sun.data.energy = 2.5; sun.rotation_euler = (math.radians(45), 0, math.radians(-30)); sc.collection.objects.link(sun)
cam = bpy.data.objects.new('C', bpy.data.cameras.new('C')); cam.data.type = 'ORTHO'; sc.collection.objects.link(cam); sc.camera = cam
for v, d in {'front': (1, 0, 0), 'left': (0, 1, 0), 'back': (-1, 0, 0), 'right': (0, -1, 0), 'q': (-0.7, 0.5, 0.6)}.items():
    d = Vector(d).normalized(); cam.location = ctr + d * h * 3; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    cam.data.ortho_scale = h * 1.05; cam.data.clip_end = h * 10
    sc.render.resolution_x, sc.render.resolution_y = 600, 900
    sc.render.filepath = f'{out}_{v}.png'; bpy.ops.render.render(write_still=True)
