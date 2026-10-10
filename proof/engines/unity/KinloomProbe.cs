// Runs the C# conformance scenario (Program.Main) inside the Unity editor: Unity's Mono and its main-thread
// SynchronizationContext. Arguments and the output file come from KL_PROBE_ARGS / KL_PROBE_OUT; exits the editor.
using System;
using System.IO;
using System.Threading;
using UnityEditor;

public static class KinloomProbe
{
    public static void Run()
    {
        var args = (Environment.GetEnvironmentVariable("KL_PROBE_ARGS") ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        var outPath = Environment.GetEnvironmentVariable("KL_PROBE_OUT");
        var sw = new StringWriter();
        var err = new StringWriter();
        Console.SetOut(sw);
        Console.SetError(err);
        Go(args, sw, err, outPath, Thread.CurrentThread.ManagedThreadId);
    }

    static async void Go(string[] args, StringWriter sw, StringWriter err, string outPath, int mainThread)
    {
        int code = 0;
        try
        {
            await Program.Main(args);
            var ctx = SynchronizationContext.Current;
            sw.WriteLine("UNITY back on the main thread: " + (Thread.CurrentThread.ManagedThreadId == mainThread ? "yes" : "no")
                         + ", context " + (ctx == null ? "none" : ctx.GetType().Name));
        }
        catch (Exception e)
        {
            sw.WriteLine("UNITY EXCEPTION " + e);
            code = 1;
        }
        foreach (var line in err.ToString().Split('\n'))
            if (line.Trim().Length > 0) sw.WriteLine("UNITY ERR " + line.TrimEnd('\r'));
        File.WriteAllText(outPath, sw.ToString());
        EditorApplication.Exit(code);
    }
}
