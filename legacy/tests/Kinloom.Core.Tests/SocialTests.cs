using System.Linq;
using Kinloom.Core;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class SocialTests
    {
        private static (World w, Agent witness, Agent listener) Gossipers()
        {
            var w = new World(Helpers.Medieval(), 1);
            w.Tuning.RumorBaseChance = 1f;
            var witness = Helpers.Npc(w, "witness", 0, 0, 0.9f, 1f);
            var listener = Helpers.Npc(w, "listener", 50, 0, 0.5f, 1f);
            var player = Helpers.Player(w, 1, 0);
            Actions.PerformDeed(w, player, "draw_weapon", null, null); // brave witness scolds, stays in Routine
            listener.Position = new Vec2(1, 1);
            return (w, witness, listener);
        }

        [Fact]
        public void Rumor_spreads_with_lower_confidence_and_a_source()
        {
            var (w, _, listener) = Gossipers();
            Rumors.Spread(w);
            var heard = Assert.Single(listener.Mind.Memories);
            Assert.False(heard.Firsthand);
            Assert.Equal("witness", heard.SourceId);
            Assert.Equal(0.8, heard.Confidence, 3);
            Assert.True(listener.Mind.OpinionOf("player") < 0f);
        }

        [Fact]
        public void A_rumor_is_not_learned_twice()
        {
            var (w, _, listener) = Gossipers();
            Rumors.Spread(w);
            Rumors.Spread(w);
            Assert.Single(listener.Mind.Memories);
        }

        [Fact]
        public void The_most_salient_memory_is_told_first()
        {
            var w = new World(Helpers.Medieval(), 1);
            w.Journal.Add(0, "deed", null, "root");
            w.Tuning.RumorBaseChance = 1f;
            var speaker = Helpers.Npc(w, "speaker", 0, 0, 0.9f, 1f);
            var listener = Helpers.Npc(w, "listener", 1, 0, 0.5f, 0f);
            Learning.Learn(w, speaker, Helpers.Seen("help", "player", null, 1, 0.3f));
            Learning.Learn(w, speaker, Helpers.Seen("steal", "player", null, 2, -0.8f, crime: true));
            Learning.Learn(w, speaker, Helpers.Seen("draw_weapon", "player", null, 3, -0.3f));
            Rumors.Spread(w);
            Assert.Equal("steal", Assert.Single(listener.Mind.Memories).Kind);
        }

        [Fact]
        public void Nobody_gossips_while_fleeing()
        {
            var (w, witness, listener) = Gossipers();
            witness.Intent = new Intent(IntentKind.Flee, "player", null, w.Tick + 10, null);
            Rumors.Spread(w);
            Assert.Empty(listener.Mind.Memories);
        }

        [Fact]
        public void Agents_are_not_told_rumors_about_themselves()
        {
            var w = new World(Helpers.Medieval(), 1);
            w.Tuning.RumorBaseChance = 1f;
            Helpers.Npc(w, "witness", 0, 0, 0.9f, 1f);
            var thief = Helpers.Npc(w, "thief", 1, 0, 0.9f, 0f);
            Actions.PerformDeed(w, thief, "draw_weapon", null, null);
            Rumors.Spread(w);
            Assert.DoesNotContain(thief.Mind.Memories, m => m.ActorId == "thief");
        }

        [Fact]
        public void Price_follows_opinion_and_trader_refuses_enemies()
        {
            var w = new World(Helpers.Medieval(), 1);
            var trader = Helpers.Npc(w, "trader", 0, 0, 0.5f, 0.5f, Tags.Trader);
            var buyer = Helpers.Player(w, 1, 0);
            trader.Mind.ShiftOpinion("player", -0.5f);
            Assert.Equal(12.5, Commerce.PriceFor(trader, buyer, 10f), 3);
            trader.Mind.ShiftOpinion("player", 0.9f);
            Assert.Equal(8.0, Commerce.PriceFor(trader, buyer, 10f), 3);
            trader.Mind.ShiftOpinion("player", -5f);
            Assert.False(Commerce.WillTrade(trader, buyer));
            var result = Commerce.Trade(w, buyer, trader, 10f);
            Assert.True(result.Refused);
            Assert.Contains("refuses", w.Journal.Get(result.EntryId).Text);
        }

        [Fact]
        public void Price_never_exceeds_one_and_a_half_times_base()
        {
            var w = new World(Helpers.Medieval(), 1);
            var trader = Helpers.Npc(w, "trader", 0, 0, 0.5f, 0.5f, Tags.Trader);
            var buyer = Helpers.Player(w, 1, 0);
            trader.Mind.ShiftOpinion("player", -10f);
            Assert.Equal(15.0, Commerce.PriceFor(trader, buyer, 10f), 3);
        }

        [Fact]
        public void A_higher_price_can_be_explained_back_to_the_deed()
        {
            var w = new World(Helpers.Medieval(), 1);
            var smith = Helpers.Npc(w, "smith", 3, 0, 0.9f, 0.5f, Tags.Trader);
            var player = Helpers.Player(w, 0, 0);
            Actions.PerformDeed(w, player, "draw_weapon", null, null);
            var result = Commerce.Trade(w, player, smith, 10f);
            Assert.False(result.Refused);
            Assert.True(result.Price > 10f);
            var chain = w.Journal.Why(result.EntryId);
            Assert.Contains(chain, e => e.Kind == "opinion");
            Assert.Equal("deed", chain.Last().Kind);
        }
    }
}
