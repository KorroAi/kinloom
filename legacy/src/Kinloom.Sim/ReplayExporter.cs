using System.Text.Json;
using Kinloom.Core;

namespace Kinloom.Sim;

public static class ReplayExporter
{
    public const string Marker = "/*__REPLAY_DATA__*/null";

    public static string ToJson(Simulation sim)
    {
        var w = sim.World;
        var data = new
        {
            places = w.Places.Select(p => new { p.Id, p.Name, x = p.Position.X, y = p.Position.Y, p.Radius }),
            agents = w.Agents.Select(a => new { a.Id, a.Name, a.IsPlayer, tags = a.Tags.OrderBy(t => t) }),
            frames = sim.Frames.Select(f => new
            {
                t = f.Tick,
                clock = World.Clock(f.Tick),
                a = f.Agents.Select(x => new object?[] { x.Id, R(x.X), R(x.Y), x.Intent, R(x.Fear), R(x.Anger), R(x.OpinionOfPlayer), x.Bark }),
            }),
            journal = w.Journal.Entries.Select(e => new { e.Id, t = e.Tick, clock = World.Clock(e.Tick), e.Kind, agent = e.AgentId, e.Text, cause = e.CauseId }),
        };
        return JsonSerializer.Serialize(data, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
    }

    public static void WriteHtml(Simulation sim, string templatePath, string outPath)
    {
        if (!File.Exists(templatePath)) throw new ScenarioException($"Viewer template not found: {templatePath}");
        string template = File.ReadAllText(templatePath);
        if (!template.Contains(Marker)) throw new ScenarioException($"Viewer template {templatePath} has no replay marker");
        string json = ToJson(sim).Replace("</", "<\\/"); // a "</script>" inside data would close the tag
        File.WriteAllText(outPath, template.Replace(Marker, json));
    }

    private static float R(float v) => MathF.Round(v, 2);
}
