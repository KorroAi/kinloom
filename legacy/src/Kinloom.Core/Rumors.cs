using System.Collections.Generic;

namespace Kinloom.Core
{
    /// <summary>Nearby idle agents share their most salient unknown memory; each retelling loses confidence.</summary>
    public static class Rumors
    {
        public static void Spread(World world)
        {
            var agents = world.Agents;
            float talk = world.Tuning.TalkRadius;
            var grid = BuildGrid(agents, talk);
            var candidates = new List<int>();

            for (int i = 0; i < agents.Count; i++)
            {
                var speaker = agents[i];
                if (speaker.IsPlayer || !speaker.Active || speaker.Intent.Kind != IntentKind.Routine || speaker.Mind.Memories.Count == 0) continue;

                // Only agents in the 3x3 neighbouring cells can be within TalkRadius. Visiting them in index order
                // keeps the exact same random draws as a full scan, so stories are unchanged.
                Neighbours(grid, speaker.Position, talk, candidates);
                foreach (int j in candidates)
                {
                    if (i == j) continue;
                    var listener = agents[j];
                    if (listener.IsPlayer || !listener.Active || listener.Intent.Kind != IntentKind.Routine) continue;
                    if (speaker.Position.DistanceTo(listener.Position) > talk) continue;
                    if (!world.Random.Chance(world.Tuning.RumorBaseChance * speaker.Mind.Personality.Sociability)) continue;

                    var topic = PickTopic(world, speaker, listener);
                    if (topic == null) continue;

                    int entry = world.Journal.Add(world.Tick, "rumor", listener.Id,
                        $"{speaker.Name} tells {listener.Name}: {world.NameOf(topic.ActorId)} {topic.Kind}"
                        + (topic.TargetId != null ? $" -> {world.NameOf(topic.TargetId)}" : ""),
                        topic.EntryId);
                    Learning.Learn(world, listener, topic.Retold(speaker.Id, world.Tuning.RumorConfidenceFactor, entry));
                }
            }
        }

        private static long Cell(float x, float y, float size) =>
            ((long)System.Math.Floor(x / size) << 32) ^ (uint)(int)System.Math.Floor(y / size);

        private static Dictionary<long, List<int>> BuildGrid(IReadOnlyList<Agent> agents, float size)
        {
            var grid = new Dictionary<long, List<int>>();
            for (int i = 0; i < agents.Count; i++)
            {
                long key = Cell(agents[i].Position.X, agents[i].Position.Y, size);
                if (!grid.TryGetValue(key, out var list)) grid[key] = list = new List<int>();
                list.Add(i); // ascending, since i increases
            }
            return grid;
        }

        private static void Neighbours(Dictionary<long, List<int>> grid, Vec2 p, float size, List<int> result)
        {
            result.Clear();
            int cx = (int)System.Math.Floor(p.X / size), cy = (int)System.Math.Floor(p.Y / size);
            for (int dx = -1; dx <= 1; dx++)
                for (int dy = -1; dy <= 1; dy++)
                    if (grid.TryGetValue(((long)(cx + dx) << 32) ^ (uint)(cy + dy), out var list)) result.AddRange(list);
            result.Sort();
        }

        private static Memory? PickTopic(World world, Agent speaker, Agent listener)
        {
            Memory? best = null;
            foreach (var m in speaker.Mind.Memories)
            {
                if (m.Confidence < world.Tuning.MinRumorConfidence) continue;
                if (m.ActorId == listener.Id || listener.Mind.Remembers(m.Key)) continue;
                if (best == null || m.Salience > best.Salience || (m.Salience == best.Salience && m.DeedTick > best.DeedTick))
                    best = m;
            }
            return best;
        }
    }
}
