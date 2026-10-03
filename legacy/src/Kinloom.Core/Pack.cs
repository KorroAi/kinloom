using System.Collections.Generic;

namespace Kinloom.Core
{
    /// <summary>A kind of deed in a genre pack. Settable properties so JSON loaders can fill it.</summary>
    public sealed class DeedDefinition
    {
        public string Kind { get; set; } = "";
        public float Valence { get; set; }
        public float Threat { get; set; }
        public float Radius { get; set; } = 10f;
        public bool IsCrime { get; set; }
        public bool TransfersItem { get; set; }
    }

    public sealed class PackDefinition
    {
        public string Name { get; set; } = "";
        public List<DeedDefinition> Deeds { get; set; } = new List<DeedDefinition>();
        public Dictionary<string, List<string>> Barks { get; set; } = new Dictionary<string, List<string>>();
        /// <summary>Barks in other languages: language code -> bark key -> lines.</summary>
        public Dictionary<string, Dictionary<string, List<string>>> LocalizedBarks { get; set; } = new Dictionary<string, Dictionary<string, List<string>>>();

        /// <summary>Switches barks to a language (keys it lacks keep their original lines). False if the pack has no such language.</summary>
        public bool UseLanguage(string code)
        {
            if (!LocalizedBarks.TryGetValue(code, out var lines)) return false;
            foreach (var kv in lines) Barks[kv.Key] = kv.Value;
            return true;
        }

        public bool HasDeed(string? kind)
        {
            foreach (var d in Deeds) if (d.Kind == kind) return true;
            return false;
        }

        public DeedDefinition Deed(string kind)
        {
            foreach (var d in Deeds) if (d.Kind == kind) return d;
            throw new KeyNotFoundException($"Unknown deed '{kind}' in pack '{Name}'");
        }

        public string? Bark(string key, DeterministicRandom random)
        {
            if (!Barks.TryGetValue(key, out var lines) || lines.Count == 0) return null;
            return lines[(int)(random.NextUInt() % (uint)lines.Count)];
        }
    }
}
