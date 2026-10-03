using System.Globalization;
using Kinloom.Core;
using Kinloom.Sim;

CultureInfo.DefaultThreadCurrentCulture = CultureInfo.InvariantCulture;
CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;

try
{
    if (args.Length >= 2 && args[0] == "--bench")
    {
        if (!int.TryParse(args[1], out int count) || count < 1) { Console.Error.WriteLine("--bench needs a positive agent count"); return 2; }
        Bench.Run(count, args.Length > 2 ? args[2] : "packs/medieval.pack.json");
        return 0;
    }
    if (args.Length >= 1 && args[0] == "--brain")
    {
        if (args.Length < 4 || !int.TryParse(args[3], out int hours) || hours < 1) { Console.Error.WriteLine("Usage: Kinloom.Sim --brain <scenario.json> <pack.json> <hours> [out-dir]"); return 2; }
        return BrainRun.Run(args[1], args[2], hours, args.Length > 4 ? args[4] : "out/brain");
    }
    if (args.Length < 3)
    {
        Console.Error.WriteLine("Usage: Kinloom.Sim <scenario.json> <pack.json> <out-dir> [--publish <site-dir>]");
        Console.Error.WriteLine("       Kinloom.Sim --bench <agents> [pack.json]");
        Console.Error.WriteLine("       Kinloom.Sim --brain <scenario.json> <pack.json> <hours> [out-dir]   (LLM brain; set DEEPSEEK_API_KEY or KINLOOM_PROVIDER)");
        return 2;
    }
    string? publishDir = null;
    if (args.Length > 3)
    {
        if (args[3] != "--publish" || args.Length < 5) { Console.Error.WriteLine("--publish needs a target folder, e.g. --publish site"); return 2; }
        publishDir = args[4];
    }

    var pack = ScenarioLoader.LoadPack(args[1]);
    var scenario = ScenarioLoader.LoadScenario(args[0]);
    var sim = ScenarioLoader.Build(scenario, pack);
    sim.Run(scenario.Days * World.TicksPerDay);

    string outDir = args[2];
    Directory.CreateDirectory(outDir);
    File.WriteAllLines(Path.Combine(outDir, "journal.txt"), sim.World.Journal.Entries.Select(e =>
        $"#{e.Id} [{World.Clock(e.Tick)}] {e.Kind,-11} {e.Text}" + (e.CauseId.HasValue ? $"  (because #{e.CauseId})" : "")));
    string report = Report.Build(sim);
    File.WriteAllText(Path.Combine(outDir, "report.txt"), report);
    string replay = Path.Combine(outDir, "replay.html");
    ReplayExporter.WriteHtml(sim, Path.Combine(AppContext.BaseDirectory, "viewer", "template.html"), replay);

    Console.WriteLine(report);
    Console.WriteLine($"Replay: {Path.GetFullPath(replay)}");
    if (publishDir != null)
    {
        Directory.CreateDirectory(publishDir);
        string demo = Path.Combine(publishDir, "demo.html");
        File.Copy(replay, demo, overwrite: true);
        Console.WriteLine($"Published: {Path.GetFullPath(demo)}");
    }
    return 0;
}
catch (ScenarioException e)
{
    Console.Error.WriteLine($"Scenario error: {e.Message}");
    return 1;
}
