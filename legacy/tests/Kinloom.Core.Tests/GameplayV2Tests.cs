using System.Linq;
using Kinloom.Core;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class GameplayV2Tests
    {
        private static World NewWorld()
        {
            var w = new World(Helpers.Medieval(), 1);
            w.Pack.Deeds.Add(new DeedDefinition { Kind = "give", Valence = 0.5f, Radius = 5f });
            w.Pack.Deeds.Add(new DeedDefinition { Kind = "attack", Valence = -0.9f, Threat = 0.9f, Radius = 10f, IsCrime = true });
            w.Add(new Place("shrine", "Shrine", new Vec2(0, 0), 3f));
            w.Add(new Place("camp", "Camp", new Vec2(40, 0), 3f));
            w.Add(new Place("home", "Home", new Vec2(0, 20), 3f));
            return w;
        }

        // ---------- fixed plans (story beats) ----------

        [Fact]
        public void A_fixed_plan_takes_over_during_its_window_then_hands_back()
        {
            var w = NewWorld();
            var riku = Helpers.Npc(w, "riku", 0, 20);
            riku.Plan = new Plan("Daily life", 0, new[] { new PlanStep(0, 0, Verbs.Goto, "home") });
            riku.FixedPlans.Add(new Plan("Steal the relic", 1, new[] { new PlanStep(1, 0, Verbs.Goto, "shrine"), new PlanStep(2, 0, Verbs.Goto, "camp") }, null, untilMinute: 3 * 60));
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            Assert.True(sim.DestinationOf(riku)!.Value.DistanceTo(new Vec2(0, 20)) < 2f);   // 00:00 normal plan
            sim.Run(World.TicksPerHour + 1);
            Assert.True(sim.DestinationOf(riku)!.Value.DistanceTo(new Vec2(0, 0)) < 2f);    // 01:05 story beat
            sim.Run(World.TicksPerHour);
            Assert.True(sim.DestinationOf(riku)!.Value.DistanceTo(new Vec2(40, 0)) < 2f);   // 02:05
            sim.Run(World.TicksPerHour);
            Assert.True(sim.DestinationOf(riku)!.Value.DistanceTo(new Vec2(0, 20)) < 2f);   // 03:05 back to normal
        }

        [Fact]
        public void A_fixed_plan_can_steal_and_hand_over_an_item()
        {
            var w = NewWorld();
            var jun = Helpers.Npc(w, "jun", 0, 0);
            var riku = Helpers.Npc(w, "riku", 0, 1);
            var crow = Helpers.Npc(w, "crow", 0, 2);
            var relic = w.Add(new Item("relic", "Relic", new Vec2(0, 0), 60f, "jun"));
            riku.FixedPlans.Add(new Plan("Steal", 1, new[]
            {
                new PlanStep(0, 0, Verbs.Steal, "jun", "relic"),
                new PlanStep(0, 5, Verbs.Give, "crow", "relic"),
            }, null, untilMinute: 60));
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            sim.Run(3);
            Assert.Equal("crow", relic.OwnerId);
        }

        // ---------- companions ----------

        [Fact]
        public void A_companion_follows_until_the_time_runs_out()
        {
            var w = NewWorld();
            var kaito = Helpers.Npc(w, "kaito", 0, 20);
            kaito.Schedule = new Schedule().Add(0, "home");
            var hero = Helpers.Player(w, 30, 30);
            Companions.Follow(w, kaito, hero, World.TicksPerHour, null);
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            Assert.True(sim.DestinationOf(kaito)!.Value.DistanceTo(hero.Position) < 2f);
            sim.Run(World.TicksPerHour + 1);
            Assert.Null(kaito.FollowId);
            Assert.True(sim.DestinationOf(kaito)!.Value.DistanceTo(new Vec2(0, 20)) < 2f);
        }

        // ---------- investigation ----------

        [Fact]
        public void Accusing_the_true_culprit_completes_the_quest_and_a_false_accusation_costs_trust()
        {
            var w = NewWorld();
            var jun = Helpers.Npc(w, "jun", 0, 0);
            var riku = Helpers.Npc(w, "riku", 0, 1);
            var ben = Helpers.Npc(w, "ben", 0, 2);
            var hero = Helpers.Player(w, 1, 0);
            jun.Gold = 20;
            var q = w.Quests.Offer(w, "jun", QuestKinds.Accuse, "riku", null, 15, "Who stole the relic?", null);
            w.Quests.Accept(w, q.Id, "player");

            Assert.False(w.Quests.Accuse(w, "player", "jun", "ben"));
            Assert.Equal(QuestStatus.Active, q.Status);
            Assert.True(jun.Mind.OpinionOf("player") < 0f);
            Assert.True(ben.Mind.OpinionOf("player") < 0f);

            Assert.True(w.Quests.Accuse(w, "player", "jun", "riku"));
            Assert.Equal(QuestStatus.Completed, q.Status);
            Assert.Equal(15, hero.Gold);
            Assert.True(jun.Mind.OpinionOf("riku") < 0f);
        }

        // ---------- the world's loose items ----------

        [Fact]
        public void Picking_up_an_unowned_item_is_not_a_crime()
        {
            var w = NewWorld();
            var hero = Helpers.Player(w, 0, 0);
            var witness = Helpers.Npc(w, "ben", 1, 0);
            var herb = w.Add(new Item("herb1", "Moon Herb", new Vec2(0, 0), 5f, null));
            Assert.True(Actions.PickUp(w, hero, herb.Id) >= 0);
            Assert.Equal("player", herb.OwnerId);
            Assert.DoesNotContain(witness.Mind.Memories, m => m.IsCrime);
            Assert.Equal(-1, Actions.PickUp(w, hero, herb.Id)); // already owned by someone
        }

        // ---------- justice ----------

        [Fact]
        public void A_guard_who_catches_the_player_journals_an_arrest()
        {
            var w = NewWorld();
            w.Tuning.Arrests = true;
            var guard = Helpers.Npc(w, "ren", 0, 0, 0.9f, 0.5f, Tags.Authority);
            var hero = Helpers.Player(w, 1, 0);
            var victim = Helpers.Npc(w, "jun", 30, 0);
            w.Add(new Item("relic", "Relic", new Vec2(30, 0), 60f, "player"));
            int deed = w.Journal.Add(0, "deed", "player", "Traveller steal -> jun (Relic)");
            guard.Mind.AddMemory(new Memory("steal", "player", "jun", "relic", 0, true, null, 1f, -0.8f, true, deed));
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            sim.Run(3);
            var arrest = w.Journal.Entries.Single(e => e.Kind == "arrest");
            Assert.Equal("ren", arrest.AgentId);
            Assert.Equal("player", arrest.TargetId);
            Assert.Equal("jun", w.FindItem("relic")!.OwnerId); // stolen goods go back
        }
    }
}
