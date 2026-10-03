namespace Kinloom.Core
{
    /// <summary>NPCs who agreed to walk with someone (usually the player) for a while.</summary>
    public static class Companions
    {
        public static int Follow(World world, Agent agent, Agent leader, int durationTicks, int? cause)
        {
            agent.FollowId = leader.Id;
            agent.FollowUntilTick = world.Tick + durationTicks;
            return world.Journal.Add(world.Tick, "follow", agent.Id, $"{agent.Name} joins {leader.Name}", cause, leader.Id);
        }

        internal static void Update(World world)
        {
            foreach (var a in world.Agents)
            {
                if (a.FollowId == null) continue;
                var leader = world.FindAgent(a.FollowId);
                if (world.Tick < a.FollowUntilTick && a.Active && leader != null && leader.Active) continue;
                world.Journal.Add(world.Tick, "follow", a.Id, $"{a.Name} parts ways with {world.NameOf(a.FollowId)}", null, a.FollowId);
                a.FollowId = null;
            }
        }
    }
}
