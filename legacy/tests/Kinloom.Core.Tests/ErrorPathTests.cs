using System;
using System.Linq;
using Kinloom.Core;
using Kinloom.Sim;
using Xunit;

namespace Kinloom.Core.Tests
{
    /// <summary>Every invalid scenario names what is wrong; every runtime problem is journaled, never thrown.</summary>
    public class ErrorPathTests
    {
        private static string BuildError(Action<ScenarioDefinition> corrupt)
        {
            var s = ScenarioTests.Village();
            corrupt(s);
            return Assert.Throws<ScenarioException>(() => ScenarioLoader.Build(s, ScenarioTests.Pack())).Message;
        }

        [Fact] public void Days_below_one() => Assert.Contains("'days'", BuildError(s => s.Days = 0));
        [Fact] public void Unknown_home() => Assert.Contains("unknown home place 'moon'", BuildError(s => s.Agents[0].Home = "moon"));
        [Fact] public void Schedule_hour_out_of_range() => Assert.Contains("schedule hour 24", BuildError(s => s.Agents[0].Schedule[0].Hour = 24));
        [Fact] public void Item_unknown_place() => Assert.Contains("Item 'bread': unknown place 'attic'", BuildError(s => s.Items[0].Place = "attic"));
        [Fact] public void Item_unknown_owner() => Assert.Contains("Item 'bread': unknown owner 'ghost'", BuildError(s => s.Items[0].Owner = "ghost"));
        [Fact] public void Duplicate_ids() => Assert.Contains("Duplicate id 'square'", BuildError(s => s.Places[1].Id = "square"));
        [Fact] public void Script_without_player() => Assert.Contains("no player", BuildError(s => s.Player = null));
        [Fact] public void Invalid_time() => Assert.Contains("Script step 1 (goto): invalid time", BuildError(s => s.Script[0].Minute = 60));
        [Fact] public void Unknown_action() => Assert.Contains("unknown action 'dance'", BuildError(s => s.Script[0].Action = "dance"));
        [Fact] public void Goto_unknown_place() => Assert.Contains("unknown place 'mars'", BuildError(s => s.Script[0].Place = "mars"));
        [Fact] public void Deed_unknown_target() => Assert.Contains("unknown target 'nobody'", BuildError(s => s.Script[1].Target = "nobody"));
        [Fact] public void Deed_unknown_item() => Assert.Contains("unknown item 'cake'", BuildError(s => s.Script[1].Item = "cake"));
        [Fact] public void Buy_from_non_trader() => Assert.Contains("'guard' is not a trader", BuildError(s => s.Script[4].Target = "guard"));
        [Fact] public void Buy_with_zero_price() => Assert.Contains("price must be greater than 0", BuildError(s => s.Script[4].Price = 0));

        private static (World w, Agent trader) Shop(bool withPlayer = true)
        {
            var w = new World(Helpers.Medieval(), 1);
            var trader = Helpers.Npc(w, "trader", 0, 0, 0.5f, 0.5f, Tags.Trader);
            Helpers.Npc(w, "farmer", 20, 0);
            if (withPlayer) Helpers.Player(w, 50, 0);
            return (w, trader);
        }

        [Fact]
        public void Runtime_problems_are_journaled_not_thrown()
        {
            var (w, _) = Shop();
            var sim = new Simulation(w, new[]
            {
                new PlayerCommand(0, "goto", "mars", null, null, null, 0f),
                new PlayerCommand(0, "buy", null, null, "farmer", null, 1f),
                new PlayerCommand(0, "buy", null, null, "trader", null, 1f),
                new PlayerCommand(0, "dance", null, null, null, null, 0f),
            });
            sim.Run(1);
            var errors = w.Journal.Entries.Where(e => e.Kind == "error").Select(e => e.Text).ToList();
            Assert.Contains(errors, t => t.Contains("Unknown place 'mars'"));
            Assert.Contains(errors, t => t.Contains("'farmer' is not a trader"));
            Assert.Contains(errors, t => t.Contains("too far to trade"));
            Assert.Contains(errors, t => t.Contains("Unknown action 'dance'"));
        }

        [Fact]
        public void Commands_without_a_player_are_ignored_with_an_error()
        {
            var (w, _) = Shop(withPlayer: false);
            var sim = new Simulation(w, new[] { new PlayerCommand(0, "goto", "mars", null, null, null, 0f) });
            sim.Run(1);
            Assert.Contains(w.Journal.Entries, e => e.Kind == "error" && e.Text.Contains("no player"));
        }

        [Fact]
        public void Report_counts_script_errors()
        {
            var (w, _) = Shop();
            var sim = new Simulation(w, new[] { new PlayerCommand(0, "dance", null, null, null, null, 0f) });
            sim.Run(1);
            Assert.Contains("1 script errors", Report.Build(sim));
        }

        [Fact]
        public void Public_state_accessors_report_what_happened()
        {
            var (w, trader) = Shop();
            var bread = w.Add(new Item("bread", "Bread", new Vec2(0, 0), 2.5f, "trader"));
            w.FindAgent("player")!.Position = new Vec2(1, 0);
            var sim = new Simulation(w, new[] { new PlayerCommand(0, "buy", null, null, "trader", null, 3f) }) { FrameInterval = 2 };
            sim.Run(World.TicksPerDay + 1);
            Assert.Equal(2, w.Day);
            Assert.Same(bread, Assert.Single(w.Items));
            Assert.Equal(2.5f, bread.Value);
            Assert.Equal("player", Assert.Single(sim.Trades).BuyerId);
            Assert.Equal(2, sim.FrameInterval);
            Assert.Empty(trader.Mind.Memories);
        }

        [Fact]
        public void Place_contains_points_within_its_radius()
        {
            var p = new Place("p", "P", new Vec2(10, 10), 3f);
            Assert.True(p.Contains(new Vec2(12, 10)));
            Assert.False(p.Contains(new Vec2(14, 10)));
        }
    }
}
