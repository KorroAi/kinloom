using System.Globalization;
using Kinloom.Core;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class CultureTests
    {
        [Fact]
        public void Journal_numbers_use_invariant_culture_whatever_the_machine_locale()
        {
            var previous = CultureInfo.CurrentCulture;
            try
            {
                CultureInfo.CurrentCulture = new CultureInfo("fr-FR");
                var w = new World(Helpers.Medieval(), 1);
                var smith = Helpers.Npc(w, "smith", 3, 0, 0.9f, 0.5f, Tags.Trader);
                var player = Helpers.Player(w, 0, 0);
                Actions.PerformDeed(w, player, "draw_weapon", null, null);
                Commerce.Trade(w, player, smith, 10f);
                Assert.All(w.Journal.Entries, e => Assert.DoesNotMatch(@"\d,\d", e.Text));
                Assert.Contains(w.Journal.Entries, e => e.Text.Contains("for 10.6"));
            }
            finally
            {
                CultureInfo.CurrentCulture = previous;
            }
        }

        [Fact]
        public void Positions_print_with_a_dot_whatever_the_machine_locale()
        {
            var previous = CultureInfo.CurrentCulture;
            try
            {
                CultureInfo.CurrentCulture = new CultureInfo("fr-FR");
                Assert.Equal("(1.5, 2)", new Vec2(1.5f, 2f).ToString());
            }
            finally
            {
                CultureInfo.CurrentCulture = previous;
            }
        }
    }
}
