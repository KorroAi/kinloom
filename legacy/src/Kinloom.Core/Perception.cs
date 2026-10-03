namespace Kinloom.Core
{
    /// <summary>Event-based perception: a deed emits one stimulus; only agents in its radius evaluate it.</summary>
    public static class Perception
    {
        public static int Emit(World world, Stimulus s)
        {
            var actor = world.GetAgent(s.ActorId);
            string text = $"{actor.Name} {s.Deed.Kind}"
                + (s.TargetId != null ? $" -> {world.NameOf(s.TargetId)}" : "")
                + (s.ItemId != null ? $" ({world.NameOf(s.ItemId)})" : "");
            int deedEntry = world.Journal.Add(s.Tick, "deed", actor.Id, text, null, s.TargetId);

            foreach (var agent in world.Agents)
            {
                if (agent.Id == s.ActorId || agent.IsPlayer || !agent.Active) continue;
                if (world.IsAsleep(agent) || agent.Has(WorldEvents.HostileTag)) continue; // sleepers and outlaws are not the village's eyes
                if (agent.Position.DistanceTo(s.Position) > s.Deed.Radius) continue;

                int witnessEntry = world.Journal.Add(s.Tick, "witness", agent.Id, $"{agent.Name} saw: {text}", deedEntry);
                var memory = new Memory(s.Deed.Kind, s.ActorId, s.TargetId, s.ItemId, s.Tick, true, null, 1f,
                    s.Deed.Valence, s.Deed.IsCrime, witnessEntry);
                Learning.Learn(world, agent, memory);

                bool victim = s.TargetId == agent.Id;
                agent.Mind.Emotions.AddFear(s.Deed.Threat * (1f - agent.Mind.Personality.Bravery));
                if (s.Deed.Valence < 0f) agent.Mind.Emotions.AddAnger(-s.Deed.Valence * (victim ? 1f : 0.3f));

                Reactions.React(world, agent, s, memory);
            }
            return deedEntry;
        }
    }
}
