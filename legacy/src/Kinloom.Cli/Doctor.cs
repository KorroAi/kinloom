using System.Diagnostics;
using Kinloom.Config;
using Kinloom.Llm;
using Kinloom.Schema;

namespace Kinloom.Cli;

/// <summary><c>kinloom doctor</c>: checks config, key presence (never its value), manifest, prices and media tools.</summary>
internal static class Doctor
{
    public static Report Run(string dir, Func<string, string?> env, bool ping)
    {
        var report = new Report();
        dir = Path.GetFullPath(dir);
        KinloomConfig config;
        try { config = KinloomConfig.Load(dir); }
        catch (InvalidOperationException e) { report.Fail("✗ " + e.Message); return report; }
        report.Add(File.Exists(Path.Combine(dir, KinloomConfig.FileName)) ? "✓ kinloom.json found" : "• no kinloom.json (defaults; run `kinloom init`)");

        if (!string.IsNullOrEmpty(env("KINLOOM_PROVIDER")))
            report.Add($"• provider from the environment: {env("KINLOOM_PROVIDER")}");
        else if (config.ProviderKind == null)
            report.Add("• no provider: the game runs on rules and fallbacks only");
        else
        {
            report.Add($"• provider: {config.ProviderKind}, fast model: {config.FastModel ?? "(not set)"}, deep model: {config.DeepModel ?? config.FastModel ?? "(not set)"}");
            if (config.ProviderKind != "scripted" && config.ProviderKind != "ollama")
            {
                string keyEnv = config.KeyEnv ?? KinloomConfig.DefaultKeyEnv(config.ProviderKind);
                report.Add(!string.IsNullOrEmpty(env(keyEnv)) ? $"✓ {keyEnv} is set" : $"• {keyEnv} is not set: the game will run on rules and fallbacks only");
            }
        }
        var clients = config.CreateClients(env, dir);
        if (clients.Problem != null && config.ProviderKind != null) report.Add("• " + clients.Problem);

        var errors = new List<ManifestError>();
        string manifestDir = config.ManifestDir(dir);
        if (!Directory.Exists(manifestDir)) report.Fail($"✗ manifest folder {config.Manifest}/ not found");
        else
        {
            var d = Manifest.LoadDirectory(manifestDir, errors);
            if (errors.Count == 0) Manifest.Check(d, errors);
            if (errors.Count == 0)
                report.Add($"✓ manifest: {d.Types.Count} types, {d.Things.Count} things, {d.Events.Count} events, {d.Roles.Count} roles, {d.Behaviors.Count} behaviors, {d.Generators.Count} generators");
            else
            {
                report.Fail($"✗ manifest has {errors.Count} problem(s):");
                foreach (var e in errors.Take(40)) report.Add("    " + e);
            }
        }

        report.Add(config.Prices != null
            ? $"✓ prices declared{(config.PricesSource != null ? " (source: " + config.PricesSource + ")" : " (add prices.source: where they come from)")}"
            : "• no prices declared: costs are not computed (none are assumed)");
        report.Add(config.Media.Count > 0 ? $"✓ media tools: {string.Join(", ", config.Media.Select(m => m.Key))}" : "• no media tools declared (optional)");

        if (ping)
        {
            if (clients.Fast == null) report.Add("• ping skipped: no model client");
            else
            {
                var watch = Stopwatch.StartNew();
                var r = clients.Fast.CompleteAsync(new LlmRequest("doctor", "You check connectivity.", "Answer with the JSON object {\"ok\": true}.", 20, 0)).GetAwaiter().GetResult();
                if (r.Ok) report.Add($"✓ model answered in {watch.ElapsedMilliseconds} ms ({r.InputTokens} in / {r.OutputTokens} out tokens)");
                else report.Fail("✗ model call failed: " + r.Error);
            }
        }
        return report;
    }
}
