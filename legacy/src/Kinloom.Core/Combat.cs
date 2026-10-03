using System.Collections.Generic;

namespace Kinloom.Core
{
    /// <summary>Damage, death and what witnesses make of it. One fight = one memory: blows within the cooldown only deal damage.</summary>
    public static class Combat
    {
        public const string AttackDeed = "attack";
        public const string KillDeed = "kill";
        /// <summary>Striking a raider (hostile agent) is defence: witnesses approve instead of reporting a crime.</summary>
        public const string DefendDeed = "defend";
        /// <summary>Agents with this tag (children, key characters) can be hurt but never killed.</summary>
        public const string ProtectedTag = "protected";

        /// <summary>Returns the target's health after the blow.</summary>
        public static int Attack(World world, Agent attacker, Agent target, int damage)
        {
            if (!attacker.Active || !target.Active || damage <= 0) return target.Health;
            target.Health = System.Math.Max(target.Has(ProtectedTag) ? 1 : 0, target.Health - damage);
            world.Fights.Hit(world, attacker, target);

            string key = attacker.Id + ">" + target.Id;
            if (!world.Fights.RecentlyReported(key, world.Tick))
            {
                world.Fights.MarkReported(key, world.Tick);
                string deed = target.Has(WorldEvents.HostileTag) ? DefendDeed : AttackDeed;
                if (world.Pack.HasDeed(deed)) Actions.PerformDeed(world, attacker, deed, target.Id, null);
            }
            if (!target.IsAlive)
            {
                world.Journal.Add(world.Tick, "death", target.Id, $"{target.Name} dies, struck down by {attacker.Name}", null, attacker.Id);
                string deed = target.Has(WorldEvents.HostileTag) ? DefendDeed : KillDeed;
                if (world.Pack.HasDeed(deed) && (deed == KillDeed || !world.Fights.RecentlyReported(attacker.Id + ">" + target.Id + "!", world.Tick)))
                {
                    world.Fights.MarkReported(attacker.Id + ">" + target.Id + "!", world.Tick);
                    Actions.PerformDeed(world, attacker, deed, target.Id, null);
                }
                target.Plan = null;
                target.Intent = Intent.Routine();
            }
            return target.Health;
        }
    }

    /// <summary>Per-world fight bookkeeping: report cooldowns and who hurt whom since a tick (used by quests).</summary>
    public sealed class FightLog
    {
        private readonly Dictionary<string, int> _lastReported = new Dictionary<string, int>();
        private readonly List<(int Tick, string Attacker, string Target)> _hits = new List<(int, string, string)>();

        public int CooldownTicks { get; set; } = World.TicksPerHour;

        internal bool RecentlyReported(string key, int tick) =>
            _lastReported.TryGetValue(key, out int last) && tick - last < CooldownTicks;

        internal void MarkReported(string key, int tick) => _lastReported[key] = tick;

        internal void Hit(World world, Agent attacker, Agent target) => _hits.Add((world.Tick, attacker.Id, target.Id));

        public bool HasHurt(string attackerId, string targetId, int sinceTick)
        {
            for (int i = _hits.Count - 1; i >= 0; i--)
            {
                var h = _hits[i];
                if (h.Tick < sinceTick) break;
                if (h.Attacker == attackerId && h.Target == targetId) return true;
            }
            return false;
        }
    }
}
