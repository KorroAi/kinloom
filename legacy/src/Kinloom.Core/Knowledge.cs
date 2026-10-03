namespace Kinloom.Core
{
    /// <summary>Deliberate sharing of knowledge between agents (brains call this; rumors are the ambient version).</summary>
    public static class Knowledge
    {
        /// <summary>The speaker shares a memory they hold. Returns the journal entry, or -1 if the speaker does not know it.</summary>
        public static int Tell(World world, Agent speaker, Agent listener, string memoryKey, int? causeId)
        {
            var memory = speaker.Mind.Recall(memoryKey);
            if (memory == null) return -1;
            int entry = world.Journal.Add(world.Tick, "tell", speaker.Id,
                $"{speaker.Name} tells {listener.Name}: {Describe(world, memory)}", causeId ?? memory.EntryId, listener.Id);
            Learning.Learn(world, listener, memory.Retold(speaker.Id, world.Tuning.RumorConfidenceFactor, entry));
            return entry;
        }

        /// <summary>The speaker claims a deed that never happened. The listener believes it as hearsay; only the journal knows.
        /// Returns the journal entry, or -1 if the deed kind or the people are unknown.</summary>
        public static int Lie(World world, Agent liar, Agent listener, string deedKind, string actorId, string? targetId, string? itemId, int? causeId)
        {
            if (!world.Pack.HasDeed(deedKind) || world.FindAgent(actorId) == null) return -1;
            if (targetId != null && world.FindAgent(targetId) == null) return -1;
            if (itemId != null && world.FindItem(itemId) == null) return -1;
            var deed = world.Pack.Deed(deedKind);
            int claimedTick = world.Tick > 0 ? world.Tick - 1 : 0;
            int entry = world.Journal.Add(world.Tick, "lie", liar.Id,
                $"{liar.Name} lies to {listener.Name}: {world.NameOf(actorId)} {deedKind}" + (targetId != null ? $" -> {world.NameOf(targetId)}" : ""),
                causeId, listener.Id);
            var memory = new Memory(deedKind, actorId, targetId, itemId, claimedTick, false, liar.Id,
                world.Tuning.RumorConfidenceFactor, deed.Valence, deed.IsCrime, entry, isLie: true);
            Learning.Learn(world, listener, memory);
            return entry;
        }

        public static string Describe(World world, Memory m) =>
            $"{world.NameOf(m.ActorId)} {m.Kind}" + (m.TargetId != null ? $" -> {world.NameOf(m.TargetId)}" : "")
            + (m.ItemId != null ? $" ({world.NameOf(m.ItemId)})" : "");
    }
}
