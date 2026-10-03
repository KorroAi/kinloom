using System.Diagnostics;
using Kinloom.Brain;
using Kinloom.Llm;
using Kinloom.Core;

namespace Kinloom.Sim;

/// <summary>Headless run of a world with its brain: the story is printed as it happens (lockstep: the clock waits for the model).</summary>
public static class BrainRun
{
    public static int Run(string scenarioPath, string packPath, int hours, string outDir)
    {
        var pack = ScenarioLoader.LoadPack(packPath);
        var scenario = ScenarioLoader.LoadScenario(scenarioPath);
        var sim = ScenarioLoader.Build(scenario, pack);
        sim.CaptureFrames = false;
        var client = LlmConfig.FromEnvironment();
        Console.WriteLine(client == null ? "No model configured (set DEEPSEEK_API_KEY or KINLOOM_PROVIDER): rules only." : $"Model: {client.Name}");
        string language = Environment.GetEnvironmentVariable("KINLOOM_LANGUAGE") ?? "English";
        if (language.StartsWith("fr", StringComparison.OrdinalIgnoreCase)) pack.UseLanguage("fr");
        var brain = new Brain.Brain(sim, client, new BrainOptions
        {
            WorldDescription = scenario.World ?? "A village.",
            Lockstep = true,
            Language = language,
            Prices = LlmConfig.PricesFromEnvironment(),
        });

        Directory.CreateDirectory(outDir);
        using var log = new StreamWriter(Path.Combine(outDir, "brain-events.txt"));
        var watch = Stopwatch.StartNew();
        int end = sim.World.Tick + hours * World.TicksPerHour;
        while (sim.World.Tick < end)
        {
            sim.Step();
            brain.Update();
            foreach (var e in brain.DrainEvents())
            {
                if (e.Kind == "thinking") continue;
                string line = $"[{World.Clock(e.Tick)}] {e.Kind,-9} {Name(sim, e.AgentId)}{(e.TargetId != null && e.Kind is "say" or "reply" ? " -> " + Name(sim, e.TargetId) : "")}: {e.Text.Replace("\n", " / ")}";
                Console.WriteLine(line);
                log.WriteLine(line);
            }
        }
        File.WriteAllLines(Path.Combine(outDir, "journal.txt"), sim.World.Journal.Entries.Select(e =>
            $"#{e.Id} [{World.Clock(e.Tick)}] {e.Kind,-11} {e.Text}" + (e.CauseId.HasValue ? $"  (because #{e.CauseId})" : "")));
        string stats = $"{hours} game hours in {watch.Elapsed.TotalSeconds:0}s real. Brain: {brain.Stats}. By task: {string.Join(", ", brain.Stats.CallsByTask.Select(kv => kv.Key + "=" + kv.Value))}";
        Console.WriteLine(stats);
        log.WriteLine(stats);
        return 0;
    }

    private static string Name(Simulation sim, string? id) => id == null ? "world" : sim.World.NameOf(id);
}
