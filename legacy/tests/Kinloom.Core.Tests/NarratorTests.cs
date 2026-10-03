using System.IO;
using System.Linq;
using Kinloom.Core;
using Kinloom.Game;
using Kinloom.Sim;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class NarratorTests
    {
        private static GameSession Village()
        {
            var scenario = ScenarioLoader.LoadScenario(Path.Combine(ScenarioTests.Root(), "scenarios", "village-game.json"));
            return new GameSession(ScenarioLoader.Build(scenario, ScenarioTests.Pack()));
        }

        private static GameSession PlayTheft()
        {
            var g = Village();
            g.WarmUp(10 * World.TicksPerHour);
            g.Player.Position = g.World.FindPlace("bakery")!.Position;
            g.Steal();
            for (int i = 0; i < 25; i++) g.Update(0.4f, new Vec2(0, 0));
            g.Player.Position = g.World.FindPlace("square")!.Position;
            for (int i = 0; i < 30; i++) g.Update(0.4f, new Vec2(0, 0));
            g.WarmUp(10 * World.TicksPerHour); // evening at the tavern: rumors
            return g;
        }

        [Fact]
        public void Feed_reads_like_a_story_not_like_a_log()
        {
            var texts = PlayTheft().Feed.Select(l => l.Text).ToList();
            Assert.Contains(texts, t => t == "You steal the Loaf of Bread from Berta.");
            Assert.Contains(texts, t => t == "Berta runs to tell the guard.");
            Assert.Contains(texts, t => t == "Berta tells Aldric you're a thief.");
            Assert.Contains(texts, t => t == "Aldric recognizes you, thanks to Berta.");
            Assert.Contains(texts, t => t == "Aldric confronts you about the theft.");
            Assert.Contains(texts, t => t == "The Loaf of Bread goes back to Berta.");
            Assert.Contains(texts, t => t.EndsWith("you robbed Berta.") && !t.StartsWith("Berta"));
            Assert.DoesNotContain(texts, t => t.Contains("bravery") || t.Contains("->") || t.Contains("The Stranger"));
        }

        [Fact]
        public void Drawing_a_weapon_makes_people_run_and_the_guard_react()
        {
            var g = Village();
            g.WarmUp(12 * World.TicksPerHour + 6); // 12:30, market time on the square
            g.Player.Position = g.World.FindPlace("square")!.Position;
            g.DrawWeapon();
            var texts = g.Feed.Select(l => l.Text).ToList();
            Assert.Contains("You draw your weapon.", texts);
            Assert.Contains(texts, t => t.EndsWith("runs away in fear."));
            Assert.Contains(texts, t => t == "Aldric comes after you.");
        }

        [Fact]
        public void Trades_and_kindness_are_narrated()
        {
            var g = Village();
            g.WarmUp(10 * World.TicksPerHour);
            g.Player.Position = g.World.FindPlace("field")!.Position;
            g.Help();
            g.Player.Position = g.World.FindPlace("forge")!.Position;
            g.Buy();
            var texts = g.Feed.Select(l => l.Text).ToList();
            Assert.Contains("You help Mila.", texts);
            Assert.Contains("Mila is grateful.", texts);
            Assert.Contains(texts, t => t.StartsWith("Hugo sells to you for 10.0"));
        }

        [Fact]
        public void Why_story_explains_the_guard_in_plain_words()
        {
            var g = PlayTheft();
            var story = g.WhyStory(g.World.GetAgent("guard"));
            Assert.Equal("The Loaf of Bread goes back to Berta.", story.First());
            Assert.Contains("Aldric recognizes you, thanks to Berta.", story);
            Assert.Contains("Berta saw you steal the Loaf of Bread.", story);
            Assert.Equal("You steal the Loaf of Bread from Berta.", story.Last());
        }

        [Fact]
        public void Opinion_changes_are_narrated_with_their_direction()
        {
            var g = Village();
            var up = new JournalEntry(0, 0, "opinion", "farmer", "Mila the Farmer's opinion of The Stranger: -0.19 -> +0.37", null);
            var down = new JournalEntry(0, 0, "opinion", "smith", "Hugo the Smith's opinion of The Stranger: 0.00 -> -0.26", null);
            Assert.Equal("Mila now likes you more (+0.37).", Narrator.Narrate(up, g.World, g.Player));
            Assert.Equal("Hugo now likes you less (-0.26).", Narrator.Narrate(down, g.World, g.Player));
        }

        [Fact]
        public void Unknown_formats_fall_back_to_the_raw_text()
        {
            var g = Village();
            var entry = new JournalEntry(0, 0, "note", null, "Something unusual happened", null);
            Assert.Equal("Something unusual happened", Narrator.Narrate(entry, g.World, g.Player));
        }
    }
}
