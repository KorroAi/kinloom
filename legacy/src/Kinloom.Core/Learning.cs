namespace Kinloom.Core
{
    public static class Learning
    {
        /// <summary>Stores the memory (once) and updates the opinion of the actor. Returns false if already known.</summary>
        public static bool Learn(World world, Agent self, Memory memory)
        {
            if (!self.Mind.AddMemory(memory)) return false;
            float before = self.Mind.OpinionOf(memory.ActorId);
            float weight = memory.TargetId == self.Id ? world.Tuning.VictimWeight : world.Tuning.WitnessWeight;
            self.Mind.ShiftOpinion(memory.ActorId, memory.Valence * memory.Confidence * weight);
            float after = self.Mind.OpinionOf(memory.ActorId);
            if (System.Math.Abs(after - before) > 0.001f)
            {
                int entry = world.Journal.Add(world.Tick, "opinion", self.Id,
                    System.FormattableString.Invariant($"{self.Name}'s opinion of {world.NameOf(memory.ActorId)}: {before:+0.00;-0.00;0.00} -> {after:+0.00;-0.00;0.00}"),
                    memory.EntryId);
                self.Mind.SetOpinionCause(memory.ActorId, entry);
            }
            return true;
        }
    }
}
