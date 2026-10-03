using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Kinloom
{
    /// <summary>One line of the session's journal: what happened, who proposed what, what was refused and why.</summary>
    public sealed class JournalEntry
    {
        public JournalEntry(double time, string kind, string source, string text, JsonNode? data = null)
        {
            Time = time;
            Kind = kind;
            Source = source;
            Text = text;
            Data = data;
        }

        public long Seq { get; internal set; }
        public double Time { get; }
        /// <summary>event, effect, resolved, refused, dropped, call, reply, say, memory, behavior, fallback, error, note.</summary>
        public string Kind { get; }
        public string Source { get; }
        public string Text { get; }
        public JsonNode? Data { get; }

        public JsonObject ToJson() => new JsonObject
        {
            ["seq"] = Seq, ["time"] = Time, ["kind"] = Kind, ["source"] = Source, ["text"] = Text, ["data"] = Data?.DeepClone(),
        };

        public override string ToString() => $"[{Time:0.0}] {Kind} {Source}: {Text}";
    }

    /// <summary>A bounded ring of journal entries. Thread-safe; <see cref="Added"/> fires after each entry.</summary>
    public sealed class Journal
    {
        private readonly JournalEntry?[] _ring;
        private readonly object _lock = new object();
        private long _next;

        public Journal(int capacity = 2000) { _ring = new JournalEntry?[Math.Max(1, capacity)]; }

        public int Capacity => _ring.Length;
        public event Action<JournalEntry>? Added;

        public void Add(JournalEntry entry)
        {
            lock (_lock)
            {
                entry.Seq = ++_next;
                _ring[(int)((entry.Seq - 1) % _ring.Length)] = entry;
            }
            Added?.Invoke(entry);
        }

        /// <summary>The last <paramref name="n"/> entries, oldest first.</summary>
        public IReadOnlyList<JournalEntry> Recent(int n)
        {
            lock (_lock)
            {
                var list = new List<JournalEntry>();
                long count = Math.Min(Math.Min(n, _ring.Length), _next);
                for (long seq = _next - count + 1; seq <= _next; seq++)
                {
                    var e = _ring[(int)((seq - 1) % _ring.Length)];
                    if (e != null) list.Add(e);
                }
                return list;
            }
        }
    }
}
