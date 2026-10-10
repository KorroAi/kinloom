// In a built Unity player (IL2CPP or Mono): runs the C# conformance scenario (Program.Main) at Start, writes what it
// printed to KL_PROBE_OUT (arguments from KL_PROBE_ARGS), then quits with 0 or 1.
using System;
using System.IO;
using UnityEngine;

public class KinloomPlayerProbe : MonoBehaviour
{
    private async void Start()
    {
        var args = (Environment.GetEnvironmentVariable("KL_PROBE_ARGS") ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        var outPath = Environment.GetEnvironmentVariable("KL_PROBE_OUT");
        var sw = new StringWriter();
        var err = new StringWriter();
        Console.SetOut(sw);
        Console.SetError(err);
        int code = 0;
        try
        {
            await Program.Main(args);
#if ENABLE_IL2CPP
            sw.WriteLine("UNITY player: IL2CPP, " + Application.platform);
#else
            sw.WriteLine("UNITY player: Mono, " + Application.platform);
#endif
        }
        catch (Exception e)
        {
            sw.WriteLine("UNITY EXCEPTION " + e);
            code = 1;
        }
        foreach (var line in err.ToString().Split('\n'))
            if (line.Trim().Length > 0) sw.WriteLine("UNITY ERR " + line.TrimEnd('\r'));
        File.WriteAllText(outPath, sw.ToString());
        Application.Quit(code);
    }
}
