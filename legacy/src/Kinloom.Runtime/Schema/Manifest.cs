using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Kinloom.Schema
{
    /// <summary>Reads manifest JSON (types, things, events, roles, behaviors, generators) and checks cross-references.</summary>
    public static class Manifest
    {
        public const string WorldId = "world";
        public const string WorldTypeName = "World";
        private static readonly Regex IdPattern = new Regex("^[A-Za-z0-9_\\-]+$");

        /// <summary>The built-in thing every game has: global facts, free-form properties and params.</summary>
        public static TypeDecl WorldType { get; } = new TypeDecl
        {
            Name = WorldTypeName,
            Description = "The game world: global facts and settings.",
            Open = true,
            Source = "built-in",
            Functions = new Dictionary<string, FunctionDecl>
            {
                ["generated"] = new FunctionDecl { Description = "Receives content produced by a generator for the game." },
            },
        };

        public static Declarations Parse(string json, string source, List<ManifestError> errors)
        {
            var d = new Declarations();
            JsonNode? root;
            try { root = JsonNode.Parse(json, documentOptions: new JsonDocumentOptions { CommentHandling = JsonCommentHandling.Skip, AllowTrailingCommas = true }); }
            catch (JsonException e)
            {
                errors.Add(new ManifestError(source, "invalid JSON: " + e.Message));
                return d;
            }
            if (!(root is JsonObject o)) { errors.Add(new ManifestError(source, "a manifest must be a JSON object")); return d; }
            Json.UnknownKeys(o, "", errors, "types", "things", "events", "roles", "behaviors", "generators", "$schema", "description");

            if (o["types"] is JsonObject types)
                foreach (var t in types)
                {
                    var decl = TypeDecl.Parse(t.Key, t.Value, "types." + t.Key, errors);
                    decl.Source = source;
                    d.Types[t.Key] = decl;
                }
            else if (o.ContainsKey("types")) errors.Add(new ManifestError("types", "must be an object of type name → type"));

            ForEach(o, "things", errors, (n, p) => { var x = ThingDecl.Parse(n, p, errors); x.Source = source; d.Things.Add(x); });
            ForEach(o, "roles", errors, (n, p) => { var x = RoleDecl.Parse(n, p, errors); x.Source = source; d.Roles.Add(x); });
            ForEach(o, "behaviors", errors, (n, p) => { var x = BehaviorDecl.Parse(n, p, errors); x.Source = source; d.Behaviors.Add(x); });
            ForEach(o, "generators", errors, (n, p) => { var x = GeneratorDecl.Parse(n, p, errors); x.Source = source; d.Generators.Add(x); });

            if (o["events"] is JsonObject events)
                foreach (var e in events)
                {
                    string path = "events." + e.Key;
                    var decl = new EventDecl { Type = e.Key };
                    if (e.Value is JsonObject eo)
                    {
                        Json.UnknownKeys(eo, path, errors, "description", "importance");
                        decl.Description = Json.Str(eo, "description");
                        decl.Importance = Json.Num(eo, "importance", path, errors) ?? 0.5;
                        if (decl.Importance < 0 || decl.Importance > 1) errors.Add(new ManifestError(path + ".importance", "must be between 0 and 1"));
                    }
                    else if (e.Value is JsonValue ev && ev.TryGetValue(out string? text)) decl.Description = text;
                    else if (e.Value != null) errors.Add(new ManifestError(path, "must be a description string or {description, importance}"));
                    d.Events[e.Key] = decl;
                }
            else if (o.ContainsKey("events")) errors.Add(new ManifestError("events", "must be an object of event type → description"));
            return d;
        }

        private static void ForEach(JsonObject o, string key, List<ManifestError> errors, Action<JsonNode?, string> each)
        {
            if (o[key] is JsonArray a) { for (int i = 0; i < a.Count; i++) each(a[i], $"{key}[{i}]"); }
            else if (o.ContainsKey(key)) errors.Add(new ManifestError(key, "must be a list"));
        }

        /// <summary>Merges every <c>*.json</c> file directly inside <paramref name="dir"/> (sub-folders such as <c>tests/</c> are ignored).</summary>
        public static Declarations LoadDirectory(string dir, List<ManifestError> errors)
        {
            var all = new Declarations();
            if (!Directory.Exists(dir)) { errors.Add(new ManifestError(dir, "manifest folder not found")); return all; }
            foreach (var file in Directory.GetFiles(dir, "*.json").OrderBy(f => f, StringComparer.Ordinal))
                all.Merge(Parse(File.ReadAllText(file), Path.GetFileName(file), errors), errors);
            return all;
        }

        /// <summary>The type of a thing id, including the built-in world.</summary>
        internal static TypeDecl? TypeOfThing(Declarations d, string id)
        {
            if (id == WorldId) return WorldType;
            var thing = d.Things.FirstOrDefault(t => t.Id == id);
            return thing != null && d.Types.TryGetValue(thing.Type, out var type) ? type : null;
        }

        /// <summary>Checks every cross-reference and the syntax of every expression.</summary>
        public static void Check(Declarations d, List<ManifestError> errors)
        {
            for (int i = 0; i < d.Things.Count; i++) CheckThing(d.Things[i], $"things[{i}]", d.Types, errors);

            for (int i = 0; i < d.Roles.Count; i++) CheckRole(d, d.Roles[i], $"roles[{i}]", errors);

            for (int i = 0; i < d.Behaviors.Count; i++)
            {
                var b = d.Behaviors[i];
                string path = $"behaviors[{i}]";
                if (b.Owner != null && TypeOfThing(d, b.Owner) == null)
                    errors.Add(new ManifestError(path + ".owner", $"unknown thing '{b.Owner}'"));
                for (int r = 0; r < b.Rules.Count; r++)
                    for (int a = 0; a < b.Rules[r].Do.Count; a++)
                    {
                        var act = b.Rules[r].Do[a];
                        string ap = $"{path}.rules[{r}].do[{a}]";
                        if (act.Set != null) CheckMemberRef(d, act.Set, b.Owner, isFunction: false, ap + ".set", errors);
                        if (act.Invoke != null) CheckMemberRef(d, act.Invoke, b.Owner, isFunction: true, ap + ".invoke", errors);
                        if (act.Wake != null && d.Roles.All(x => x.Id != act.Wake)) errors.Add(new ManifestError(ap + ".wake", $"unknown role '{act.Wake}'"));
                    }
            }

            Expressions.ExprCheck.Check(d, errors);
        }

        /// <summary>A thing's own rules: a valid, unreserved id and a known type.</summary>
        internal static void CheckThing(ThingDecl t, string path, IReadOnlyDictionary<string, TypeDecl> types, List<ManifestError> errors)
        {
            if (t.Id == WorldId) errors.Add(new ManifestError(path + ".id", "'world' is built in; set its facts with updates instead of declaring it"));
            else if (t.Id == "self" || t.Id == "event") errors.Add(new ManifestError(path + ".id", $"'{t.Id}' is reserved in expressions; choose another id"));
            else if (t.Id.Length > 0 && !IdPattern.IsMatch(t.Id)) errors.Add(new ManifestError(path + ".id", $"'{t.Id}' may only use letters, digits, _ and -"));
            if (t.Type.Length > 0 && !types.ContainsKey(t.Type))
                errors.Add(new ManifestError(path + ".type", $"unknown type '{t.Type}'{Suggest(t.Type, types.Keys)}"));
        }

        private static void CheckRole(Declarations d, RoleDecl role, string path, List<ManifestError> errors)
        {
            if (role.Id.Length > 0 && !IdPattern.IsMatch(role.Id)) errors.Add(new ManifestError(path + ".id", $"'{role.Id}' may only use letters, digits, _ and -"));
            if (role.Inhabits != null && TypeOfThing(d, role.Inhabits) == null)
                errors.Add(new ManifestError(path + ".inhabits", $"unknown thing '{role.Inhabits}'{Suggest(role.Inhabits, d.Things.Select(t => t.Id))}"));

            for (int i = 0; i < role.Sees.Count; i++)
            {
                string s = role.Sees[i], sp = $"{path}.sees[{i}]";
                if (s == "*" || s == "world" || s == "event:*") continue;
                if (s.StartsWith("thing:", StringComparison.Ordinal))
                {
                    string id = s.Substring(6);
                    if (id == "self") { if (role.Inhabits == null) errors.Add(new ManifestError(sp, "'self' needs the role to inhabit a thing (set inhabits)")); }
                    else if (TypeOfThing(d, id) == null) errors.Add(new ManifestError(sp, $"unknown thing '{id}'{Suggest(id, d.Things.Select(t => t.Id))}"));
                }
                else if (s.StartsWith("type:", StringComparison.Ordinal))
                {
                    if (!d.Types.ContainsKey(s.Substring(5))) errors.Add(new ManifestError(sp, $"unknown type '{s.Substring(5)}'"));
                }
                else if (!s.StartsWith("tag:", StringComparison.Ordinal) && !s.StartsWith("event:", StringComparison.Ordinal))
                    errors.Add(new ManifestError(sp, $"'{s}' is not a view (expected thing:<id|self>, type:<Type>, tag:<tag>, event:<type|*>, world or *)"));
            }

            for (int i = 0; i < role.Can.Count; i++)
            {
                string cp = $"{path}.can[{i}]";
                var perm = Permission.TryParse(role.Can[i], out var error);
                if (perm == null) { errors.Add(new ManifestError(cp, error!)); continue; }
                CheckPermission(d, role, perm, cp, errors);
            }

            if (role.Fallback?.Behavior != null && d.Behaviors.All(b => b.Id != role.Fallback.Behavior))
                errors.Add(new ManifestError(path + ".fallback.behavior", $"unknown behavior '{role.Fallback.Behavior}'"));
        }

        private static void CheckPermission(Declarations d, RoleDecl role, Permission p, string path, List<ManifestError> errors)
        {
            switch (p.Verb)
            {
                case Verb.Set:
                case Verb.Invoke:
                case Verb.Behavior:
                case Verb.Destroy:
                {
                    if (p.Verb == Verb.Destroy && p.Target == "own") return;
                    var types = ResolveTarget(d, role.Inhabits, p.Target!, path, errors);
                    if (types == null || p.Member == null || p.Member == "*") return;
                    bool isFunction = p.Verb == Verb.Invoke;
                    if (!types.Any(t => isFunction ? t.Functions.ContainsKey(p.Member) : t.Params.Find(p.Member) != null || t.Open))
                    {
                        var names = types.SelectMany(t => isFunction ? t.Functions.Keys : t.Params.Names).Distinct();
                        errors.Add(new ManifestError(path, $"'{p.Member}' is not a {(isFunction ? "function" : "param")} of {string.Join("/", types.Select(t => t.Name))}{Suggest(p.Member, names)}"));
                    }
                    return;
                }
                case Verb.Create:
                    if (p.Target == "*") return;
                    if (!d.Types.TryGetValue(p.Target!, out var type)) errors.Add(new ManifestError(path, $"unknown type '{p.Target}'"));
                    else if (type.Creatable == null) errors.Add(new ManifestError(path, $"type '{p.Target}' is not creatable (add \"creatable\" to it)"));
                    return;
                case Verb.Generate:
                    if (p.Target != "*" && d.Generators.All(g => g.Id != p.Target)) errors.Add(new ManifestError(path, $"unknown generator '{p.Target}'"));
                    return;
            }
        }

        /// <summary>Types a permission target can refer to; null (and an error) when it refers to nothing.</summary>
        private static IReadOnlyList<TypeDecl>? ResolveTarget(Declarations d, string? inhabits, string target, string path, List<ManifestError> errors)
        {
            if (target == "*") return d.Types.Values.ToList();
            if (target == "self")
            {
                if (inhabits == null) { errors.Add(new ManifestError(path, "'self' needs the role to inhabit a thing (set inhabits)")); return null; }
                var own = TypeOfThing(d, inhabits);
                return own == null ? null : new[] { own };
            }
            if (target.StartsWith("tag:", StringComparison.Ordinal))
            {
                string tag = target.Substring(4);
                var tagged = d.Things.Where(t => t.Tags.Contains(tag)).Select(t => TypeOfThing(d, t.Id)).Where(t => t != null).Distinct().ToList();
                if (tagged.Count == 0) { errors.Add(new ManifestError(path, $"no thing has the tag '{tag}'")); return null; }
                return tagged!;
            }
            if (d.Types.TryGetValue(target, out var type)) return new[] { type };
            var thingType = TypeOfThing(d, target);
            if (thingType != null) return new[] { thingType };
            errors.Add(new ManifestError(path, $"unknown target '{target}' (expected self, a thing id, a type, tag:<tag> or *){Suggest(target, d.Things.Select(t => t.Id).Concat(d.Types.Keys))}"));
            return null;
        }

        private static void CheckMemberRef(Declarations d, string reference, string? owner, bool isFunction, string path, List<ManifestError> errors)
        {
            int dot = reference.LastIndexOf('.');
            if (dot <= 0) { errors.Add(new ManifestError(path, $"'{reference}' must look like target.{(isFunction ? "function" : "param")}")); return; }
            string target = reference.Substring(0, dot), member = reference.Substring(dot + 1);
            string? id = target == "self" ? owner : target;
            if (id == null) { errors.Add(new ManifestError(path, "'self' needs the behavior to have an owner")); return; }
            var type = TypeOfThing(d, id);
            if (type == null) { errors.Add(new ManifestError(path, $"unknown thing '{id}'")); return; }
            bool exists = isFunction ? type.Functions.ContainsKey(member) : type.Params.Find(member) != null || type.Open;
            if (!exists) errors.Add(new ManifestError(path, $"'{member}' is not a {(isFunction ? "function" : "param")} of {type.Name}"));
        }

        /// <summary>" (did you mean 'x'?)" for close names.</summary>
        internal static string Suggest(string wrong, IEnumerable<string> candidates)
        {
            // Edit distance is quadratic: a model can send a megabyte-long id, and nothing that long is a typo.
            if (wrong.Length > 64) return "";
            string? best = null;
            int bestDistance = int.MaxValue;
            foreach (var c in candidates)
            {
                if (c.Length > 64) continue;
                int dist = Distance(wrong.ToLowerInvariant(), c.ToLowerInvariant());
                if (dist < bestDistance) { bestDistance = dist; best = c; }
            }
            return best != null && bestDistance <= Math.Max(2, wrong.Length / 3) ? $" (did you mean '{best}'?)" : "";
        }

        private static int Distance(string a, string b)
        {
            var dp = new int[a.Length + 1, b.Length + 1];
            for (int i = 0; i <= a.Length; i++) dp[i, 0] = i;
            for (int j = 0; j <= b.Length; j++) dp[0, j] = j;
            for (int i = 1; i <= a.Length; i++)
                for (int j = 1; j <= b.Length; j++)
                    dp[i, j] = Math.Min(Math.Min(dp[i - 1, j] + 1, dp[i, j - 1] + 1), dp[i - 1, j - 1] + (a[i - 1] == b[j - 1] ? 0 : 1));
            return dp[a.Length, b.Length];
        }
    }
}
