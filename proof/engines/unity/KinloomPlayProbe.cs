// The KinloomDialogue component in play mode (batch editor), through a real relay: she speaks first, the reply
// choices come, the player picks one, she answers, the box closes. Writes what happened to KL_PROBE_OUT, then exits.
using System;
using System.Collections.Generic;
using System.IO;
using Kinloom;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class KinloomPlayProbe
{
    static readonly List<string> Log = new List<string>();
    static KinloomDialogue box;
    static double deadline;
    static int step;
    static string outPath;

    public static void Run()
    {
        outPath = Environment.GetEnvironmentVariable("KL_PROBE_OUT");
        EditorSettings.enterPlayModeOptionsEnabled = true;   // statics and the scene stay: no domain reload
        EditorSettings.enterPlayModeOptions = EnterPlayModeOptions.DisableDomainReload | EnterPlayModeOptions.DisableSceneReload;
        EditorSceneManager.NewScene(NewSceneSetup.EmptyScene);
        EditorApplication.playModeStateChanged += Changed;
        deadline = EditorApplication.timeSinceStartup + 120;
        EditorApplication.update += Tick;
        EditorApplication.EnterPlaymode();
    }

    static void Changed(PlayModeStateChange state)
    {
        if (state != PlayModeStateChange.EnteredPlayMode) return;
        Log.Add("play mode: " + Application.isPlaying);
        KinloomDialogue.Client = new KinloomClient("http://127.0.0.1:" + Environment.GetEnvironmentVariable("KL_PROBE_ARGS"));
        var go = new GameObject("Mira");
        go.SetActive(false);
        box = go.AddComponent<KinloomDialogue>();
        box.characterName = "MIRA";
        box.offlineLine = "Busy. Come back later.";
        box.toolsJson = "{\"give\": {\"item\": \"sword\"}}";
        box.typewriter = false;
        box.replyExamples = new[] { "Ask about the sword", "Leave" };
        box.onReply.AddListener(t => Log.Add("reply: " + t));
        box.onAction.AddListener((tool, args) => Log.Add("action: " + tool + " " + args));
        box.onGesture.AddListener(g => Log.Add("gesture: " + g));
        box.onChoices.AddListener(c => Log.Add("choices: " + string.Join(" | ", c)));
        box.onClosed.AddListener(() => Log.Add("closed"));
        go.SetActive(true);        // Start(): declares MIRA and opens the box (openOnStart); she speaks first
        step = 1;
    }

    static int Replies() => Log.FindAll(l => l.StartsWith("reply: ")).Count;

    static void Tick()
    {
        if (EditorApplication.timeSinceStartup > deadline) { Finish("TIMEOUT at step " + step, 1); return; }
        if (step == 1 && box != null && !box.Busy && Replies() >= 1 && box.Choices.Length == 2)
        {
            Log.Add("open: " + box.IsOpen + ", mood: " + box.Mood);
            box.Choose(1);         // "Leave"
            step = 2;
        }
        else if (step == 2 && !box.Busy && Replies() >= 2 && Log.FindAll(l => l.StartsWith("choices: ")).Count >= 2)
        {
            Log.Add("mood: " + box.Mood);
            box.Close();
            Finish("DONE", 0);
        }
    }

    static void Finish(string how, int code)
    {
        EditorApplication.update -= Tick;
        Log.Add(how);
        File.WriteAllLines(outPath, Log);
        EditorApplication.Exit(code);
    }
}
