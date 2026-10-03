using System.IO;
using System.Text.RegularExpressions;
using Kinloom.Core;
using Kinloom.Sim;
using Xunit;

namespace Kinloom.Core.Tests
{
    public class ReplayTests
    {
        [Fact]
        public void Replay_html_embeds_data_and_escapes_closing_script_tags()
        {
            var sim = ScenarioTests.RunVillage(42, World.TicksPerDay);
            sim.World.Journal.Add(sim.World.Tick, "note", null, "</script><b>injected</b>");
            string outPath = Path.Combine(Path.GetTempPath(), $"kinloom-replay-{System.Guid.NewGuid():N}.html");
            ReplayExporter.WriteHtml(sim, Path.Combine(ScenarioTests.Root(), "viewer", "template.html"), outPath);
            string html = File.ReadAllText(outPath);
            Assert.DoesNotContain("/*__REPLAY_DATA__*/null", html);
            Assert.Contains("\"frames\"", html);
            Assert.Single(Regex.Matches(html, "</script>"));
        }

        [Fact]
        public void Template_without_marker_is_rejected()
        {
            var sim = ScenarioTests.RunVillage(42, 1);
            string template = Path.GetTempFileName();
            File.WriteAllText(template, "<html></html>");
            Assert.Throws<ScenarioException>(() => ReplayExporter.WriteHtml(sim, template, Path.GetTempFileName()));
        }

        [Fact]
        public void Report_lists_opinions_knowledge_and_why_chains()
        {
            var sim = ScenarioTests.RunVillage(42, 7 * World.TicksPerDay);
            string report = Report.Build(sim);
            Assert.Contains("Opinions of The Stranger", report);
            Assert.Contains("heard from", report);
            Assert.Contains("<-", report);
        }
    }
}
