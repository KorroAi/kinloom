using System.Text;
using Kinloom.Core;

namespace Kinloom.Sim;

public static class Report
{
    public static string Build(Simulation sim)
    {
        var w = sim.World;
        var sb = new StringBuilder();
        sb.AppendLine($"Kinloom Phase 0 - {w.Agents.Count} agents, reached {World.Clock(w.Tick)}, {w.Journal.Entries.Count} journal entries");

        if (sim.Player != null)
        {
            var player = sim.Player;
            sb.AppendLine();
            sb.AppendLine($"Opinions of {player.Name}:");
            foreach (var a in w.Agents.Where(a => !a.IsPlayer))
                sb.AppendLine($"  {a.Name,-24} {a.Mind.OpinionOf(player.Id):+0.00;-0.00;0.00}");

            sb.AppendLine();
            sb.AppendLine($"Who knows what {player.Name} did:");
            foreach (var a in w.Agents.Where(a => !a.IsPlayer))
                foreach (var m in a.Mind.Memories.Where(m => m.ActorId == player.Id))
                {
                    string how = m.Firsthand ? "saw it" : $"heard from {w.NameOf(m.SourceId)}";
                    sb.AppendLine($"  {a.Name,-24} {m.Kind,-12} {how,-30} confidence {m.Confidence:0.00}");
                }
        }

        sb.AppendLine();
        sb.AppendLine("Trades:");
        foreach (var t in sim.Trades)
            sb.AppendLine($"  [{World.Clock(t.Tick)}] {w.NameOf(t.TraderId)}: " + (t.Result.Refused ? "refused" : $"{t.Result.Price:0.0}"));

        sb.AppendLine();
        sb.AppendLine("Consequences (with why-chains):");
        foreach (var e in w.Journal.Entries.Where(e => e.Kind == "consequence"))
        {
            sb.AppendLine($"  [{World.Clock(e.Tick)}] {e.Text}");
            foreach (var cause in w.Journal.Why(e.Id).Skip(1))
                sb.AppendLine($"      <- [{World.Clock(cause.Tick)}] {cause.Text}");
        }

        int errors = w.Journal.Entries.Count(e => e.Kind == "error");
        if (errors > 0)
        {
            sb.AppendLine();
            sb.AppendLine($"{errors} script errors - see journal.txt");
        }
        return sb.ToString();
    }
}
