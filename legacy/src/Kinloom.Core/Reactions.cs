namespace Kinloom.Core
{
    /// <summary>Utility-based choice of an immediate reaction. Scores are simple and fully logged.</summary>
    public static class Reactions
    {
        public static string React(World world, Agent self, Stimulus s, Memory memory)
        {
            var deed = s.Deed;
            var traits = self.Mind.Personality;
            Agent? authority = null;
            string choice;

            if (deed.Valence >= 0f && deed.Threat <= 0f)
            {
                choice = s.TargetId == self.Id ? "grateful" : "approve";
            }
            else
            {
                bool isAuthority = self.Has(Tags.Authority);
                if (!isAuthority) authority = world.NearestWithTag(Tags.Authority, self.Position, self.Id);
                float fear = self.Mind.Emotions.Fear;
                float scold = 0.2f + traits.Bravery * 0.2f;
                float flee = isAuthority ? -1f : deed.Threat * (1f - traits.Bravery) + fear * 0.5f;
                float confront = isAuthority ? (deed.IsCrime ? 0.6f : 0f) + deed.Threat * 0.5f + traits.Bravery * 0.3f : -1f;
                float report = authority != null && deed.IsCrime ? 0.5f + traits.Bravery * 0.3f - deed.Threat * 0.3f : -1f;

                choice = "scold";
                float best = scold;
                if (flee > best) { choice = "flee"; best = flee; }
                if (confront > best) { choice = "confront"; best = confront; }
                if (report > best) { choice = "report"; }
            }

            float opinion = self.Mind.OpinionOf(s.ActorId);
            string verb = choice == "grateful" ? "is grateful" : choice == "approve" ? "approves" : $"decides to {choice}";
            int entry = world.Journal.Add(world.Tick, "reaction", self.Id,
                System.FormattableString.Invariant($"{self.Name} {verb} (fear {self.Mind.Emotions.Fear:0.00}, bravery {traits.Bravery:0.00}, opinion of {world.NameOf(s.ActorId)} {opinion:+0.00;-0.00;0.00})"),
                memory.EntryId);

            switch (choice)
            {
                case "flee":
                    self.Intent = new Intent(IntentKind.Flee, s.ActorId, memory.Key, world.Tick + world.Tuning.FleeTicks, entry);
                    break;
                case "confront":
                    self.Intent = new Intent(IntentKind.Approach, s.ActorId, memory.Key, world.Tick + world.Tuning.PursuitTicks, entry);
                    break;
                case "report":
                    self.Intent = new Intent(IntentKind.Report, authority!.Id, memory.Key, world.Tick + world.Tuning.PursuitTicks, entry);
                    break;
            }

            self.Say(world.Pack.Bark(choice, world.Random), world.Tick);
            return choice;
        }
    }
}
