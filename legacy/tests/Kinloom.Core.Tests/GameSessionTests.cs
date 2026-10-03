using System.IO;
using System.Linq;
using Kinloom.Core;
using Kinloom.Game;
using Kinloom.Sim;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class GameSessionTests
    {
        private static GameSession NewSession(int seed = 42)
        {
            var scenario = ScenarioLoader.LoadScenario(Path.Combine(ScenarioTests.Root(), "scenarios", "village-game.json"));
            scenario.Seed = seed;
            var sim = ScenarioLoader.Build(scenario, ScenarioTests.Pack());
            return new GameSession(sim);
        }

        private static void TeleportTo(GameSession g, string placeId) => g.Player.Position = g.World.FindPlace(placeId)!.Position;

        [Fact]
        public void Warm_up_starts_the_day_in_the_morning_without_a_replay_buffer()
        {
            var g = NewSession();
            g.WarmUp(9 * World.TicksPerHour);
            Assert.Equal(9, g.World.Hour);
            Assert.Empty(g.Sim.Frames);
        }

        [Fact]
        public void Real_time_advances_ticks_and_keeps_the_remainder_for_interpolation()
        {
            var g = NewSession();
            g.SecondsPerTick = 0.4f;
            g.Update(1.0f, new Vec2(0, 0));
            Assert.Equal(2, g.World.Tick);
            Assert.Equal(0.5f, g.TickProgress, 3);
        }

        [Fact]
        public void Pause_freezes_time_and_the_player()
        {
            var g = NewSession();
            var start = g.Player.Position;
            g.Paused = true;
            g.Update(5f, new Vec2(1, 0));
            Assert.Equal(0, g.World.Tick);
            Assert.Equal(start.X, g.Player.Position.X);
        }

        [Fact]
        public void Player_moves_with_input_and_stays_inside_the_map()
        {
            var g = NewSession();
            g.Player.Position = new Vec2(50, 30);
            g.Update(0.5f, new Vec2(1, 0));
            Assert.Equal(50 + 0.5f * GameSession.PlayerSpeed, g.Player.Position.X, 3);
            g.Update(60f, new Vec2(-1, -1));
            Assert.Equal(0f, g.Player.Position.X);
            Assert.Equal(0f, g.Player.Position.Y);
        }

        [Fact]
        public void Diagonal_input_is_not_faster_than_straight_input()
        {
            var g = NewSession();
            g.Player.Position = new Vec2(50, 30);
            g.Update(0.5f, new Vec2(1, 1));
            Assert.Equal(0.5 * GameSession.PlayerSpeed, new Vec2(50, 30).DistanceTo(g.Player.Position), 3);
        }

        [Fact]
        public void Stealing_nearby_bread_takes_it_and_is_seen_by_the_baker()
        {
            var g = NewSession();
            g.WarmUp(10 * World.TicksPerHour);
            TeleportTo(g, "bakery");
            string message = g.Steal();
            Assert.Contains("Loaf of Bread", message);
            Assert.Equal("player", g.World.FindItem("bread")!.OwnerId);
            Assert.Contains(g.Feed, l => l.Kind == "deed" && l.Text.Contains("steal"));
            Assert.Contains(g.World.GetAgent("baker").Mind.Memories, m => m.Kind == "steal" && m.Firsthand);
        }

        [Fact]
        public void Nothing_to_steal_far_from_items()
        {
            var g = NewSession();
            g.Player.Position = new Vec2(0, 0);
            int before = g.World.Journal.Entries.Count;
            Assert.Equal("Nothing to steal here.", g.Steal());
            Assert.Equal(before, g.World.Journal.Entries.Count);
        }

        [Fact]
        public void Buying_from_the_nearest_trader_uses_opinion_based_prices()
        {
            var g = NewSession();
            g.WarmUp(10 * World.TicksPerHour);
            TeleportTo(g, "forge");
            string message = g.Buy();
            Assert.Contains("Hugo the Smith", message);
            Assert.Single(g.Sim.Trades);
            g.World.GetAgent("smith").Mind.ShiftOpinion("player", -2f);
            Assert.Contains("refuses", g.Buy());
        }

        [Fact]
        public void Helping_the_nearest_villager_raises_their_opinion()
        {
            var g = NewSession();
            g.WarmUp(10 * World.TicksPerHour);
            TeleportTo(g, "field");
            string message = g.Help();
            Assert.Contains("Mila the Farmer", message);
            Assert.True(g.World.GetAgent("farmer").Mind.OpinionOf("player") > 0f);
        }

        [Fact]
        public void Acting_with_nobody_around_says_so()
        {
            var g = NewSession();
            g.Player.Position = new Vec2(0, 0);
            Assert.Equal("Nobody close enough to help.", g.Help());
            Assert.Equal("Nobody close enough to pay.", g.Pay());
            Assert.Equal("No trader close enough.", g.Buy());
        }

        [Fact]
        public void Why_explains_the_guard_after_he_confronts_the_thief()
        {
            var g = NewSession();
            g.WarmUp(10 * World.TicksPerHour);
            TeleportTo(g, "bakery");
            g.Steal();
            for (int i = 0; i < 30; i++) g.Update(0.4f, new Vec2(0, 0));
            TeleportTo(g, "square");
            for (int i = 0; i < 30; i++) g.Update(0.4f, new Vec2(0, 0));
            var chain = g.Why(g.World.GetAgent("guard"));
            Assert.NotEmpty(chain);
            Assert.Equal("deed", chain.Last().Kind);
            Assert.Equal("baker", g.World.FindItem("bread")!.OwnerId);
        }

        [Fact]
        public void Traders_restock_stolen_goods_the_next_morning()
        {
            var g = NewSession();
            g.WarmUp(10 * World.TicksPerHour);
            TeleportTo(g, "forge");
            g.Steal();
            Assert.Null(g.NearestStealable());
            g.WarmUp(22 * World.TicksPerHour); // next day, 08:00
            var fresh = g.NearestStealable();
            Assert.NotNull(fresh);
            Assert.Equal("Iron Sword", fresh!.Name);
            Assert.Equal("smith", fresh.OwnerId);
            Assert.Contains(g.Feed, l => l.Text == "Hugo restocks: a new Iron Sword.");
        }

        [Fact]
        public void Goals_tick_off_as_the_player_discovers_the_systems()
        {
            var g = NewSession();
            Assert.All(g.Goals, goal => Assert.False(goal.Done));
            g.WarmUp(10 * World.TicksPerHour);
            TeleportTo(g, "bakery");
            g.Steal();
            Assert.True(g.Goals.Single(x => x.Id == "steal").Done);
            for (int i = 0; i < 25; i++) g.Update(0.4f, new Vec2(0, 0));
            TeleportTo(g, "square");
            for (int i = 0; i < 30; i++) g.Update(0.4f, new Vec2(0, 0));
            Assert.True(g.Goals.Single(x => x.Id == "confronted").Done);
            g.WarmUp(10 * World.TicksPerHour);
            Assert.True(g.Goals.Single(x => x.Id == "rumor").Done);
            Assert.False(g.Goals.Single(x => x.Id == "flee").Done);
        }

        [Fact]
        public void Every_goal_can_be_reached()
        {
            var g = NewSession();
            g.WarmUp(10 * World.TicksPerHour);
            TeleportTo(g, "bakery");
            g.Steal();
            g.Pay();
            Assert.True(g.Goals.Single(x => x.Id == "forgiven").Done);

            TeleportTo(g, "forge");
            g.World.GetAgent("smith").Mind.ShiftOpinion("player", -0.5f);
            g.Buy();
            Assert.True(g.Goals.Single(x => x.Id == "overcharged").Done);
            g.World.GetAgent("smith").Mind.ShiftOpinion("player", -2f);
            g.Buy();
            Assert.True(g.Goals.Single(x => x.Id == "refused").Done);

            g.WarmUp(2 * World.TicksPerHour + 6); // 12:30 on the square
            TeleportTo(g, "square");
            g.DrawWeapon();
            Assert.True(g.Goals.Single(x => x.Id == "flee").Done);
        }

        [Fact]
        public void Previous_positions_allow_smooth_interpolation()
        {
            var g = NewSession();
            g.WarmUp(11 * World.TicksPerHour); // 11:00: the farmer leaves the field for the market square
            var farmer = g.World.GetAgent("farmer");
            g.Update(g.SecondsPerTick, new Vec2(0, 0));
            Assert.NotEqual(farmer.Position.X, g.PreviousPosition(farmer).X);
            var mid = g.DisplayPosition(farmer);
            Assert.InRange(mid.X, System.Math.Min(farmer.Position.X, g.PreviousPosition(farmer).X), System.Math.Max(farmer.Position.X, g.PreviousPosition(farmer).X));
        }
    }
}
