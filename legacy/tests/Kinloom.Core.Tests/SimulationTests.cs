using System.Linq;
using Kinloom.Core;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class SimulationTests
    {
        private static Simulation TheftScene(int seed)
        {
            var w = new World(Helpers.Medieval(), seed);
            w.Add(new Place("shop", "Shop", new Vec2(0, 0), 3f));
            w.Add(new Place("post", "Post", new Vec2(30, 0), 3f));
            var baker = Helpers.Npc(w, "baker", 0, 0, 0.3f, 0.5f, Tags.Trader);
            baker.Schedule = new Schedule().Add(0, "shop");
            var guard = Helpers.Npc(w, "guard", 30, 0, 0.8f, 0.3f, Tags.Authority);
            guard.Schedule = new Schedule().Add(0, "post");
            Helpers.Player(w, 0, 0);
            w.Add(new Item("bread", "Bread", new Vec2(0, 0), 2f, "baker"));
            return new Simulation(w, new[]
            {
                new PlayerCommand(1, "deed", null, "steal", "baker", "bread", 0f),
                new PlayerCommand(24, "goto", "post", null, null, null, 0f),
            });
        }

        [Fact]
        public void Guard_recognizes_the_reported_thief_and_returns_the_item()
        {
            var sim = TheftScene(3);
            sim.Run(60);
            var w = sim.World;
            Assert.Contains(w.Journal.Entries, e => e.Kind == "report");
            Assert.Contains(w.Journal.Entries, e => e.Kind == "consequence" && e.Text.Contains("confronts"));
            Assert.Equal("baker", w.FindItem("bread")!.OwnerId);
        }

        [Fact]
        public void A_handled_crime_is_not_confronted_twice()
        {
            var sim = TheftScene(3);
            sim.Run(200);
            Assert.Equal(1, sim.World.Journal.Entries.Count(e => e.Text.Contains("confronts")));
        }

        [Fact]
        public void Same_seed_gives_the_same_story()
        {
            var a = TheftScene(11); a.Run(300);
            var b = TheftScene(11); b.Run(300);
            Assert.Equal(a.World.Journal.Entries.Select(e => e.Text), b.World.Journal.Entries.Select(e => e.Text));
        }

        [Fact]
        public void Agent_without_home_or_schedule_flees_away_from_the_threat()
        {
            var w = new World(Helpers.Medieval(), 1);
            var timid = Helpers.Npc(w, "timid", 3, 0, 0.1f);
            var player = Helpers.Player(w, 0, 0);
            var sim = new Simulation(w, new[] { new PlayerCommand(0, "deed", null, "draw_weapon", null, null, 0f) });
            sim.Run(5);
            Assert.True(timid.Position.DistanceTo(player.Position) > 3f);
        }

        [Fact]
        public void Frames_record_every_agent_every_tick()
        {
            var sim = TheftScene(3);
            sim.Run(10);
            Assert.Equal(10, sim.Frames.Count);
            Assert.All(sim.Frames, f => Assert.Equal(3, f.Agents.Count));
        }

        [Fact]
        public void Deed_while_still_walking_is_flagged_with_a_warning()
        {
            var w = new World(Helpers.Medieval(), 1);
            w.Add(new Place("far", "Far Place", new Vec2(100, 0), 3f));
            Helpers.Npc(w, "npc", 1, 0, 0.9f);
            Helpers.Player(w, 0, 0);
            var sim = new Simulation(w, new[]
            {
                new PlayerCommand(0, "goto", "far", null, null, null, 0f),
                new PlayerCommand(1, "deed", null, "draw_weapon", null, null, 0f),
            });
            sim.Run(3);
            var warning = Assert.Single(w.Journal.Entries, e => e.Kind == "warning");
            Assert.Contains("Far Place", warning.Text);
        }

        [Fact]
        public void Deed_after_arrival_has_no_warning()
        {
            var w = new World(Helpers.Medieval(), 1);
            w.Add(new Place("near", "Near Place", new Vec2(4, 0), 3f));
            Helpers.Player(w, 0, 0);
            var sim = new Simulation(w, new[]
            {
                new PlayerCommand(0, "goto", "near", null, null, null, 0f),
                new PlayerCommand(5, "deed", null, "draw_weapon", null, null, 0f),
            });
            sim.Run(6);
            Assert.DoesNotContain(w.Journal.Entries, e => e.Kind == "warning");
        }

        [Fact]
        public void Frame_interval_samples_frames_to_bound_memory()
        {
            var sim = TheftScene(3);
            sim.FrameInterval = 12;
            sim.Run(World.TicksPerDay);
            Assert.Equal(World.TicksPerDay / 12, sim.Frames.Count);
            Assert.Equal(12, sim.Frames[1].Tick);
        }

        [Fact]
        public void Frame_interval_below_one_is_rejected()
        {
            var sim = TheftScene(3);
            Assert.Throws<System.ArgumentOutOfRangeException>(() => sim.FrameInterval = 0);
        }

        [Fact]
        public void Buy_command_records_a_trade()
        {
            var sim = TheftScene(3);
            var w = sim.World;
            var cmdSim = new Simulation(w, new[] { new PlayerCommand(0, "buy", null, null, "baker", null, 2f) });
            cmdSim.Run(1);
            var trade = Assert.Single(cmdSim.Trades);
            Assert.Equal("baker", trade.TraderId);
            Assert.False(trade.Result.Refused);
        }
    }
}
