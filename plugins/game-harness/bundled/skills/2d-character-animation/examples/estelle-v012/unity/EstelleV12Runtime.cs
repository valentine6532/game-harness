using System;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.U2D.Animation;

// Play-mode check for v012: both instances start in Idle, the preview driver triggers Attack,
// skinned sprites deform while attacking, and both return to Idle without console errors.
public static class EstelleV12Runtime
{
    static bool previousEnabled;
    static EnterPlayModeOptions previousOptions;
    static double start;
    static int stage, errors;
    static float maxTipTravel;
    static Vector3 tipRest;
    static string report = "";

    public static void Run()
    {
        EditorSceneManager.OpenScene("Assets/EstelleV12/EstelleV12Directions.unity");
        previousEnabled = EditorSettings.enterPlayModeOptionsEnabled;
        previousOptions = EditorSettings.enterPlayModeOptions;
        EditorSettings.enterPlayModeOptionsEnabled = true;
        EditorSettings.enterPlayModeOptions = EnterPlayModeOptions.DisableDomainReload;
        Application.logMessageReceived += Count;
        start = EditorApplication.timeSinceStartup;
        stage = 0; errors = 0; maxTipTravel = 0;
        EditorApplication.update += Check;
        EditorApplication.isPlaying = true;
    }

    static void Count(string message, string stack, LogType type)
    {
        if (type == LogType.Error || type == LogType.Exception || type == LogType.Assert) errors++;
    }

    static bool All(Animator[] animators, string state) => animators.All(a => a.GetCurrentAnimatorStateInfo(0).IsName(state));

    static void Check()
    {
        double elapsed = EditorApplication.timeSinceStartup - start;
        if (EditorApplication.isPlaying)
        {
            var roots = new[] { GameObject.Find("EstelleV12_FacingRight"), GameObject.Find("EstelleV12_FacingLeft") };
            if (roots.All(r => r != null))
            {
                var animators = roots.Select(r => r.GetComponent<Animator>()).ToArray();
                var tip = roots[0].GetComponentsInChildren<Transform>().First(t => t.name == "StaffTip");
                if (stage == 0 && All(animators, "Idle")) { stage = 1; tipRest = tip.position; report += $"idle@{elapsed:F2} "; }
                else if (stage == 1 && All(animators, "Attack"))
                {
                    maxTipTravel = Mathf.Max(maxTipTravel, Vector3.Distance(tip.position, tipRest));
                    if (animators[0].GetCurrentAnimatorStateInfo(0).normalizedTime > .45f)
                    {
                        bool deformed = roots[0].GetComponentsInChildren<SpriteSkin>().All(s => s.HasCurrentDeformedVertices());
                        report += $"attack@{elapsed:F2} skinsDeforming={deformed} ";
                        stage = deformed ? 2 : 99;
                    }
                }
                else if (stage == 2)
                {
                    maxTipTravel = Mathf.Max(maxTipTravel, Vector3.Distance(tip.position, tipRest));
                    if (All(animators, "Idle")) { stage = 3; report += $"backToIdle@{elapsed:F2} "; }
                }
            }
        }
        bool done = stage == 3 || stage == 99 || elapsed > 20;
        if (!done) return;
        EditorApplication.update -= Check;
        Application.logMessageReceived -= Count;
        EditorSettings.enterPlayModeOptionsEnabled = previousEnabled;
        EditorSettings.enterPlayModeOptions = previousOptions;
        bool ok = stage == 3 && errors == 0 && maxTipTravel > .3f;
        Debug.Log($"ESTELLE_V12_RUNTIME ok={ok} {report}staffTipTravel={maxTipTravel:F3} errors={errors} elapsed={elapsed:F2}");
        EditorApplication.Exit(ok ? 0 : 1);
    }
}
