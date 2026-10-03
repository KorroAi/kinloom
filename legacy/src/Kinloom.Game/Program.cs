using System.Globalization;
using Kinloom.Core;
using Kinloom.Game;
using Kinloom.Sim;

CultureInfo.DefaultThreadCurrentCulture = CultureInfo.InvariantCulture;
CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;

// Usage: Kinloom.Game [--autoplay <screenshot-dir>]
string? autoplayDir = args.Length >= 1 && args[0] == "--autoplay" ? (args.Length >= 2 ? args[1] : "out/game") : null;

string root = FindRoot();
try
{
    var pack = ScenarioLoader.LoadPack(Path.Combine(root, "packs", "medieval.pack.json"));
    var scenario = ScenarioLoader.LoadScenario(Path.Combine(root, "scenarios", "village-game.json"));
    var session = new GameSession(ScenarioLoader.Build(scenario, pack));
    session.WarmUp(8 * World.TicksPerHour); // start the day at 08:00, when the village is awake
    new GameApp(session, autoplayDir).Run();
    return 0;
}
catch (ScenarioException e)
{
    Console.Error.WriteLine($"Scenario error: {e.Message}");
    return 1;
}

static string FindRoot()
{
    foreach (var start in new[] { Directory.GetCurrentDirectory(), AppContext.BaseDirectory })
    {
        var dir = new DirectoryInfo(start);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "packs", "medieval.pack.json"))) dir = dir.Parent;
        if (dir != null) return dir.FullName;
    }
    throw new DirectoryNotFoundException("Run Kinloom.Game from inside the kinloom folder (packs/ and scenarios/ not found).");
}
