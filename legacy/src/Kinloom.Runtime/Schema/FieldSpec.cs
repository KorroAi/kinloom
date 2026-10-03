using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Kinloom.Schema
{
    public enum FieldKind { Number, Integer, Boolean, String, Enum, Vec2, Vec3, Color, Ref, List, Object, Any }

    /// <summary>A problem found in a manifest, located by a JSON-like path (e.g. <c>types.Truck.params.aggression.max</c>).</summary>
    public sealed class ManifestError
    {
        public ManifestError(string path, string message) { Path = path; Message = message; }
        public string Path { get; }
        public string Message { get; }
        public override string ToString() => Path + ": " + Message;
    }

    /// <summary>Describes one value: a property, a param, a function argument, a generator output.
    /// JSON form: <c>"number"</c> (shorthand) or <c>{"type":"number","min":0,"max":1,"unit":"m","description":"...","default":0.5}</c>.
    /// For strings and lists, min/max bound the length.</summary>
    public sealed class FieldSpec
    {
        private static readonly Dictionary<string, FieldKind> Kinds = new Dictionary<string, FieldKind>(StringComparer.OrdinalIgnoreCase)
        {
            ["number"] = FieldKind.Number, ["float"] = FieldKind.Number, ["integer"] = FieldKind.Integer, ["int"] = FieldKind.Integer,
            ["boolean"] = FieldKind.Boolean, ["bool"] = FieldKind.Boolean, ["string"] = FieldKind.String, ["text"] = FieldKind.String,
            ["enum"] = FieldKind.Enum, ["vec2"] = FieldKind.Vec2, ["vec3"] = FieldKind.Vec3, ["color"] = FieldKind.Color,
            ["ref"] = FieldKind.Ref, ["list"] = FieldKind.List, ["array"] = FieldKind.List, ["object"] = FieldKind.Object, ["any"] = FieldKind.Any,
        };

        public FieldKind Kind { get; private set; } = FieldKind.Any;
        public string? Description { get; private set; }
        public string? Unit { get; private set; }
        public double? Min { get; private set; }
        public double? Max { get; private set; }
        public IReadOnlyList<string> Options { get; private set; } = Array.Empty<string>();
        public FieldSpec? Items { get; private set; }
        public FieldSet Fields { get; private set; } = FieldSet.Empty;
        public IReadOnlyList<string> Required { get; private set; } = Array.Empty<string>();
        public JsonNode? Default { get; private set; }

        public static FieldSpec AnyValue { get; } = new FieldSpec();

        /// <summary>Longest string accepted when the spec declares no max.</summary>
        public const int MaxStringLength = 20000;
        /// <summary>Longest list accepted when the spec declares no max.</summary>
        public const int MaxListLength = 2000;

        public static FieldSpec Parse(JsonNode? node, string path, List<ManifestError> errors)
        {
            var spec = new FieldSpec();
            if (node is JsonValue shorthand && shorthand.TryGetValue(out string? kindName))
            {
                spec.Kind = KindOf(kindName, path + ".type", errors);
                return spec;
            }
            if (!(node is JsonObject o))
            {
                if (node != null) errors.Add(new ManifestError(path, "must be a type name like \"number\" or an object like {\"type\":\"number\"}"));
                return spec;
            }
            foreach (var key in o.Select(p => p.Key))
                if (!IsKnownKey(key)) errors.Add(new ManifestError(path + "." + key, $"unknown field '{key}' (expected type, description, unit, min, max, options, items, fields, required, default)"));

            spec.Kind = o["type"] is JsonValue t && t.TryGetValue(out string? k) ? KindOf(k, path + ".type", errors) : FieldKind.Any;
            if (o["type"] != null && !(o["type"] is JsonValue)) errors.Add(new ManifestError(path + ".type", "must be a string"));
            spec.Description = Json.Str(o, "description");
            spec.Unit = Json.Str(o, "unit");
            spec.Min = Json.Num(o, "min", path, errors);
            spec.Max = Json.Num(o, "max", path, errors);
            if (spec.Min.HasValue && spec.Max.HasValue && spec.Max < spec.Min)
                errors.Add(new ManifestError(path + ".max", $"must be ≥ min ({Fmt(spec.Min.Value)})"));
            if (o["options"] is JsonArray options)
                spec.Options = options.Select(x => x is JsonValue v && v.TryGetValue(out string? s) ? s! : x?.ToJsonString() ?? "").ToArray();
            if (spec.Kind == FieldKind.Enum && spec.Options.Count == 0)
                errors.Add(new ManifestError(path + ".options", "an enum needs a non-empty list of options"));
            if (o.ContainsKey("items")) spec.Items = Parse(o["items"], path + ".items", errors);
            if (o["fields"] is JsonObject fields) spec.Fields = FieldSet.Parse(fields, path + ".fields", errors);
            else if (o.ContainsKey("fields")) errors.Add(new ManifestError(path + ".fields", "must be an object of field specs"));
            if (o["required"] is JsonArray required)
            {
                spec.Required = required.Select(x => x?.GetValue<string>() ?? "").ToArray();
                foreach (var r in spec.Required)
                    if (spec.Fields.Find(r) == null) errors.Add(new ManifestError(path + ".required", $"'{r}' is not one of the fields"));
            }
            if (o.ContainsKey("default"))
            {
                spec.Default = o["default"]?.DeepClone();
                string? problem = spec.Validate(spec.Default, path + ".default");
                if (problem != null) errors.Add(new ManifestError(path + ".default", problem));
            }
            return spec;
        }

        private static bool IsKnownKey(string key) =>
            key == "type" || key == "description" || key == "unit" || key == "min" || key == "max" || key == "options"
            || key == "items" || key == "fields" || key == "required" || key == "default";

        private static FieldKind KindOf(string? name, string path, List<ManifestError> errors)
        {
            if (name != null && Kinds.TryGetValue(name, out var kind)) return kind;
            errors.Add(new ManifestError(path, $"unknown type '{name}' (expected number, integer, boolean, string, enum, vec2, vec3, color, ref, list, object or any)"));
            return FieldKind.Any;
        }

        /// <summary>Null when the value fits, otherwise a sentence naming <paramref name="path"/>.</summary>
        public string? Validate(JsonNode? value, string path)
        {
            var kind = Json.KindOf(value);
            switch (Kind)
            {
                case FieldKind.Any:
                    return null;
                case FieldKind.Number:
                case FieldKind.Integer:
                {
                    if (kind != JsonValueKind.Number) return $"{path} must be a number";
                    double d = JsonNumber.ToDouble(value!);
                    if (double.IsNaN(d) || double.IsInfinity(d)) return $"{path} must be a finite number";
                    if (Kind == FieldKind.Integer && Math.Abs(d - Math.Round(d)) > 1e-9) return $"{path} must be a whole number";
                    // An undeclared bound on an integer still has to fit the int most engines will cast it to.
                    if (Kind == FieldKind.Integer && ((!Min.HasValue && d < int.MinValue) || (!Max.HasValue && d > int.MaxValue)))
                        return $"{path} must be between {int.MinValue} and {int.MaxValue}";
                    return Range(d, path, "");
                }
                case FieldKind.Boolean:
                    return kind == JsonValueKind.True || kind == JsonValueKind.False ? null : $"{path} must be true or false";
                case FieldKind.String:
                case FieldKind.Ref:
                {
                    if (kind != JsonValueKind.String) return Kind == FieldKind.Ref ? $"{path} must be a thing id (string)" : $"{path} must be a string";
                    int length = value!.GetValue<string>().Length;
                    if (!Max.HasValue && length > MaxStringLength) return $"{path} must be at most {MaxStringLength} characters long";
                    return Range(length, path, " characters long");
                }
                case FieldKind.Enum:
                {
                    string? s = kind == JsonValueKind.String ? value!.GetValue<string>() : null;
                    return s != null && Options.Contains(s) ? null : $"{path} must be one of: {string.Join(", ", Options)}";
                }
                case FieldKind.Vec2:
                    return Vector(value, 2) ? Components(value, path) : $"{path} must be a vec2 like [x, y] or {{\"x\":..,\"y\":..}}";
                case FieldKind.Vec3:
                    return Vector(value, 3) ? Components(value, path) : $"{path} must be a vec3 like [x, y, z] or {{\"x\":..,\"y\":..,\"z\":..}}";
                case FieldKind.Color:
                {
                    if (kind == JsonValueKind.String)
                    {
                        string s = value!.GetValue<string>();
                        bool hex = s.Length == 7 || s.Length == 9;
                        if (hex && s[0] == '#' && s.Skip(1).All(Uri.IsHexDigit)) return null;
                    }
                    if (value is JsonArray a && (a.Count == 3 || a.Count == 4) && a.All(x => Json.KindOf(x) == JsonValueKind.Number))
                        return a.All(x => Finite(x)) ? null : $"{path} must use finite numbers";
                    return $"{path} must be a color like \"#rrggbb\" or [r, g, b(, a)]";
                }
                case FieldKind.List:
                {
                    if (!(value is JsonArray list)) return $"{path} must be a list";
                    if (!Max.HasValue && list.Count > MaxListLength) return $"{path} must be at most {MaxListLength} items long";
                    string? count = Range(list.Count, path, " items long");
                    if (count != null) return count;
                    if (Items == null) return null;
                    for (int i = 0; i < list.Count; i++)
                    {
                        string? problem = Items.Validate(list[i], $"{path}[{i}]");
                        if (problem != null) return problem;
                    }
                    return null;
                }
                case FieldKind.Object:
                {
                    if (!(value is JsonObject obj)) return $"{path} must be an object";
                    foreach (var r in Required)
                        if (!obj.ContainsKey(r)) return $"{path}.{r} is required";
                    if (Fields.Count > 0)
                        foreach (var key in obj.Select(p => p.Key))
                            if (Fields.Find(key) == null) return $"{path} has no field '{key}' (expected {string.Join(", ", Fields.Names)})";
                    foreach (var field in Fields)
                    {
                        if (!obj.ContainsKey(field.Name)) continue;
                        string? problem = field.Spec.Validate(obj[field.Name], path + "." + field.Name);
                        if (problem != null) return problem;
                    }
                    return null;
                }
                default:
                    return null;
            }
        }

        private string? Range(double d, string path, string suffix)
        {
            if (Min.HasValue && d < Min.Value) return $"{path} must be ≥ {Fmt(Min.Value)}{suffix}";
            if (Max.HasValue && d > Max.Value) return $"{path} must be ≤ {Fmt(Max.Value)}{suffix}";
            return null;
        }

        private static bool Finite(JsonNode? n)
        {
            double d = JsonNumber.ToDouble(n!);
            return !double.IsNaN(d) && !double.IsInfinity(d);
        }

        /// <summary>Every component finite and within min/max.</summary>
        private string? Components(JsonNode? value, string path)
        {
            IEnumerable<JsonNode?> parts = value is JsonArray a ? a : ((JsonObject)value!).Select(p => p.Value);
            foreach (var part in parts)
            {
                if (!Finite(part)) return $"{path} must use finite numbers";
                string? outOfRange = Range(JsonNumber.ToDouble(part!), path + " components", "");
                if (outOfRange != null) return outOfRange;
            }
            return null;
        }

        private static bool Vector(JsonNode? value, int n)
        {
            if (value is JsonArray a) return a.Count == n && a.All(x => Json.KindOf(x) == JsonValueKind.Number);
            if (value is JsonObject o)
            {
                string[] axes = { "x", "y", "z" };
                return o.Count == n && axes.Take(n).All(k => Json.KindOf(o[k]) == JsonValueKind.Number);
            }
            return false;
        }

        internal static string Fmt(double d) => d.ToString("0.####", CultureInfo.InvariantCulture);

        /// <summary>JSON Schema for tools and generators.</summary>
        public JsonObject ToJsonSchema()
        {
            var s = new JsonObject();
            switch (Kind)
            {
                case FieldKind.Number: s["type"] = "number"; Bounds(s, "minimum", "maximum"); break;
                case FieldKind.Integer: s["type"] = "integer"; Bounds(s, "minimum", "maximum"); break;
                case FieldKind.Boolean: s["type"] = "boolean"; break;
                case FieldKind.String: s["type"] = "string"; Bounds(s, "minLength", "maxLength"); break;
                case FieldKind.Ref: s["type"] = "string"; break;
                case FieldKind.Enum: s["type"] = "string"; s["enum"] = new JsonArray(Options.Select(x => (JsonNode)JsonValue.Create(x)!).ToArray()); break;
                case FieldKind.Vec2:
                case FieldKind.Vec3:
                {
                    int n = Kind == FieldKind.Vec2 ? 2 : 3;
                    s["type"] = "array"; s["items"] = new JsonObject { ["type"] = "number" }; s["minItems"] = n; s["maxItems"] = n;
                    break;
                }
                case FieldKind.Color: s["type"] = "string"; s["pattern"] = "^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"; break;
                case FieldKind.List:
                    s["type"] = "array";
                    if (Items != null) s["items"] = Items.ToJsonSchema();
                    Bounds(s, "minItems", "maxItems");
                    break;
                case FieldKind.Object:
                {
                    s["type"] = "object";
                    var props = new JsonObject();
                    foreach (var f in Fields) props[f.Name] = f.Spec.ToJsonSchema();
                    s["properties"] = props;
                    if (Required.Count > 0) s["required"] = new JsonArray(Required.Select(x => (JsonNode)JsonValue.Create(x)!).ToArray());
                    break;
                }
            }
            string? description = Description;
            if (Kind == FieldKind.Ref) description = (description == null ? "" : description + " ") + "(a thing id)";
            if (Unit != null) description = (description == null ? "" : description + " ") + "(unit: " + Unit + ")";
            if (description != null) s["description"] = description;
            return s;
        }

        private void Bounds(JsonObject s, string min, string max)
        {
            if (Min.HasValue) s[min] = Min.Value;
            if (Max.HasValue) s[max] = Max.Value;
        }

        /// <summary>Short human/model-readable form, e.g. <c>number 0..1 (km/h)</c>.</summary>
        public string Describe()
        {
            string text = Kind.ToString().ToLowerInvariant();
            if (Kind == FieldKind.Enum) text = "one of " + string.Join("|", Options);
            if (Kind == FieldKind.List && Items != null) text = "list of " + Items.Describe();
            if (Kind == FieldKind.Object && Fields.Count > 0) text = "{" + string.Join(", ", Fields.Select(f => f.Name + ": " + f.Spec.Describe())) + "}";
            if (Min.HasValue || Max.HasValue) text += " " + (Min.HasValue ? Fmt(Min.Value) : "") + ".." + (Max.HasValue ? Fmt(Max.Value) : "");
            if (Unit != null) text += " (" + Unit + ")";
            return text;
        }
    }

    /// <summary>An ordered set of named field specs (order matters for function arguments).</summary>
    public sealed class FieldSet : IEnumerable<FieldSet.Field>
    {
        public sealed class Field
        {
            public Field(string name, FieldSpec spec) { Name = name; Spec = spec; }
            public string Name { get; }
            public FieldSpec Spec { get; }
        }

        private readonly List<Field> _fields;
        private readonly Dictionary<string, FieldSpec> _byName = new Dictionary<string, FieldSpec>(StringComparer.Ordinal);
        private readonly IReadOnlyList<string> _names;

        public FieldSet(IEnumerable<Field> fields)
        {
            _fields = fields.ToList();
            foreach (var f in _fields) if (!_byName.ContainsKey(f.Name)) _byName[f.Name] = f.Spec;
            _names = _fields.Select(f => f.Name).ToList();
        }

        public static FieldSet Empty { get; } = new FieldSet(Array.Empty<Field>());

        public int Count => _fields.Count;
        public IReadOnlyList<string> Names => _names;
        /// <summary>O(1): called for every property of every update, every frame.</summary>
        public FieldSpec? Find(string name) => name != null && _byName.TryGetValue(name, out var spec) ? spec : null;

        public static FieldSet Parse(JsonNode? node, string path, List<ManifestError> errors)
        {
            if (node == null) return Empty;
            if (!(node is JsonObject o)) { errors.Add(new ManifestError(path, "must be an object of name → field spec")); return Empty; }
            return new FieldSet(o.Select(p => new Field(p.Key, FieldSpec.Parse(p.Value, path + "." + p.Key, errors))));
        }

        public IEnumerator<Field> GetEnumerator() => _fields.GetEnumerator();
        IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
    }
}
