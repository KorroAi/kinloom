using System;
using System.Collections.Generic;

namespace Kinloom.Core
{
    public sealed class JournalEntry
    {
        public JournalEntry(int id, int tick, string kind, string? agentId, string text, int? causeId, string? targetId = null)
        {
            Id = id;
            Tick = tick;
            Kind = kind;
            AgentId = agentId;
            Text = text;
            CauseId = causeId;
            TargetId = targetId;
        }

        public int Id { get; }
        public int Tick { get; }
        public string Kind { get; }
        public string? AgentId { get; }
        public string Text { get; }
        public int? CauseId { get; }
        /// <summary>The other agent involved, if any (who was met, attacked, told...).</summary>
        public string? TargetId { get; }
    }

    /// <summary>Append-only causal log. A cause always has a smaller id, so Why() always terminates.</summary>
    public sealed class Journal
    {
        private readonly List<JournalEntry> _entries = new List<JournalEntry>();

        public IReadOnlyList<JournalEntry> Entries => _entries;

        public int Add(int tick, string kind, string? agentId, string text, int? causeId = null, string? targetId = null)
        {
            if (causeId.HasValue && (causeId.Value < 0 || causeId.Value >= _entries.Count))
                throw new ArgumentOutOfRangeException(nameof(causeId), $"Cause #{causeId} does not exist yet");
            var entry = new JournalEntry(_entries.Count, tick, kind, agentId, text, causeId, targetId);
            _entries.Add(entry);
            return entry.Id;
        }

        public JournalEntry Get(int id) => _entries[id];

        public List<JournalEntry> Why(int entryId)
        {
            var chain = new List<JournalEntry>();
            int? current = entryId;
            while (current.HasValue && current.Value >= 0 && current.Value < _entries.Count)
            {
                var entry = _entries[current.Value];
                chain.Add(entry);
                current = entry.CauseId;
            }
            return chain;
        }
    }
}
