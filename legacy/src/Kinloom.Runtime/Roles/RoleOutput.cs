using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Kinloom.Roles
{
    /// <summary>What a model answered, normalized: tool calls, an optional private thought, or plain prose.</summary>
    internal sealed class RoleOutput
    {
        /// <summary>Spoken lines never contain these; prose that does is broken JSON, not something to say.</summary>
        private static readonly char[] JsonMarks = { '{', '}', '[', ']' };

        public List<(string tool, JsonObject args)> Actions { get; } = new List<(string, JsonObject)>();
        public string? Thought { get; private set; }
        /// <summary>The whole answer when it was not JSON at all.</summary>
        public string? Prose { get; private set; }
        /// <summary>Set when the answer tried to be JSON but could not be read.</summary>
        public string? Error { get; private set; }

        /// <summary>Accepts canonical JSON (<c>{"thought","actions"}</c>), <c>{"say": ...}</c>, a single <c>{"tool","args"}</c>,
        /// a bare array of actions, JSON wrapped in code fences or chatter, or prose.</summary>
        public static RoleOutput Parse(string text)
        {
            var output = new RoleOutput();
            var node = FindJson(text);
            if (node == null)
            {
                string t = text.Trim();
                if (t.Length == 0) output.Error = "the answer was empty";
                else if (t.IndexOfAny(JsonMarks) >= 0 || t.Contains("```") || t.Contains("\"actions\""))
                    output.Error = "the answer looked like JSON but could not be parsed";
                else if (t.Any(c => char.IsControl(c) && c != '\n' && c != '\r' && c != '\t'))
                    output.Error = "the answer contained unreadable characters";
                else output.Prose = t;
                return output;
            }
            if (node is JsonArray list) { AddActions(output, list); return output; }
            if (node is JsonObject o)
            {
                if (o["thought"] is JsonValue t && t.TryGetValue(out string? thought)) output.Thought = thought;
                if (o["say"] is JsonValue s && s.TryGetValue(out string? say) && !string.IsNullOrWhiteSpace(say))
                    output.Actions.Add(("say", new JsonObject { ["text"] = say }));
                if (o["actions"] is JsonArray actions) AddActions(output, actions);
                else if (o["tool"] != null) AddActions(output, new JsonArray(o.DeepClone()));
            }
            return output;
        }

        private static void AddActions(RoleOutput output, JsonArray list)
        {
            foreach (var item in list)
            {
                if (!(item is JsonObject a)) { output.Actions.Add(("?", new JsonObject { ["_raw"] = item?.ToJsonString() })); continue; }
                string tool = a["tool"] is JsonValue v && v.TryGetValue(out string? name) ? name! : a["name"] is JsonValue n && n.TryGetValue(out string? alt) ? alt! : "?";
                var args = a["args"] as JsonObject ?? a["arguments"] as JsonObject ?? a["input"] as JsonObject;
                if (args == null)
                {
                    // Lenient: {"tool":"say","text":"hi"} — arguments inline.
                    args = new JsonObject();
                    foreach (var p in a) if (p.Key != "tool" && p.Key != "name") args[p.Key] = p.Value?.DeepClone();
                }
                output.Actions.Add((tool, (JsonObject)args.DeepClone()));
            }
        }

        /// <summary>The first JSON object or array in a model answer (inside code fences or chatter), or null.</summary>
        internal static JsonNode? FindJson(string text)
        {
            string t = text.Trim();
            int fence = t.IndexOf("```", System.StringComparison.Ordinal);
            if (fence >= 0)
            {
                int start = t.IndexOf('\n', fence);
                int end = start < 0 ? -1 : t.IndexOf("```", start, System.StringComparison.Ordinal);
                if (start >= 0 && end > start) t = t.Substring(start + 1, end - start - 1).Trim();
            }
            foreach (char open in new[] { '{', '[' })
            {
                int i = t.IndexOf(open);
                int j = t.LastIndexOf(open == '{' ? '}' : ']');
                if (i < 0 || j <= i) continue;
                try { return JsonNode.Parse(t.Substring(i, j - i + 1)); }
                catch (JsonException) { }
            }
            return null;
        }
    }
}
