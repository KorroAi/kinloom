using System.Collections.Generic;
using Kinloom.Llm;

namespace Kinloom
{
    public sealed class SessionOptions
    {
        /// <summary>Model for the fast tier (tactics, barks, quick decisions). Null = rules and fallbacks only.</summary>
        public ILlmClient? Fast { get; set; }
        /// <summary>Model for the deep tier (plans, stories, generation). Falls back to <see cref="Fast"/> when null.</summary>
        public ILlmClient? Deep { get; set; }
        /// <summary>The developer's prices per million tokens. Null = no cost is computed (none is invented).</summary>
        public TokenPrices? Prices { get; set; }
        /// <summary>Language of everything models write for players.</summary>
        public string Language { get; set; } = "English";
        /// <summary>Global cap on model calls per real minute across all roles and generators.</summary>
        public int MaxCallsPerMinute { get; set; } = 30;
        /// <summary>Global cap on spend per real hour (needs <see cref="Prices"/>).</summary>
        public double? MaxCostPerHour { get; set; }
        /// <summary>Game seconds after which an effect the game never resolved counts as failed.</summary>
        public double EffectTimeout { get; set; } = 10;
        /// <summary>When true, effects only go to things the game has bound (engine adapters bind nodes as they appear).</summary>
        public bool RequireBind { get; set; }
        public int JournalCapacity { get; set; } = 2000;
        public int Seed { get; set; } = 1;
        /// <summary>Real-time clock in seconds, for call and spend budgets (tests replace it). Null = a monotonic stopwatch.</summary>
        public System.Func<double>? Clock { get; set; }
        /// <summary>Folder for the media cache (null = system temp).</summary>
        public string? MediaCache { get; set; }
        /// <summary>Real seconds a fast-tier model call may take before it is abandoned (the role's fallback runs).</summary>
        public double FastTimeout { get; set; } = 20;
        /// <summary>Real seconds a deep-tier model call (plans, generators) may take before it is abandoned.</summary>
        public double DeepTimeout { get; set; } = 60;
    }

    /// <summary>Limits on what roles may queue.</summary>
    public static class RoleLimits
    {
        /// <summary>Questions waiting while a role is already thinking; more are answered by the fallback at once.</summary>
        public const int MaxQueuedAsks = 4;
    }

    /// <summary>Limits on behaviors installed by roles (the game's own behaviors are trusted and unlimited).</summary>
    public static class BehaviorLimits
    {
        /// <summary>Invoke/emit/wake actions a role-installed rule may fire per second, however often its condition flips.</summary>
        public const double MaxEdgeFiresPerSecond = 5;
    }

    /// <summary>Counters for the inspector and cost reports.</summary>
    public sealed class RuntimeStats
    {
        public int Calls { get; internal set; }
        public int Failures { get; internal set; }
        public int Repairs { get; internal set; }
        public int Fallbacks { get; internal set; }
        public int Refusals { get; internal set; }
        public int Effects { get; internal set; }
        public long InputTokens { get; internal set; }
        public long CachedInputTokens { get; internal set; }
        public long OutputTokens { get; internal set; }
        public long LatencyMs { get; internal set; }
        /// <summary>Money spent, in the currency of the declared prices; null without prices.</summary>
        public double? Cost { get; internal set; }
        public Dictionary<string, int> CallsBySource { get; } = new Dictionary<string, int>();

        public override string ToString() =>
            $"{Calls} calls ({Failures} failed, {Repairs} repairs, {Fallbacks} fallbacks, {Refusals} refusals), {Effects} effects, "
            + $"{InputTokens} in ({CachedInputTokens} cached) / {OutputTokens} out tokens" + (Cost.HasValue ? $", cost {Cost.Value:0.0000}" : "");
    }
}
