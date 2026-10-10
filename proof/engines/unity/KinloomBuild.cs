// Builds a Windows player whose one scene runs the conformance scenario (KinloomPlayerProbe). KL_BUILD_OUT: the .exe;
// KL_BACKEND: il2cpp (default) or mono; KL_STRIPPING: minimal, low, medium or high (managed code stripping).
using System;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class KinloomBuild
{
    public static void Build()
    {
        const string path = "Assets/KinloomConformance/Probe.unity";
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene);
        new GameObject("Probe").AddComponent<KinloomPlayerProbe>();
        EditorSceneManager.SaveScene(scene, path);
        var target = NamedBuildTarget.Standalone;
        bool mono = Environment.GetEnvironmentVariable("KL_BACKEND") == "mono";
        PlayerSettings.SetScriptingBackend(target, mono ? ScriptingImplementation.Mono2x : ScriptingImplementation.IL2CPP);
        var level = Environment.GetEnvironmentVariable("KL_STRIPPING") ?? "low";
        PlayerSettings.SetManagedStrippingLevel(target, level == "high" ? ManagedStrippingLevel.High
            : level == "medium" ? ManagedStrippingLevel.Medium : level == "minimal" ? ManagedStrippingLevel.Minimal : ManagedStrippingLevel.Low);
        var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
        {
            scenes = new[] { path },
            locationPathName = Environment.GetEnvironmentVariable("KL_BUILD_OUT"),
            target = BuildTarget.StandaloneWindows64,
            options = BuildOptions.None,
        });
        Debug.Log("KINLOOM BUILD " + report.summary.result + " " + report.summary.totalSize + " bytes, " + report.summary.totalErrors + " errors");
        EditorApplication.Exit(report.summary.result == BuildResult.Succeeded ? 0 : 1);
    }
}
