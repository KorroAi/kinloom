using System.Linq;
using Kinloom.Core;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class StoryTests
    {
        private static World NewWorld()
        {
            var w = new World(Helpers.Medieval(), 1);
            w.Add(new Place("shrine", "Shrine", new Vec2(0, 0), 3f));
            w.Add(new Place("forge", "Forge", new Vec2(30, 0), 3f));
            return w;
        }

        [Fact]
        public void An_item_remembers_its_rightful_owner_after_it_is_stolen()
        {
            var w = NewWorld();
            var jun = Helpers.Npc(w, "jun", 0, 0);
            var riku = Helpers.Npc(w, "riku", 1, 0);
            var relic = w.Add(new Item("relic", "Relic", new Vec2(0, 0), 60f, "jun"));
            Actions.PerformDeed(w, riku, "steal", "jun", "relic");
            Assert.Equal("riku", relic.OwnerId);
            Assert.Equal("jun", relic.RightfulOwnerId);
        }

        [Fact]
        public void A_quest_can_reward_an_item_the_giver_owns()
        {
            var w = NewWorld();
            var goro = Helpers.Npc(w, "goro", 30, 0);
            var hero = Helpers.Player(w, 29, 0);
            var ore = w.Add(new Item("ore", "Iron Ore", new Vec2(0, 0), 5f, "player"));
            var katana = w.Add(new Item("katana", "Katana", new Vec2(30, 0), 40f, "goro"));
            var q = w.Quests.Offer(w, "goro", QuestKinds.RetrieveItem, "goro", "ore", 0, "Bring me iron ore", null);
            q.RewardItemId = "katana";
            w.Quests.Accept(w, q.Id, "player");
            ore.OwnerId = "goro";
            new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true }.Step();
            Assert.Equal(QuestStatus.Completed, q.Status);
            Assert.Equal("player", katana.OwnerId);
        }

        [Fact]
        public void A_scheduled_quest_is_offered_at_its_time()
        {
            var w = NewWorld();
            Helpers.Npc(w, "jun", 0, 0);
            w.Quests.ScheduleOffer(World.TicksPerHour * 2, "jun", QuestKinds.Protect, "jun", null, 5, "Guard the shrine tonight", 10);
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            sim.Run(World.TicksPerHour);
            Assert.Empty(w.Quests.All);
            sim.Run(World.TicksPerHour + 1);
            Assert.Equal("Guard the shrine tonight", w.Quests.All.Single().Reason);
        }

        [Fact]
        public void Raiders_leave_story_items_alone_and_never_rob_each_other()
        {
            var w = NewWorld();
            var jun = Helpers.Npc(w, "jun", 0, 0);
            var relic = w.Add(new Item("relic", "Relic", new Vec2(0, 0), 60f, "jun", new[] { "story" }));
            var rice = w.Add(new Item("rice", "Rice", new Vec2(0, 0), 2f, "jun"));
            var a = w.Add(new Agent("jackal", "Jackal", new Vec2(0, 1), new Personality(1, 0, 0), false, new[] { WorldEvents.HostileTag }));
            var b = w.Add(new Agent("rat", "Rat", new Vec2(1, 1), new Personality(1, 0, 0), false, new[] { WorldEvents.HostileTag }));
            a.Present = b.Present = false;
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            WorldEvents.Start(w, WorldEvents.BanditRaid, "shrine", 12, "", null);
            Assert.DoesNotContain(a.Plan!.Steps, s => s.ItemId == "relic");
            sim.Run(4);
            Assert.Equal("jun", relic.OwnerId);
            Assert.Contains(rice.OwnerId, new[] { "jackal", "rat" }); // one of them took it, and kept it
            Assert.DoesNotContain(w.Journal.Entries, e => e.Kind == "deed" && e.Text.StartsWith("Rat steal -> Jackal") || e.Text.StartsWith("Jackal steal -> Rat"));
        }

        [Fact]
        public void Bandits_and_beasts_do_not_take_part_in_village_perception()
        {
            var w = NewWorld();
            var thug = Helpers.Npc(w, "thug", 0, 0);
            var bandit = w.Add(new Agent("viper", "Viper", new Vec2(1, 0), new Personality(1, 0, 0), false, new[] { WorldEvents.HostileTag }));
            Actions.PerformDeed(w, thug, "draw_weapon", null, null);
            Assert.Empty(bandit.Mind.Memories);
            Assert.Equal(IntentKind.Routine, bandit.Intent.Kind);
        }

        [Fact]
        public void Sleepers_at_home_see_nothing_at_night_when_sleep_is_on()
        {
            var w = NewWorld();
            w.Tuning.Sleep = true;
            var jun = Helpers.Npc(w, "jun", 0, 0);
            jun.HomePlaceId = "shrine";
            var riku = Helpers.Npc(w, "riku", 1, 0);
            w.Add(new Item("relic", "Relic", new Vec2(0, 0), 60f, "jun"));
            w.StartAt(World.TicksPerHour * 1); // 01:00
            Actions.PerformDeed(w, riku, "steal", "jun", "relic");
            Assert.Empty(jun.Mind.Memories);
        }

        [Fact]
        public void Awake_villagers_still_see_at_night()
        {
            var w = NewWorld();
            w.Tuning.Sleep = true;
            var jun = Helpers.Npc(w, "jun", 0, 0);
            jun.HomePlaceId = "forge"; // not at home: awake
            var riku = Helpers.Npc(w, "riku", 1, 0);
            w.Add(new Item("relic", "Relic", new Vec2(0, 0), 60f, "jun"));
            w.StartAt(World.TicksPerHour * 1);
            Actions.PerformDeed(w, riku, "steal", "jun", "relic");
            Assert.NotEmpty(jun.Mind.Memories);
        }
    }
}
