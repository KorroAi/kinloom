using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using Kinloom.Core;
using Kinloom.Sim;
using Xunit;

namespace Kinloom.Core.Tests
{
    /// <summary>Skips (instead of passing vacuously) when no Chrome/Chromium is installed.</summary>
    public sealed class BrowserFactAttribute : FactAttribute
    {
        public BrowserFactAttribute()
        {
            if (Browser.Path == null) Skip = "Chrome/Chromium not found (set KINLOOM_CHROME to its path)";
        }
    }

    internal static class Browser
    {
        public static readonly string? Path = Find();

        private static string? Find()
        {
            var candidates = new[]
            {
                Environment.GetEnvironmentVariable("KINLOOM_CHROME"),
                @"C:\Program Files\Google\Chrome\Application\chrome.exe",
                @"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                "/usr/bin/chromium", "/usr/bin/google-chrome",
            };
            return candidates.FirstOrDefault(p => !string.IsNullOrEmpty(p) && File.Exists(p));
        }

        /// <summary>Loads the page in headless Chrome, lets its scripts run, returns the rendered DOM.</summary>
        public static string RenderedDom(string file, string hash = "")
        {
            string profile = Directory.CreateDirectory(System.IO.Path.Combine(System.IO.Path.GetTempPath(), "kinloom-chrome-" + Guid.NewGuid().ToString("N"))).FullName;
            var psi = new ProcessStartInfo(Path!) { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
            foreach (var a in new[] { "--headless=new", "--disable-gpu", "--no-first-run", "--allow-file-access-from-files", $"--user-data-dir={profile}", "--virtual-time-budget=3000", "--dump-dom", new Uri(file).AbsoluteUri + hash })
                psi.ArgumentList.Add(a);
            using var p = Process.Start(psi)!;
            string dom = p.StandardOutput.ReadToEnd();
            p.StandardError.ReadToEnd();
            p.WaitForExit(60000);
            return dom;
        }
    }

    public class ViewerTests
    {
        private static string Template => System.IO.Path.Combine(ScenarioTests.Root(), "viewer", "template.html");

        private static string Replay(Action<Simulation>? tweak = null)
        {
            var sim = ScenarioTests.RunVillage(42, 2 * World.TicksPerDay);
            tweak?.Invoke(sim);
            string file = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"kinloom-viewer-{Guid.NewGuid():N}.html");
            ReplayExporter.WriteHtml(sim, Template, file);
            return file;
        }

        private static string Between(string dom, string startId)
        {
            int i = dom.IndexOf($"id=\"{startId}\"", StringComparison.Ordinal);
            Assert.True(i >= 0, $"#{startId} not found in rendered page");
            return dom.Substring(i, Math.Min(4000, dom.Length - i));
        }

        [BrowserFact]
        public void Deep_link_opens_the_moment_and_explains_the_selected_character()
        {
            string dom = Browser.RenderedDom(Replay(), "#t=138&select=guard");
            Assert.Contains("D1 11:30", Between(dom, "clock"));
            string inspector = Between(dom, "inspector");
            Assert.Contains("Captain Aldric", inspector);
            Assert.Contains("Why?", inspector);
            Assert.Contains("recognizes The Stranger", inspector);
        }

        [BrowserFact]
        public void Deep_link_to_an_unknown_character_or_time_falls_back_gracefully()
        {
            string dom = Browser.RenderedDom(Replay(), "#t=999999&select=nobody");
            Assert.Contains("D2 23:55", Between(dom, "clock"));
            Assert.Contains("Click a character.", Between(dom, "inspector"));
        }

        [BrowserFact]
        public void Template_without_data_shows_the_empty_state()
        {
            string dom = Browser.RenderedDom(Template);
            Assert.Contains("No replay data", dom);
        }

        [BrowserFact]
        public void Journal_text_is_escaped_not_executed()
        {
            string file = Replay(sim => sim.World.Journal.Add(10, "note", null, "<img src=x onerror=\"document.title='pwned'\">"));
            string dom = Browser.RenderedDom(file, "#t=500");
            Assert.Contains("&lt;img src=x", Between(dom, "journal"));
            Assert.DoesNotContain("<title>pwned</title>", dom);
        }
    }
}
