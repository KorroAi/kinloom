using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

namespace Kinloom.Memory
{
    /// <summary>Something remembered: an event noticed, a refusal, a note a role chose to keep.</summary>
    public sealed class MemoryEntry
    {
        public MemoryEntry(double time, string text, double importance, IEnumerable<string>? tags = null, IEnumerable<string>? refs = null)
        {
            Time = time;
            Text = text;
            Importance = Math.Max(0, Math.Min(1, importance));
            Tags = tags?.ToArray() ?? Array.Empty<string>();
            Refs = refs?.ToArray() ?? Array.Empty<string>();
        }

        public double Time { get; internal set; }
        public string Text { get; }
        public double Importance { get; }
        public IReadOnlyList<string> Tags { get; }
        /// <summary>Thing ids this memory is about.</summary>
        public IReadOnlyList<string> Refs { get; }

        internal JsonObject ToJson() => new JsonObject
        {
            ["time"] = Time, ["text"] = Text, ["importance"] = Importance,
            ["tags"] = new JsonArray(Tags.Select(t => (JsonNode)JsonValue.Create(t)!).ToArray()),
            ["refs"] = new JsonArray(Refs.Select(t => (JsonNode)JsonValue.Create(t)!).ToArray()),
        };

        internal static MemoryEntry FromJson(JsonObject o) => new MemoryEntry(
            o["time"] is JsonNode t ? JsonNumber.ToDouble(t) : 0,
            o["text"]?.GetValue<string>() ?? "",
            o["importance"] is JsonNode i ? JsonNumber.ToDouble(i) : 0.5,
            (o["tags"] as JsonArray)?.Select(x => x?.GetValue<string>() ?? ""),
            (o["refs"] as JsonArray)?.Select(x => x?.GetValue<string>() ?? ""));
    }

    /// <summary>Scoped memories (<c>role:&lt;id&gt;</c>, <c>thing:&lt;id&gt;</c>, <c>shared</c>) with ranked recall:
    /// 0.4 × importance + 0.3 × recency (half-life 10 game minutes) + 0.3 × keyword overlap with the query.</summary>
    public sealed class MemoryStore
    {
        public const double HalfLife = 600;
        private static readonly HashSet<string> Stop = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "the", "and", "for", "with", "that", "this", "you", "your", "are", "was", "has", "have", "not", "but", "from", "they", "them", "its", "into", "who", "what",
        };

        private readonly Dictionary<string, List<MemoryEntry>> _scopes = new Dictionary<string, List<MemoryEntry>>();
        private readonly object _lock = new object();

        public IReadOnlyCollection<string> Scopes { get { lock (_lock) return _scopes.Keys.ToList(); } }

        public void Add(string scope, MemoryEntry entry, int max)
        {
            lock (_lock)
            {
                if (!_scopes.TryGetValue(scope, out var list)) _scopes[scope] = list = new List<MemoryEntry>();
                list.Add(entry);
                while (list.Count > Math.Max(1, max))
                {
                    // Evict the least important; among equals, the oldest.
                    var victim = list.OrderBy(m => m.Importance).ThenBy(m => m.Time).First();
                    list.Remove(victim);
                }
            }
        }

        public IReadOnlyList<MemoryEntry> All(string scope)
        {
            lock (_lock) return _scopes.TryGetValue(scope, out var list) ? list.ToList() : new List<MemoryEntry>();
        }

        public IReadOnlyList<MemoryEntry> Recall(string scope, string query, int k, double now)
        {
            lock (_lock)
            {
                if (!_scopes.TryGetValue(scope, out var list) || list.Count == 0) return new List<MemoryEntry>();
                var words = Words(query);
                return list
                    .Select(m => (m, score: 0.4 * m.Importance + 0.3 * Math.Pow(0.5, Math.Max(0, now - m.Time) / HalfLife) + 0.3 * Overlap(words, m.Text)))
                    .OrderByDescending(x => x.score).ThenByDescending(x => x.m.Time)
                    .Take(k).Select(x => x.m).ToList();
            }
        }

        public void Clear(string scope) { lock (_lock) _scopes.Remove(scope); }

        private static double Overlap(HashSet<string> query, string text)
        {
            if (query.Count == 0) return 0;
            int hits = Words(text).Count(query.Contains);
            return Math.Min(1, (double)hits / query.Count);
        }

        internal static HashSet<string> Words(string text) =>
            new HashSet<string>(text.ToLowerInvariant().Split(new[] { ' ', ',', '.', '!', '?', ';', ':', '"', '\'', '(', ')', '\n', '\t', '-', '_' }, StringSplitOptions.RemoveEmptyEntries)
                .Where(w => w.Length >= 3 && !Stop.Contains(w)));

        internal JsonObject ToJson(Func<string, bool> include)
        {
            lock (_lock)
            {
                var o = new JsonObject();
                foreach (var scope in _scopes.Where(s => include(s.Key)))
                    o[scope.Key] = new JsonArray(scope.Value.Select(m => (JsonNode)m.ToJson()).ToArray());
                return o;
            }
        }

        internal void Load(JsonObject o, double timeShift)
        {
            lock (_lock)
            {
                _scopes.Clear();
                foreach (var scope in o)
                {
                    var list = new List<MemoryEntry>();
                    foreach (var item in scope.Value as JsonArray ?? new JsonArray())
                        if (item is JsonObject m) { var entry = MemoryEntry.FromJson(m); entry.Time += timeShift; list.Add(entry); }
                    _scopes[scope.Key] = list;
                }
            }
        }
    }
}
