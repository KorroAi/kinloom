using System;
using System.Collections.Generic;
using System.Linq;
using Kinloom.Core;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class MindTests
    {
        private static World NewWorld()
        {
            var w = new World(Helpers.Medieval(), 1);
            w.Journal.Add(0, "deed", "player", "root entry"); // entry #0, used as memory cause
            return w;
        }

        [Fact]
        public void Victim_opinion_moves_twice_as_much_as_a_bystander()
        {
            var w = NewWorld();
            var victim = Helpers.Npc(w, "victim", 0, 0);
            var bystander = Helpers.Npc(w, "bystander", 1, 0);
            Learning.Learn(w, victim, Helpers.Seen("steal", "player", "victim", 0, -0.8f, true));
            Learning.Learn(w, bystander, Helpers.Seen("steal", "player", "victim", 0, -0.8f, true));
            Assert.Equal(-0.64, victim.Mind.OpinionOf("player"), 3);
            Assert.Equal(-0.32, bystander.Mind.OpinionOf("player"), 3);
        }

        [Fact]
        public void The_same_deed_is_learned_once()
        {
            var w = NewWorld();
            var npc = Helpers.Npc(w, "npc", 0, 0);
            Assert.True(Learning.Learn(w, npc, Helpers.Seen("steal", "player", null, 3, -0.8f, true)));
            Assert.False(Learning.Learn(w, npc, Helpers.Seen("steal", "player", null, 3, -0.8f, true)));
            Assert.Single(npc.Mind.Memories);
        }

        [Fact]
        public void Opinion_is_clamped_to_minus_one()
        {
            var w = NewWorld();
            var npc = Helpers.Npc(w, "npc", 0, 0);
            for (int i = 0; i < 20; i++) Learning.Learn(w, npc, Helpers.Seen("draw_weapon", "player", null, i, -0.3f));
            Assert.Equal(-1f, npc.Mind.OpinionOf("player"));
        }

        [Fact]
        public void Opinion_change_is_journaled_with_its_cause()
        {
            var w = NewWorld();
            var npc = Helpers.Npc(w, "npc", 0, 0);
            Learning.Learn(w, npc, Helpers.Seen("steal", "player", "npc", 0, -0.8f, true));
            var last = w.Journal.Entries.Last();
            Assert.Equal("opinion", last.Kind);
            Assert.Equal(0, last.CauseId);
            Assert.Equal(last.Id, npc.Mind.OpinionCause("player"));
        }

        [Fact]
        public void Crime_lookup_respects_confidence_and_handled_crimes()
        {
            var w = NewWorld();
            var guard = Helpers.Npc(w, "guard", 0, 0);
            var weak = new Memory("steal", "player", null, null, 1, false, "x", 0.3f, -0.8f, true, 0);
            Learning.Learn(w, guard, weak);
            Assert.Null(guard.Mind.CrimeBy("player", 0.5f));
            var strong = Helpers.Seen("steal", "player", null, 2, -0.8f, true);
            Learning.Learn(w, guard, strong);
            Assert.Equal(strong.Key, guard.Mind.CrimeBy("player", 0.5f)!.Key);
            guard.Mind.HandledCrimes.Add(strong.Key);
            Assert.Null(guard.Mind.CrimeBy("player", 0.5f));
        }

        [Fact]
        public void Unknown_ids_return_null_and_GetAgent_throws()
        {
            var w = NewWorld();
            Assert.Null(w.FindAgent("ghost"));
            Assert.Null(w.FindPlace(null));
            Assert.Throws<KeyNotFoundException>(() => w.GetAgent("ghost"));
        }

        [Fact]
        public void Duplicate_ids_are_rejected()
        {
            var w = NewWorld();
            Helpers.Npc(w, "a", 0, 0);
            Assert.Throws<ArgumentException>(() => Helpers.Npc(w, "a", 1, 1));
        }

        [Fact]
        public void Clock_formats_day_and_time()
        {
            Assert.Equal("D2 01:05", World.Clock(World.TicksPerDay + World.TicksPerHour + 1));
            Assert.Equal(2, World.DayOf(World.TicksPerDay));
        }

        [Fact]
        public void Unknown_deed_throws_with_its_name()
        {
            var ex = Assert.Throws<KeyNotFoundException>(() => Helpers.Medieval().Deed("teleport"));
            Assert.Contains("teleport", ex.Message);
        }
    }
}
