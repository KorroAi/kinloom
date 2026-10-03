using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

namespace Kinloom.Schema
{
    /// <summary>A kind of thing: readable properties, writable params, invokable functions, optional creation.</summary>
    public sealed class TypeDecl
    {
        public string Name { get; internal set; } = "";
        public string? Description { get; internal set; }
        public FieldSet Properties { get; internal set; } = FieldSet.Empty;
        public FieldSet Params { get; internal set; } = FieldSet.Empty;
        public IReadOnlyDictionary<string, FunctionDecl> Functions { get; internal set; } = new Dictionary<string, FunctionDecl>();
        public CreatableDecl? Creatable { get; internal set; }
        /// <summary>Engine-specific hints (e.g. <c>{"godot": {"scene": "res://x.tscn"}}</c>); ignored by the runtime.</summary>
        public JsonObject? Engine { get; internal set; }
        /// <summary>Accepts any property/param name (the built-in <c>world</c>).</summary>
        public bool Open { get; internal set; }
        public string Source { get; internal set; } = "";

        internal static TypeDecl Parse(string name, JsonNode? node, string path, List<ManifestError> errors)
        {
            var t = new TypeDecl { Name = name };
            if (node == null) return t;
            if (!(node is JsonObject o)) { errors.Add(new ManifestError(path, "must be an object")); return t; }
            Json.UnknownKeys(o, path, errors, "description", "properties", "params", "functions", "creatable", "engine");
            t.Description = Json.Str(o, "description");
            t.Properties = FieldSet.Parse(o["properties"], path + ".properties", errors);
            t.Params = FieldSet.Parse(o["params"], path + ".params", errors);
            var functions = new Dictionary<string, FunctionDecl>();
            if (o["functions"] is JsonObject fs)
                foreach (var f in fs) functions[f.Key] = FunctionDecl.Parse(f.Value, path + ".functions." + f.Key, errors);
            else if (o.ContainsKey("functions")) errors.Add(new ManifestError(path + ".functions", "must be an object of name → function"));
            t.Functions = functions;
            if (o.ContainsKey("creatable"))
            {
                var c = o["creatable"];
                if (c is JsonValue v && v.TryGetValue(out bool yes)) t.Creatable = yes ? new CreatableDecl() : null;
                else if (c is JsonObject co)
                {
                    Json.UnknownKeys(co, path + ".creatable", errors, "args", "max");
                    var max = Json.Num(co, "max", path + ".creatable", errors);
                    t.Creatable = new CreatableDecl { Args = FieldSet.Parse(co["args"], path + ".creatable.args", errors), Max = max.HasValue ? (int)max.Value : (int?)null };
                }
                else errors.Add(new ManifestError(path + ".creatable", "must be true or an object {args, max}"));
            }
            t.Engine = o["engine"] as JsonObject;
            foreach (var p in t.Params)
                if (t.Properties.Find(p.Name) != null) errors.Add(new ManifestError(path + ".params." + p.Name, $"'{p.Name}' is both a property and a param; a param is already readable"));
            return t;
        }

        /// <summary>A param or property spec by name (params first).</summary>
        public FieldSpec? Member(string name) => Params.Find(name) ?? Properties.Find(name) ?? (Open ? FieldSpec.AnyValue : null);
    }

    public sealed class FunctionDecl
    {
        public string? Description { get; internal set; }
        public FieldSet Args { get; internal set; } = FieldSet.Empty;
        public double Cooldown { get; internal set; }

        internal static FunctionDecl Parse(JsonNode? node, string path, List<ManifestError> errors)
        {
            var f = new FunctionDecl();
            if (node == null) return f;
            if (!(node is JsonObject o)) { errors.Add(new ManifestError(path, "must be an object {description, args, cooldown}")); return f; }
            Json.UnknownKeys(o, path, errors, "description", "args", "cooldown");
            f.Description = Json.Str(o, "description");
            f.Args = FieldSet.Parse(o["args"], path + ".args", errors);
            f.Cooldown = Json.Num(o, "cooldown", path, errors) ?? 0;
            return f;
        }
    }

    public sealed class CreatableDecl
    {
        public FieldSet Args { get; internal set; } = FieldSet.Empty;
        /// <summary>Maximum number of live instances Kinloom may have created at once (null = no limit).</summary>
        public int? Max { get; internal set; }
    }

    public sealed class ThingDecl
    {
        public string Id { get; internal set; } = "";
        public string Type { get; internal set; } = "";
        public string? Name { get; internal set; }
        public string? Description { get; internal set; }
        public IReadOnlyList<string> Tags { get; internal set; } = Array.Empty<string>();
        public string Source { get; internal set; } = "";

        public static ThingDecl Create(string id, string type, string? name = null, IEnumerable<string>? tags = null) =>
            new ThingDecl { Id = id, Type = type, Name = name, Tags = tags?.ToArray() ?? Array.Empty<string>() };

        internal static ThingDecl Parse(JsonNode? node, string path, List<ManifestError> errors)
        {
            var t = new ThingDecl();
            if (!(node is JsonObject o)) { errors.Add(new ManifestError(path, "must be an object {id, type, name}")); return t; }
            Json.UnknownKeys(o, path, errors, "id", "type", "name", "description", "tags");
            t.Id = Json.Str(o, "id") ?? "";
            t.Type = Json.Str(o, "type") ?? "";
            t.Name = Json.Str(o, "name");
            t.Description = Json.Str(o, "description");
            t.Tags = Json.Strings(o, "tags", path, errors);
            if (t.Id.Length == 0) errors.Add(new ManifestError(path + ".id", "is required"));
            if (t.Type.Length == 0) errors.Add(new ManifestError(path + ".type", "is required"));
            return t;
        }
    }

    public sealed class EventDecl
    {
        public string Type { get; internal set; } = "";
        public string? Description { get; internal set; }
        public double Importance { get; internal set; } = 0.5;
    }

    public sealed class WakeDecl
    {
        /// <summary><c>event:&lt;type&gt;</c> or <c>ask</c>.</summary>
        public string? On { get; internal set; }
        public double? Every { get; internal set; }
        public string? When { get; internal set; }
        /// <summary>Extra condition for event wakes, with <c>event</c> in scope.</summary>
        public string? Where { get; internal set; }
    }

    public sealed class MemoryDecl
    {
        public string Scope { get; internal set; } = "role";
        public bool Persist { get; internal set; } = true;
        public int Max { get; internal set; } = 50;
    }

    public sealed class BudgetDecl
    {
        public int? CallsPerMinute { get; internal set; }
    }

    public sealed class FallbackDecl
    {
        public string? Behavior { get; internal set; }
        public IReadOnlyList<string> Say { get; internal set; } = Array.Empty<string>();
    }

    /// <summary>An AI with a mission. Inhabits a thing, governs several, or serves on demand.</summary>
    public sealed class RoleDecl
    {
        public string Id { get; internal set; } = "";
        public string Mission { get; internal set; } = "";
        public string? Inhabits { get; internal set; }
        public IReadOnlyList<string> Sees { get; internal set; } = Array.Empty<string>();
        public IReadOnlyList<string> Can { get; internal set; } = Array.Empty<string>();
        public IReadOnlyList<WakeDecl> Wake { get; internal set; } = Array.Empty<WakeDecl>();
        public string Tier { get; internal set; } = "fast";
        public MemoryDecl Memory { get; internal set; } = new MemoryDecl();
        public BudgetDecl Budget { get; internal set; } = new BudgetDecl();
        public FallbackDecl? Fallback { get; internal set; }
        /// <summary>Minimum game seconds between two model calls of this role.</summary>
        public double MinInterval { get; internal set; }
        public string Source { get; internal set; } = "";

        internal static RoleDecl Parse(JsonNode? node, string path, List<ManifestError> errors)
        {
            var r = new RoleDecl();
            if (!(node is JsonObject o)) { errors.Add(new ManifestError(path, "must be an object")); return r; }
            Json.UnknownKeys(o, path, errors, "id", "mission", "inhabits", "sees", "can", "wake", "tier", "memory", "budget", "fallback", "minInterval");
            r.Id = Json.Str(o, "id") ?? "";
            r.Mission = Json.Str(o, "mission") ?? "";
            r.Inhabits = Json.Str(o, "inhabits");
            r.Sees = Json.Strings(o, "sees", path, errors);
            r.Can = Json.Strings(o, "can", path, errors);
            r.Tier = Json.Str(o, "tier") ?? "fast";
            r.MinInterval = Json.Num(o, "minInterval", path, errors) ?? 0;
            if (r.Id.Length == 0) errors.Add(new ManifestError(path + ".id", "is required"));
            if (r.Mission.Length == 0) errors.Add(new ManifestError(path + ".mission", "is required: describe what this AI is and wants"));
            if (r.Tier != "fast" && r.Tier != "deep") errors.Add(new ManifestError(path + ".tier", "must be \"fast\" or \"deep\""));

            var wakes = new List<WakeDecl>();
            if (o["wake"] is JsonArray wa)
                for (int i = 0; i < wa.Count; i++)
                {
                    string wp = $"{path}.wake[{i}]";
                    if (!(wa[i] is JsonObject w)) { errors.Add(new ManifestError(wp, "must be an object like {\"on\":\"event:hit\"}, {\"every\":10} or {\"when\":\"expr\"}")); continue; }
                    Json.UnknownKeys(w, wp, errors, "on", "every", "when", "where");
                    var wake = new WakeDecl { On = Json.Str(w, "on"), Every = Json.Num(w, "every", wp, errors), When = Json.Str(w, "when"), Where = Json.Str(w, "where") };
                    int triggers = (wake.On != null ? 1 : 0) + (wake.Every.HasValue ? 1 : 0) + (wake.When != null ? 1 : 0);
                    if (triggers != 1) errors.Add(new ManifestError(wp, "needs exactly one of on, every, when"));
                    if (wake.On != null && wake.On != "ask" && !wake.On.StartsWith("event:", StringComparison.Ordinal))
                        errors.Add(new ManifestError(wp + ".on", "must be \"event:<type>\" or \"ask\""));
                    if (wake.Every.HasValue && wake.Every <= 0) errors.Add(new ManifestError(wp + ".every", "must be > 0 seconds"));
                    if (wake.Where != null && (wake.On == null || wake.On == "ask")) errors.Add(new ManifestError(wp + ".where", "only applies to event wakes"));
                    wakes.Add(wake);
                }
            else if (o.ContainsKey("wake")) errors.Add(new ManifestError(path + ".wake", "must be a list"));
            r.Wake = wakes;

            if (o["memory"] is JsonObject m)
            {
                Json.UnknownKeys(m, path + ".memory", errors, "scope", "persist", "max");
                r.Memory = new MemoryDecl
                {
                    Scope = Json.Str(m, "scope") ?? "role",
                    Persist = Json.Bool(m, "persist", path + ".memory", errors) ?? true,
                    Max = (int)(Json.Num(m, "max", path + ".memory", errors) ?? 50),
                };
                if (!new[] { "role", "thing", "shared", "none" }.Contains(r.Memory.Scope))
                    errors.Add(new ManifestError(path + ".memory.scope", "must be role, thing, shared or none"));
                if (r.Memory.Scope == "thing" && r.Inhabits == null) errors.Add(new ManifestError(path + ".memory.scope", "\"thing\" memory needs the role to inhabit a thing"));
            }
            if (o["budget"] is JsonObject b)
            {
                Json.UnknownKeys(b, path + ".budget", errors, "callsPerMinute");
                var cpm = Json.Num(b, "callsPerMinute", path + ".budget", errors);
                r.Budget = new BudgetDecl { CallsPerMinute = cpm.HasValue ? (int)cpm.Value : (int?)null };
            }
            if (o["fallback"] is JsonObject fb)
            {
                Json.UnknownKeys(fb, path + ".fallback", errors, "behavior", "say");
                r.Fallback = new FallbackDecl { Behavior = Json.Str(fb, "behavior"), Say = Json.Strings(fb, "say", path + ".fallback", errors) };
            }
            return r;
        }
    }

    public sealed class ActionDecl
    {
        /// <summary><c>target.param</c> to write, with <see cref="To"/> as an expression.</summary>
        public string? Set { get; internal set; }
        public string? To { get; internal set; }
        /// <summary><c>target.function</c> to call, with <see cref="Args"/> as expressions.</summary>
        public string? Invoke { get; internal set; }
        public IReadOnlyDictionary<string, string> Args { get; internal set; } = new Dictionary<string, string>();
        /// <summary>Event type to raise, with <see cref="Data"/> as expressions.</summary>
        public string? Emit { get; internal set; }
        public IReadOnlyDictionary<string, string> Data { get; internal set; } = new Dictionary<string, string>();
        /// <summary>Role id to wake.</summary>
        public string? Wake { get; internal set; }
    }

    public sealed class RuleDecl
    {
        public string When { get; internal set; } = "true";
        public IReadOnlyList<ActionDecl> Do { get; internal set; } = Array.Empty<ActionDecl>();
        public double Cooldown { get; internal set; }
    }

    /// <summary>Instant-tier rules evaluated locally every pump, without any model call.</summary>
    public sealed class BehaviorDecl
    {
        public string Id { get; internal set; } = "";
        /// <summary>Thing id that <c>self</c> refers to.</summary>
        public string? Owner { get; internal set; }
        public IReadOnlyList<RuleDecl> Rules { get; internal set; } = Array.Empty<RuleDecl>();
        public JsonObject Raw { get; internal set; } = new JsonObject();
        public string Source { get; internal set; } = "";

        public static BehaviorDecl Parse(JsonNode? node, string path, List<ManifestError> errors)
        {
            var b = new BehaviorDecl();
            if (!(node is JsonObject o)) { errors.Add(new ManifestError(path, "must be an object {id, owner, rules}")); return b; }
            b.Raw = (JsonObject)o.DeepClone();
            Json.UnknownKeys(o, path, errors, "id", "owner", "rules");
            b.Id = Json.Str(o, "id") ?? "";
            b.Owner = Json.Str(o, "owner");
            if (b.Id.Length == 0) errors.Add(new ManifestError(path + ".id", "is required"));
            var rules = new List<RuleDecl>();
            if (o["rules"] is JsonArray ra)
                for (int i = 0; i < ra.Count; i++)
                {
                    string rp = $"{path}.rules[{i}]";
                    if (!(ra[i] is JsonObject ro)) { errors.Add(new ManifestError(rp, "must be an object {when, do, cooldown}")); continue; }
                    Json.UnknownKeys(ro, rp, errors, "when", "do", "cooldown");
                    var rule = new RuleDecl { When = ExprText(ro["when"]) ?? "true", Cooldown = Json.Num(ro, "cooldown", rp, errors) ?? 0 };
                    var actions = new List<ActionDecl>();
                    if (ro["do"] is JsonArray da)
                        for (int j = 0; j < da.Count; j++) actions.Add(ParseAction(da[j], $"{rp}.do[{j}]", errors));
                    else errors.Add(new ManifestError(rp + ".do", "must be a list of actions"));
                    rule.Do = actions;
                    rules.Add(rule);
                }
            else errors.Add(new ManifestError(path + ".rules", "must be a list of rules"));
            b.Rules = rules;
            return b;
        }

        private static ActionDecl ParseAction(JsonNode? node, string path, List<ManifestError> errors)
        {
            var a = new ActionDecl();
            if (!(node is JsonObject o)) { errors.Add(new ManifestError(path, "must be an object like {\"set\":\"self.speed\",\"to\":\"2\"}")); return a; }
            Json.UnknownKeys(o, path, errors, "set", "to", "invoke", "args", "emit", "data", "wake");
            a.Set = Json.Str(o, "set");
            a.To = ExprText(o["to"]);
            a.Invoke = Json.Str(o, "invoke");
            a.Args = ExprMap(o["args"], path + ".args", errors);
            a.Emit = Json.Str(o, "emit");
            a.Data = ExprMap(o["data"], path + ".data", errors);
            a.Wake = Json.Str(o, "wake");
            int kinds = (a.Set != null ? 1 : 0) + (a.Invoke != null ? 1 : 0) + (a.Emit != null ? 1 : 0) + (a.Wake != null ? 1 : 0);
            if (kinds != 1) errors.Add(new ManifestError(path, "needs exactly one of set, invoke, emit, wake"));
            if (a.Set != null && a.To == null) errors.Add(new ManifestError(path + ".to", "is required with set"));
            return a;
        }

        /// <summary>Expressions may be written as strings or as plain JSON literals (numbers, booleans).</summary>
        private static string? ExprText(JsonNode? node) =>
            node == null ? null : node is JsonValue v && v.TryGetValue(out string? s) ? s : node.ToJsonString();

        private static IReadOnlyDictionary<string, string> ExprMap(JsonNode? node, string path, List<ManifestError> errors)
        {
            var map = new Dictionary<string, string>();
            if (node == null) return map;
            if (!(node is JsonObject o)) { errors.Add(new ManifestError(path, "must be an object of name → expression")); return map; }
            foreach (var p in o) map[p.Key] = ExprText(p.Value) ?? "null";
            return map;
        }
    }

    /// <summary>Structured content on demand, validated then repaired.</summary>
    public sealed class GeneratorDecl
    {
        public string Id { get; internal set; } = "";
        public string Description { get; internal set; } = "";
        public FieldSpec Schema { get; internal set; } = FieldSpec.AnyValue;
        public IReadOnlyList<string> Constraints { get; internal set; } = Array.Empty<string>();
        public int Repair { get; internal set; } = 1;
        public bool GameValidate { get; internal set; }
        public string Tier { get; internal set; } = "deep";
        public JsonNode? Fallback { get; internal set; }
        public string Source { get; internal set; } = "";

        internal static GeneratorDecl Parse(JsonNode? node, string path, List<ManifestError> errors)
        {
            var g = new GeneratorDecl();
            if (!(node is JsonObject o)) { errors.Add(new ManifestError(path, "must be an object")); return g; }
            Json.UnknownKeys(o, path, errors, "id", "description", "schema", "constraints", "repair", "gameValidate", "tier", "fallback");
            g.Id = Json.Str(o, "id") ?? "";
            g.Description = Json.Str(o, "description") ?? "";
            g.Schema = FieldSpec.Parse(o["schema"], path + ".schema", errors);
            g.Constraints = Json.Strings(o, "constraints", path, errors);
            g.Repair = (int)(Json.Num(o, "repair", path, errors) ?? 1);
            g.GameValidate = Json.Bool(o, "gameValidate", path, errors) ?? false;
            g.Tier = Json.Str(o, "tier") ?? "deep";
            g.Fallback = o["fallback"]?.DeepClone();
            if (g.Id.Length == 0) errors.Add(new ManifestError(path + ".id", "is required"));
            if (g.Description.Length == 0) errors.Add(new ManifestError(path + ".description", "is required: say what to generate"));
            if (!o.ContainsKey("schema")) errors.Add(new ManifestError(path + ".schema", "is required"));
            if (g.Tier != "fast" && g.Tier != "deep") errors.Add(new ManifestError(path + ".tier", "must be \"fast\" or \"deep\""));
            if (g.Repair < 0 || g.Repair > 3) errors.Add(new ManifestError(path + ".repair", "must be between 0 and 3"));
            if (g.Fallback != null)
            {
                string? problem = g.Schema.Validate(g.Fallback, path + ".fallback");
                if (problem != null) errors.Add(new ManifestError(path + ".fallback", problem));
            }
            return g;
        }
    }

    /// <summary>Everything a game declared: the union of its manifest files.</summary>
    public sealed class Declarations
    {
        public Dictionary<string, TypeDecl> Types { get; } = new Dictionary<string, TypeDecl>();
        public List<ThingDecl> Things { get; } = new List<ThingDecl>();
        public Dictionary<string, EventDecl> Events { get; } = new Dictionary<string, EventDecl>();
        public List<RoleDecl> Roles { get; } = new List<RoleDecl>();
        public List<BehaviorDecl> Behaviors { get; } = new List<BehaviorDecl>();
        public List<GeneratorDecl> Generators { get; } = new List<GeneratorDecl>();

        /// <summary>Adds <paramref name="other"/> into this set; duplicate names are errors that name both files.</summary>
        public void Merge(Declarations other, List<ManifestError> errors)
        {
            foreach (var t in other.Types)
            {
                if (Types.TryGetValue(t.Key, out var existing)) errors.Add(new ManifestError("types." + t.Key, $"type '{t.Key}' is declared twice ({existing.Source} and {t.Value.Source})"));
                else Types[t.Key] = t.Value;
            }
            foreach (var th in other.Things)
            {
                var existing = Things.FirstOrDefault(x => x.Id == th.Id);
                if (existing != null) errors.Add(new ManifestError("things", $"thing '{th.Id}' is declared twice ({existing.Source} and {th.Source})"));
                else Things.Add(th);
            }
            foreach (var e in other.Events)
            {
                if (Events.ContainsKey(e.Key)) errors.Add(new ManifestError("events." + e.Key, $"event '{e.Key}' is declared twice"));
                else Events[e.Key] = e.Value;
            }
            foreach (var r in other.Roles)
            {
                var existing = Roles.FirstOrDefault(x => x.Id == r.Id);
                if (existing != null) errors.Add(new ManifestError("roles", $"role '{r.Id}' is declared twice ({existing.Source} and {r.Source})"));
                else Roles.Add(r);
            }
            foreach (var b in other.Behaviors)
            {
                var existing = Behaviors.FirstOrDefault(x => x.Id == b.Id);
                if (existing != null) errors.Add(new ManifestError("behaviors", $"behavior '{b.Id}' is declared twice ({existing.Source} and {b.Source})"));
                else Behaviors.Add(b);
            }
            foreach (var g in other.Generators)
            {
                var existing = Generators.FirstOrDefault(x => x.Id == g.Id);
                if (existing != null) errors.Add(new ManifestError("generators", $"generator '{g.Id}' is declared twice ({existing.Source} and {g.Source})"));
                else Generators.Add(g);
            }
        }
    }
}
