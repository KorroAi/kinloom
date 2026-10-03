using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Kinloom.Expressions
{
    public enum ValueKind { Null, Number, Bool, String, Vector, List, Object }

    /// <summary>A dynamically typed expression value. JSON is converted once (objects become dictionaries), so reading
    /// a field during evaluation is a dictionary lookup. Numeric arrays and {x,y(,z)} objects of length 2–3 are vectors.</summary>
    public readonly struct Value
    {
        private readonly double _number;
        private readonly object? _ref;

        private Value(ValueKind kind, double number, object? reference)
        {
            Kind = kind;
            _number = number;
            _ref = reference;
        }

        public ValueKind Kind { get; }
        public static Value Null => default;
        public static Value True => new Value(ValueKind.Bool, 1, null);
        public static Value False => new Value(ValueKind.Bool, 0, null);

        public static Value Of(double d) => new Value(ValueKind.Number, d, null);
        public static Value Of(bool b) => b ? True : False;
        public static Value Of(string? s) => s == null ? Null : new Value(ValueKind.String, 0, s);
        public static Value OfVector(double[] v) => new Value(ValueKind.Vector, 0, v);
        public static Value OfList(IReadOnlyList<Value> items) =>
            items.Count >= 2 && items.Count <= 3 && items.All(i => i.Kind == ValueKind.Number)
                ? OfVector(items.Select(i => i.Number).ToArray())
                : new Value(ValueKind.List, 0, items);

        public double Number => Kind == ValueKind.Number || Kind == ValueKind.Bool ? _number : 0;
        public bool IsBool => Kind == ValueKind.Bool;
        public string String => Kind == ValueKind.String ? (string)_ref! : ToString();
        public double[] Vector => Kind == ValueKind.Vector ? (double[])_ref! : Array.Empty<double>();

        public bool Truthy => Kind switch
        {
            ValueKind.Null => false,
            ValueKind.Number => _number != 0,
            ValueKind.Bool => _number != 0,
            ValueKind.String => ((string)_ref!).Length > 0,
            _ => true,
        };

        public int Count => Kind switch
        {
            ValueKind.String => ((string)_ref!).Length,
            ValueKind.Vector => Vector.Length,
            ValueKind.List => ((IReadOnlyList<Value>)_ref!).Count,
            ValueKind.Object => ((Dictionary<string, Value>)_ref!).Count,
            _ => 0,
        };

        public IEnumerable<Value> Items()
        {
            if (Kind == ValueKind.Vector) foreach (var d in Vector) yield return Of(d);
            else if (Kind == ValueKind.List) foreach (var v in (IReadOnlyList<Value>)_ref!) yield return v;
        }

        public static Value From(JsonNode? node)
        {
            switch (node)
            {
                case null: return Null;
                case JsonArray a:
                {
                    if (a.Count >= 2 && a.Count <= 3 && a.All(IsNumber)) return OfVector(a.Select(n => JsonNumber.ToDouble(n!)).ToArray());
                    return new Value(ValueKind.List, 0, a.Select(From).ToArray());
                }
                case JsonObject o:
                {
                    if ((o.Count == 2 || o.Count == 3) && IsNumber(o["x"]) && IsNumber(o["y"]) && (o.Count == 2 || IsNumber(o["z"])))
                        return OfVector(o.Count == 2 ? new[] { JsonNumber.ToDouble(o["x"]!), JsonNumber.ToDouble(o["y"]!) } : new[] { JsonNumber.ToDouble(o["x"]!), JsonNumber.ToDouble(o["y"]!), JsonNumber.ToDouble(o["z"]!) });
                    var dict = new Dictionary<string, Value>(o.Count);
                    foreach (var p in o) dict[p.Key] = From(p.Value);
                    return new Value(ValueKind.Object, 0, dict);
                }
                default:
                {
                    var kind = node.GetValueKind();
                    if (kind == JsonValueKind.Number) return Of(JsonNumber.ToDouble(node));
                    if (kind == JsonValueKind.True) return True;
                    if (kind == JsonValueKind.False) return False;
                    if (kind == JsonValueKind.String) return Of(node.GetValue<string>());
                    return Null;
                }
            }
        }

        private static bool IsNumber(JsonNode? n) => n is JsonValue && n.GetValueKind() == JsonValueKind.Number;

        /// <summary>A field of an object, a component of a vector (x/y/z or index), an item of a list.</summary>
        public Value Get(string key)
        {
            switch (Kind)
            {
                case ValueKind.Object: return ((Dictionary<string, Value>)_ref!).TryGetValue(key, out var field) ? field : Null;
                case ValueKind.Vector:
                {
                    var v = Vector;
                    int i = key == "x" ? 0 : key == "y" ? 1 : key == "z" ? 2 : int.TryParse(key, NumberStyles.Integer, CultureInfo.InvariantCulture, out var n) ? n : -1;
                    return i >= 0 && i < v.Length ? Of(v[i]) : Null;
                }
                case ValueKind.List:
                {
                    if (!int.TryParse(key, NumberStyles.Integer, CultureInfo.InvariantCulture, out var i) || i < 0) return Null;
                    var list = (IReadOnlyList<Value>)_ref!;
                    return i < list.Count ? list[i] : Null;
                }
                default: return Null;
            }
        }

        public Value Navigate(IReadOnlyList<string> path, int start)
        {
            var v = this;
            for (int i = start; i < path.Count && v.Kind != ValueKind.Null; i++) v = v.Get(path[i]);
            return v;
        }

        public JsonNode? ToJson() => Kind switch
        {
            ValueKind.Null => null,
            ValueKind.Number => JsonValue.Create(_number),
            ValueKind.Bool => JsonValue.Create(_number != 0),
            ValueKind.String => JsonValue.Create((string)_ref!),
            ValueKind.Vector => new JsonArray(Vector.Select(d => (JsonNode)JsonValue.Create(d)!).ToArray()),
            ValueKind.List => new JsonArray(((IReadOnlyList<Value>)_ref!).Select(v => v.ToJson()).ToArray()),
            ValueKind.Object => ObjectToJson((Dictionary<string, Value>)_ref!),
            _ => null,
        };

        private static JsonObject ObjectToJson(Dictionary<string, Value> dict)
        {
            var o = new JsonObject();
            foreach (var p in dict) o[p.Key] = p.Value.ToJson();
            return o;
        }

        public bool SameAs(Value other)
        {
            if (Kind == ValueKind.Null || other.Kind == ValueKind.Null) return Kind == other.Kind;
            if ((Kind == ValueKind.Number || Kind == ValueKind.Bool) && (other.Kind == ValueKind.Number || other.Kind == ValueKind.Bool))
                return Kind == other.Kind && Math.Abs(_number - other._number) < 1e-9;
            if (Kind != other.Kind) return false;
            switch (Kind)
            {
                case ValueKind.String: return (string)_ref! == (string)other._ref!;
                case ValueKind.Vector:
                {
                    var a = Vector; var b = other.Vector;
                    if (a.Length != b.Length) return false;
                    for (int i = 0; i < a.Length; i++) if (Math.Abs(a[i] - b[i]) >= 1e-9) return false;
                    return true;
                }
                default: return JsonNode.DeepEquals(ToJson(), other.ToJson());
            }
        }

        public override string ToString() => Kind switch
        {
            ValueKind.Null => "null",
            ValueKind.Number => _number.ToString("0.####", CultureInfo.InvariantCulture),
            ValueKind.Bool => _number != 0 ? "true" : "false",
            ValueKind.String => (string)_ref!,
            _ => ToJson()?.ToJsonString() ?? "null",
        };
    }
}
