using System;
using System.Collections.Generic;
using System.Linq;
using Kinloom.Core;

namespace Kinloom.Brain
{
    /// <summary>Models say "Forge", "[forge]" or "the bakery" when they mean an id. Resolve leniently, but only to one real entity.</summary>
    public static class Ids
    {
        public static string? Place(World w, string? raw) => Resolve(raw, w.Places.Select(p => (p.Id, p.Name)));

        public static string? Agent(World w, string? raw) => Resolve(raw, w.Agents.Select(a => (a.Id, a.Name)));

        public static string? Item(World w, string? raw) => Resolve(raw, w.Items.Select(i => (i.Id, i.Name)));

        private static string? Resolve(string? raw, IEnumerable<(string Id, string Name)> candidates)
        {
            if (string.IsNullOrWhiteSpace(raw)) return null;
            string key = Normalize(raw!);
            var list = candidates.ToList();
            foreach (var c in list) if (string.Equals(c.Id, raw!.Trim(), StringComparison.Ordinal)) return c.Id;
            foreach (var c in list) if (Normalize(c.Id) == key || Normalize(c.Name) == key) return c.Id;
            var partial = list.Where(c => key.Length >= 3 && (Normalize(c.Name).Contains(key) || key.Contains(Normalize(c.Name)) || Normalize(c.Id).Contains(key))).ToList();
            return partial.Count == 1 ? partial[0].Id : null;
        }

        private static string Normalize(string s)
        {
            s = s.Trim().Trim('[', ']', '"', '\'').ToLowerInvariant().Replace('_', ' ');
            if (s.StartsWith("the ")) s = s.Substring(4);
            return s.Trim();
        }
    }
}
