using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using Kinloom.Core;

namespace Kinloom.Brain
{
    /// <summary>Short handles ("a1", "b3") for memory keys inside one prompt, mapped back by the arbiter.
    /// A handle only exists for a memory its holder really has: the model cannot cite what the agent does not know.</summary>
    public sealed class MemoryHandles
    {
        private readonly Dictionary<string, (string Holder, string Key)> _map = new Dictionary<string, (string, string)>();

        public string Add(string prefix, string holderId, string key)
        {
            string handle = prefix + (_map.Count(kv => kv.Key.StartsWith(prefix)) + 1).ToString(CultureInfo.InvariantCulture);
            _map[handle] = (holderId, key);
            return handle;
        }

        public bool TryResolve(string? handle, string holderId, out string key)
        {
            key = "";
            if (handle == null || !_map.TryGetValue(handle.Trim(), out var entry) || entry.Holder != holderId) return false;
            key = entry.Key;
            return true;
        }
    }

    /// <summary>Renders what one agent knows — and nothing else — as prompt text.</summary>
    public sealed class PromptBuilder
    {
        private readonly Simulation _sim;
        private readonly BrainOptions _options;

        public PromptBuilder(Simulation sim, BrainOptions options)
        {
            _sim = sim;
            _options = options;
        }

        private World World => _sim.World;

        public string Rules =>
            "You are part of Kinloom, the mind of a character in a living game world. " +
            "Stay in character. You only know what is written below: never invent people, places, items or events that are not listed. " +
            "Refer to people, places and items only by the ids given in [brackets]. Keep spoken lines short (under 25 words), vivid and natural. " +
            "People in this world have no gender: never use gendered pronouns (he/she/him/her, il/elle, lui/elle…) or gendered agreements for anyone — repeat their name or use neutral wording. " +
            $"Write everything people say, think, plan or narrate in {_options.Language}; JSON keys, ids and enum values stay in English. " +
            "Answer with one JSON object that follows the requested schema exactly.";

        public string Setting => "SETTING: " + _options.WorldDescription;

        public string Clock() => $"It is day {World.Day}, {World.Hour:00}:{World.MinuteOfDay % 60:00}.";

        public string Persona(Agent a)
        {
            var p = a.Profile;
            var sb = new StringBuilder();
            sb.Append($"You are {a.Name} [{a.Id}]");
            if (p.Role.Length > 0) sb.Append($", {p.Role}");
            sb.Append(".\n");
            if (p.Bio.Length > 0) sb.Append($"Who you are: {p.Bio}\n");
            if (p.Traits.Length > 0) sb.Append($"Personality: {p.Traits}\n");
            if (p.Style.Length > 0) sb.Append($"How you speak: {p.Style}\n");
            if (p.Goals.Count > 0) sb.Append($"Your goals: {string.Join("; ", p.Goals)}\n");
            if (p.Secrets.Count > 0) sb.Append($"Your secrets (never reveal them lightly): {string.Join("; ", p.Secrets)}\n");
            return sb.ToString();
        }

        public string State(Agent a, AgentState s)
        {
            var sb = new StringBuilder();
            var place = PlaceOf(a);
            sb.Append($"You are at {(place != null ? $"{place.Name} [{place.Id}]" : "the village outskirts")}. ");
            sb.Append($"Health {a.Health}/{a.MaxHealth}. Gold: {a.Gold}. ");
            var owned = World.Items.Where(i => i.OwnerId == a.Id).Select(i => $"{i.Name} [{i.Id}]").ToList();
            sb.Append(owned.Count > 0 ? $"You own: {string.Join(", ", owned)}. " : "You own nothing of note. ");
            sb.Append(Feelings(a));
            sb.Append('\n');
            if (a.Has(WorldEvents.SickTag)) sb.Append("You are sick and weak.\n");
            if (s.Goal != null) sb.Append($"What you want right now: {s.Goal}\n");
            if (s.Beliefs.Count > 0) sb.Append($"Your recent thoughts: {string.Join(" | ", s.Beliefs)}\n");
            if (a.Plan != null && (a.Plan.Day == World.Day || a.Plan.Day == 0))
                sb.Append($"Your plan today: {a.Plan.Intention} ({string.Join("; ", a.Plan.Steps.Select(st => st.ToString()))})\n");
            foreach (var ev in World.Events.Active)
                sb.Append($"Happening now: {ev.Kind.Replace('_', ' ')}{(ev.WhereId != null ? " at " + World.NameOf(ev.WhereId) : "")}{(ev.Reason.Length > 0 ? " — " + ev.Reason : "")}\n");
            return sb.ToString();
        }

        private static string Feelings(Agent a)
        {
            var e = a.Mind.Emotions;
            var parts = new List<string>();
            if (e.Fear > 0.5f) parts.Add("very frightened"); else if (e.Fear > 0.2f) parts.Add("uneasy");
            if (e.Anger > 0.5f) parts.Add("furious"); else if (e.Anger > 0.2f) parts.Add("irritated");
            return parts.Count == 0 ? "You feel calm." : $"You feel {string.Join(" and ", parts)}.";
        }

        public static string OpinionWord(float o) =>
            o <= -0.6f ? "hate" : o <= -0.3f ? "dislike" : o <= -0.1f ? "are wary of" : o < 0.1f ? "feel neutral about" : o < 0.3f ? "like" : o < 0.6f ? "trust" : "love";

        /// <summary>People worth listing for these agents: those they feel strongly about, those in their memories, and the player.
        /// Keeps prompts short (and cheap) without hiding anyone who matters to them.</summary>
        public static HashSet<string> Relevant(params Agent[] selves)
        {
            var ids = new HashSet<string>();
            foreach (var self in selves)
            {
                foreach (var m in self.Mind.Memories)
                {
                    ids.Add(m.ActorId);
                    if (m.TargetId != null) ids.Add(m.TargetId);
                    if (m.SourceId != null) ids.Add(m.SourceId);
                }
                foreach (var other in selves) ids.Add(other.Id);
            }
            return ids;
        }

        /// <summary>Public knowledge: who lives here and what they do. Plus how this agent feels about each.</summary>
        public string People(Agent self, IEnumerable<string>? onlyIds = null)
        {
            var sb = new StringBuilder("PEOPLE (public knowledge):\n");
            var filter = onlyIds == null ? null : new HashSet<string>(onlyIds);
            foreach (var other in World.Agents)
            {
                if (other.Id == self.Id || !other.Present || other.Has("monster")) continue;
                if (filter != null && !filter.Contains(other.Id) && !other.IsPlayer && System.Math.Abs(self.Mind.OpinionOf(other.Id)) < 0.15f) continue;
                string role = other.IsPlayer ? "a traveller new to the valley" : (other.Profile.Role.Length > 0 ? other.Profile.Role : "villager");
                float o = self.Mind.OpinionOf(other.Id);
                sb.Append($"- [{other.Id}] {other.Name}, {role}");
                if (!other.IsAlive) sb.Append(" (dead)");
                sb.Append($". You {OpinionWord(o)} them ({o.ToString("+0.00;-0.00;0.00", CultureInfo.InvariantCulture)}).");
                sb.Append('\n');
            }
            return sb.ToString();
        }

        public string Places()
        {
            return "PLACES: " + string.Join(", ", World.Places.Select(p => $"[{p.Id}] {p.Name}")) + "\n";
        }

        public string Items()
        {
            // Who an item belongs to is common knowledge; who holds it right now is not (only witnesses and hearsay tell).
            var sb = new StringBuilder("THINGS OF NOTE: ");
            sb.Append(string.Join(", ", World.Items.Where(i => i.RightfulOwnerId != null)
                .Select(i => $"[{i.Id}] {i.Name} (belongs to {World.NameOf(i.RightfulOwnerId)})")));
            return sb.Append('\n').ToString();
        }

        /// <summary>This agent's memories only, most salient and recent first, each with a handle.</summary>
        public string Memories(Agent a, MemoryHandles handles, string prefix, string heading)
        {
            var list = a.Mind.Memories
                .OrderByDescending(m => m.Salience + (m.DeedTick > World.Tick - World.TicksPerDay ? 0.5f : 0f))
                .ThenByDescending(m => m.DeedTick)
                .Take(_options.MaxMemoriesInPrompt).ToList();
            if (list.Count == 0) return heading + ": nothing notable.\n";
            var sb = new StringBuilder(heading + ":\n");
            foreach (var m in list)
            {
                string h = handles.Add(prefix, a.Id, m.Key);
                string how = m.Firsthand ? "saw it yourself" : $"heard it from {World.NameOf(m.SourceId)}, {(m.Confidence >= 0.7f ? "fairly sure" : "not sure")}";
                sb.Append($"- ({h}) {World.Clock(m.DeedTick)}: {Knowledge.Describe(World, m)} [{how}]\n");
            }
            return sb.ToString();
        }

        public string Talks(AgentState s, string partnerId)
        {
            if (!s.Talks.TryGetValue(partnerId, out var lines) || lines.Count == 0) return "";
            return "What was said between you before:\n" + string.Join("\n", lines) + "\n";
        }

        public Place? PlaceOf(Agent a)
        {
            Place? best = null;
            float bestD = float.MaxValue;
            foreach (var p in World.Places)
            {
                float d = p.Position.DistanceTo(a.Position);
                if (d <= p.Radius + 2f && d < bestD) { best = p; bestD = d; }
            }
            return best;
        }

        public static string VerbGuide =>
            "VERBS for plan steps: goto/work/rest (target: a place id); talk (target: a person id, note: what about); " +
            "give (target: person id, item: an item you own); steal (item: an item someone else owns, target: its owner); attack (target: person id — only if you are truly enraged or defending yourself).";
    }
}
