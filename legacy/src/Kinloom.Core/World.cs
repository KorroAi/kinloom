using System;
using System.Collections.Generic;

namespace Kinloom.Core
{
    public sealed class World
    {
        public const int TicksPerHour = 12; // 1 tick = 5 in-game minutes
        public const int TicksPerDay = TicksPerHour * 24;

        private readonly List<Agent> _agents = new List<Agent>();
        private readonly List<Place> _places = new List<Place>();
        private readonly List<Item> _items = new List<Item>();
        private readonly Dictionary<string, Entity> _byId = new Dictionary<string, Entity>();

        public World(PackDefinition pack, int seed)
        {
            Pack = pack;
            Random = new DeterministicRandom(seed);
        }

        public PackDefinition Pack { get; }
        public DeterministicRandom Random { get; }
        public Journal Journal { get; } = new Journal();
        public Tuning Tuning { get; } = new Tuning();
        public QuestBook Quests { get; } = new QuestBook();
        public FightLog Fights { get; } = new FightLog();
        public EventLog Events { get; } = new EventLog();
        public int Tick { get; private set; }
        public int Day => DayOf(Tick);
        public int Hour => Tick % TicksPerDay / TicksPerHour;
        public IReadOnlyList<Agent> Agents => _agents;
        public IReadOnlyList<Place> Places => _places;
        public IReadOnlyList<Item> Items => _items;

        public Agent Add(Agent agent) { Register(agent); _agents.Add(agent); return agent; }
        public Place Add(Place place) { Register(place); _places.Add(place); return place; }
        public Item Add(Item item) { Register(item); _items.Add(item); return item; }

        private void Register(Entity entity)
        {
            if (_byId.ContainsKey(entity.Id)) throw new ArgumentException($"Duplicate id '{entity.Id}'");
            _byId[entity.Id] = entity;
        }

        public Agent? FindAgent(string? id) => Find(id) as Agent;
        public Place? FindPlace(string? id) => Find(id) as Place;
        public Item? FindItem(string? id) => Find(id) as Item;

        private Entity? Find(string? id) => id != null && _byId.TryGetValue(id, out var e) ? e : null;

        public Agent GetAgent(string id) => FindAgent(id) ?? throw new KeyNotFoundException($"Unknown agent '{id}'");

        public string NameOf(string? id) => Find(id)?.Name ?? "?";

        public Agent? NearestWithTag(string tag, Vec2 from, string? excludeId)
        {
            Agent? best = null;
            float bestDistance = float.MaxValue;
            foreach (var agent in _agents)
            {
                if (agent.Id == excludeId || agent.IsPlayer || !agent.Active || !agent.Has(tag)) continue;
                float d = agent.Position.DistanceTo(from);
                if (d < bestDistance) { best = agent; bestDistance = d; }
            }
            return best;
        }

        public int MinuteOfDay => Tick % TicksPerDay * (60 / TicksPerHour);

        public void AdvanceTick() => Tick++;

        /// <summary>With Tuning.Sleep: between 00:00 and 05:00, an agent at home (and not on a story beat) sleeps.</summary>
        public bool IsAsleep(Agent agent)
        {
            if (!Tuning.Sleep || Hour >= 5 || agent.IsPlayer) return false;
            var home = FindPlace(agent.HomePlaceId);
            return home != null && home.Contains(agent.Position) && agent.Intent.Kind == IntentKind.Routine;
        }

        /// <summary>Starts the clock later than midnight of day 1 (only before the first tick).</summary>
        public void StartAt(int tick)
        {
            if (Tick != 0 || tick < 0) throw new InvalidOperationException("The start time can only be set once, before the world runs");
            Tick = tick;
        }

        public static int DayOf(int tick) => tick / TicksPerDay + 1;

        public static string Clock(int tick)
        {
            int minutes = tick % TicksPerDay * (60 / TicksPerHour);
            return $"D{DayOf(tick)} {minutes / 60:00}:{minutes % 60:00}";
        }
    }
}
