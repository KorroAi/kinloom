using System.Linq;
using System.Text.Json.Nodes;

namespace Kinloom.Protocol
{
    /// <summary>Read-only views of a session for the inspector and the MCP <c>attach</c> tool.</summary>
    public static class DebugFeed
    {
        public static JsonObject Snapshot(KinloomSession s)
        {
            return new JsonObject
            {
                ["time"] = s.Now,
                ["requireBind"] = s.Options.RequireBind,
                ["things"] = new JsonArray(s.Things.All.Select(t => (JsonNode)new JsonObject
                {
                    ["id"] = t.Id,
                    ["type"] = t.Type.Name,
                    ["name"] = t.Name,
                    ["tags"] = new JsonArray(t.Tags.Select(x => (JsonNode)JsonValue.Create(x)!).ToArray()),
                    ["properties"] = new JsonObject(t.Properties.Select(p => new System.Collections.Generic.KeyValuePair<string, JsonNode?>(p.Key, p.Value?.DeepClone()))),
                    ["params"] = new JsonObject(t.Params.Select(p => new System.Collections.Generic.KeyValuePair<string, JsonNode?>(p.Key, p.Value?.DeepClone()))),
                    ["bound"] = t.Bound,
                    ["createdBy"] = t.CreatedBy,
                }).ToArray()),
                ["roles"] = new JsonArray(s.Declared.Roles.Select(r => (JsonNode)new JsonObject
                {
                    ["id"] = r.Id,
                    ["mission"] = s.MissionOf(r.Id) ?? r.Mission,
                    ["inhabits"] = r.Inhabits,
                    ["tier"] = r.Tier,
                    ["sees"] = new JsonArray(r.Sees.Select(x => (JsonNode)JsonValue.Create(x)!).ToArray()),
                    ["can"] = new JsonArray(r.Can.Select(x => (JsonNode)JsonValue.Create(x)!).ToArray()),
                    ["memories"] = new JsonArray(s.Memory.All("role:" + r.Id).Select(m => (JsonNode)JsonValue.Create(m.Text)!).ToArray()),
                }).ToArray()),
                ["behaviors"] = new JsonArray(s.Behaviors.Select(b => (JsonNode)new JsonObject
                {
                    ["id"] = b.behavior.Id, ["source"] = b.source, ["owner"] = b.owner, ["rules"] = b.behavior.Raw["rules"]?.DeepClone(),
                }).ToArray()),
                ["generators"] = new JsonArray(s.Declared.Generators.Select(g => (JsonNode)JsonValue.Create(g.Id)!).ToArray()),
                ["media"] = new JsonArray(s.Media.Kinds.Select(k => (JsonNode)JsonValue.Create(k)!).ToArray()),
                ["stats"] = Wire.Stats(s.Stats),
                ["journal"] = new JsonArray(s.Journal.Recent(300).Select(j => (JsonNode)j.ToJson()).ToArray()),
            };
        }

        public static string JournalNotification(JournalEntry entry) =>
            new JsonObject { ["jsonrpc"] = "2.0", ["method"] = "journal", ["params"] = entry.ToJson() }.ToJsonString();
    }
}
