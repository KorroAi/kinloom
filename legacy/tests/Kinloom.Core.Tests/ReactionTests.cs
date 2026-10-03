using System.Collections.Generic;
using System.Linq;
using Kinloom.Core;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class ReactionTests
    {
        [Fact]
        public void Witnesses_in_radius_remember_firsthand_others_do_not()
        {
            var w = new World(Helpers.Medieval(), 1);
            var near = Helpers.Npc(w, "near", 5, 0, 0.9f);
            var far = Helpers.Npc(w, "far", 50, 0);
            var player = Helpers.Player(w, 0, 0);
            Actions.PerformDeed(w, player, "draw_weapon", null, null);
            Assert.True(Assert.Single(near.Mind.Memories).Firsthand);
            Assert.Empty(far.Mind.Memories);
            Assert.True(near.Mind.OpinionOf("player") < 0f);
            Assert.Empty(player.Mind.Memories);
        }

        [Fact]
        public void Steal_transfers_the_item_to_the_thief()
        {
            var w = new World(Helpers.Medieval(), 1);
            Helpers.Npc(w, "baker", 1, 0, 0.3f, 0.5f, Tags.Trader);
            var player = Helpers.Player(w, 0, 0);
            w.Add(new Item("bread", "Bread", new Vec2(0, 0), 2f, "baker"));
            Actions.PerformDeed(w, player, "steal", "baker", "bread");
            Assert.Equal("player", w.FindItem("bread")!.OwnerId);
        }

        [Fact]
        public void Timid_bystander_flees_from_a_drawn_weapon()
        {
            var w = new World(Helpers.Medieval(), 1);
            var timid = Helpers.Npc(w, "timid", 3, 0, 0.1f);
            var player = Helpers.Player(w, 0, 0);
            Actions.PerformDeed(w, player, "draw_weapon", null, null);
            Assert.Equal(IntentKind.Flee, timid.Intent.Kind);
            Assert.Equal("Run!", timid.CurrentBark(w.Tick));
        }

        [Fact]
        public void Authority_confronts_a_threat()
        {
            var w = new World(Helpers.Medieval(), 1);
            var guard = Helpers.Npc(w, "guard", 3, 0, 0.8f, 0.3f, Tags.Authority);
            var player = Helpers.Player(w, 0, 0);
            Actions.PerformDeed(w, player, "draw_weapon", null, null);
            Assert.Equal(IntentKind.Approach, guard.Intent.Kind);
            Assert.Equal("player", guard.Intent.TargetId);
        }

        [Fact]
        public void Crime_witness_reports_to_the_nearest_authority()
        {
            var w = new World(Helpers.Medieval(), 1);
            var baker = Helpers.Npc(w, "baker", 1, 0, 0.3f, 0.5f, Tags.Trader);
            Helpers.Npc(w, "guard", 40, 0, 0.8f, 0.3f, Tags.Authority);
            var player = Helpers.Player(w, 0, 0);
            w.Add(new Item("bread", "Bread", new Vec2(0, 0), 2f, "baker"));
            Actions.PerformDeed(w, player, "steal", "baker", "bread");
            Assert.Equal(IntentKind.Report, baker.Intent.Kind);
            Assert.Equal("guard", baker.Intent.TargetId);
        }

        [Fact]
        public void Crime_witness_without_any_authority_scolds_instead()
        {
            var w = new World(Helpers.Medieval(), 1);
            var baker = Helpers.Npc(w, "baker", 1, 0, 0.3f, 0.5f, Tags.Trader);
            var player = Helpers.Player(w, 0, 0);
            w.Add(new Item("bread", "Bread", new Vec2(0, 0), 2f, "baker"));
            Actions.PerformDeed(w, player, "steal", "baker", "bread");
            Assert.Equal(IntentKind.Routine, baker.Intent.Kind);
            Assert.Contains(w.Journal.Entries, e => e.Kind == "reaction" && e.Text.Contains("scold"));
        }

        [Fact]
        public void Kind_deed_reactions_read_as_natural_sentences()
        {
            var w = new World(Helpers.Medieval(), 1);
            Helpers.Npc(w, "helped", 1, 0);
            Helpers.Npc(w, "onlooker", 2, 0);
            var player = Helpers.Player(w, 0, 0);
            Actions.PerformDeed(w, player, "help", "helped", null);
            var texts = w.Journal.Entries.Where(e => e.Kind == "reaction").Select(e => e.Text).ToList();
            Assert.Contains(texts, t => t.StartsWith("helped is grateful"));
            Assert.Contains(texts, t => t.StartsWith("onlooker approves"));
            Assert.DoesNotContain(texts, t => t.Contains("decides to grateful") || t.Contains("decides to approve"));
        }

        [Fact]
        public void Every_reaction_can_be_traced_back_to_the_deed()
        {
            var w = new World(Helpers.Medieval(), 1);
            Helpers.Npc(w, "timid", 3, 0, 0.1f);
            var player = Helpers.Player(w, 0, 0);
            Actions.PerformDeed(w, player, "draw_weapon", null, null);
            var reaction = w.Journal.Entries.Last(e => e.Kind == "reaction");
            var chain = w.Journal.Why(reaction.Id);
            Assert.Equal("deed", chain.Last().Kind);
            Assert.Contains(chain, e => e.Kind == "witness");
        }

        [Fact]
        public void Invalid_deeds_are_logged_as_errors_not_thrown()
        {
            var w = new World(Helpers.Medieval(), 1);
            var player = Helpers.Player(w, 0, 0);
            Assert.Equal("error", w.Journal.Get(Actions.PerformDeed(w, player, "teleport", null, null)).Kind);
            Assert.Equal("error", w.Journal.Get(Actions.PerformDeed(w, player, "steal", null, "ghost")).Kind);
            Assert.Equal("error", w.Journal.Get(Actions.PerformDeed(w, player, "help", "nobody", null)).Kind);
            Assert.Equal("error", w.Journal.Get(Actions.PerformDeed(w, player, "steal", null, null)).Kind);
        }

        [Fact]
        public void Same_engine_runs_a_scifi_pack_with_its_own_vocabulary()
        {
            var pack = new PackDefinition
            {
                Name = "scifi",
                Deeds = { new DeedDefinition { Kind = "hack_terminal", Valence = -0.7f, Threat = 0.2f, Radius = 10f, IsCrime = true } },
                Barks = { ["report"] = new List<string> { "Security! Intrusion!" } }
            };
            var w = new World(pack, 5);
            var tech = Helpers.Npc(w, "tech", 2, 0, 0.4f);
            Helpers.Npc(w, "drone", 40, 0, 0.9f, 0f, Tags.Authority);
            var player = Helpers.Player(w, 0, 0);
            Actions.PerformDeed(w, player, "hack_terminal", null, null);
            Assert.Equal(IntentKind.Report, tech.Intent.Kind);
            Assert.Equal("drone", tech.Intent.TargetId);
            Assert.Equal("Security! Intrusion!", tech.CurrentBark(w.Tick));
        }
    }
}
