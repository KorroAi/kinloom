using System.IO;
using System.Linq;
using Kinloom.Core;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class ScenarioV2Tests
    {
        private static Simulation Load(string json)
        {
            string path = Path.Combine(Path.GetTempPath(), $"kinloom-scn-{System.Guid.NewGuid():N}.json");
            File.WriteAllText(path, json);
            try { return ScenarioLoader.Build(ScenarioLoader.LoadScenario(path), Helpers.Medieval()); }
            finally { File.Delete(path); }
        }

        private const string Base = @"
          ""places"": [ { ""id"": ""shrine"", ""name"": ""Shrine"", ""x"": 0, ""y"": 0 }, { ""id"": ""camp"", ""name"": ""Camp"", ""x"": 30, ""y"": 0 } ],
          ""items"": [ { ""id"": ""relic"", ""name"": ""Relic"", ""place"": ""shrine"", ""value"": 60, ""owner"": ""jun"" } ],";

        [Fact]
        public void Fixed_plans_quests_and_rules_are_loaded()
        {
            var sim = Load(@"{ ""arrests"": true, ""sleep"": true," + Base + @"
              ""agents"": [
                { ""id"": ""jun"", ""name"": ""Jun"", ""x"": 0, ""y"": 0, ""gold"": 50 },
                { ""id"": ""riku"", ""name"": ""Riku"", ""x"": 1, ""y"": 0,
                  ""fixedPlans"": [ { ""day"": 2, ""until"": ""03:00"", ""intention"": ""Steal the relic"",
                    ""steps"": [ { ""time"": ""01:00"", ""verb"": ""steal"", ""target"": ""jun"", ""item"": ""relic"" }, { ""time"": ""02:00"", ""verb"": ""goto"", ""target"": ""camp"" } ] } ] }
              ],
              ""quests"": [ { ""giver"": ""jun"", ""kind"": ""retrieve_item"", ""target"": ""riku"", ""item"": ""relic"", ""reward"": 40, ""text"": ""Find the relic"", ""day"": 2, ""hour"": 6 } ]
            }");
            var w = sim.World;
            Assert.True(w.Tuning.Arrests);
            Assert.True(w.Tuning.Sleep);
            var plan = w.GetAgent("riku").FixedPlans.Single();
            Assert.Equal(2, plan.Day);
            Assert.Equal(180, plan.UntilMinute);
            Assert.Equal(new[] { "steal", "goto" }, plan.Steps.Select(s => s.Verb));
            sim.Run(World.TicksPerDay + 6 * World.TicksPerHour + 1);
            Assert.Equal("Find the relic", w.Quests.All.Single().Reason);
        }

        [Fact]
        public void A_bad_verb_in_a_fixed_plan_is_reported()
        {
            var e = Assert.Throws<ScenarioException>(() => Load(@"{" + Base + @"
              ""agents"": [ { ""id"": ""jun"", ""name"": ""Jun"", ""x"": 0, ""y"": 0,
                ""fixedPlans"": [ { ""day"": 1, ""steps"": [ { ""time"": ""01:00"", ""verb"": ""fly"", ""target"": ""camp"" } ] } ] } ] }"));
            Assert.Contains("fly", e.Message);
        }

        [Fact]
        public void A_quest_with_an_unknown_giver_is_reported()
        {
            var e = Assert.Throws<ScenarioException>(() => Load(@"{" + Base + @"
              ""agents"": [ { ""id"": ""jun"", ""name"": ""Jun"", ""x"": 0, ""y"": 0 } ],
              ""quests"": [ { ""giver"": ""nobody"", ""kind"": ""slay"", ""target"": ""jun"", ""text"": ""?"" } ] }"));
            Assert.Contains("nobody", e.Message);
        }
    }
}
