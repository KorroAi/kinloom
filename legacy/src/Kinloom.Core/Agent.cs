using System.Collections.Generic;

namespace Kinloom.Core
{
    public sealed class Agent : Entity
    {
        public Agent(string id, string name, Vec2 position, Personality personality, bool isPlayer = false, IEnumerable<string>? tags = null)
            : base(id, name, position, tags)
        {
            IsPlayer = isPlayer;
            Mind = new Mind(personality);
        }

        public bool IsPlayer { get; }
        public Mind Mind { get; }
        public Profile Profile { get; set; } = new Profile();
        public int MaxHealth { get; set; } = 10;
        public int Health { get; set; } = 10;
        public bool IsAlive => Health > 0;
        public int Gold { get; set; }
        /// <summary>False for reserve agents (bandits, strangers) until an event brings them in, and after they leave.</summary>
        public bool Present { get; set; } = true;
        /// <summary>Alive and in the world: can perceive, act and be seen.</summary>
        public bool Active => Present && IsAlive;
        /// <summary>Today's plan (usually written by a brain). Null means the schedule applies.</summary>
        public Plan? Plan { get; set; }
        /// <summary>Authored story beats: while one is in its window on its day, it beats any other plan (brains cannot overwrite them).</summary>
        public List<Plan> FixedPlans { get; } = new List<Plan>();
        /// <summary>Companion: the agent walks with this one until FollowUntilTick.</summary>
        public string? FollowId { get; set; }
        public int FollowUntilTick { get; set; }
        public Schedule? Schedule { get; set; }
        public string? HomePlaceId { get; set; }
        public Intent Intent { get; set; } = Intent.Routine();
        public Vec2? Destination { get; set; }
        public float Speed { get; set; } = 4f;
        public string? Bark { get; private set; }
        public int BarkUntilTick { get; private set; } = -1;

        public void Say(string? text, int tick)
        {
            if (string.IsNullOrEmpty(text)) return;
            Bark = text;
            BarkUntilTick = tick + 6;
        }

        public string? CurrentBark(int tick) => tick <= BarkUntilTick ? Bark : null;
    }
}
