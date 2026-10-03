using System.Collections.Generic;

namespace Kinloom.Core
{
    public sealed class WorldEvent
    {
        internal WorldEvent(string kind, string? whereId, int startTick, int endTick, string reason, int entryId)
        {
            Kind = kind;
            WhereId = whereId;
            StartTick = startTick;
            EndTick = endTick;
            Reason = reason;
            EntryId = entryId;
        }

        public string Kind { get; }
        /// <summary>Place id (festival, raid, stranger), agent id (illness) or null (storm).</summary>
        public string? WhereId { get; }
        public int StartTick { get; }
        public int EndTick { get; }
        public string Reason { get; }
        public int EntryId { get; }
        public List<string> Participants { get; } = new List<string>();
    }

    /// <summary>Director-level events. A brain (or a rule director) picks them; their effects are rules.</summary>
    public static class WorldEvents
    {
        public const string Festival = "festival";              // where: place. Everyone gathers there.
        public const string Storm = "storm";                    // where: none. Everyone shelters at home.
        public const string BanditRaid = "bandit_raid";         // where: place. Reserve "hostile" agents come to steal.
        public const string StrangerArrives = "stranger_arrives"; // where: place. One reserve non-hostile agent arrives.
        public const string Illness = "illness";                // where: agent. They fall sick and stay home.

        public const string HostileTag = "hostile";
        public const string SickTag = "sick";
        /// <summary>Items that belong to an authored story beat: raids never target them.</summary>
        public const string StoryTag = "story";

        public static readonly string[] All = { Festival, Storm, BanditRaid, StrangerArrives, Illness };

        public static WorldEvent Start(World world, string kind, string? whereId, int durationTicks, string reason, int? causeId) =>
            TryStart(world, kind, whereId, durationTicks, reason, causeId, out var error) ?? throw new System.ArgumentException(error);

        public static WorldEvent? TryStart(World world, string kind, string? whereId, int durationTicks, string reason, int? causeId, out string error)
        {
            error = "";
            if (System.Array.IndexOf(All, kind) < 0) { error = $"unknown event '{kind}' (use {string.Join(", ", All)})"; return null; }
            if (durationTicks < 1) { error = "duration must be at least one tick"; return null; }
            foreach (var active in world.Events.Active)
                if (active.Kind == kind) { error = $"a {kind} is already happening"; return null; }

            Place? place = null;
            Agent? agent = null;
            switch (kind)
            {
                case Festival:
                case BanditRaid:
                case StrangerArrives:
                    place = world.FindPlace(whereId);
                    if (place == null) { error = $"{kind} needs a known place (got '{whereId}')"; return null; }
                    break;
                case Illness:
                    agent = world.FindAgent(whereId);
                    if (agent == null || !agent.Active || agent.IsPlayer) { error = $"illness needs a present villager (got '{whereId}')"; return null; }
                    break;
            }

            var reserve = new List<Agent>();
            if (kind == BanditRaid || kind == StrangerArrives)
            {
                bool hostile = kind == BanditRaid;
                foreach (var a in world.Agents)
                    if (!a.Present && a.IsAlive && a.Has(HostileTag) == hostile) reserve.Add(a);
                if (reserve.Count == 0) { error = hostile ? "no reserve bandits in this world" : "no reserve stranger in this world"; return null; }
                if (!hostile) reserve.RemoveRange(1, reserve.Count - 1);
            }

            string? where = place?.Name ?? agent?.Name;
            int entry = world.Journal.Add(world.Tick, "event", null,
                $"Event: {kind}" + (where != null ? $" at {where}" : "") + (string.IsNullOrEmpty(reason) ? "" : $" — {reason}"), causeId, agent?.Id);
            var ev = new WorldEvent(kind, whereId, world.Tick, world.Tick + durationTicks, reason, entry);

            foreach (var a in reserve)
            {
                a.Present = true;
                ev.Participants.Add(a.Id);
                a.Plan = kind == BanditRaid ? RaidPlan(world, place!) : new Plan($"Arrive at {place!.Name}", 0, new[] { new PlanStep(0, 0, Verbs.Goto, place.Id) }, entry);
                world.Journal.Add(world.Tick, "arrival", a.Id, $"{a.Name} arrives", entry);
            }
            if (agent != null)
            {
                agent.Tags.Add(SickTag);
                agent.Health = System.Math.Max(1, agent.Health - agent.MaxHealth / 2);
                ev.Participants.Add(agent.Id);
            }
            world.Events.Add(ev);
            return ev;
        }

        /// <summary>Raiders go for whatever is owned by the people of the targeted place, nearest first.</summary>
        private static Plan RaidPlan(World world, Place place)
        {
            var steps = new List<PlanStep>();
            foreach (var item in world.Items)
            {
                var owner = world.FindAgent(item.OwnerId);
                if (owner == null || owner.Has(HostileTag) || item.Has(StoryTag)) continue; // story items are for the story
                if (item.Position.DistanceTo(place.Position) > place.Radius * 3f) continue;
                steps.Add(new PlanStep(0, 0, Verbs.Steal, owner.Id, item.Id));
                if (steps.Count == 3) break;
            }
            steps.Add(new PlanStep(0, 0, Verbs.Goto, place.Id));
            return new Plan($"Raid {place.Name}", 0, steps);
        }

        internal static void Update(World world)
        {
            var active = world.Events.Active;
            for (int i = active.Count - 1; i >= 0; i--)
            {
                var ev = active[i];
                if (world.Tick < ev.EndTick) continue;
                world.Events.End(i);
                world.Journal.Add(world.Tick, "event", null, $"Event over: {ev.Kind}", ev.EntryId);
                foreach (var id in ev.Participants)
                {
                    var a = world.FindAgent(id)!;
                    if (ev.Kind == BanditRaid && a.IsAlive)
                    {
                        a.Present = false;
                        a.Plan = null;
                        a.Intent = Intent.Routine();
                        world.Journal.Add(world.Tick, "departure", a.Id, $"{a.Name} slips away", ev.EntryId);
                    }
                    else if (ev.Kind == Illness)
                    {
                        a.Tags.Remove(SickTag);
                        if (a.IsAlive) a.Health = a.MaxHealth;
                    }
                }
            }
        }

        /// <summary>Where an active event sends this agent, if anywhere.</summary>
        internal static Place? Override(World world, Agent agent)
        {
            foreach (var ev in world.Events.Active)
            {
                switch (ev.Kind)
                {
                    case Festival:
                        if (!agent.Has(HostileTag)) return world.FindPlace(ev.WhereId);
                        break;
                    case Storm:
                        if (!agent.Has(HostileTag)) return world.FindPlace(agent.HomePlaceId);
                        break;
                    case Illness:
                        if (ev.WhereId == agent.Id) return world.FindPlace(agent.HomePlaceId);
                        break;
                }
            }
            return null;
        }
    }

    public sealed class EventLog
    {
        private readonly List<WorldEvent> _active = new List<WorldEvent>();
        private readonly List<WorldEvent> _history = new List<WorldEvent>();

        public IReadOnlyList<WorldEvent> Active => _active;
        public IReadOnlyList<WorldEvent> History => _history;

        internal void Add(WorldEvent ev) { _active.Add(ev); _history.Add(ev); }
        internal void End(int index) => _active.RemoveAt(index);
    }
}
