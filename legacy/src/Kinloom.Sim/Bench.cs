using System.Diagnostics;
using Kinloom.Core;

namespace Kinloom.Sim;

public static class Bench
{
    public static void Run(int agentCount, string packPath)
    {
        var pack = ScenarioLoader.LoadPack(packPath);
        var world = new World(pack, 7);
        var rng = new DeterministicRandom(7);
        var places = new List<Place>();
        for (int i = 0; i < 10; i++)
            places.Add(world.Add(new Place($"p{i}", $"Place {i}", new Vec2(rng.NextFloat() * 200f, rng.NextFloat() * 200f), 4f)));

        for (int i = 0; i < agentCount; i++)
        {
            var tags = i % 20 == 0 ? new[] { Tags.Authority } : null;
            var agent = new Agent($"a{i}", $"Agent {i}", places[i % 10].Position,
                new Personality(rng.NextFloat(), rng.NextFloat(), rng.NextFloat()), false, tags);
            agent.HomePlaceId = places[i % 10].Id;
            agent.Schedule = new Schedule().Add(8, places[(i + 3) % 10].Id).Add(18, places[(i + 5) % 10].Id).Add(22, places[i % 10].Id);
            world.Add(agent);
        }
        world.Add(new Agent("player", "Player", places[0].Position, new Personality(0.5f, 0f, 0.5f), true));

        string badDeed = pack.Deeds.First(d => d.Valence < 0 && !d.TransfersItem).Kind;
        var script = new List<PlayerCommand>();
        for (int h = 0; h < 24; h += 2)
        {
            script.Add(new PlayerCommand(h * World.TicksPerHour, "goto", places[h / 2 % 10].Id, null, null, null, 0f));
            script.Add(new PlayerCommand(h * World.TicksPerHour + 8, "deed", null, badDeed, null, null, 0f));
        }

        var sim = new Simulation(world, script) { CaptureFrames = false };
        var watch = Stopwatch.StartNew();
        sim.Run(World.TicksPerDay);
        watch.Stop();
        Console.WriteLine($"{agentCount} agents, {World.TicksPerDay} ticks: {watch.Elapsed.TotalMilliseconds:0} ms total, " +
            $"{watch.Elapsed.TotalMilliseconds / World.TicksPerDay:0.000} ms/tick, {world.Journal.Entries.Count} journal entries");
    }
}
