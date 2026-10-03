using System.Collections.Generic;
using Kinloom.Core;

namespace Kinloom.Core.Tests
{
    internal static class Helpers
    {
        public static PackDefinition Medieval() => new PackDefinition
        {
            Name = "test-medieval",
            Deeds =
            {
                new DeedDefinition { Kind = "draw_weapon", Valence = -0.3f, Threat = 0.8f, Radius = 12f },
                new DeedDefinition { Kind = "steal", Valence = -0.8f, Threat = 0.1f, Radius = 8f, IsCrime = true, TransfersItem = true },
                new DeedDefinition { Kind = "help", Valence = 0.7f, Threat = 0f, Radius = 6f },
            },
            Barks =
            {
                ["flee"] = new List<string> { "Run!" },
                ["confront"] = new List<string> { "Stop!" },
                ["report"] = new List<string> { "Guard!" },
            }
        };

        public static Agent Npc(World w, string id, float x, float y, float bravery = 0.5f, float sociability = 0.5f, params string[] tags)
            => w.Add(new Agent(id, id, new Vec2(x, y), new Personality(bravery, sociability, 0.5f), false, tags));

        public static Agent Player(World w, float x, float y)
            => w.Add(new Agent("player", "Player", new Vec2(x, y), new Personality(0.5f, 0f, 0.5f), true));

        public static Memory Seen(string kind, string actor, string? target, int tick, float valence, bool crime = false)
            => new Memory(kind, actor, target, null, tick, true, null, 1f, valence, crime, 0);
    }
}
