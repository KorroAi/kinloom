using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Kinloom.Memory;
using Kinloom.Schema;

namespace Kinloom
{
    /// <summary>Save/load of everything Kinloom owns (the game owns the rest): memories, behaviors roles installed,
    /// things Kinloom created, role state. Times are stored relative to the save's clock so ages survive a new game clock.</summary>
    public sealed partial class KinloomSession
    {
        public const int SaveVersion = 1;

        public MemoryStore Memory { get; } = new MemoryStore();

        public string Save()
        {
            lock (_gate)
            {
                var root = new JsonObject
                {
                    ["version"] = SaveVersion,
                    ["time"] = Now,
                    ["memories"] = Memory.ToJson(ShouldPersist),
                    ["behaviors"] = new JsonArray(_behaviors.All.Where(b => b.Source.StartsWith("role:", StringComparison.Ordinal)).Select(b => (JsonNode)new JsonObject
                    {
                        ["source"] = b.Source,
                        ["self"] = b.Self,
                        ["can"] = b.Can == null ? null : new JsonArray(b.Can.Select(c => (JsonNode)JsonValue.Create(c.Source)!).ToArray()),
                        ["behavior"] = b.Decl.Raw.DeepClone(),
                    }).ToArray()),
                    ["created"] = new JsonArray(Things.All.Where(t => t.CreatedBy != null).Select(t => (JsonNode)new JsonObject
                    {
                        ["id"] = t.Id, ["type"] = t.Type.Name, ["name"] = t.Name, ["createdBy"] = t.CreatedBy,
                    }).ToArray()),
                    ["roles"] = SaveRoleState(),
                };
                return root.ToJsonString();
            }
        }

        public void Load(string json)
        {
            JsonObject root;
            try { root = JsonNode.Parse(json) as JsonObject ?? throw new InvalidOperationException("This is not a Kinloom save (expected a JSON object)."); }
            catch (JsonException e) { throw new InvalidOperationException("This is not a Kinloom save: " + e.Message, e); }
            int version = root["version"] is JsonValue v && v.TryGetValue(out int n) ? n : -1;
            if (version != SaveVersion) throw new InvalidOperationException($"Unsupported Kinloom save version {version} (this runtime reads version {SaveVersion}).");

            lock (_gate)
            {
                double shift = Now - (root["time"] is JsonNode t ? JsonNumber.ToDouble(t) : 0);
                Memory.Load(root["memories"] as JsonObject ?? new JsonObject(), shift);

                foreach (var item in root["created"] as JsonArray ?? new JsonArray())
                {
                    if (!(item is JsonObject c)) continue;
                    string id = c["id"]?.GetValue<string>() ?? "", type = c["type"]?.GetValue<string>() ?? "";
                    if (Things.Find(id) != null || !Declared.Types.TryGetValue(type, out var decl)) continue;
                    var thingDecl = ThingDecl.Create(id, type, c["name"]?.GetValue<string>());
                    Declared.Things.Add(thingDecl);
                    Things.Add(thingDecl, decl, c["createdBy"]?.GetValue<string>());
                }

                foreach (var item in root["behaviors"] as JsonArray ?? new JsonArray())
                {
                    if (!(item is JsonObject b)) continue;
                    var errors = new List<ManifestError>();
                    var decl = BehaviorDecl.Parse(b["behavior"], "save.behaviors", errors);
                    if (errors.Count > 0) { Log("error", "load", $"saved behavior skipped: {string.Join("; ", errors)}"); continue; }
                    // A save is a file players can edit: permissions come from the role as declared now, never from the save.
                    string source = b["source"]?.GetValue<string>() ?? "";
                    var can = source.StartsWith("role:", StringComparison.Ordinal) ? RolePermissions(source.Substring(5)) : null;
                    if (can == null) { Log("error", "load", $"saved behavior {decl.Id} skipped: '{source}' is not a declared role"); continue; }
                    var role = Declared.Roles.First(r => r.Id == source.Substring(5));
                    _behaviors.Install(decl, source, can, role.Inhabits);
                }

                LoadRoleState(root["roles"] as JsonObject, shift);
                Log("note", "session", "state loaded");
            }
        }

        /// <summary>Memories are persisted unless they belong to a role declared with persist: false.</summary>
        private bool ShouldPersist(string scope)
        {
            if (!scope.StartsWith("role:", StringComparison.Ordinal)) return true;
            var role = Declared.Roles.FirstOrDefault(r => r.Id == scope.Substring(5));
            return role == null || role.Memory.Persist;
        }
    }
}
