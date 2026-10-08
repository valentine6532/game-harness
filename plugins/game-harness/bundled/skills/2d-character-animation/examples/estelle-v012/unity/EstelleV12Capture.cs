using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.U2D.Animation;

// Batch capture and checks for v012. Writes to references/7_validation/v012-* and 8_results/v012.
public static class EstelleV12Capture
{
    const string Scene = "Assets/EstelleV12/EstelleV12Directions.unity";
    static readonly Queue<Action> Steps = new Queue<Action>();
    static readonly Dictionary<string, Vector3[]> Rest = new Dictionary<string, Vector3[]>();
    static readonly List<string> Log = new List<string>();
    static int wait;
    static GameObject right, left;
    static AnimationClip idle, attack;
    static string validation, results;

    public static void Run()
    {
        EditorSceneManager.OpenScene(Scene);
        right = GameObject.Find("EstelleV12_FacingRight");
        left = GameObject.Find("EstelleV12_FacingLeft");
        idle = AssetDatabase.LoadAssetAtPath<AnimationClip>("Assets/EstelleV12/Animation/EstelleIdleV12.anim");
        attack = AssetDatabase.LoadAssetAtPath<AnimationClip>("Assets/EstelleV12/Animation/EstelleAttackV12.anim");
        validation = Path.GetFullPath("../../references/7_validation");
        results = Path.GetFullPath("../../references/8_results/v012");
        foreach (var d in new[] { "v012-idle", "v012-attack", "v012-detail" }) Directory.CreateDirectory(Path.Combine(validation, d));
        Directory.CreateDirectory(results);
        Steps.Clear(); Rest.Clear(); Log.Clear();

        var wide = new Vector3(0, 2.95f, -10);
        var close = new Vector3(3.15f, 2.95f, -10);
        Steps.Enqueue(RestCheck);
        Steps.Enqueue(() => Render(Path.Combine(results, "estelle-v12-idle.png"), 1920, 1080, wide, 3.6f));
        Steps.Enqueue(() => Render(Path.Combine(validation, "v012-rest-closeup.png"), 960, 1080, close, 3.25f));
        Steps.Enqueue(() => { AnimationMode.StartAnimationMode(); Sample(attack, .48f); });
        Steps.Enqueue(() => { Render(Path.Combine(results, "estelle-v12-attack.png"), 1920, 1080, wide, 3.6f); AttackMetrics(); });
        int idleFrames = Mathf.RoundToInt(idle.length * 30);
        for (int i = 0; i < idleFrames; i++)
        {
            int f = i;
            Steps.Enqueue(() => Sample(idle, f / 30f));
            Steps.Enqueue(() => Render(Path.Combine(validation, "v012-idle", $"frame-{f:D3}.png"), 960, 1080, close, 3.25f));
        }
        int attackFrames = Mathf.RoundToInt(attack.length * 30) + 1;
        for (int i = 0; i < attackFrames; i++)
        {
            int f = i;
            Steps.Enqueue(() => Sample(attack, Mathf.Min(f / 30f, attack.length)));
            Steps.Enqueue(() => Render(Path.Combine(validation, "v012-attack", $"frame-{f:D3}.png"), 960, 1080, close, 3.25f));
        }
        foreach (var t in new[] { 0f, .28f, .38f, .48f, .66f, .9f })
        {
            float time = t;
            Steps.Enqueue(() => Sample(attack, time));
            Steps.Enqueue(() => Render(Path.Combine(validation, "v012-detail", $"arms-{Mathf.RoundToInt(time * 100):D3}.png"), 1200, 1200, new Vector3(3.1f, 4.0f, -10), 1.5f));
        }
        Steps.Enqueue(() =>
        {
            AnimationMode.StopAnimationMode();
            File.WriteAllLines(Path.Combine(validation, "v012-capture-metrics.txt"), Log);
            Debug.Log("ESTELLE_V12_CAPTURE_SUCCESS\n" + string.Join("\n", Log));
            Finish(0);
        });
        wait = 30;
        EditorApplication.update += Tick;
    }

    static void Tick()
    {
        if (--wait > 0) return;
        try
        {
            if (Steps.Count == 0) return;
            Steps.Dequeue()();
            wait = 3;
        }
        catch (Exception e)
        {
            Debug.LogException(e);
            Finish(1);
        }
    }

    static void Finish(int code)
    {
        EditorApplication.update -= Tick;
        if (AnimationMode.InAnimationMode()) AnimationMode.StopAnimationMode();
        EditorApplication.Exit(code);
    }

    static void Sample(AnimationClip clip, float time)
    {
        AnimationMode.BeginSampling();
        AnimationMode.SampleAnimationClip(right, clip, time);
        AnimationMode.SampleAnimationClip(left, clip, time);
        AnimationMode.EndSampling();
    }

    // At rest every skinned sprite must match its undeformed mesh (bind pose == transform pose).
    static void RestCheck()
    {
        foreach (var skin in right.GetComponentsInChildren<SpriteSkin>())
        {
            var sprite = skin.GetComponent<SpriteRenderer>().sprite;
            var deformed = skin.GetDeformedVertexPositionData().ToArray();
            var source = sprite.vertices;
            if (deformed.Length != source.Length) throw new Exception("Vertex count mismatch " + skin.name);
            float max = 0;
            for (int i = 0; i < source.Length; i++) max = Mathf.Max(max, Vector2.Distance(deformed[i], source[i]));
            Rest[skin.name] = deformed;
            Log.Add($"rest {skin.name}: vertices={source.Length} maxBindDelta={max:F5}");
            if (max > .005f) throw new Exception($"{skin.name} deforms at rest ({max}). Bind pose mismatch.");
        }
    }

    static void AttackMetrics()
    {
        foreach (var skin in right.GetComponentsInChildren<SpriteSkin>())
        {
            var deformed = skin.GetDeformedVertexPositionData().ToArray();
            var rest = Rest[skin.name];
            int moved = 0; float max = 0;
            for (int i = 0; i < rest.Length; i++)
            {
                float d = Vector3.Distance(deformed[i], rest[i]);
                if (d > .002f) moved++;
                max = Mathf.Max(max, d);
            }
            Log.Add($"attack@0.48 {skin.name}: movedVertices={moved}/{rest.Length} maxLocalDelta={max:F4}");
            if (moved == 0) throw new Exception(skin.name + " did not deform during Attack.");
        }
        var tip = right.GetComponentsInChildren<Transform>().First(t => t.name == "StaffTip");
        var flash = tip.Find("CastFlash");
        Log.Add($"attack@0.48 staffTipLocal={right.transform.InverseTransformPoint(tip.position)} " +
                $"flashScale={flash.localScale.x:F2} flashAlpha={flash.GetComponent<SpriteRenderer>().color.a:F2}");
    }

    static void Render(string path, int width, int height, Vector3 position, float size)
    {
        var camera = Camera.main;
        var oldPosition = camera.transform.position;
        float oldSize = camera.orthographicSize;
        var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32) { antiAliasing = 4 };
        var image = new Texture2D(width, height, TextureFormat.RGB24, false);
        var oldTarget = camera.targetTexture;
        var oldActive = RenderTexture.active;
        try
        {
            camera.transform.position = position;
            camera.orthographicSize = size;
            camera.targetTexture = rt;
            camera.Render();
            RenderTexture.active = rt;
            image.ReadPixels(new Rect(0, 0, width, height), 0, 0);
            image.Apply();
            File.WriteAllBytes(path, image.EncodeToPNG());
        }
        finally
        {
            camera.transform.position = oldPosition;
            camera.orthographicSize = oldSize;
            camera.targetTexture = oldTarget;
            RenderTexture.active = oldActive;
            UnityEngine.Object.DestroyImmediate(image);
            UnityEngine.Object.DestroyImmediate(rt);
        }
    }
}
