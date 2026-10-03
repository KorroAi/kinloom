using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Kinloom.Schema
{
    /// <summary>Small lenient readers over JsonNode used by the manifest parser.</summary>
    internal static class Json
    {
        public static JsonValueKind KindOf(JsonNode? node) => node switch
        {
            null => JsonValueKind.Null,
            JsonObject _ => JsonValueKind.Object,
            JsonArray _ => JsonValueKind.Array,
            _ => node.GetValueKind(),
        };

        public static string? Str(JsonObject o, string key) =>
            o[key] is JsonValue v && v.TryGetValue(out string? s) ? s : null;

        public static double? Num(JsonObject o, string key, string path, List<ManifestError> errors)
        {
            if (!o.ContainsKey(key) || o[key] == null) return null;
            if (KindOf(o[key]) == JsonValueKind.Number) return JsonNumber.ToDouble(o[key]!);
            errors.Add(new ManifestError(path + "." + key, "must be a number"));
            return null;
        }

        public static bool? Bool(JsonObject o, string key, string path, List<ManifestError> errors)
        {
            var kind = KindOf(o[key]);
            if (kind == JsonValueKind.Null) return null;
            if (kind == JsonValueKind.True) return true;
            if (kind == JsonValueKind.False) return false;
            errors.Add(new ManifestError(path + "." + key, "must be true or false"));
            return null;
        }

        public static IReadOnlyList<string> Strings(JsonObject o, string key, string path, List<ManifestError> errors)
        {
            var node = o[key];
            if (node == null) return new string[0];
            if (node is JsonValue single && single.TryGetValue(out string? one)) return new[] { one! };
            if (!(node is JsonArray a)) { errors.Add(new ManifestError(path + "." + key, "must be a list of strings")); return new string[0]; }
            var list = new List<string>();
            for (int i = 0; i < a.Count; i++)
            {
                if (a[i] is JsonValue v && v.TryGetValue(out string? s)) list.Add(s!);
                else errors.Add(new ManifestError($"{path}.{key}[{i}]", "must be a string"));
            }
            return list;
        }

        public static void UnknownKeys(JsonObject o, string path, List<ManifestError> errors, params string[] known)
        {
            foreach (var key in o.Select(p => p.Key))
                if (!known.Contains(key))
                    errors.Add(new ManifestError(path.Length == 0 ? key : path + "." + key, $"unknown field '{key}' (expected {string.Join(", ", known)})"));
        }
    }
}
