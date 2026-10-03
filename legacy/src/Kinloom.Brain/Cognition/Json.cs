using System.Collections.Generic;
using System.Globalization;
using System.Text.Json;

namespace Kinloom.Brain
{
    /// <summary>Tolerant readers for model output: models add code fences, change number types, drop fields.</summary>
    internal static class Json
    {
        public static JsonDocument? Parse(string text)
        {
            int start = text.IndexOf('{');
            int end = text.LastIndexOf('}');
            if (start < 0 || end <= start) return null;
            try { return JsonDocument.Parse(text.Substring(start, end - start + 1)); }
            catch (JsonException) { return null; }
        }

        public static string? Str(JsonElement e, string name)
        {
            if (e.ValueKind != JsonValueKind.Object || !e.TryGetProperty(name, out var v)) return null;
            switch (v.ValueKind)
            {
                case JsonValueKind.String: var s = v.GetString(); return string.IsNullOrWhiteSpace(s) || s == "null" ? null : s!.Trim();
                case JsonValueKind.Number: return v.GetRawText();
                case JsonValueKind.True: return "true";
                case JsonValueKind.False: return "false";
                default: return null;
            }
        }

        public static float? Num(JsonElement e, string name)
        {
            if (e.ValueKind != JsonValueKind.Object || !e.TryGetProperty(name, out var v)) return null;
            if (v.ValueKind == JsonValueKind.Number && v.TryGetDouble(out double d)) return (float)d;
            if (v.ValueKind == JsonValueKind.String && float.TryParse(v.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out float f)) return f;
            return null;
        }

        public static bool Bool(JsonElement e, string name) =>
            e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) && (v.ValueKind == JsonValueKind.True || (v.ValueKind == JsonValueKind.String && v.GetString() == "true"));

        public static IEnumerable<JsonElement> Arr(JsonElement e, string name)
        {
            if (e.ValueKind != JsonValueKind.Object || !e.TryGetProperty(name, out var v) || v.ValueKind != JsonValueKind.Array) yield break;
            foreach (var item in v.EnumerateArray()) yield return item;
        }

        public static JsonElement? Obj(JsonElement e, string name) =>
            e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Object ? v : (JsonElement?)null;

        public static IEnumerable<string> Strings(JsonElement e, string name)
        {
            foreach (var item in Arr(e, name))
                if (item.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(item.GetString())) yield return item.GetString()!.Trim();
        }

        /// <summary>"14:30", "14", "2pm" → minutes of day; null if unreadable.</summary>
        public static int? MinuteOfDay(string? time)
        {
            if (string.IsNullOrWhiteSpace(time)) return null;
            string t = time!.Trim().ToLowerInvariant();
            bool pm = t.EndsWith("pm"), am = t.EndsWith("am");
            if (pm || am) t = t.Substring(0, t.Length - 2).Trim();
            var parts = t.Split(':');
            if (!int.TryParse(parts[0], out int h)) return null;
            int m = 0;
            if (parts.Length > 1 && !int.TryParse(parts[1], out m)) return null;
            if (pm && h < 12) h += 12;
            if (am && h == 12) h = 0;
            if (h < 0 || h > 23 || m < 0 || m > 59) return null;
            return h * 60 + m;
        }
    }
}
