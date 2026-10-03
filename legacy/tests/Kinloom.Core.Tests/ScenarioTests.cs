using System;
using System.IO;
using System.Linq;
using Kinloom.Core;
using Kinloom.Sim;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class ScenarioTests
    {
        internal static string Root()
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null && !File.Exists(Path.Combine(dir.FullName, "packs", "medieval.pack.json"))) dir = dir.Parent;
            return dir?.FullName ?? throw new InvalidOperationException("Repository root not found");
        }

        internal static PackDefinition Pack() => ScenarioLoader.LoadPack(Path.Combine(Root(), "packs", "medieval.pack.json"));
        internal static ScenarioDefinition Village() => ScenarioLoader.LoadScenario(Path.Combine(Root(), "scenarios", "village.json"));

        internal static Simulation RunVillage(int seed, int ticks)
        {
            var scenario = Village();
            scenario.Seed = seed;
            var sim = ScenarioLoader.Build(scenario, Pack());
            sim.Run(ticks);
            return sim;
        }

        private const int Week = 7 * World.TicksPerDay;

        [Fact]
        public void Village_runs_a_full_week_without_script_errors()
        {
            var sim = RunVillage(42, Week);
            Assert.Equal(Week, sim.World.Tick);
            Assert.DoesNotContain(sim.World.Journal.Entries, e => e.Kind == "error");
            Assert.DoesNotContain(sim.World.Journal.Entries, e => e.Kind == "warning");
        }

        [Fact]
        public void Baker_saw_the_theft_and_the_bread_came_back()
        {
            var sim = RunVillage(42, Week);
            Assert.Contains(sim.World.GetAgent("baker").Mind.Memories, m => m.Kind == "steal" && m.Firsthand);
            Assert.Equal("baker", sim.World.FindItem("bread")!.OwnerId);
        }

        [Fact]
        public void Theft_rumor_reaches_the_smith_secondhand_in_most_seeds()
        {
            int hits = 0;
            for (int seed = 1; seed <= 50; seed++)
            {
                var smith = RunVillage(seed, 2 * World.TicksPerDay).World.GetAgent("smith");
                if (smith.Mind.Memories.Any(m => m.Kind == "steal" && !m.Firsthand)) hits++;
            }
            Assert.True(hits >= 45, $"Smith heard the rumor in only {hits}/50 seeds");
        }

        [Fact]
        public void Smith_overcharges_the_thief_on_day_two_in_most_seeds()
        {
            int hits = 0;
            for (int seed = 1; seed <= 50; seed++)
            {
                var sim = RunVillage(seed, 2 * World.TicksPerDay);
                if (sim.Trades.Any(t => t.TraderId == "smith" && World.DayOf(t.Tick) == 2 && !t.Result.Refused && t.Result.Price > 10f)) hits++;
            }
            Assert.True(hits >= 45, $"Smith overcharged in only {hits}/50 seeds");
        }

        [Fact]
        public void Scenario_frame_interval_is_applied_and_validated()
        {
            var scenario = Village();
            scenario.FrameInterval = 6;
            var sim = ScenarioLoader.Build(scenario, Pack());
            sim.Run(World.TicksPerDay);
            Assert.Equal(World.TicksPerDay / 6, sim.Frames.Count);

            scenario.FrameInterval = 0;
            Assert.Contains("frameInterval", Assert.Throws<ScenarioException>(() => ScenarioLoader.Build(scenario, Pack())).Message);
        }

        [Fact]
        public void Paying_the_baker_improves_her_opinion()
        {
            int payTick = 5 * World.TicksPerDay + 11 * World.TicksPerHour;
            float before = RunVillage(42, payTick).World.GetAgent("baker").Mind.OpinionOf("player");
            float after = RunVillage(42, payTick + 2).World.GetAgent("baker").Mind.OpinionOf("player");
            Assert.True(after > before, $"before {before}, after {after}");
        }

        [Fact]
        public void Same_seed_same_story()
        {
            var a = RunVillage(7, World.TicksPerDay * 2);
            var b = RunVillage(7, World.TicksPerDay * 2);
            Assert.Equal(a.World.Journal.Entries.Select(e => e.Text), b.World.Journal.Entries.Select(e => e.Text));
        }

        [Fact]
        public void Unknown_place_in_a_schedule_names_the_agent_and_the_place()
        {
            var scenario = Village();
            scenario.Agents[0].Schedule.Add(new SlotDef { Hour = 12, Place = "nowhere" });
            var ex = Assert.Throws<ScenarioException>(() => ScenarioLoader.Build(scenario, Pack()));
            Assert.Contains("nowhere", ex.Message);
            Assert.Contains(scenario.Agents[0].Id, ex.Message);
        }

        [Fact]
        public void Unknown_deed_in_the_script_names_the_step_and_the_deed()
        {
            var scenario = Village();
            scenario.Script[1].Deed = "stael";
            var ex = Assert.Throws<ScenarioException>(() => ScenarioLoader.Build(scenario, Pack()));
            Assert.Contains("stael", ex.Message);
            Assert.Contains("Script step 2", ex.Message);
        }

        [Fact]
        public void Misspelled_json_keys_are_rejected_with_their_name()
        {
            string scenario = Path.GetTempFileName();
            File.WriteAllText(scenario, "{ \"seed\": 1, \"days\": 1, \"agents\": [ { \"id\": \"a\", \"name\": \"A\", \"shedule\": [] } ] }");
            Assert.Contains("shedule", Assert.Throws<ScenarioException>(() => ScenarioLoader.LoadScenario(scenario)).Message);

            string pack = Path.GetTempFileName();
            File.WriteAllText(pack, "{ \"name\": \"p\", \"deeds\": [ { \"kind\": \"steal\", \"valance\": -0.8 } ] }");
            Assert.Contains("valance", Assert.Throws<ScenarioException>(() => ScenarioLoader.LoadPack(pack)).Message);
        }

        [Theory]
        [InlineData("{ \"name\": \"p\", \"deeds\": [ { \"kind\": \"\", \"valence\": 0 } ] }", "empty kind")]
        [InlineData("{ \"name\": \"p\", \"deeds\": [ { \"kind\": \"a\" }, { \"kind\": \"a\" } ] }", "'a' is defined twice")]
        [InlineData("{ \"name\": \"p\", \"deeds\": [ { \"kind\": \"a\", \"valence\": 1.5 } ] }", "'a': valence")]
        [InlineData("{ \"name\": \"p\", \"deeds\": [ { \"kind\": \"a\", \"threat\": -0.1 } ] }", "'a': threat")]
        [InlineData("{ \"name\": \"p\", \"deeds\": [ { \"kind\": \"a\", \"radius\": -1 } ] }", "'a': radius")]
        public void Invalid_pack_values_are_rejected_with_the_deed_named(string json, string expected)
        {
            string pack = Path.GetTempFileName();
            File.WriteAllText(pack, json);
            var ex = Assert.Throws<ScenarioException>(() => ScenarioLoader.LoadPack(pack));
            Assert.Contains(expected, ex.Message);
        }

        [Fact]
        public void Missing_file_and_bad_json_give_readable_errors()
        {
            Assert.Contains("not found", Assert.Throws<ScenarioException>(() => ScenarioLoader.LoadPack("does-not-exist.json")).Message);
            string bad = Path.GetTempFileName();
            File.WriteAllText(bad, "{ not json");
            Assert.Contains("Invalid JSON", Assert.Throws<ScenarioException>(() => ScenarioLoader.LoadScenario(bad)).Message);
        }
    }
}
