using System.Text.Json.Nodes;

namespace Kinloom
{
    public enum EffectKind { Set, Invoke, Create, Destroy, Say, Media, Validate }

    /// <summary>Something Kinloom asks the game to do. Already validated by the Arbiter; the game applies it and calls
    /// <see cref="KinloomSession.Resolve"/> with the outcome.</summary>
    public sealed class Effect
    {
        public Effect(EffectKind kind, string thing, string? member, JsonObject? args, string source, string? text = null)
        {
            Kind = kind;
            Thing = thing;
            Member = member;
            Args = args ?? new JsonObject();
            Source = source;
            Text = text;
        }

        /// <summary>Unique per session; pass it back to Resolve.</summary>
        public long Id { get; internal set; }
        public EffectKind Kind { get; }
        /// <summary>Target thing id (for Create: the id the new thing will have).</summary>
        public string Thing { get; }
        /// <summary>Param (Set), function (Invoke), type (Create), media kind (Media), generator (Validate).</summary>
        public string? Member { get; }
        /// <summary>Set: {value}. Invoke: the function args. Create: the creation args. Say: {to?}. Media: {path, format, prompt}. Validate: {value}.</summary>
        public JsonObject Args { get; }
        /// <summary>Who proposed it: <c>role:&lt;id&gt;</c>, <c>behavior:&lt;id&gt;</c>, <c>generator:&lt;id&gt;</c>.</summary>
        public string Source { get; }
        /// <summary>Say: the line to show or speak.</summary>
        public string? Text { get; }
        public double Created { get; internal set; }

        public JsonObject ToJson() => new JsonObject
        {
            ["id"] = Id,
            ["kind"] = Kind.ToString().ToLowerInvariant(),
            ["thing"] = Thing,
            ["member"] = Member,
            ["args"] = Args.DeepClone(),
            ["source"] = Source,
            ["text"] = Text,
            ["time"] = Created,
        };

        public override string ToString() => Kind switch
        {
            EffectKind.Set => $"set {Thing}.{Member} = {Expressions.Value.From(Args["value"])}",
            EffectKind.Invoke => $"{Thing}.{Member}({Args.ToJsonString()})",
            EffectKind.Create => $"create {Member} as {Thing} {Args.ToJsonString()}",
            EffectKind.Destroy => $"destroy {Thing}",
            EffectKind.Say => $"{Thing} says \"{Text}\"",
            EffectKind.Media => $"media {Member} ready for {Thing}",
            _ => $"validate {Member}",
        };
    }

    public enum ResolveStatus { Ok, Failed, Refused }

    /// <summary>What the game reports after applying an effect. Refused means the game's own rules said no.</summary>
    public sealed class EffectResult
    {
        private EffectResult(ResolveStatus status, string? reason, JsonNode? value)
        {
            Status = status;
            Reason = reason;
            Value = value;
        }

        public ResolveStatus Status { get; }
        public string? Reason { get; }
        public JsonNode? Value { get; }

        public static EffectResult Ok(JsonNode? value = null) => new EffectResult(ResolveStatus.Ok, null, value);
        public static EffectResult Failed(string reason) => new EffectResult(ResolveStatus.Failed, reason, null);
        public static EffectResult Refused(string reason) => new EffectResult(ResolveStatus.Refused, reason, null);

        public override string ToString() => Status + (Reason != null ? ": " + Reason : "");
    }

    /// <summary>Applies effects on the game side (used by <see cref="KinloomSession.Pump(double, IEffectHandler)"/>).</summary>
    public interface IEffectHandler
    {
        EffectResult Apply(Effect effect);
    }

    /// <summary>Something that happened in the game.</summary>
    public sealed class GameEvent
    {
        public GameEvent(string type, JsonObject? data = null, string[]? perceivedBy = null, double? time = null, double? importance = null)
        {
            Type = type;
            Data = data ?? new JsonObject();
            PerceivedBy = perceivedBy;
            Time = time ?? double.NaN;
            Importance = importance ?? double.NaN;
        }

        public string Type { get; }
        public JsonObject Data { get; }
        /// <summary>Thing ids that noticed it; null = public knowledge.</summary>
        public string[]? PerceivedBy { get; }
        public double Time { get; internal set; }
        public double Importance { get; internal set; }
        /// <summary>Who raised it inside Kinloom (a behavior), or null when the game did.</summary>
        public string? Source { get; internal set; }

        public string Describe() => $"{Type} {Data.ToJsonString()}";
    }
}
