// Generic builder for rigs exported by scripts/rig_layers.py (rig.json) and clips baked into
// anim.json. Copy into an Editor folder of the Unity project (requires com.unity.2d.animation).
//
// Batch build:   Unity -batchmode -quit -projectPath <p> -executeMethod LayeredRigBuild.Build  -rigRoot Assets/<Char>
// Batch verify:  Unity -batchmode      -projectPath <p> -executeMethod LayeredRigBuild.Verify -rigRoot Assets/<Char>
// Batch capture: Unity -batchmode      -projectPath <p> -executeMethod LayeredRigBuild.Capture -rigRoot Assets/<Char> -out <dir> [-size 960x1080]
//                writes <dir>/rest.png and <dir>/<clip>/frame-000.png ... at 30 fps (encode with scripts/inspect_tools.py mp4)
//
// <rigRoot>/rig.json, <rigRoot>/anim.json and <rigRoot>/Art/*.png must exist. The build writes
// <rigRoot>/Animation/*, <rigRoot>/<Name>Rig.prefab and <rigRoot>/<Name>Preview.unity.
// Rebuilding replaces those generated assets.
//
// anim.json: { "clips": [ { "name", "length", "loop", "trigger"?, "channels": [
//              { "bone", "prop": rot|posX|posY|scale|alpha, "times", "values", "tangents" } ] } ] }
// rot = local Z degrees added to rest (all joints rest at 0); posX/posY = local offset in units;
// scale/alpha are absolute (for effects). The first looping clip becomes the default state;
// every one-shot clip gets a trigger (its "trigger" or its name) and returns to the default.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEditor.U2D.Sprites;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.U2D;
using UnityEngine.U2D.Animation;

public static class LayeredRigBuild
{
    [Serializable] class RigBone { public string name; public string parent; public float x; public float y; }
    [Serializable] class SkinBone { public string name; public int parent; public float x; public float y; }
    [Serializable] class RigPart
    {
        public string name; public string file; public int width; public int height; public int order;
        public float ppu; public string anchor; public float pivotX; public float pivotY;
        public SkinBone[] bones; public float[] vertices; public int[] indices; public int[] edges; public float[] weights;
    }
    [Serializable] class Effect { public string name; public string file; public string anchor; public float worldSize = .7f; public int order = 100; }
    [Serializable] class Rig { public float refPpu; public float groundY; public float originX; public RigBone[] bones; public RigPart[] parts; public Effect[] effects; }
    [Serializable] class Channel { public string bone; public string prop; public float[] times; public float[] values; public float[] tangents; }
    [Serializable] class Clip { public string name; public float length; public bool loop; public string trigger; public Channel[] channels; }
    [Serializable] class AnimData { public Clip[] clips; }

    static string root;
    static Rig rig;

    static string Arg(string key, string fallback)
    {
        var args = Environment.GetCommandLineArgs();
        int i = Array.IndexOf(args, key);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : fallback;
    }

    static string RigName => Path.GetFileName(root);
    static string PrefabPath => root + "/" + RigName + "Rig.prefab";
    static string ScenePath => root + "/" + RigName + "Preview.unity";

    public static void Build()
    {
        root = Arg("-rigRoot", "Assets/LayeredRig").TrimEnd('/');
        rig = JsonUtility.FromJson<Rig>(File.ReadAllText(root + "/rig.json"));
        var anim = JsonUtility.FromJson<AnimData>(File.ReadAllText(root + "/anim.json"));
        Directory.CreateDirectory(root + "/Animation");
        AssetDatabase.Refresh();
        var sprites = rig.parts.ToDictionary(p => p.name, ImportPart);
        foreach (var fx in rig.effects ?? new Effect[0]) sprites[fx.name] = ImportPlain(fx.file, 256f / fx.worldSize);
        var go = MakeRig(sprites, out var rest);
        var clips = anim.clips.Select(c => MakeClip(c, go, rest)).ToArray();
        go.GetComponent<Animator>().runtimeAnimatorController = MakeController(anim.clips, clips);
        var prefab = PrefabUtility.SaveAsPrefabAsset(go, PrefabPath);
        UnityEngine.Object.DestroyImmediate(go);
        MakeScene(prefab);
        AssetDatabase.SaveAssets();
        Validate(prefab);
        Debug.Log("LAYERED_RIG_BUILD_SUCCESS " + PrefabPath);
    }

    static Vector3 World(float x, float y) => new Vector3((x - rig.originX) / rig.refPpu, (rig.groundY - y) / rig.refPpu, 0);

    static TextureImporter BaseImport(string file, float ppu)
    {
        var importer = (TextureImporter)AssetImporter.GetAtPath(root + "/Art/" + file);
        if (importer == null) throw new Exception("Missing art " + file);
        importer.textureType = TextureImporterType.Sprite;
        importer.spriteImportMode = SpriteImportMode.Single;
        importer.spritePixelsPerUnit = ppu;
        importer.alphaIsTransparency = true;
        // No mipmaps: trilinear mips (Kaiser) made the 0.65x view soft and washed out (Estelle v013).
        // Compare Unity with the Python render only in captures at 1 texel = 1 screen pixel.
        importer.mipmapEnabled = false;
        importer.maxTextureSize = 4096;
        importer.textureCompression = TextureImporterCompression.Uncompressed;
        importer.wrapMode = TextureWrapMode.Clamp;
        var settings = new TextureImporterSettings();
        importer.ReadTextureSettings(settings);
        settings.spriteMeshType = SpriteMeshType.Tight;
        importer.SetTextureSettings(settings);
        importer.SaveAndReimport();
        return importer;
    }

    static Sprite ImportPlain(string file, float ppu)
    {
        BaseImport(file, ppu);
        return AssetDatabase.LoadAssetAtPath<Sprite>(root + "/Art/" + file);
    }

    static Sprite ImportPart(RigPart part)
    {
        var importer = BaseImport(part.file, part.ppu);
        var factories = new SpriteDataProviderFactories(); factories.Init();
        var data = factories.GetSpriteEditorDataProviderFromObject(importer);
        data.InitSpriteEditorDataProvider();
        var rects = data.GetSpriteRects();
        rects[0].name = part.name;
        rects[0].alignment = SpriteAlignment.Custom;
        rects[0].pivot = new Vector2(part.pivotX, part.pivotY);
        data.SetSpriteRects(rects);
        data.Apply();
        if (part.bones != null && part.bones.Length > 0)
        {
            var id = rects[0].spriteID;
            data.GetDataProvider<ISpriteBoneDataProvider>().SetBones(id, part.bones.Select((b, i) => new SpriteBone {
                name = b.name, guid = GUID.Generate().ToString(), parentId = b.parent, position = new Vector3(b.x, b.y, 0),
                rotation = Quaternion.identity, length = 40f, color = Color.HSVToRGB((i * .618f) % 1f, .8f, 1f) }).ToList());
            var w = part.weights;
            var vertices = new Vertex2DMetaData[part.vertices.Length / 2];
            for (int v = 0; v < vertices.Length; v++)
                vertices[v] = new Vertex2DMetaData {
                    position = new Vector2(part.vertices[2 * v], part.vertices[2 * v + 1]),
                    boneWeight = new BoneWeight {
                        boneIndex0 = (int)w[8 * v], weight0 = w[8 * v + 1], boneIndex1 = (int)w[8 * v + 2], weight1 = w[8 * v + 3],
                        boneIndex2 = (int)w[8 * v + 4], weight2 = w[8 * v + 5], boneIndex3 = (int)w[8 * v + 6], weight3 = w[8 * v + 7] } };
            var edges = new Vector2Int[part.edges.Length / 2];
            for (int e = 0; e < edges.Length; e++) edges[e] = new Vector2Int(part.edges[2 * e], part.edges[2 * e + 1]);
            var mesh = data.GetDataProvider<ISpriteMeshDataProvider>();
            mesh.SetVertices(id, vertices);
            mesh.SetIndices(id, part.indices);
            mesh.SetEdges(id, edges);
            data.Apply();
        }
        importer.SaveAndReimport();
        return AssetDatabase.LoadAssetAtPath<Sprite>(root + "/Art/" + part.file) ?? throw new Exception("Import failed " + part.name);
    }

    static GameObject SpriteObject(string name, Sprite sprite, Transform parent, Vector3 world, int order)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);
        go.transform.position = world;
        var r = go.AddComponent<SpriteRenderer>();
        r.sprite = sprite;
        r.sortingOrder = order;
        return go;
    }

    static GameObject MakeRig(Dictionary<string, Sprite> sprites, out Dictionary<Transform, Vector3> rest)
    {
        var go = new GameObject(RigName + "Rig");
        go.AddComponent<SortingGroup>();
        var skeleton = new GameObject("Skeleton").transform; skeleton.SetParent(go.transform, false);
        var layers = new GameObject("Layers").transform; layers.SetParent(go.transform, false);
        var bones = new Dictionary<string, Transform>();
        foreach (var b in rig.bones)
        {
            var t = new GameObject(b.name).transform;
            t.SetParent(string.IsNullOrEmpty(b.parent) ? skeleton : bones[b.parent], false);
            t.position = World(b.x, b.y);
            t.localRotation = Quaternion.identity;          // every joint rests at zero: curves are deltas
            bones[b.name] = t;
        }
        foreach (var part in rig.parts)
        {
            var anchor = bones[part.anchor];
            if (part.bones != null && part.bones.Length > 0)
            {
                var obj = SpriteObject(part.name, sprites[part.name], layers, anchor.position, part.order);
                var skin = obj.AddComponent<SpriteSkin>();
                skin.SetRootBone(bones[part.bones[0].name]);
                var state = skin.SetBoneTransforms(part.bones.Select(b => bones[b.name]).ToArray());
                skin.alwaysUpdate = true;
                skin.forceCpuDeformation = true;      // lets Verify read deformed vertices in batch mode; optional in production
                if (state.ToString() != "Ready") throw new Exception("Sprite Skin not ready: " + part.name + " " + state);
            }
            else SpriteObject(part.name, sprites[part.name], anchor, anchor.position, part.order);
        }
        foreach (var fx in rig.effects ?? new Effect[0])
        {
            var obj = SpriteObject(fx.name, sprites[fx.name], bones[fx.anchor], bones[fx.anchor].position, fx.order);
            obj.transform.localScale = new Vector3(0, 0, 1);
            obj.GetComponent<SpriteRenderer>().color = new Color(1, 1, 1, 0);
        }
        rest = go.GetComponentsInChildren<Transform>(true).ToDictionary(t => t, t => t.localPosition);
        go.AddComponent<Animator>();
        return go;
    }

    static AnimationClip MakeClip(Clip data, GameObject go, Dictionary<Transform, Vector3> rest)
    {
        string path = root + "/Animation/" + data.name + ".anim";
        AssetDatabase.DeleteAsset(path);
        var clip = new AnimationClip { name = data.name, frameRate = 30 };
        var all = go.GetComponentsInChildren<Transform>(true).ToDictionary(t => t.name);
        foreach (var ch in data.channels)
        {
            var target = all.TryGetValue(ch.bone, out var t) ? t : throw new Exception("Unknown transform " + ch.bone);
            string tPath = AnimationUtility.CalculateTransformPath(target, go.transform);
            void Set(Type type, string prop, float offset)
            {
                var keys = ch.times.Select((time, k) => new Keyframe(time, ch.values[k] + offset, ch.tangents[k], ch.tangents[k])).ToArray();
                AnimationUtility.SetEditorCurve(clip, EditorCurveBinding.FloatCurve(tPath, type, prop), new AnimationCurve(keys));
            }
            switch (ch.prop)
            {
                case "rot": Set(typeof(Transform), "localEulerAnglesRaw.z", 0); break;
                case "posX": Set(typeof(Transform), "m_LocalPosition.x", rest[target].x); break;
                case "posY": Set(typeof(Transform), "m_LocalPosition.y", rest[target].y); break;
                case "scale": Set(typeof(Transform), "m_LocalScale.x", 0); Set(typeof(Transform), "m_LocalScale.y", 0); break;
                case "alpha": Set(typeof(SpriteRenderer), "m_Color.a", 0); break;
                default: throw new Exception("Unknown property " + ch.prop);
            }
        }
        var settings = AnimationUtility.GetAnimationClipSettings(clip);
        settings.loopTime = data.loop;
        settings.stopTime = data.length;
        AnimationUtility.SetAnimationClipSettings(clip, settings);
        AssetDatabase.CreateAsset(clip, path);
        return clip;
    }

    static AnimatorController MakeController(Clip[] data, AnimationClip[] clips)
    {
        string path = root + "/Animation/" + RigName + ".controller";
        AssetDatabase.DeleteAsset(path);
        var controller = AnimatorController.CreateAnimatorControllerAtPath(path);
        var machine = controller.layers[0].stateMachine;
        int defaultIndex = Math.Max(0, Array.FindIndex(data, c => c.loop));
        var states = clips.Select(c => { var s = machine.AddState(c.name); s.motion = c; return s; }).ToArray();
        machine.defaultState = states[defaultIndex];
        for (int i = 0; i < data.Length; i++)
        {
            if (data[i].loop) continue;
            string trigger = string.IsNullOrEmpty(data[i].trigger) ? data[i].name : data[i].trigger;
            controller.AddParameter(trigger, AnimatorControllerParameterType.Trigger);
            var enter = machine.AddAnyStateTransition(states[i]);
            enter.hasExitTime = false; enter.duration = .06f; enter.hasFixedDuration = true;
            enter.canTransitionToSelf = false;
            enter.AddCondition(AnimatorConditionMode.If, 0, trigger);
            var exit = states[i].AddTransition(states[defaultIndex]);
            exit.hasExitTime = true; exit.exitTime = .92f; exit.duration = .15f; exit.hasFixedDuration = true;
        }
        return controller;
    }

    static void MakeScene(GameObject prefab)
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);
        var bounds = new Bounds(instance.transform.position, Vector3.zero);
        foreach (var r in instance.GetComponentsInChildren<SpriteRenderer>()) if (r.sprite != null) bounds.Encapsulate(r.bounds);
        var cam = new GameObject("Main Camera") { tag = "MainCamera" }.AddComponent<Camera>();
        cam.orthographic = true;
        cam.orthographicSize = bounds.extents.y * 1.15f;
        cam.transform.position = new Vector3(bounds.center.x, bounds.center.y, -10);
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = new Color(.035f, .045f, .095f);
        EditorSceneManager.SaveScene(scene, ScenePath);
    }

    static void Validate(GameObject prefab)
    {
        var skins = prefab.GetComponentsInChildren<SpriteSkin>(true);
        foreach (var skin in skins)
        {
            var sprite = skin.GetComponent<SpriteRenderer>().sprite;
            if (skin.rootBone == null || skin.boneTransforms.Length != sprite.GetBones().Length || skin.boneTransforms.Any(t => t == null))
                throw new Exception("Unbound Sprite Skin: " + skin.name);
        }
        Debug.Log($"LAYERED_RIG_VALIDATION renderers={prefab.GetComponentsInChildren<SpriteRenderer>(true).Length} skins={skins.Length}");
    }

    // ---------------------------------------------------------------- frame capture (batch)
    static readonly Queue<Action> Jobs = new Queue<Action>();

    public static void Capture()
    {
        root = Arg("-rigRoot", "Assets/LayeredRig").TrimEnd('/');
        string outDir = Path.GetFullPath(Arg("-out", "Captures/" + RigName));
        var size = Arg("-size", "960x1080").Split('x').Select(int.Parse).ToArray();
        EditorSceneManager.OpenScene(ScenePath);
        instance = GameObject.Find(RigName + "Rig");
        var clips = AssetDatabase.FindAssets("t:AnimationClip", new[] { root + "/Animation" })
            .Select(g => AssetDatabase.LoadAssetAtPath<AnimationClip>(AssetDatabase.GUIDToAssetPath(g))).ToArray();
        Directory.CreateDirectory(outDir);
        Jobs.Clear();
        Jobs.Enqueue(() => Shot(Path.Combine(outDir, "rest.png"), size[0], size[1]));
        Jobs.Enqueue(() => AnimationMode.StartAnimationMode());
        foreach (var clip in clips)
        {
            string dir = Path.Combine(outDir, clip.name);
            Directory.CreateDirectory(dir);
            int frames = Mathf.RoundToInt(clip.length * 30) + (clip.isLooping ? 0 : 1);
            for (int f = 0; f < frames; f++)
            {
                var c = clip; int i = f;
                Jobs.Enqueue(() => { AnimationMode.BeginSampling(); AnimationMode.SampleAnimationClip(instance, c, Mathf.Min(i / 30f, c.length)); AnimationMode.EndSampling(); });
                Jobs.Enqueue(() => Shot(Path.Combine(dir, $"frame-{i:D3}.png"), size[0], size[1]));
            }
        }
        Jobs.Enqueue(() => { AnimationMode.StopAnimationMode(); Debug.Log("LAYERED_RIG_CAPTURE_SUCCESS " + outDir); EditorApplication.Exit(0); });
        wait = 30;
        EditorApplication.update += RunJobs;
    }

    static void RunJobs()
    {
        if (--wait > 0) return;
        try { if (Jobs.Count > 0) Jobs.Dequeue()(); wait = 3; }
        catch (Exception e)
        {
            Debug.LogException(e);
            EditorApplication.update -= RunJobs;
            if (AnimationMode.InAnimationMode()) AnimationMode.StopAnimationMode();
            EditorApplication.Exit(1);
        }
    }

    static void Shot(string path, int width, int height)
    {
        var cam = Camera.main;
        var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32) { antiAliasing = 4 };
        var tex = new Texture2D(width, height, TextureFormat.RGB24, false);
        var old = RenderTexture.active;
        try
        {
            cam.targetTexture = rt; cam.Render();
            RenderTexture.active = rt;
            tex.ReadPixels(new Rect(0, 0, width, height), 0, 0); tex.Apply();
            File.WriteAllBytes(path, tex.EncodeToPNG());
        }
        finally
        {
            cam.targetTexture = null; RenderTexture.active = old;
            UnityEngine.Object.DestroyImmediate(tex); UnityEngine.Object.DestroyImmediate(rt);
        }
    }

    // ---------------------------------------------------------------- verification (batch)
    static int wait, stage;
    static GameObject instance;
    static AnimationClip[] verifyClips;
    static readonly Dictionary<SpriteSkin, Vector3[]> Rest = new Dictionary<SpriteSkin, Vector3[]>();

    // Checks that every skin matches its bind pose at rest (delta ~0) and deforms in every clip.
    public static void Verify()
    {
        root = Arg("-rigRoot", "Assets/LayeredRig").TrimEnd('/');
        EditorSceneManager.OpenScene(ScenePath);
        instance = GameObject.Find(RigName + "Rig");
        verifyClips = AssetDatabase.FindAssets("t:AnimationClip", new[] { root + "/Animation" })
            .Select(g => AssetDatabase.LoadAssetAtPath<AnimationClip>(AssetDatabase.GUIDToAssetPath(g))).ToArray();
        wait = 30; stage = 0; Rest.Clear();
        EditorApplication.update += Tick;
    }

    static void Tick()
    {
        if (--wait > 0) return;
        try
        {
            var skins = instance.GetComponentsInChildren<SpriteSkin>();
            if (stage == 0)
            {
                foreach (var skin in skins)
                {
                    var d = skin.GetDeformedVertexPositionData().ToArray();
                    var src = skin.GetComponent<SpriteRenderer>().sprite.vertices;
                    float max = 0;
                    for (int i = 0; i < src.Length; i++) max = Mathf.Max(max, Vector2.Distance(d[i], src[i]));
                    Debug.Log($"LAYERED_RIG_REST {skin.name} vertices={src.Length} maxBindDelta={max:F5}");
                    if (max > .005f) throw new Exception(skin.name + " deforms at rest: bind pose mismatch");
                    Rest[skin] = d;
                }
                AnimationMode.StartAnimationMode();
            }
            else
            {
                var clip = verifyClips[stage - 1];
                foreach (var skin in skins)
                {
                    var d = skin.GetDeformedVertexPositionData().ToArray();
                    int moved = d.Where((p, i) => Vector3.Distance(p, Rest[skin][i]) > .002f).Count();
                    Debug.Log($"LAYERED_RIG_CLIP {clip.name} {skin.name} movedVertices={moved}/{d.Length}");
                }
            }
            if (stage < verifyClips.Length)
            {
                var next = verifyClips[stage];
                AnimationMode.BeginSampling();
                AnimationMode.SampleAnimationClip(instance, next, next.length * .45f);
                AnimationMode.EndSampling();
                stage++; wait = 5;
                return;
            }
            AnimationMode.StopAnimationMode();
            EditorApplication.update -= Tick;
            Debug.Log("LAYERED_RIG_VERIFY_SUCCESS");
            EditorApplication.Exit(0);
        }
        catch (Exception e)
        {
            Debug.LogException(e);
            EditorApplication.update -= Tick;
            if (AnimationMode.InAnimationMode()) AnimationMode.StopAnimationMode();
            EditorApplication.Exit(1);
        }
    }
}
