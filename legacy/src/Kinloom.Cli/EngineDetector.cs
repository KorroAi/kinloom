using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Kinloom.Cli;

internal enum EngineKind { Godot, Unity, Unreal, Other }

internal sealed record Engine(EngineKind Kind, string? Version, string? Name, string Language);

/// <summary>Recognizes the game project in a folder from the files engines leave behind.</summary>
internal static class EngineDetector
{
    private static readonly string[] Skip = { ".git", ".godot", ".import", "bin", "obj", "node_modules", "Library", "Temp", "Intermediate", "Binaries", "Saved", ".kinloom" };

    public static Engine Detect(string dir)
    {
        string godot = Path.Combine(dir, "project.godot");
        if (File.Exists(godot))
        {
            string text = File.ReadAllText(godot);
            string? version = Regex.Match(text, "config/features=PackedStringArray\\(\"(\\d+\\.\\d+)\"").Groups[1].Value;
            string? name = Regex.Match(text, "config/name=\"([^\"]*)\"").Groups[1].Value;
            bool csharp = Directory.GetFiles(dir, "*.csproj").Length > 0 || text.Contains("\"C#\"");
            return new Engine(EngineKind.Godot, Empty(version), Empty(name), csharp ? "C#" : "GDScript");
        }
        string unity = Path.Combine(dir, "ProjectSettings", "ProjectVersion.txt");
        if (File.Exists(unity))
        {
            string version = Regex.Match(File.ReadAllText(unity), "m_EditorVersion:\\s*(\\S+)").Groups[1].Value;
            return new Engine(EngineKind.Unity, Empty(version), Path.GetFileName(Path.GetFullPath(dir)), "C#");
        }
        var uproject = Directory.GetFiles(dir, "*.uproject").FirstOrDefault();
        if (uproject != null)
        {
            string? version = null;
            try { version = (JsonNode.Parse(File.ReadAllText(uproject)) as JsonObject)?["EngineAssociation"]?.GetValue<string>(); }
            catch (System.Text.Json.JsonException) { }
            return new Engine(EngineKind.Unreal, Empty(version), Path.GetFileNameWithoutExtension(uproject), "C++");
        }
        return new Engine(EngineKind.Other, null, Path.GetFileName(Path.GetFullPath(dir)), Language(dir));
    }

    private static string? Empty(string? s) => string.IsNullOrWhiteSpace(s) ? null : s;

    /// <summary>The dominant source language, by file count.</summary>
    private static string Language(string dir)
    {
        var map = new Dictionary<string, string>
        {
            [".cs"] = "C#", [".gd"] = "GDScript", [".cpp"] = "C++", [".h"] = "C++", [".hpp"] = "C++", [".c"] = "C", [".py"] = "Python",
            [".ts"] = "TypeScript", [".js"] = "JavaScript", [".lua"] = "Lua", [".rs"] = "Rust", [".go"] = "Go", [".java"] = "Java", [".kt"] = "Kotlin",
            [".hx"] = "Haxe", [".swift"] = "Swift", [".zig"] = "Zig",
        };
        var counts = new Dictionary<string, int>();
        foreach (var file in Files(dir).Take(20000))
            if (map.TryGetValue(Path.GetExtension(file).ToLowerInvariant(), out var lang)) counts[lang] = counts.GetValueOrDefault(lang) + 1;
        return counts.Count == 0 ? "unknown" : counts.OrderByDescending(c => c.Value).First().Key;
    }

    /// <summary>Source files, skipping build output, engine caches and dependencies.</summary>
    public static IEnumerable<string> Files(string dir)
    {
        var stack = new Stack<string>();
        stack.Push(dir);
        while (stack.Count > 0)
        {
            string current = stack.Pop();
            string[] files, dirs;
            try { files = Directory.GetFiles(current); dirs = Directory.GetDirectories(current); }
            catch (UnauthorizedAccessException) { continue; }
            catch (IOException) { continue; }
            foreach (var f in files) yield return f;
            foreach (var d in dirs)
            {
                string name = Path.GetFileName(d);
                if (Skip.Contains(name, StringComparer.OrdinalIgnoreCase)) continue;
                if (name == "kinloom" && Path.GetFileName(current) == "addons") continue;
                stack.Push(d);
            }
        }
    }
}
