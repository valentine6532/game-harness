"""Shared helpers for Nyablo editor scripts (run inside UnrealEditor Python)."""
import os
import unreal

ROOT = 'D:/HarnessPrograming/diablo'
ASSET_TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary


def log(*parts):
    unreal.log('NYABLO ' + ' '.join(str(p) for p in parts))


SKIP_IMPORT = os.environ.get('NYABLO_SKIP_IMPORT') == '1'   # layout/lighting iteration: reuse imported assets


def import_file(path, dest, name=None, skeletal=False, anims=False, skeleton=None, combine=True):
    """Import one FBX/GLB/PNG with explicit options. Returns imported object paths."""
    existing = f'{dest}/{name or os.path.splitext(os.path.basename(path))[0]}'
    if SKIP_IMPORT and EAL.does_asset_exist(existing):
        return [existing]
    task = unreal.AssetImportTask()
    task.filename = path
    task.destination_path = dest
    if name:
        task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.save = True
    if path.lower().endswith('.fbx'):
        opt = unreal.FbxImportUI()
        opt.import_materials = True
        opt.import_textures = True
        opt.import_as_skeletal = skeletal
        opt.import_mesh = True
        opt.import_animations = anims
        opt.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH if skeletal else unreal.FBXImportType.FBXIT_STATIC_MESH
        if skeleton:
            opt.skeleton = skeleton
        if skeletal:
            opt.skeletal_mesh_import_data.import_morph_targets = False
            opt.anim_sequence_import_data.import_bone_tracks = True
        else:
            opt.static_mesh_import_data.combine_meshes = combine
            opt.static_mesh_import_data.generate_lightmap_u_vs = True
            opt.static_mesh_import_data.auto_generate_collision = True
        task.options = opt
    ASSET_TOOLS.import_asset_tasks([task])
    paths = list(task.imported_object_paths)
    log('imported', path, '->', paths)
    return paths


def ensure_dir(path):
    if not EAL.does_directory_exist(path):
        EAL.make_directory(path)


def master_material(path='/Game/Materials/M_TexturedSurface'):
    """BaseColor texture param * Tint, Roughness/Metallic scalars, optional normal off."""
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    pkg, name = path.rsplit('/', 1)
    mat = ASSET_TOOLS.create_asset(name, pkg, unreal.Material, unreal.MaterialFactoryNew())
    tex = MEL.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, -600, 0)
    tex.set_editor_property('parameter_name', 'BaseColor')
    tint = MEL.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -600, 250)
    tint.set_editor_property('parameter_name', 'Tint')
    tint.set_editor_property('default_value', unreal.LinearColor(1, 1, 1, 1))
    mul = MEL.create_material_expression(mat, unreal.MaterialExpressionMultiply, -250, 0)
    MEL.connect_material_expressions(tex, 'RGB', mul, 'A')
    MEL.connect_material_expressions(tint, '', mul, 'B')
    MEL.connect_material_property(mul, '', unreal.MaterialProperty.MP_BASE_COLOR)
    rough = MEL.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -600, 400)
    rough.set_editor_property('parameter_name', 'Roughness')
    rough.set_editor_property('default_value', 0.85)
    MEL.connect_material_property(rough, '', unreal.MaterialProperty.MP_ROUGHNESS)
    metal = MEL.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -600, 500)
    metal.set_editor_property('parameter_name', 'Metallic')
    metal.set_editor_property('default_value', 0.0)
    MEL.connect_material_property(metal, '', unreal.MaterialProperty.MP_METALLIC)
    MEL.recompile_material(mat)
    EAL.save_asset(path)
    return mat


def flat_master(path='/Game/Materials/M_Flat'):
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    pkg, name = path.rsplit('/', 1)
    mat = ASSET_TOOLS.create_asset(name, pkg, unreal.Material, unreal.MaterialFactoryNew())
    col = MEL.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -500, 0)
    col.set_editor_property('parameter_name', 'Color')
    MEL.connect_material_property(col, '', unreal.MaterialProperty.MP_BASE_COLOR)
    for i, (pname, val, prop) in enumerate((('Roughness', 0.6, unreal.MaterialProperty.MP_ROUGHNESS),
                                             ('Metallic', 0.0, unreal.MaterialProperty.MP_METALLIC))):
        s = MEL.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -500, 250 + i * 120)
        s.set_editor_property('parameter_name', pname)
        s.set_editor_property('default_value', val)
        MEL.connect_material_property(s, '', prop)
    MEL.recompile_material(mat)
    EAL.save_asset(path)
    return mat


def material_instance(path, parent, textures=None, scalars=None, vectors=None):
    pkg, name = path.rsplit('/', 1)
    if EAL.does_asset_exist(path):
        mi = EAL.load_asset(path)
    else:
        mi = ASSET_TOOLS.create_asset(name, pkg, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property('parent', parent)
    for k, v in (textures or {}).items():
        MEL.set_material_instance_texture_parameter_value(mi, k, v)
    for k, v in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(mi, k, v)
    for k, v in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(*v))
    MEL.update_material_instance(mi)
    EAL.save_asset(path)
    return mi


def blender_to_ue(loc_m, yaw_deg):
    """Blender FBX default axes (-Z fwd, Y up) import into UE as X->X, Y->-Y, metres->cm."""
    x, y, z = loc_m
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0), unreal.Rotator(0.0, 0.0, -yaw_deg)
