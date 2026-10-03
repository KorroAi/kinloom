using System;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Kinloom.Core;
using Xunit;

namespace Kinloom.Core.Tests
{
    /// <summary>Locks the exact seed-42 village story so that performance work cannot change behavior silently.</summary>
    public class GoldenTests
    {
        internal static string Fingerprint(Simulation sim)
        {
            string all = string.Join("\n", sim.World.Journal.Entries.Select(e => $"{e.Tick}|{e.Kind}|{e.AgentId}|{e.Text}|{e.CauseId}"));
            return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(all))).Substring(0, 16);
        }

        [Fact]
        public void Village_seed_42_story_is_unchanged()
        {
            var sim = ScenarioTests.RunVillage(42, 7 * World.TicksPerDay);
            Assert.Equal("9B90167E14ED5D23", Fingerprint(sim));
        }

        [Fact]
        public void Opinions_drift_toward_zero_scaled_by_forgiveness()
        {
            var mind = new Mind(new Personality(0.5f, 0.5f, 1f));
            mind.ShiftOpinion("a", -0.5f);
            mind.ShiftOpinion("b", 0.4f);
            mind.DriftOpinions(0.1f);
            Assert.Equal(-0.45, mind.OpinionOf("a"), 4);
            Assert.Equal(0.36, mind.OpinionOf("b"), 4);
        }
    }
}
