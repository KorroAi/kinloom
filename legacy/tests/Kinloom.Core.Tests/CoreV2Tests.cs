using System.Linq;
using Kinloom.Core;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class CoreV2Tests
    {
        private static World NewWorld()
        {
            var w = new World(Helpers.Medieval(), 1);
            w.Pack.Deeds.Add(new DeedDefinition { Kind = "attack", Valence = -0.9f, Threat = 0.9f, Radius = 10f, IsCrime = true });
            w.Pack.Deeds.Add(new DeedDefinition { Kind = "give", Valence = 0.5f, Radius = 5f, TransfersItem = true });
            w.Pack.Deeds.Add(new DeedDefinition { Kind = "kill", Valence = -1f, Threat = 1f, Radius = 14f, IsCrime = true });
            w.Add(new Place("square", "Square", new Vec2(0, 0), 4f));
            w.Add(new Place("forge", "Forge", new Vec2(30, 0), 3f));
            return w;
        }

        private static int At(int hour, int minute = 0) => hour * World.TicksPerHour + minute / 5;

        private static void RunUntil(Simulation sim, int tick)
        {
            while (sim.World.Tick < tick) sim.Step();
        }

        // ---------- plans ----------

        [Fact]
        public void Plan_step_sends_agent_to_its_place_at_its_hour()
        {
            var w = NewWorld();
            var a = Helpers.Npc(w, "aiko", 0, 0);
            a.Plan = new Plan("Work at the forge", 0, new[] { new PlanStep(8, 0, Verbs.Goto, "forge") });
            var sim = new Simulation(w, new PlayerCommand[0]);
            RunUntil(sim, At(7));
            Assert.Null(sim.DestinationOf(a));
            RunUntil(sim, At(8));
            var d = sim.DestinationOf(a);
            Assert.NotNull(d);
            Assert.True(d!.Value.DistanceTo(new Vec2(30, 0)) < 2f);
        }

        [Fact]
        public void Without_a_plan_the_schedule_still_applies()
        {
            var w = NewWorld();
            var a = Helpers.Npc(w, "aiko", 0, 0);
            a.Schedule = new Schedule().Add(0, "forge");
            var sim = new Simulation(w, new PlayerCommand[0]);
            Assert.True(sim.DestinationOf(a)!.Value.DistanceTo(new Vec2(30, 0)) < 2f);
        }

        [Fact]
        public void External_movement_leaves_positions_to_the_host()
        {
            var w = NewWorld();
            var a = Helpers.Npc(w, "aiko", 0, 0);
            a.Schedule = new Schedule().Add(0, "forge");
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            sim.Run(20);
            Assert.Equal(new Vec2(0, 0), a.Position);
        }

        [Fact]
        public void Give_step_transfers_the_item_on_arrival_and_is_witnessed()
        {
            var w = NewWorld();
            var a = Helpers.Npc(w, "aiko", 0, 0);
            var b = Helpers.Npc(w, "ben", 1, 0);
            var c = Helpers.Npc(w, "chie", 2, 0);
            var rice = w.Add(new Item("rice", "Rice", new Vec2(0, 0), 2f, "aiko"));
            a.Plan = new Plan("Share food", 0, new[] { new PlanStep(0, 0, Verbs.Give, "ben", "rice") });
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            sim.Run(2);
            Assert.Equal("ben", rice.OwnerId);
            Assert.True(a.Plan!.Steps[0].Done);
            Assert.Contains(c.Mind.Memories, m => m.Kind == "give" && m.ActorId == "aiko");
            Assert.True(b.Mind.OpinionOf("aiko") > 0f);
        }

        [Fact]
        public void Give_step_fails_cleanly_when_the_item_is_not_owned()
        {
            var w = NewWorld();
            var a = Helpers.Npc(w, "aiko", 0, 0);
            Helpers.Npc(w, "ben", 1, 0);
            w.Add(new Item("rice", "Rice", new Vec2(0, 0), 2f, "ben"));
            a.Plan = new Plan("Share food", 0, new[] { new PlanStep(0, 0, Verbs.Give, "ben", "rice") });
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            sim.Run(2);
            Assert.Contains(w.Journal.Entries, e => e.Kind == "error" && e.Text.Contains("does not own"));
            Assert.True(a.Plan!.Steps[0].Done);
        }

        [Fact]
        public void Meeting_step_journals_a_meet_entry_with_both_ids()
        {
            var w = NewWorld();
            var a = Helpers.Npc(w, "aiko", 0, 0);
            Helpers.Npc(w, "ben", 1, 0);
            a.Plan = new Plan("Gossip", 0, new[] { new PlanStep(0, 0, Verbs.Talk, "ben", null, "ask about the theft") });
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            sim.Run(2);
            var meet = w.Journal.Entries.Single(e => e.Kind == "meet");
            Assert.Equal("aiko", meet.AgentId);
            Assert.Equal("ben", meet.TargetId);
            Assert.Contains("ask about the theft", meet.Text);
        }

        [Fact]
        public void A_reflex_interrupts_the_plan_which_resumes_afterwards()
        {
            var w = NewWorld();
            var a = Helpers.Npc(w, "aiko", 0, 0, bravery: 0f);
            var thug = Helpers.Npc(w, "thug", 2, 0);
            a.Plan = new Plan("Work", 0, new[] { new PlanStep(0, 0, Verbs.Goto, "forge") });
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            Actions.PerformDeed(w, thug, "draw_weapon", null, null);
            Assert.Equal(IntentKind.Flee, a.Intent.Kind);
            RunUntil(sim, w.Tuning.FleeTicks + 2);
            Assert.Equal(IntentKind.Routine, a.Intent.Kind);
            Assert.True(sim.DestinationOf(a)!.Value.DistanceTo(new Vec2(30, 0)) < 2f);
        }

        // ---------- knowledge ----------

        [Fact]
        public void Tell_shares_a_memory_the_speaker_holds_as_hearsay()
        {
            var w = NewWorld();
            var a = Helpers.Npc(w, "aiko", 0, 0);
            var b = Helpers.Npc(w, "ben", 1, 0);
            w.Journal.Add(3, "deed", "thug", "thug steal -> aiko");
            var m = Helpers.Seen("steal", "thug", "aiko", 3, -0.8f, crime: true);
            a.Mind.AddMemory(m);
            int entry = Knowledge.Tell(w, a, b, m.Key, null);
            Assert.True(entry >= 0);
            var heard = b.Mind.Recall(m.Key);
            Assert.NotNull(heard);
            Assert.False(heard!.Firsthand);
            Assert.Equal("aiko", heard.SourceId);
            Assert.True(heard.Confidence < 1f);
        }

        [Fact]
        public void Tell_refuses_a_memory_the_speaker_does_not_hold()
        {
            var w = NewWorld();
            var a = Helpers.Npc(w, "aiko", 0, 0);
            var b = Helpers.Npc(w, "ben", 1, 0);
            Assert.Equal(-1, Knowledge.Tell(w, a, b, "steal|x|y|3", null));
            Assert.Empty(b.Mind.Memories);
        }

        [Fact]
        public void A_lie_plants_a_false_memory_flagged_only_in_the_truth_journal()
        {
            var w = NewWorld();
            var liar = Helpers.Npc(w, "tob", 0, 0);
            var b = Helpers.Npc(w, "ben", 1, 0);
            Helpers.Npc(w, "smith", 20, 0);
            int entry = Knowledge.Lie(w, liar, b, "steal", "smith", "ben", null, null);
            Assert.True(entry >= 0);
            var m = b.Mind.Memories.Single();
            Assert.Equal("smith", m.ActorId);
            Assert.True(m.IsLie);
            Assert.True(b.Mind.OpinionOf("smith") < 0f);
            Assert.Equal("lie", w.Journal.Get(entry).Kind);
        }

        [Fact]
        public void A_lie_about_an_unknown_deed_is_rejected()
        {
            var w = NewWorld();
            var liar = Helpers.Npc(w, "tob", 0, 0);
            var b = Helpers.Npc(w, "ben", 1, 0);
            Assert.Equal(-1, Knowledge.Lie(w, liar, b, "teleport", "ben", null, null, null));
        }

        // ---------- combat ----------

        [Fact]
        public void Attack_hurts_and_a_lethal_blow_is_a_witnessed_death()
        {
            var w = NewWorld();
            var thug = Helpers.Npc(w, "thug", 0, 0);
            var victim = Helpers.Npc(w, "ben", 1, 0);
            var witness = Helpers.Npc(w, "chie", 3, 0);
            victim.Health = 5;
            Combat.Attack(w, thug, victim, 3);
            Assert.Equal(2, victim.Health);
            Combat.Attack(w, thug, victim, 3);
            Assert.False(victim.IsAlive);
            Assert.Contains(witness.Mind.Memories, m => m.Kind == "kill" && m.ActorId == "thug");
            Assert.Contains(w.Journal.Entries, e => e.Kind == "death" && e.AgentId == "ben");
        }

        [Fact]
        public void Striking_a_raider_is_defence_not_a_crime()
        {
            var w = NewWorld();
            w.Pack.Deeds.Add(new DeedDefinition { Kind = "defend", Valence = 0.6f, Threat = 0f, Radius = 10f });
            var hero = Helpers.Player(w, 0, 0);
            var bandit = w.Add(new Agent("crow", "Crow", new Vec2(1, 0), new Personality(0.9f, 0.1f, 0.1f), false, new[] { WorldEvents.HostileTag }));
            var witness = Helpers.Npc(w, "chie", 3, 0);
            bandit.Health = 3;
            Combat.Attack(w, hero, bandit, 3);
            Assert.DoesNotContain(witness.Mind.Memories, m => m.IsCrime);
            Assert.Contains(witness.Mind.Memories, m => m.Kind == "defend" && m.ActorId == "player");
            Assert.True(witness.Mind.OpinionOf("player") > 0f);
        }

        [Fact]
        public void A_protected_agent_is_hurt_but_never_killed()
        {
            var w = NewWorld();
            var thug = Helpers.Npc(w, "thug", 0, 0);
            var child = Helpers.Npc(w, "hana", 1, 0, 0.5f, 0.5f, Combat.ProtectedTag);
            child.Health = 2;
            Combat.Attack(w, thug, child, 5);
            Assert.Equal(1, child.Health);
            Assert.True(child.IsAlive);
            Assert.DoesNotContain(w.Journal.Entries, e => e.Kind == "death");
        }

        [Fact]
        public void Repeated_blows_in_one_fight_make_one_memory_not_many()
        {
            var w = NewWorld();
            var thug = Helpers.Npc(w, "thug", 0, 0);
            var victim = Helpers.Npc(w, "ben", 1, 0);
            var witness = Helpers.Npc(w, "chie", 3, 0);
            victim.Health = 100;
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            for (int i = 0; i < 5; i++) { Combat.Attack(w, thug, victim, 1); sim.Step(); }
            Assert.Equal(1, witness.Mind.Memories.Count(m => m.Kind == "attack"));
            Assert.Equal(95, victim.Health);
        }

        [Fact]
        public void The_dead_do_not_perceive_or_act()
        {
            var w = NewWorld();
            var thug = Helpers.Npc(w, "thug", 0, 0);
            var dead = Helpers.Npc(w, "ben", 1, 0);
            dead.Health = 0;
            Actions.PerformDeed(w, thug, "draw_weapon", null, null);
            Assert.Empty(dead.Mind.Memories);
        }

        // ---------- quests ----------

        [Fact]
        public void Retrieve_quest_completes_when_the_item_is_back_and_pays_the_hero()
        {
            var w = NewWorld();
            var giver = Helpers.Npc(w, "mira", 0, 0);
            var thief = Helpers.Npc(w, "tob", 20, 0);
            var hero = Helpers.Player(w, 1, 0);
            giver.Gold = 30;
            var cart = w.Add(new Item("cart", "Cart", new Vec2(20, 0), 10f, "tob"));
            var q = w.Quests.Offer(w, "mira", QuestKinds.RetrieveItem, "tob", "cart", 20, "Tob stole my cart", null);
            w.Quests.Accept(w, q.Id, "player");
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            sim.Step();
            Assert.Equal(QuestStatus.Active, q.Status);
            cart.OwnerId = "mira";
            sim.Step();
            Assert.Equal(QuestStatus.Completed, q.Status);
            Assert.Equal(20, hero.Gold);
            Assert.Equal(10, giver.Gold);
            Assert.True(giver.Mind.OpinionOf("player") > 0.2f);
        }

        [Fact]
        public void Punish_quest_completes_when_the_hero_hurts_the_target()
        {
            var w = NewWorld();
            Helpers.Npc(w, "mira", 0, 0);
            var tob = Helpers.Npc(w, "tob", 20, 0);
            var hero = Helpers.Player(w, 19, 0);
            var q = w.Quests.Offer(w, "mira", QuestKinds.Punish, "tob", null, 0, "He humiliated me", null);
            w.Quests.Accept(w, q.Id, "player");
            Combat.Attack(w, hero, tob, 2);
            new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true }.Step();
            Assert.Equal(QuestStatus.Completed, q.Status);
        }

        [Fact]
        public void Protect_quest_fails_when_the_target_dies()
        {
            var w = NewWorld();
            Helpers.Npc(w, "mira", 0, 0);
            var ben = Helpers.Npc(w, "ben", 20, 0);
            Helpers.Player(w, 0, 0);
            var q = w.Quests.Offer(w, "mira", QuestKinds.Protect, "ben", null, 5, "Bandits want him", w.Tick + 100);
            w.Quests.Accept(w, q.Id, "player");
            ben.Health = 0;
            new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true }.Step();
            Assert.Equal(QuestStatus.Failed, q.Status);
        }

        [Fact]
        public void Persuade_quest_completes_when_the_target_likes_the_giver_enough()
        {
            var w = NewWorld();
            Helpers.Npc(w, "mira", 0, 0);
            var tob = Helpers.Npc(w, "tob", 20, 0);
            Helpers.Player(w, 0, 0);
            var q = w.Quests.Offer(w, "mira", QuestKinds.Persuade, "tob", null, 5, "I want Tob to forgive me", null);
            w.Quests.Accept(w, q.Id, "player");
            tob.Mind.ShiftOpinion("mira", 0.5f);
            new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true }.Step();
            Assert.Equal(QuestStatus.Completed, q.Status);
        }

        [Fact]
        public void A_quest_needs_a_known_giver_kind_and_target()
        {
            var w = NewWorld();
            Helpers.Npc(w, "mira", 0, 0);
            Assert.Null(w.Quests.TryOffer(w, "mira", "dance", "tob", null, 0, "", null, out var error));
            Assert.Contains("kind", error);
            Assert.Null(w.Quests.TryOffer(w, "mira", QuestKinds.Punish, "nobody", null, 0, "", null, out error));
            Assert.Contains("nobody", error);
        }

        [Fact]
        public void A_pack_can_switch_its_barks_to_another_language()
        {
            var pack = Helpers.Medieval();
            pack.LocalizedBarks["fr"] = new System.Collections.Generic.Dictionary<string, System.Collections.Generic.List<string>> { ["flee"] = new() { "Fuyez !" } };
            Assert.True(pack.UseLanguage("fr"));
            Assert.Equal("Fuyez !", pack.Bark("flee", new DeterministicRandom(1)));
            Assert.Equal("Guard!", pack.Bark("report", new DeterministicRandom(1))); // missing keys keep the original
            Assert.False(pack.UseLanguage("de"));
        }

        // ---------- world events ----------

        [Fact]
        public void Festival_gathers_everyone_at_the_place_until_it_ends()
        {
            var w = NewWorld();
            var a = Helpers.Npc(w, "aiko", 0, 0);
            a.Schedule = new Schedule().Add(0, "forge");
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            var ev = WorldEvents.Start(w, WorldEvents.Festival, "square", 12, "Harvest is in", null);
            Assert.NotNull(ev);
            Assert.True(sim.DestinationOf(a)!.Value.DistanceTo(new Vec2(0, 0)) < 3f);
            sim.Run(13);
            Assert.True(sim.DestinationOf(a)!.Value.DistanceTo(new Vec2(30, 0)) < 3f);
        }

        [Fact]
        public void Bandit_raid_brings_reserve_bandits_into_the_world_then_they_leave()
        {
            var w = NewWorld();
            w.Add(new Place("forest", "Forest", new Vec2(60, 0), 5f));
            var bandit = w.Add(new Agent("bandit1", "Masked bandit", new Vec2(60, 0), new Personality(0.9f, 0.1f, 0.1f), false, new[] { "hostile" }));
            bandit.Present = false;
            var victim = Helpers.Npc(w, "aiko", 0, 0);
            w.Add(new Item("rice", "Rice", new Vec2(0, 0), 2f, "aiko"));
            var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
            Assert.NotNull(WorldEvents.Start(w, WorldEvents.BanditRaid, "square", 24, "The granary is full", null));
            Assert.True(bandit.Present);
            Assert.NotNull(bandit.Plan);
            Assert.NotNull(sim.DestinationOf(bandit));
            sim.Run(25);
            Assert.False(bandit.Present);
        }

        [Fact]
        public void An_absent_agent_neither_perceives_nor_is_seen()
        {
            var w = NewWorld();
            var ghost = Helpers.Npc(w, "ghost", 0, 0);
            ghost.Present = false;
            var thug = Helpers.Npc(w, "thug", 1, 0);
            Actions.PerformDeed(w, thug, "draw_weapon", null, null);
            Assert.Empty(ghost.Mind.Memories);
        }

        [Fact]
        public void Unknown_event_kind_or_place_is_refused_with_a_reason()
        {
            var w = NewWorld();
            Assert.Null(WorldEvents.TryStart(w, "earthquake", "square", 10, "", null, out var error));
            Assert.Contains("earthquake", error);
            Assert.Null(WorldEvents.TryStart(w, WorldEvents.Festival, "moon", 10, "", null, out error));
            Assert.Contains("moon", error);
        }
    }
}
