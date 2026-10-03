using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Kinloom.Media;
using Kinloom.Schema;

namespace Kinloom.Protocol
{
    /// <summary>JSON shapes shared by the dispatcher (server) and <see cref="RemoteSession"/> (client).</summary>
    public static class Wire
    {
        public static Effect EffectFrom(JsonObject o)
        {
            var kind = (EffectKind)Enum.Parse(typeof(EffectKind), o["kind"]!.GetValue<string>(), ignoreCase: true);
            var e = new Effect(kind, o["thing"]?.GetValue<string>() ?? "", o["member"]?.GetValue<string>(), o["args"]?.DeepClone() as JsonObject,
                o["source"]?.GetValue<string>() ?? "", o["text"]?.GetValue<string>())
            {
                Id = o["id"]!.GetValue<long>(),
                Created = o["time"] is JsonNode t ? JsonNumber.ToDouble(t) : 0,
            };
            return e;
        }

        public static JsonArray Effects(IEnumerable<Effect> effects) => new JsonArray(effects.Select(e => (JsonNode)e.ToJson()).ToArray());

        public static JsonObject Errors(IEnumerable<ManifestError> errors) =>
            new JsonObject { ["errors"] = new JsonArray(errors.Select(e => (JsonNode)new JsonObject { ["path"] = e.Path, ["message"] = e.Message }).ToArray()) };

        public static IReadOnlyList<ManifestError> ErrorsFrom(JsonNode? result) =>
            (result?["errors"] as JsonArray ?? new JsonArray()).OfType<JsonObject>()
                .Select(e => new ManifestError(e["path"]?.GetValue<string>() ?? "", e["message"]?.GetValue<string>() ?? "")).ToList();

        public static JsonObject Ask(AskResult r) => new JsonObject
        {
            ["reply"] = r.Reply, ["usedFallback"] = r.UsedFallback, ["error"] = r.Error, ["effects"] = Effects(r.Effects),
        };

        public static AskResult AskFrom(JsonNode r) => new AskResult(
            r["reply"]?.GetValue<string>(),
            (r["effects"] as JsonArray ?? new JsonArray()).OfType<JsonObject>().Select(EffectFrom).ToList(),
            r["usedFallback"]?.GetValue<bool>() ?? false,
            r["error"]?.GetValue<string>());

        public static JsonObject Generate(GenerateResult r) => new JsonObject
        {
            ["ok"] = r.Ok, ["value"] = r.Value?.DeepClone(), ["usedFallback"] = r.UsedFallback,
            ["errors"] = new JsonArray(r.Errors.Select(e => (JsonNode)JsonValue.Create(e)!).ToArray()),
        };

        public static GenerateResult GenerateFrom(JsonNode r) => new GenerateResult(
            r["ok"]?.GetValue<bool>() ?? false,
            r["value"]?.DeepClone(),
            (r["errors"] as JsonArray ?? new JsonArray()).Select(x => x?.GetValue<string>() ?? "").ToList(),
            r["usedFallback"]?.GetValue<bool>() ?? false);

        public static MediaResult MediaFrom(JsonNode r) =>
            r["ok"]?.GetValue<bool>() == true
                ? MediaResult.Success(r["path"]!.GetValue<string>(), r["format"]?.GetValue<string>(), r["cached"]?.GetValue<bool>() ?? false)
                : MediaResult.Failure(r["error"]?.GetValue<string>() ?? "media failed");

        public static EffectResult ResultFrom(string status, string? reason, JsonNode? value) => status.ToLowerInvariant() switch
        {
            "ok" => EffectResult.Ok(value),
            "refused" => EffectResult.Refused(reason ?? "refused by the game"),
            _ => EffectResult.Failed(reason ?? "failed"),
        };

        public static JsonObject Stats(RuntimeStats s) => new JsonObject
        {
            ["calls"] = s.Calls, ["failures"] = s.Failures, ["repairs"] = s.Repairs, ["fallbacks"] = s.Fallbacks, ["refusals"] = s.Refusals,
            ["effects"] = s.Effects, ["inputTokens"] = s.InputTokens, ["cachedInputTokens"] = s.CachedInputTokens, ["outputTokens"] = s.OutputTokens,
            ["latencyMs"] = s.LatencyMs, ["cost"] = s.Cost,
            ["callsBySource"] = new JsonObject(s.CallsBySource.Select(p => new KeyValuePair<string, JsonNode?>(p.Key, p.Value))),
        };
    }
}
