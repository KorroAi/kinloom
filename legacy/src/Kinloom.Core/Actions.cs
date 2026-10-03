namespace Kinloom.Core
{
    /// <summary>Validated deeds. Invalid input becomes an "error" journal entry: the simulation never crashes on bad data.</summary>
    public static class Actions
    {
        public static int PerformDeed(World world, Agent actor, string deedKind, string? targetId, string? itemId)
        {
            if (!world.Pack.HasDeed(deedKind)) return Error(world, actor, $"Unknown deed '{deedKind}' in pack '{world.Pack.Name}'");
            var deed = world.Pack.Deed(deedKind);
            if (targetId != null && world.FindAgent(targetId) == null) return Error(world, actor, $"Unknown target '{targetId}'");

            Item? item = null;
            if (itemId != null)
            {
                item = world.FindItem(itemId);
                if (item == null) return Error(world, actor, $"Unknown item '{itemId}'");
            }

            if (deed.TransfersItem)
            {
                if (item == null) return Error(world, actor, $"Deed '{deedKind}' needs an item");
                if (item.OwnerId == actor.Id) return Error(world, actor, $"{actor.Name} already owns {item.Name}");
                item.OwnerId = actor.Id;
            }

            return Perception.Emit(world, new Stimulus(deed, actor.Id, targetId, itemId, actor.Position, world.Tick));
        }

        /// <summary>The giver hands over an item they own; witnesses see a "give" deed if the pack has one. Returns the entry, or -1.</summary>
        public static int Give(World world, Agent giver, Agent receiver, string? itemId)
        {
            var item = world.FindItem(itemId);
            if (item == null || item.OwnerId != giver.Id)
            {
                Error(world, giver, $"{giver.Name} does not own {world.NameOf(itemId)}");
                return -1;
            }
            item.OwnerId = receiver.Id;
            if (!world.Pack.HasDeed("give"))
                return world.Journal.Add(world.Tick, "deed", giver.Id, $"{giver.Name} give -> {receiver.Name} ({item.Name})", null, receiver.Id);
            return Perception.Emit(world, new Stimulus(world.Pack.Deed("give"), giver.Id, receiver.Id, item.Id, giver.Position, world.Tick));
        }

        /// <summary>Takes an item nobody owns (herbs in the forest, a dropped purse). Not a crime; nobody reacts. -1 if it is owned.</summary>
        public static int PickUp(World world, Agent agent, string? itemId)
        {
            var item = world.FindItem(itemId);
            if (item == null || item.OwnerId != null) return -1;
            item.OwnerId = agent.Id;
            return world.Journal.Add(world.Tick, "pickup", agent.Id, $"{agent.Name} picks up {item.Name}");
        }

        private static int Error(World world, Agent actor, string message) =>
            world.Journal.Add(world.Tick, "error", actor.Id, message);
    }
}
