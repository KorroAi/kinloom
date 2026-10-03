using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Kinloom.Cli;

internal sealed class Report
{
    public bool Ok { get; set; } = true;
    public List<string> Lines { get; } = new();
    public void Add(string line) => Lines.Add(line);
    public void Fail(string line) { Ok = false; Lines.Add(line); }
}

/// <summary><c>kinloom init</c>: prepares a game project so the developer's coding agent can integrate Kinloom.
/// Idempotent: running it again changes nothing that is already in place.</summary>
internal static class Init
{
    public const string Marker = "<!-- kinloom -->";
    public const string EndMarker = "<!-- /kinloom -->";

    public static Report Run(string dir, string? engineOverride, Func<string, string?> env)
    {
        var report = new Report();
        dir = Path.GetFullPath(dir);
        if (!Directory.Exists(dir)) { report.Fail($"folder not found: {dir}"); return report; }
        var engine = EngineDetector.Detect(dir);
        if (engineOverride != null && Enum.TryParse<EngineKind>(engineOverride, true, out var forced)) engine = engine with { Kind = forced };
        report.Add($"project: {engine.Name ?? Path.GetFileName(dir)} — {engine.Kind}{(engine.Version != null ? " " + engine.Version : "")}, {engine.Language}");

        WriteConfig(dir, env, report);
        WriteStarterManifest(dir, report);
        foreach (var (path, data) in Kit.Files("kit/docs")) Put(dir, Path.Combine("kinloom", "docs", path), data, report);
        MergeSection(dir, "AGENTS.md", Kit.Text("kit/AGENTS.md") ?? "", report);
        MergeSection(dir, "CLAUDE.md", Kit.Text("kit/CLAUDE.section.md") ?? "", report);
        Put(dir, ".claude/skills/kinloom-integrate/SKILL.md", Bytes(Kit.Text("kit/skills/kinloom-integrate/SKILL.md")), report);
        Put(dir, ".cursor/rules/kinloom.mdc", Bytes(Kit.Text("kit/cursor/kinloom.mdc")), report);
        EnsureIgnored(dir, report);

        switch (engine.Kind)
        {
            case EngineKind.Godot:
                SetUpGodot(dir, engine, report);
                break;
            case EngineKind.Unity:
                report.Add("Unity: no Unity adapter yet. Run `kinloom serve` and connect with the protocol in kinloom/docs/protocol.md (a C# client like RemoteSession works in Unity).");
                break;
            default:
                SetUpClient(dir, engine, report);
                break;
        }
        report.Add("next: tell your coding agent \"read AGENTS.md and integrate Kinloom\"; check with `kinloom doctor` and `kinloom test`.");
        return report;
    }

    private static byte[] Bytes(string? text) => Encoding.UTF8.GetBytes(text ?? "");

    /// <summary>Games outside .NET talk to `kinloom serve`; JavaScript/TypeScript and Python get a ready client.</summary>
    private static void SetUpClient(string dir, Engine engine, Report report)
    {
        bool web = File.Exists(Path.Combine(dir, "package.json")) || engine.Language is "JavaScript" or "TypeScript";
        if (web)
        {
            foreach (var (path, data) in Kit.Files("clients/javascript")) Put(dir, Path.Combine("kinloom", "client", path), data, report);
            report.Add("JavaScript/TypeScript: `import { Kinloom } from \"./kinloom/client/kinloom.js\"`, run `kinloom serve`, then `await Kinloom.connect()` (browser, Node 22+, Deno, Bun).");
            return;
        }
        if (engine.Language == "Python")
        {
            foreach (var (path, data) in Kit.Files("clients/python")) Put(dir, Path.Combine("kinloom", "client", path), data, report);
            report.Add("Python: `from kinloom_client import Kinloom` (standard library only, add kinloom/client to sys.path), run `kinloom serve`, then `Kinloom.connect()`.");
            return;
        }
        report.Add($"{engine.Kind}: run `kinloom serve` and connect from the game over WebSocket (kinloom/docs/protocol.md shows the messages; write a small {engine.Language} client).");
    }

    /// <summary>Writes a file unless it already has exactly these bytes.</summary>
    private static void Put(string dir, string relative, byte[] data, Report report)
    {
        string path = Path.Combine(dir, relative.Replace('/', Path.DirectorySeparatorChar));
        if (File.Exists(path) && File.ReadAllBytes(path).AsSpan().SequenceEqual(data)) return;
        bool existed = File.Exists(path);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllBytes(path, data);
        report.Add($"{(existed ? "updated" : "created")} {relative.Replace('\\', '/')}");
    }

    private static void WriteConfig(string dir, Func<string, string?> env, Report report)
    {
        string path = Path.Combine(dir, Config.KinloomConfig.FileName);
        if (File.Exists(path)) return;
        JsonObject provider;
        if (!string.IsNullOrEmpty(env("DEEPSEEK_API_KEY")))
            provider = new JsonObject { ["kind"] = "deepseek", ["keyEnv"] = "DEEPSEEK_API_KEY", ["fast"] = "deepseek-flash", ["deep"] = "deepseek-flash" };
        else if (!string.IsNullOrEmpty(env("ANTHROPIC_API_KEY")))
            provider = new JsonObject { ["kind"] = "anthropic", ["keyEnv"] = "ANTHROPIC_API_KEY", ["fast"] = "claude-haiku-4-5-20251001", ["deep"] = "claude-sonnet-5" };
        else if (!string.IsNullOrEmpty(env("OPENAI_API_KEY")))
            provider = new JsonObject { ["kind"] = "openai", ["keyEnv"] = "OPENAI_API_KEY", ["fast"] = "", ["deep"] = "" };
        else
            provider = new JsonObject { ["kind"] = "", ["keyEnv"] = "", ["fast"] = "", ["deep"] = "" };
        var config = new JsonObject
        {
            ["manifest"] = "kinloom",
            ["provider"] = provider,
            ["prices"] = new JsonObject { ["input"] = null, ["cachedInput"] = null, ["output"] = null, ["source"] = "" },
            ["language"] = "English",
            ["budget"] = new JsonObject { ["maxCallsPerMinute"] = 30, ["maxCostPerHour"] = null },
            ["media"] = new JsonObject(),
            ["servePort"] = 7717,
            ["debugPort"] = 7718,
        };
        File.WriteAllText(path, config.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n");
        report.Add("created kinloom.json" + (provider["kind"]!.GetValue<string>().Length == 0
            ? " (no API key found in the environment: fill provider.kind/keyEnv/fast/deep, or run with rules only)"
            : $" (provider {provider["kind"]}, key read from {provider["keyEnv"]} at run time)"));
        if (provider["kind"]!.GetValue<string>() == "openai") report.Add("set provider.fast and provider.deep in kinloom.json to the OpenAI models you want");
        report.Add("costs: add your provider's prices per million tokens to kinloom.json (prices.*, with prices.source) to see spend; none are assumed");
    }

    private static void WriteStarterManifest(string dir, Report report)
    {
        string manifestDir = Path.Combine(dir, "kinloom");
        bool hasManifest = Directory.Exists(manifestDir) && Directory.GetFiles(manifestDir, "*.json").Length > 0;
        if (hasManifest) return;
        Put(dir, "kinloom/world.json", Bytes(Kit.Text("kit/templates/world.json")), report);
        Put(dir, "kinloom/tests/example.test.json", Bytes(Kit.Text("kit/templates/example.test.json")), report);
    }

    /// <summary>Adds or refreshes the Kinloom section of an agent instructions file, keeping everything else.</summary>
    private static void MergeSection(string dir, string file, string section, Report report)
    {
        string path = Path.Combine(dir, file);
        string block = Marker + "\n" + section.Trim() + "\n" + EndMarker + "\n";
        string current = File.Exists(path) ? File.ReadAllText(path) : "";
        string next;
        int start = current.IndexOf(Marker, StringComparison.Ordinal);
        int end = current.IndexOf(EndMarker, StringComparison.Ordinal);
        if (start >= 0 && end > start) next = current.Substring(0, start) + block + current.Substring(end + EndMarker.Length).TrimStart('\r', '\n');
        else next = current.Length == 0 ? block : current.TrimEnd() + "\n\n" + block;
        if (next == current) return;
        File.WriteAllText(path, next);
        report.Add($"{(current.Length == 0 ? "created" : "updated")} {file}");
    }

    private static void EnsureIgnored(string dir, Report report)
    {
        string path = Path.Combine(dir, ".gitignore");
        if (!File.Exists(path)) return;
        string text = File.ReadAllText(path);
        if (text.Split('\n').Any(l => l.Trim() == ".kinloom/")) return;
        File.WriteAllText(path, text.TrimEnd() + "\n.kinloom/\n");
        report.Add("updated .gitignore (.kinloom/ holds the media cache)");
    }

    private static void SetUpGodot(string dir, Engine engine, Report report)
    {
        foreach (var (path, data) in Kit.Files("godot")) Put(dir, Path.Combine("addons", "kinloom", path), data, report);
        var libs = Kit.Files("lib").ToList();
        if (libs.Count == 0) report.Fail("this kinloom build has no runtime DLLs embedded; rebuild the CLI");
        foreach (var (path, data) in libs) Put(dir, Path.Combine("addons", "kinloom", "bin", path), data, report);

        string name = Regex.Replace(engine.Name ?? Path.GetFileName(dir), "[^A-Za-z0-9_]", "");
        if (name.Length == 0 || char.IsDigit(name[0])) name = "Game" + name;
        string? csproj = Directory.GetFiles(dir, "*.csproj").FirstOrDefault();
        if (csproj == null)
        {
            csproj = Path.Combine(dir, name + ".csproj");
            File.WriteAllText(csproj, $"""
                <Project Sdk="Godot.NET.Sdk/{SdkVersion(engine.Version)}">
                  <PropertyGroup>
                    <TargetFramework>net8.0</TargetFramework>
                    <EnableDynamicLoading>true</EnableDynamicLoading>
                    <RootNamespace>{name}</RootNamespace>
                  </PropertyGroup>
                </Project>

                """);
            report.Add($"created {Path.GetFileName(csproj)} (C# support for the Kinloom addon; GDScript keeps working)");
        }
        else name = Path.GetFileNameWithoutExtension(csproj);

        string project = File.ReadAllText(csproj);
        if (!project.Contains("Kinloom.Runtime", StringComparison.Ordinal))
        {
            const string refs = """
                  <ItemGroup Label="Kinloom">
                    <Reference Include="Kinloom.Runtime"><HintPath>addons/kinloom/bin/Kinloom.Runtime.dll</HintPath></Reference>
                    <Reference Include="Kinloom.Llm"><HintPath>addons/kinloom/bin/Kinloom.Llm.dll</HintPath></Reference>
                  </ItemGroup>

                """;
            int close = project.LastIndexOf("</Project>", StringComparison.Ordinal);
            File.WriteAllText(csproj, project.Substring(0, close) + refs + project.Substring(close));
            report.Add($"updated {Path.GetFileName(csproj)} (references addons/kinloom/bin)");
        }

        string godotPath = Path.Combine(dir, "project.godot");
        string godot = File.ReadAllText(godotPath);
        string updated = godot;
        var features = Regex.Match(updated, "config/features=PackedStringArray\\(([^)]*)\\)");
        if (features.Success && !features.Groups[1].Value.Contains("\"C#\""))
            updated = updated.Replace(features.Value, $"config/features=PackedStringArray({features.Groups[1].Value.TrimEnd()}, \"C#\")");
        updated = EnsureEntry(updated, "autoload", "Kinloom", "\"*res://addons/kinloom/KinloomNode.cs\"");
        updated = EnsureEntry(updated, "dotnet", "project/assembly_name", $"\"{name}\"");
        if (updated != godot)
        {
            File.WriteAllText(godotPath, updated);
            report.Add("updated project.godot (Kinloom autoload, C# feature)");
        }
        report.Add("Godot: build once with `dotnet build` (or the editor's Build button); then the Kinloom autoload reads kinloom.json and kinloom/*.json at startup.");
    }

    /// <summary>A Godot.NET.Sdk version for this project: the newest one in the local NuGet cache matching the editor's major.minor, else x.y.0.</summary>
    private static string SdkVersion(string? editor)
    {
        string wanted = editor ?? "4.3";
        string cache = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".nuget", "packages", "godot.net.sdk");
        if (Directory.Exists(cache))
        {
            var local = Directory.GetDirectories(cache).Select(Path.GetFileName)
                .Where(v => v != null && (v == wanted || v.StartsWith(wanted + ".", StringComparison.Ordinal)))
                .OrderByDescending(v => Version.TryParse(v, out var parsed) ? parsed : new Version(0, 0)).FirstOrDefault();
            if (local != null) return local;
        }
        return wanted.Count(c => c == '.') == 1 ? wanted + ".0" : wanted;
    }

    /// <summary>Adds <c>key=value</c> to a [section] of project.godot unless the key is already there.</summary>
    private static string EnsureEntry(string text, string section, string key, string value)
    {
        string header = "[" + section + "]";
        int at = text.IndexOf(header, StringComparison.Ordinal);
        if (at < 0) return text.TrimEnd() + "\n\n" + header + "\n\n" + key + "=" + value + "\n";
        int next = text.IndexOf("\n[", at + header.Length, StringComparison.Ordinal);
        string body = next < 0 ? text.Substring(at) : text.Substring(at, next - at);
        if (Regex.IsMatch(body, "^" + Regex.Escape(key) + "=", RegexOptions.Multiline)) return text;
        int insertAt = at + header.Length;
        return text.Substring(0, insertAt) + "\n\n" + key + "=" + value + text.Substring(insertAt).TrimStart('\r', '\n').Insert(0, "\n");
    }
}
