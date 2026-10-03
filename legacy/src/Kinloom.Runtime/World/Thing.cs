using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Kinloom.Expressions;
using Kinloom.Schema;

namespace Kinloom
{
    /// <summary>Anything in the game Kinloom can read, steer or create. Properties are pushed by the game;
    /// params are writable by Kinloom (their value here is the last value the game confirmed).</summary>
    public sealed class Thing
    {
        private readonly Dictionary<string, Value> _values = new Dictionary<string, Value>();
        private Value? _snapshot;

        internal Thing(ThingDecl decl, TypeDecl type, string? createdBy)
        {
            Id = decl.Id;
            Type = type;
            Name = decl.Name ?? decl.Id;
            Description = decl.Description;
            Tags = decl.Tags;
            CreatedBy = createdBy;
            foreach (var p in type.Params) Params[p.Name] = p.Spec.Default?.DeepClone();
        }

        public string Id { get; }
        public TypeDecl Type { get; }
        public string Name { get; }
        public string? Description { get; }
        public IReadOnlyList<string> Tags { get; }
        /// <summary>Source that asked for its creation (e.g. <c>role:director</c>); null for things the game declared.</summary>
        public string? CreatedBy { get; }
        public bool Bound { get; internal set; }
        public Dictionary<string, JsonNode?> Properties { get; } = new Dictionary<string, JsonNode?>();
        public Dictionary<string, JsonNode?> Params { get; } = new Dictionary<string, JsonNode?>();
        /// <summary>Params with a Set effect on its way to the game: member → (effect id, value).</summary>
        internal Dictionary<string, (long effect, JsonNode? value)> Pending { get; } = new Dictionary<string, (long, JsonNode?)>();
        /// <summary>Game time of the last successful call of each function (cooldowns).</summary>
        internal Dictionary<string, double> LastCall { get; } = new Dictionary<string, double>();

        internal void Set(Dictionary<string, JsonNode?> bag, string name, JsonNode? value)
        {
            bag[name] = value?.DeepClone();
            _values.Remove(name);
            _snapshot = null;
        }

        /// <summary>A member as an expression value (params win over properties); cached until it changes.</summary>
        public Value Get(string name)
        {
            if (_values.TryGetValue(name, out var cached)) return cached;
            Value v;
            if (name == "id") v = Value.Of(Id);
            else if (name == "name") v = Value.Of(Name);
            else if (name == "type") v = Value.Of(Type.Name);
            else if (Params.TryGetValue(name, out var p)) v = Value.From(p);
            else if (Properties.TryGetValue(name, out var q)) v = Value.From(q);
            else return Value.Null;
            _values[name] = v;
            return v;
        }

        /// <summary>Every member as one object value (for <c>len(self)</c>, passing a thing around...).</summary>
        public Value AsValue()
        {
            if (_snapshot.HasValue) return _snapshot.Value;
            var o = new JsonObject { ["id"] = Id, ["name"] = Name, ["type"] = Type.Name };
            foreach (var p in Properties) o[p.Key] = p.Value?.DeepClone();
            foreach (var p in Params) o[p.Key] = p.Value?.DeepClone();
            _snapshot = Value.From(o);
            return _snapshot.Value;
        }

        /// <summary>Compact one-line state for prompts: <c>truck_2 (Truck "Rex") speed=120, lap=2 | aggression=0.5</c>.</summary>
        public string Describe()
        {
            string head = $"{Id} ({Type.Name}{(Name != Id ? " \"" + Name + "\"" : "")}{(Tags.Count > 0 ? ", tags: " + string.Join(",", Tags) : "")})";
            string props = string.Join(", ", Properties.Where(p => p.Value != null).Select(p => p.Key + "=" + Short(p.Value)));
            string pars = string.Join(", ", Params.Where(p => p.Value != null).Select(p => p.Key + "=" + Short(p.Value)));
            return head + (props.Length > 0 ? " " + props : "") + (pars.Length > 0 ? " | params: " + pars : "");
        }

        internal static string Short(JsonNode? n)
        {
            string s = Value.From(n).ToString();
            return s.Length > 120 ? s.Substring(0, 117) + "..." : s;
        }
    }

    /// <summary>All things of a session, including the built-in <c>world</c>.</summary>
    public sealed class Registry
    {
        private readonly Dictionary<string, Thing> _things = new Dictionary<string, Thing>(StringComparer.Ordinal);
        private readonly List<Thing> _order = new List<Thing>();

        public Thing? Find(string? id) => id != null && _things.TryGetValue(id, out var t) ? t : null;
        public IEnumerable<Thing> All => _order;
        public IEnumerable<Thing> OfType(string type) => _order.Where(t => t.Type.Name == type);
        public IEnumerable<Thing> WithTag(string tag) => _order.Where(t => t.Tags.Contains(tag));
        public int Count => _order.Count;

        internal Thing Add(ThingDecl decl, TypeDecl type, string? createdBy)
        {
            var thing = new Thing(decl, type, createdBy);
            _things[decl.Id] = thing;
            _order.Add(thing);
            return thing;
        }

        internal bool Remove(string id)
        {
            if (!_things.TryGetValue(id, out var t)) return false;
            _things.Remove(id);
            _order.Remove(t);
            return true;
        }
    }
}
