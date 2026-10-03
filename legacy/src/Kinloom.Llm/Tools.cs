using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Kinloom.Llm
{
    /// <summary>A function the model may call. Parameters are a JSON Schema object.</summary>
    public sealed class LlmTool
    {
        public LlmTool(string name, string description, JsonObject parameters)
        {
            Name = name;
            Description = description;
            Parameters = parameters;
        }

        public string Name { get; }
        public string Description { get; }
        public JsonObject Parameters { get; }
    }

    /// <summary>Normalizes native tool calls from any provider into one canonical JSON text:
    /// <c>{"thought": "...", "actions": [{"tool": "name", "args": {...}}]}</c>. Free text next to tool calls is a private
    /// thought (speech goes through a tool), so a model never says its reasoning out loud. Consumers parse a single format.</summary>
    public static class ToolCanon
    {
        public static string Canonical(string? text, IEnumerable<(string name, string argsJson)> calls)
        {
            var root = new JsonObject();
            if (!string.IsNullOrWhiteSpace(text)) root["thought"] = text!.Trim();
            var actions = new JsonArray();
            foreach (var (name, argsJson) in calls)
            {
                JsonNode? args;
                try { args = string.IsNullOrWhiteSpace(argsJson) ? new JsonObject() : JsonNode.Parse(argsJson); }
                catch (JsonException) { args = null; }
                if (!(args is JsonObject)) args = new JsonObject { ["_raw"] = argsJson }; // kept for the repair prompt
                actions.Add(new JsonObject { ["tool"] = name, ["args"] = args });
            }
            root["actions"] = actions;
            return root.ToJsonString();
        }
    }
}
