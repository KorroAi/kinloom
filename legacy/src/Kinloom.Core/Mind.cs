using System.Collections.Generic;

namespace Kinloom.Core
{
    public sealed class Mind
    {
        private readonly Dictionary<string, float> _opinions = new Dictionary<string, float>();
        private readonly List<string> _opinionKeys = new List<string>(); // insertion order, avoids a per-tick copy in DriftOpinions
        private readonly Dictionary<string, int> _opinionCauses = new Dictionary<string, int>();
        private readonly Dictionary<string, Memory> _byKey = new Dictionary<string, Memory>();

        public Mind(Personality personality)
        {
            Personality = personality;
        }

        public Personality Personality { get; }
        public Emotions Emotions { get; } = new Emotions();
        public List<Memory> Memories { get; } = new List<Memory>();
        public HashSet<string> HandledCrimes { get; } = new HashSet<string>();

        public float OpinionOf(string agentId) => _opinions.TryGetValue(agentId, out var v) ? v : 0f;

        public void ShiftOpinion(string agentId, float delta)
        {
            if (!_opinions.TryGetValue(agentId, out float current)) _opinionKeys.Add(agentId);
            float v = current + delta;
            _opinions[agentId] = v < -1f ? -1f : (v > 1f ? 1f : v);
        }

        /// <summary>Journal entry of the last opinion change about this agent (for why-chains).</summary>
        public int? OpinionCause(string agentId) => _opinionCauses.TryGetValue(agentId, out var id) ? id : (int?)null;

        public void SetOpinionCause(string agentId, int entryId) => _opinionCauses[agentId] = entryId;

        public bool Remembers(string key) => _byKey.ContainsKey(key);

        public Memory? Recall(string? key) => key != null && _byKey.TryGetValue(key, out var m) ? m : null;

        public bool AddMemory(Memory memory)
        {
            if (_byKey.ContainsKey(memory.Key)) return false;
            _byKey[memory.Key] = memory;
            Memories.Add(memory);
            return true;
        }

        public Memory? CrimeBy(string actorId, float minConfidence)
        {
            Memory? best = null;
            foreach (var m in Memories)
            {
                if (!m.IsCrime || m.ActorId != actorId || m.Confidence < minConfidence) continue;
                if (HandledCrimes.Contains(m.Key)) continue;
                if (best == null || m.DeedTick > best.DeedTick) best = m;
            }
            return best;
        }

        public void DriftOpinions(float rate)
        {
            float factor = 1f - rate * Personality.Forgiveness;
            for (int i = 0; i < _opinionKeys.Count; i++) _opinions[_opinionKeys[i]] *= factor;
        }
    }
}
