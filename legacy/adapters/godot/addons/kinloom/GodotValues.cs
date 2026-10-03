#nullable enable
using System.Globalization;
using System.Text.Json.Nodes;
using Godot;
using Kinloom;
using Kinloom.Schema;

namespace Kinloom.GodotAdapter
{
    /// <summary>Converts between Godot Variants and the JSON values Kinloom uses, guided by the declared field spec.</summary>
    internal static class GodotValues
    {
        public static JsonNode? ToJson(Variant v)
        {
            switch (v.VariantType)
            {
                case Variant.Type.Nil: return null;
                case Variant.Type.Bool: return JsonValue.Create(v.AsBool());
                case Variant.Type.Int: return JsonValue.Create(v.AsInt64());
                case Variant.Type.Float: return JsonValue.Create(v.AsDouble());
                case Variant.Type.String:
                case Variant.Type.StringName:
                case Variant.Type.NodePath: return JsonValue.Create(v.AsString());
                case Variant.Type.Vector2: { var x = v.AsVector2(); return new JsonArray(x.X, x.Y); }
                case Variant.Type.Vector2I: { var x = v.AsVector2I(); return new JsonArray(x.X, x.Y); }
                case Variant.Type.Vector3: { var x = v.AsVector3(); return new JsonArray(x.X, x.Y, x.Z); }
                case Variant.Type.Vector3I: { var x = v.AsVector3I(); return new JsonArray(x.X, x.Y, x.Z); }
                case Variant.Type.Color: { var c = v.AsColor(); return JsonValue.Create("#" + c.ToHtml(c.A < 1f)); }
                case Variant.Type.Dictionary:
                {
                    var o = new JsonObject();
                    foreach (var pair in v.AsGodotDictionary()) o[pair.Key.AsString()] = ToJson(pair.Value);
                    return o;
                }
                case Variant.Type.Array:
                {
                    var a = new JsonArray();
                    foreach (var item in v.AsGodotArray()) a.Add(ToJson(item));
                    return a;
                }
                case Variant.Type.PackedFloat32Array:
                case Variant.Type.PackedFloat64Array:
                case Variant.Type.PackedInt32Array:
                case Variant.Type.PackedInt64Array:
                case Variant.Type.PackedStringArray:
                {
                    var a = new JsonArray();
                    foreach (var item in v.AsGodotArray()) a.Add(ToJson(item));
                    return a;
                }
                case Variant.Type.Object:
                {
                    var obj = v.AsGodotObject();
                    return obj is Node n ? JsonValue.Create(n.Name.ToString()) : null;
                }
                default: return JsonValue.Create(v.ToString());
            }
        }

        public static Variant ToVariant(JsonNode? value, FieldSpec? spec)
        {
            if (value == null) return default;
            var kind = spec?.Kind ?? FieldKind.Any;
            switch (kind)
            {
                case FieldKind.Number: return JsonNumber.ToDouble(value);
                case FieldKind.Integer: return (long)JsonNumber.ToDouble(value);
                case FieldKind.Boolean: return value.GetValue<bool>();
                case FieldKind.String:
                case FieldKind.Enum:
                case FieldKind.Ref: return value.GetValue<string>();
                case FieldKind.Vec2: { var d = Numbers(value, 2); return new Vector2((float)d[0], (float)d[1]); }
                case FieldKind.Vec3: { var d = Numbers(value, 3); return new Vector3((float)d[0], (float)d[1], (float)d[2]); }
                case FieldKind.Color:
                {
                    if (value is JsonValue s && s.TryGetValue(out string? hex)) return Color.FromHtml(hex);
                    var d = Numbers(value, 4);
                    return new Color((float)d[0], (float)d[1], (float)d[2], value is JsonArray a && a.Count == 4 ? (float)d[3] : 1f);
                }
                default: return Generic(value);
            }
        }

        private static double[] Numbers(JsonNode value, int n)
        {
            var d = new double[n];
            if (value is JsonArray a) for (int i = 0; i < n && i < a.Count; i++) d[i] = a[i] is JsonNode item ? JsonNumber.ToDouble(item) : 0;
            else if (value is JsonObject o) { d[0] = o["x"] is JsonNode x ? JsonNumber.ToDouble(x) : 0; if (n > 1) d[1] = o["y"] is JsonNode y ? JsonNumber.ToDouble(y) : 0; if (n > 2) d[2] = o["z"] is JsonNode z ? JsonNumber.ToDouble(z) : 0; }
            return d;
        }

        private static Variant Generic(JsonNode value)
        {
            switch (value)
            {
                case JsonObject o:
                {
                    var dict = new global::Godot.Collections.Dictionary();
                    foreach (var p in o) dict[p.Key] = Generic(p.Value ?? JsonValue.Create(""));
                    return dict;
                }
                case JsonArray a:
                {
                    var arr = new global::Godot.Collections.Array();
                    foreach (var item in a) arr.Add(item == null ? default : Generic(item));
                    return arr;
                }
                default:
                {
                    var kind = value.GetValueKind();
                    if (kind == System.Text.Json.JsonValueKind.Number) return JsonNumber.ToDouble(value);
                    if (kind == System.Text.Json.JsonValueKind.True) return true;
                    if (kind == System.Text.Json.JsonValueKind.False) return false;
                    if (kind == System.Text.Json.JsonValueKind.String) return value.GetValue<string>();
                    return default;
                }
            }
        }

        public static JsonObject ToJsonObject(global::Godot.Collections.Dictionary dict)
        {
            var o = new JsonObject();
            foreach (var pair in dict) o[pair.Key.AsString()] = ToJson(pair.Value);
            return o;
        }

        public static string Number(double d) => d.ToString("0.####", CultureInfo.InvariantCulture);
    }
}
