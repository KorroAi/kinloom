using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Kinloom.Expressions;
using Kinloom.Schema;

namespace Kinloom.Roles
{
    /// <summary>Why a role is thinking now.</summary>
    internal sealed class Trigger
    {
        public Trigger(string reason) { Reason = reason; }
        public string Reason { get; }
        public GameEvent? Event { get; set; }
        public string? AskInput { get; set; }
        public string? From { get; set; }
        public TaskCompletionSource<AskResult>? Reply { get; set; }
        public bool IsAsk => AskInput != null;

        public string Describe() =>
            IsAsk ? $"{From ?? "Someone"} says to you: \"{AskInput}\""
            : Event != null ? $"This just happened: {Event.Describe()}"
            : Reason;
    }

    /// <summary>Everything the runtime tracks for one role.</summary>
    internal sealed class RoleState
    {
        public RoleState(RoleDecl decl, double now)
        {
            Decl = decl;
            Mission = decl.Mission;
            Can = decl.Can.Select(c => Permission.Parse(c)).ToList();
            NextEvery = decl.Wake.Select(w => w.Every.HasValue ? now + w.Every.Value : double.PositiveInfinity).ToArray();
            WhenWasTrue = new bool[decl.Wake.Count];
            When = decl.Wake.Select(w => w.When == null ? null : Expr.Parse(w.When)).ToArray();
            Where = decl.Wake.Select(w => w.Where == null ? null : Expr.Parse(w.Where)).ToArray();
        }

        public RoleDecl Decl { get; }
        public string Id => Decl.Id;
        public string Source => "role:" + Decl.Id;
        public string Mission { get; set; }
        public IReadOnlyList<Permission> Can { get; }
        public double[] NextEvery { get; }
        public bool[] WhenWasTrue { get; }
        public Expr?[] When { get; }
        public Expr?[] Where { get; }

        public bool InFlight { get; set; }
        public Trigger? Pending { get; set; }
        public Queue<Trigger> Asks { get; } = new Queue<Trigger>();
        public double LastCall { get; set; } = double.NegativeInfinity;
        public List<string> RecentRefusals { get; } = new List<string>();
        public string? LastFallbackLine { get; set; }

        public string? MemoryScope => Decl.Memory.Scope switch
        {
            "none" => null,
            "shared" => "shared",
            "thing" => Decl.Inhabits != null ? "thing:" + Decl.Inhabits : Source,
            _ => Source,
        };

        public void AddRefusal(string text)
        {
            RecentRefusals.Add(text);
            if (RecentRefusals.Count > 5) RecentRefusals.RemoveAt(0);
        }
    }
}

namespace Kinloom
{
    /// <summary>The answer to <see cref="KinloomSession.Ask"/>.</summary>
    public sealed class AskResult
    {
        public AskResult(string? reply, IReadOnlyList<Effect> effects, bool usedFallback, string? error = null)
        {
            Reply = reply;
            Effects = effects;
            UsedFallback = usedFallback;
            Error = error;
        }

        /// <summary>What the role said (null when it chose to act silently or cannot speak).</summary>
        public string? Reply { get; }
        /// <summary>Effects the answer produced (already queued for the game).</summary>
        public IReadOnlyList<Effect> Effects { get; }
        public bool UsedFallback { get; }
        public string? Error { get; }
    }
}
