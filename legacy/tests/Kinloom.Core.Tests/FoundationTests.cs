using System.Linq;
using Kinloom.Core;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class FoundationTests
    {
        [Fact]
        public void Random_is_deterministic_per_seed()
        {
            var a = new DeterministicRandom(42);
            var b = new DeterministicRandom(42);
            for (int i = 0; i < 100; i++) Assert.Equal(a.NextUInt(), b.NextUInt());
        }

        [Fact]
        public void Random_float_stays_in_unit_range()
        {
            var r = new DeterministicRandom(1);
            for (int i = 0; i < 1000; i++)
            {
                float f = r.NextFloat();
                Assert.True(f >= 0f && f < 1f, $"out of range: {f}");
            }
        }

        [Fact]
        public void Seed_zero_still_produces_numbers()
        {
            var r = new DeterministicRandom(0);
            Assert.NotEqual(0u, r.NextUInt());
        }

        [Fact]
        public void MoveTowards_stops_exactly_at_target()
        {
            var p = new Vec2(0, 0).MoveTowards(new Vec2(3, 4), 10f);
            Assert.Equal(3f, p.X);
            Assert.Equal(4f, p.Y);
            var q = new Vec2(0, 0).MoveTowards(new Vec2(3, 4), 1f);
            Assert.Equal(1.0, new Vec2(0, 0).DistanceTo(q), 3);
        }

        [Fact]
        public void Schedule_wraps_around_midnight()
        {
            var s = new Schedule().Add(22, "home").Add(7, "work");
            Assert.Equal("home", s.PlaceAt(3));
            Assert.Equal("work", s.PlaceAt(7));
            Assert.Equal("work", s.PlaceAt(21));
            Assert.Equal("home", s.PlaceAt(23));
        }

        [Fact]
        public void Empty_schedule_returns_null() => Assert.Null(new Schedule().PlaceAt(10));

        [Fact]
        public void Why_follows_causes_back_to_the_root()
        {
            var j = new Journal();
            int a = j.Add(0, "deed", null, "A");
            int b = j.Add(1, "witness", null, "B", a);
            int c = j.Add(2, "reaction", null, "C", b);
            Assert.Equal(new[] { "C", "B", "A" }, j.Why(c).Select(e => e.Text));
        }

        [Fact]
        public void Why_with_unknown_id_is_empty() => Assert.Empty(new Journal().Why(99));

        [Fact]
        public void Journal_rejects_a_cause_that_does_not_exist_yet()
        {
            var j = new Journal();
            Assert.Throws<System.ArgumentOutOfRangeException>(() => j.Add(0, "deed", null, "A", 5));
        }
    }
}
