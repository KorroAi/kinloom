using System.Text.Json;
using System.Text.Json.Nodes;
using Kinloom.Config;
using Kinloom.Llm;
using Kinloom.Schema;

namespace Kinloom.Cli;

internal sealed class TestReport
{
    public bool Passed { get; set; } = true;
    public List<string> Lines { get; } = new();
}

/// <summary><c>kinloom test</c>: replays <c>kinloom/tests/*.test.json</c> with a scripted model (no tokens) and checks expectations.
/// Format: <c>{ description, script: {task: [answers]}, resolve: ok|refused|failed, steps: [...], expect: [...] }</c>.</summary>
internal static class TestRunner
{
    public static TestReport Run(string dir)
    {
        var report = new TestReport();
        dir = Path.GetFullPath(dir);
        KinloomConfig config;
        try { config = KinloomConfig.Load(dir); }
        catch (InvalidOperationException e) { report.Passed = false; report.Lines.Add("FAIL kinloom.json: " + e.Message); return report; }
        string testsDir = Path.Combine(config.ManifestDir(dir), "tests");
        var files = Directory.Exists(testsDir) ? Directory.GetFiles(testsDir, "*.test.json").OrderBy(f => f, StringComparer.Ordinal).ToList() : new List<string>();
        if (files.Count == 0) { report.Lines.Add($"no tests found in {Path.GetRelativePath(dir, testsDir)} (files named *.test.json)"); return report; }
        int passed = 0;
        foreach (var file in files)
        {
            var problems = RunOne(dir, config, file, out string description);
            string name = Path.GetFileName(file);
            if (problems.Count == 0) { passed++; report.Lines.Add($"PASS {name}{(description.Length > 0 ? " — " + description : "")}"); }
            else
            {
                report.Passed = false;
                report.Lines.Add($"FAIL {name}{(description.Length > 0 ? " — " + description : "")}: {problems[0]}");
                foreach (var p in problems.Skip(1)) report.Lines.Add("     " + p);
            }
        }
        report.Lines.Add($"{passed}/{files.Count} passed");
        return report;
    }

    private static List<string> RunOne(string dir, KinloomConfig config, string file, out string description)
    {
        var problems = new List<string>();
        description = "";
        JsonObject test;
        try { test = JsonNode.Parse(File.ReadAllText(file), documentOptions: new JsonDocumentOptions { CommentHandling = JsonCommentHandling.Skip, AllowTrailingCommas = true }) as JsonObject ?? throw new JsonException("not an object"); }
        catch (JsonException e) { problems.Add("invalid JSON: " + e.Message); return problems; }
        description = test["description"]?.GetValue<string>() ?? "";

        var options = config.ToOptions(dir, _ => null);
        ILlmClient? model = test["script"] is JsonObject script ? ScriptFile.Parse(script.ToJsonString()) : null;
        options.Fast = model;
        options.Deep = model;
        options.Prices = null;
        var session = new KinloomSession(options);
        config.RegisterMedia(session.Media, dir);
        var manifestErrors = new List<ManifestError>();
        var declared = Manifest.LoadDirectory(config.ManifestDir(dir), manifestErrors);
        if (manifestErrors.Count == 0) manifestErrors.AddRange(session.Declare(declared));
        if (manifestErrors.Count > 0) { problems.AddRange(manifestErrors.Select(e => "manifest: " + e)); return problems; }

        var resolution = (test["resolve"]?.GetValue<string>() ?? "ok").ToLowerInvariant();
        var effects = new List<Effect>();
        var replies = new List<string>();
        var generated = new List<(string id, GenerateResult result)>();
        double time = 0;

        EffectResult Outcome(Effect e) => resolution == "refused" ? EffectResult.Refused("refused by the test") : resolution == "failed" ? EffectResult.Failed("failed by the test") : EffectResult.Ok();
        void PumpOnce()
        {
            foreach (var e in session.Pump(time)) { effects.Add(e); session.Resolve(e.Id, Outcome(e)); }
        }
        void Settle(Task? until = null)
        {
            for (int i = 0; i < 500; i++)
            {
                PumpOnce();
                if ((until == null || until.IsCompleted) && !session.HasRoleWork) { PumpOnce(); return; }
                Thread.Sleep(10);
            }
            problems.Add("the runtime did not settle within 5 s");
        }

        foreach (var node in test["steps"] as JsonArray ?? new JsonArray())
        {
            if (!(node is JsonObject step)) continue;
            if (step["time"] is JsonValue tv && tv.TryGetValue(out double t)) time = Math.Max(time, t);
            if (step["update"] is JsonObject u) session.Update(u["thing"]?.GetValue<string>() ?? "", u["props"] as JsonObject ?? new JsonObject());
            if (step["event"] is JsonObject ev)
                session.Emit(new GameEvent(ev["type"]?.GetValue<string>() ?? "", ev["data"]?.DeepClone() as JsonObject,
                    (ev["perceivedBy"] as JsonArray)?.Select(x => x?.GetValue<string>() ?? "").ToArray()));
            if (step["wait"] is JsonValue wv && wv.TryGetValue(out double wait))
            {
                double end = time + wait;
                while (time < end) { time = Math.Min(end, time + 1); Settle(); }
            }
            if (step["ask"] is JsonObject ask)
            {
                var task = session.Ask(ask["role"]?.GetValue<string>() ?? "", ask["input"]?.GetValue<string>() ?? "", ask["from"]?.GetValue<string>());
                Settle(task);
                if (task.IsCompleted) { var r = task.Result; if (r.Error != null) problems.Add("ask: " + r.Error); if (r.Reply != null) replies.Add(r.Reply); }
                continue;
            }
            if (step["generate"] is JsonObject gen)
            {
                string id = gen["generator"]?.GetValue<string>() ?? "";
                var task = session.Generate(id, gen["context"]?.DeepClone() as JsonObject);
                Settle(task);
                if (task.IsCompleted) generated.Add((id, task.Result));
                continue;
            }
            Settle();
        }

        var journal = session.Journal.Recent(2000);
        foreach (var node in test["expect"] as JsonArray ?? new JsonArray())
        {
            if (!(node is JsonObject ex)) continue;
            if (ex["effect"] is JsonObject want && !effects.Any(e => Matches(e, want)))
                problems.Add($"expected an effect {Describe(want)}; got {(effects.Count == 0 ? "none" : string.Join(", ", effects.Select(e => e.ToString())))}");
            if (ex["noEffect"] is JsonObject forbid && effects.FirstOrDefault(e => Matches(e, forbid)) is Effect bad)
                problems.Add($"expected no effect {Describe(forbid)}; got {bad}");
            if (ex["refused"]?.GetValue<string>() is string refused && !journal.Any(j => (j.Kind == "refused" || j.Kind == "dropped") && Contains(j.Text, refused)))
                problems.Add($"expected a refusal mentioning \"{refused}\"");
            if (ex["reply"]?.GetValue<string>() is string reply && !replies.Any(r => Contains(r, reply)))
                problems.Add($"expected a reply containing \"{reply}\"; got {(replies.Count == 0 ? "none" : string.Join(" | ", replies))}");
            if (ex["journal"]?.GetValue<string>() is string line && !journal.Any(j => Contains(j.Text, line)))
                problems.Add($"expected a journal line containing \"{line}\"");
            if (ex["generated"]?.GetValue<string>() is string genId && !generated.Any(g => g.id == genId && g.result.Ok))
                problems.Add($"expected generator {genId} to succeed" + (generated.FirstOrDefault(g => g.id == genId).result is GenerateResult gr ? ": " + string.Join("; ", gr.Errors) : ""));
            if (ex["fallback"] is JsonValue fb && fb.TryGetValue(out bool wantFallback) && (session.Stats.Fallbacks > 0) != wantFallback)
                problems.Add(wantFallback ? "expected a fallback" : "expected no fallback");
        }
        return problems;
    }

    private static bool Contains(string text, string part) => text.IndexOf(part, StringComparison.OrdinalIgnoreCase) >= 0;

    private static bool Matches(Effect e, JsonObject want)
    {
        if (want["kind"]?.GetValue<string>() is string kind && !string.Equals(kind, e.Kind.ToString(), StringComparison.OrdinalIgnoreCase)) return false;
        if (want["thing"]?.GetValue<string>() is string thing && thing != e.Thing) return false;
        if (want["member"]?.GetValue<string>() is string member && member != e.Member) return false;
        if (want["text"]?.GetValue<string>() is string text && (e.Text == null || !Contains(e.Text, text))) return false;
        if (want["source"]?.GetValue<string>() is string source && source != e.Source) return false;
        return true;
    }

    private static string Describe(JsonObject want)
    {
        string kind = want["kind"]?.GetValue<string>() ?? "any";
        string target = (want["thing"]?.GetValue<string>() ?? "") + (want["member"] != null ? "." + want["member"]!.GetValue<string>() : "");
        return (kind + " " + target).Trim() + (want["text"] != null ? $" \"{want["text"]}\"" : "");
    }
}
