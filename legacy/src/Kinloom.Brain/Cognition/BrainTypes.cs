using System.Collections.Generic;
using Kinloom.Llm;

namespace Kinloom.Brain
{
    /// <summary>Something the host should show: a thought bubble, a line of dialogue, a new quest... Drained by the game each frame.</summary>
    public sealed class BrainEvent
    {
        public BrainEvent(string kind, string? agentId, string? targetId, string text, int tick, int order = 0, string? emotion = null, int? entryId = null, int? ticket = null)
        {
            Kind = kind;
            AgentId = agentId;
            TargetId = targetId;
            Text = text;
            Tick = tick;
            Order = order;
            Emotion = emotion;
            EntryId = entryId;
            Ticket = ticket;
        }

        /// <summary>thinking | thought | say | plan | quest | event | chronicle | reply | rejected | error</summary>
        public string Kind { get; }
        public string? AgentId { get; }
        public string? TargetId { get; }
        public string Text { get; }
        public int Tick { get; }
        /// <summary>Position of a line inside a conversation (0, 1, 2...): hosts stagger their display.</summary>
        public int Order { get; }
        public string? Emotion { get; }
        public int? EntryId { get; }
        /// <summary>For replies to the player: the ticket returned by Brain.Talk.</summary>
        public int? Ticket { get; }

        public override string ToString() => $"[{Kind}] {AgentId}{(TargetId != null ? "->" + TargetId : "")}: {Text}";
    }

    /// <summary>What a brain remembers about its own mind, beyond the rule-level memories in Core.</summary>
    public sealed class AgentState
    {
        public List<string> Beliefs { get; } = new List<string>();
        public string? Goal { get; set; }
        public string? LastThought { get; set; }
        public int LastPlanDay { get; set; } = -1;
        public int LastReflectTick { get; set; } = -10000;
        public float PendingSalience { get; set; }
        public int LastTriggerEntry { get; set; } = -1;
        public Dictionary<string, List<string>> Talks { get; } = new Dictionary<string, List<string>>();

        internal void AddBelief(string belief, int max)
        {
            Beliefs.Add(belief);
            while (Beliefs.Count > max) Beliefs.RemoveAt(0);
        }

        internal void AddTalk(string partnerId, string line, int max)
        {
            if (!Talks.TryGetValue(partnerId, out var lines)) Talks[partnerId] = lines = new List<string>();
            lines.Add(line);
            while (lines.Count > max) lines.RemoveAt(0);
        }
    }

    public sealed class BrainOptions
    {
        /// <summary>A few sentences about the setting, given to every prompt.</summary>
        public string WorldDescription { get; set; } = "A small village.";
        public int MaxConcurrent { get; set; } = 4;
        /// <summary>Wait for every LLM job inside Update (headless runs, tests, cassette replays). Games leave it off.</summary>
        public bool Lockstep { get; set; }
        public int PlanHour { get; set; } = 5;
        public float ReflectThreshold { get; set; } = 1.5f;
        public int ReflectCooldownTicks { get; set; } = 12;
        public int PairTalkCooldownTicks { get; set; } = 12 * 6;
        /// <summary>Chance per tick that two idle villagers standing together strike up a conversation.</summary>
        public float AmbientTalkChance { get; set; } = 0.04f;
        /// <summary>Cap on spontaneous (not planned) conversations per game hour: the main cost driver.</summary>
        public int MaxAmbientTalksPerHour { get; set; } = 4;
        public int DirectorEveryHours { get; set; } = 6;
        public int DirectorMinGapHours { get; set; } = 8;
        public int ChronicleHour { get; set; } = 23;
        /// <summary>Tokens the brain may spend per game hour before low-priority jobs fall back to rules (0 = unlimited).</summary>
        public int TokensPerGameHour { get; set; }
        public int MaxBeliefs { get; set; } = 8;
        public int MaxMemoriesInPrompt { get; set; } = 7;
        public float MaxOpinionShift { get; set; } = 0.3f;
        public float MaxDialogueOpinionShift { get; set; } = 0.15f;
        public int Seed { get; set; } = 7;
        public string? PlayerName { get; set; }
        /// <summary>Language of everything NPCs say, think and narrate (ids stay as they are).</summary>
        public string Language { get; set; } = "English";
        /// <summary>The integrator's token prices, to show a running cost. Null = no cost is computed (none is invented).</summary>
        public TokenPrices? Prices { get; set; }
    }

    public sealed class BrainStats
    {
        public int Calls { get; internal set; }
        public int Failures { get; internal set; }
        public int Fallbacks { get; internal set; }
        public int Rejections { get; internal set; }
        public long InputTokens { get; internal set; }
        public long OutputTokens { get; internal set; }
        public long TotalLatencyMs { get; internal set; }
        public long CachedInputTokens { get; internal set; }
        /// <summary>Money spent so far in the currency of BrainOptions.Prices; null when no prices are configured.</summary>
        public double? Cost { get; internal set; }
        public Dictionary<string, int> CallsByTask { get; } = new Dictionary<string, int>();

        public double AverageLatencyMs => Calls == 0 ? 0 : (double)TotalLatencyMs / Calls;

        public override string ToString() =>
            $"{Calls} calls ({Failures} failed, {Fallbacks} rule fallbacks, {Rejections} rejected actions), {InputTokens} in ({CachedInputTokens} cached) / {OutputTokens} out tokens, avg {AverageLatencyMs:0} ms"
            + (Cost.HasValue ? $", cost {Cost.Value:0.0000}" : "");
    }
}
