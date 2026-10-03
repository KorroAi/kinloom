using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Kinloom.Llm
{
    /// <summary>Loads a scripted model from a JSON file: <c>{"task name": ["answer", {...}], "*": [...]}</c>.
    /// Answers are consumed in order per task; "*" serves any task whose own queue is empty. Objects are sent as JSON text.
    /// Used by headless checks and <c>kinloom test</c> so integrations are proven without spending tokens.</summary>
    public static class ScriptFile
    {
        public static ScriptedLlmClient Load(string path) => Parse(File.ReadAllText(path));

        public static ScriptedLlmClient Parse(string json)
        {
            var queues = new Dictionary<string, Queue<string>>();
            if (!(JsonNode.Parse(json) is JsonObject root)) throw new JsonException("A script file must be a JSON object of task → answers.");
            foreach (var pair in root)
            {
                var queue = new Queue<string>();
                if (pair.Value is JsonArray answers)
                    foreach (var answer in answers) queue.Enqueue(Text(answer));
                else queue.Enqueue(Text(pair.Value));
                queues[pair.Key] = queue;
            }
            return new ScriptedLlmClient(request =>
            {
                if (queues.TryGetValue(request.Task, out var own) && own.Count > 0) return own.Dequeue();
                if (queues.TryGetValue("*", out var any) && any.Count > 0) return any.Dequeue();
                return null;
            });
        }

        private static string Text(JsonNode? node) =>
            node is JsonValue value && value.TryGetValue(out string? s) ? s ?? "" : node?.ToJsonString() ?? "null";
    }
}
