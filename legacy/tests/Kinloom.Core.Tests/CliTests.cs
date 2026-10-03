using System;
using System.Diagnostics;
using System.IO;
using Xunit;

namespace Kinloom.Core.Tests
{
    /// <summary>Runs the real Kinloom.Sim executable as a user would.</summary>
    public class CliTests
    {
        private static (int code, string stdout, string stderr) Run(params string[] args)
        {
            var psi = new ProcessStartInfo("dotnet") { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
            psi.ArgumentList.Add(Path.Combine(AppContext.BaseDirectory, "Kinloom.Sim.dll"));
            foreach (var a in args) psi.ArgumentList.Add(a);
            using var p = Process.Start(psi)!;
            string stdout = p.StandardOutput.ReadToEnd();
            string stderr = p.StandardError.ReadToEnd();
            p.WaitForExit();
            return (p.ExitCode, stdout, stderr);
        }

        private static string Temp() => Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), "kinloom-cli-" + Guid.NewGuid().ToString("N"))).FullName;
        private static string Scenario => Path.Combine(ScenarioTests.Root(), "scenarios", "village.json");
        private static string Pack => Path.Combine(ScenarioTests.Root(), "packs", "medieval.pack.json");

        [Fact]
        public void No_arguments_prints_usage_and_exits_2()
        {
            var (code, _, stderr) = Run();
            Assert.Equal(2, code);
            Assert.Contains("Usage", stderr);
        }

        [Fact]
        public void Missing_scenario_exits_1_with_a_readable_error()
        {
            var (code, _, stderr) = Run("nope.json", Pack, Temp());
            Assert.Equal(1, code);
            Assert.Contains("Scenario error: File not found", stderr);
        }

        [Fact]
        public void Full_run_writes_report_journal_and_replay()
        {
            string dir = Temp();
            var (code, stdout, _) = Run(Scenario, Pack, dir);
            Assert.Equal(0, code);
            Assert.Contains("Replay:", stdout);
            Assert.True(File.Exists(Path.Combine(dir, "report.txt")));
            Assert.True(File.Exists(Path.Combine(dir, "journal.txt")));
            Assert.True(File.Exists(Path.Combine(dir, "replay.html")));
        }

        [Fact]
        public void Publish_copies_the_replay_as_the_site_demo()
        {
            string dir = Temp(), site = Temp();
            var (code, stdout, _) = Run(Scenario, Pack, dir, "--publish", site);
            Assert.Equal(0, code);
            Assert.Equal(File.ReadAllText(Path.Combine(dir, "replay.html")), File.ReadAllText(Path.Combine(site, "demo.html")));
            Assert.Contains("Published:", stdout);
        }

        [Fact]
        public void Publish_without_a_folder_exits_2()
        {
            var (code, _, stderr) = Run(Scenario, Pack, Temp(), "--publish");
            Assert.Equal(2, code);
            Assert.Contains("--publish", stderr);
        }

        [Fact]
        public void Bench_rejects_a_bad_count_and_runs_a_good_one()
        {
            Assert.Equal(2, Run("--bench", "abc").code);
            var (code, stdout, _) = Run("--bench", "20", Pack);
            Assert.Equal(0, code);
            Assert.Contains("20 agents", stdout);
        }
    }
}
