using System.Text;
using System.Text.RegularExpressions;

namespace Kinloom.Cli.Mcp;

/// <summary>Finds what in a game's code could become Kinloom things: classes/scripts with their readable or writable state
/// and their callable functions. Regex-based and language-aware enough to guide an agent, not a compiler.</summary>
internal static class ProjectScanner
{
    internal sealed record Candidate(string File, string Name, string? Base, List<string> Properties, List<string> Functions, List<string> Signals);

    public const int MaxCandidates = 250;

    public static string Report(string dir)
    {
        var engine = EngineDetector.Detect(dir);
        var found = Scan(dir);
        var sb = new StringBuilder();
        sb.AppendLine($"engine: {engine.Kind}{(engine.Version != null ? " " + engine.Version : "")}, language: {engine.Language}");
        sb.AppendLine($"{found.Count} candidate(s){(found.Count >= MaxCandidates ? " (first " + MaxCandidates + ")" : "")}:");
        foreach (var c in found)
        {
            sb.Append($"- {c.File}: {c.Name}{(c.Base != null ? " : " + c.Base : "")}");
            if (c.Properties.Count > 0) sb.Append(" | state: " + string.Join(", ", c.Properties.Take(25)));
            if (c.Functions.Count > 0) sb.Append(" | functions: " + string.Join(", ", c.Functions.Take(25)));
            if (c.Signals.Count > 0) sb.Append(" | signals/events: " + string.Join(", ", c.Signals.Take(15)));
            sb.AppendLine();
        }
        sb.AppendLine();
        sb.AppendLine("How to use this: declare a Kinloom type for each kind of object the AI should read, steer or create. State the AI only reads = properties; state it may change = params (with ranges); functions = what it may call; signals/events = good Kinloom events. Then bind each object (Godot: Kinloom.Bind(id, node)) or send updates over the protocol.");
        return sb.ToString().TrimEnd();
    }

    public static List<Candidate> Scan(string dir)
    {
        var list = new List<Candidate>();
        foreach (var file in EngineDetector.Files(dir))
        {
            if (list.Count >= MaxCandidates) break;
            string ext = Path.GetExtension(file).ToLowerInvariant();
            if (ext is not (".gd" or ".cs" or ".h" or ".hpp" or ".py" or ".ts" or ".js" or ".lua")) continue;
            string text;
            try
            {
                if (new FileInfo(file).Length > 400_000) continue;
                text = File.ReadAllText(file);
            }
            catch (IOException) { continue; }
            string rel = Path.GetRelativePath(dir, file).Replace('\\', '/');
            switch (ext)
            {
                case ".gd": Gd(rel, text, list); break;
                case ".cs": CSharp(rel, text, list); break;
                case ".h": case ".hpp": Unreal(rel, text, list); break;
                case ".py": Python(rel, text, list); break;
                case ".ts": case ".js": Js(rel, text, list); break;
                case ".lua": Lua(rel, text, list); break;
            }
        }
        return list.Where(c => c.Properties.Count + c.Functions.Count + c.Signals.Count > 0).Take(MaxCandidates).ToList();
    }

    private static List<string> All(string text, string pattern, Func<Match, string> pick, RegexOptions options = RegexOptions.Multiline) =>
        Regex.Matches(text, pattern, options).Select(pick).Where(s => s.Length > 0).Distinct().ToList();

    private static void Gd(string file, string text, List<Candidate> list)
    {
        string name = Regex.Match(text, @"^class_name\s+(\w+)", RegexOptions.Multiline).Groups[1].Value;
        if (name.Length == 0) name = Path.GetFileNameWithoutExtension(file);
        string? baseType = Regex.Match(text, @"^extends\s+([\w.""/]+)", RegexOptions.Multiline).Groups[1].Value is { Length: > 0 } b ? b : null;
        var exported = All(text, @"^@export(?:_\w+)?(?:\([^)]*\))?\s+var\s+(\w+)\s*(?::\s*(\w+))?", m => m.Groups[1].Value + (m.Groups[2].Success ? ": " + m.Groups[2].Value : "") + " (exported)");
        var vars = All(text, @"^var\s+(\w+)\s*(?::\s*(\w+))?", m => m.Groups[1].Value + (m.Groups[2].Success ? ": " + m.Groups[2].Value : ""));
        var funcs = All(text, @"^func\s+(\w+)\s*\(([^)]*)\)", m => m.Groups[1].Value.StartsWith("_") ? "" : $"{m.Groups[1].Value}({m.Groups[2].Value.Trim()})");
        var signals = All(text, @"^signal\s+(\w+)", m => m.Groups[1].Value);
        list.Add(new Candidate(file, name, baseType, exported.Concat(vars).ToList(), funcs, signals));
    }

    private static void CSharp(string file, string text, List<Candidate> list)
    {
        foreach (Match cls in Regex.Matches(text, @"class\s+(\w+)\s*(?::\s*([\w.<>, ]+?))?\s*\{"))
        {
            string name = cls.Groups[1].Value;
            string? baseType = cls.Groups[2].Success ? cls.Groups[2].Value.Trim() : null;
            var fields = All(text, @"^\s*public\s+(?:static\s+|readonly\s+)*([\w<>\[\],.?]+)\s+(\w+)\s*(?:=|;|\{\s*get)", m => m.Groups[2].Value + ": " + m.Groups[1].Value);
            var serialized = All(text, @"\[(?:SerializeField|Export)\][^\n]*?\s(?:private\s+|protected\s+|public\s+)?([\w<>\[\],.?]+)\s+(\w+)\s*(?:=|;|\{)", m => m.Groups[2].Value + ": " + m.Groups[1].Value + " (serialized)");
            var methods = All(text, @"^\s*public\s+(?:virtual\s+|override\s+|static\s+|async\s+)*(?!class\b)([\w<>\[\],.?]+)\s+(\w+)\s*\(([^)]*)\)", m => $"{m.Groups[2].Value}({m.Groups[3].Value.Trim()})");
            var events = All(text, @"public\s+event\s+[\w<>.]+\s+(\w+)|\[Signal\]\s*public\s+delegate\s+void\s+(\w+)", m => m.Groups[1].Success ? m.Groups[1].Value : m.Groups[2].Value);
            list.Add(new Candidate(file, name, baseType, serialized.Concat(fields).Distinct().ToList(), methods, events));
            break; // one candidate per file keeps the report readable
        }
    }

    private static void Unreal(string file, string text, List<Candidate> list)
    {
        var cls = Regex.Match(text, @"class\s+(?:\w+_API\s+)?(\w+)\s*:\s*public\s+(\w+)");
        if (!cls.Success) return;
        var props = All(text, @"UPROPERTY\s*\([^)]*\)\s*([\w<>*:\s]+?)\s+(\w+)\s*(?:=[^;]*)?;", m => m.Groups[2].Value + ": " + m.Groups[1].Value.Trim(), RegexOptions.Singleline);
        var funcs = All(text, @"UFUNCTION\s*\([^)]*\)\s*(?:virtual\s+|static\s+)?([\w<>*:]+)\s+(\w+)\s*\(([^)]*)\)", m => $"{m.Groups[2].Value}({m.Groups[3].Value.Trim()})", RegexOptions.Singleline);
        var delegates = All(text, @"UPROPERTY\s*\([^)]*BlueprintAssignable[^)]*\)\s*\w+\s+(\w+);", m => m.Groups[1].Value, RegexOptions.Singleline);
        list.Add(new Candidate(file, cls.Groups[1].Value, cls.Groups[2].Value, props, funcs, delegates));
    }

    private static void Python(string file, string text, List<Candidate> list)
    {
        foreach (Match cls in Regex.Matches(text, @"^class\s+(\w+)(?:\(([^)]*)\))?:", RegexOptions.Multiline))
        {
            var attrs = All(text, @"self\.(\w+)\s*=", m => m.Groups[1].Value.StartsWith("_") ? "" : m.Groups[1].Value);
            var defs = All(text, @"^\s+def\s+(\w+)\s*\(\s*self\s*,?\s*([^)]*)\)", m => m.Groups[1].Value.StartsWith("_") ? "" : $"{m.Groups[1].Value}({m.Groups[2].Value.Trim()})");
            list.Add(new Candidate(file, cls.Groups[1].Value, cls.Groups[2].Success ? cls.Groups[2].Value : null, attrs, defs, new List<string>()));
            break;
        }
    }

    private static void Js(string file, string text, List<Candidate> list)
    {
        var cls = Regex.Match(text, @"class\s+(\w+)(?:\s+extends\s+([\w.]+))?");
        if (!cls.Success) return;
        var fields = All(text, @"^\s*(?:public\s+|private\s+|protected\s+|readonly\s+)*(\w+)\s*(?:\?)?\s*[:=][^=>(]", m => m.Groups[1].Value is "return" or "const" or "let" or "var" or "case" ? "" : m.Groups[1].Value);
        var methods = All(text, @"^\s*(?:public\s+|async\s+|static\s+)*(\w+)\s*\(([^)]*)\)\s*(?::\s*[\w<>\[\]]+\s*)?\{", m => m.Groups[1].Value is "if" or "for" or "while" or "switch" or "constructor" or "function" ? "" : $"{m.Groups[1].Value}({m.Groups[2].Value.Trim()})");
        list.Add(new Candidate(file, cls.Groups[1].Value, cls.Groups[2].Success ? cls.Groups[2].Value : null, fields, methods, new List<string>()));
    }

    private static void Lua(string file, string text, List<Candidate> list)
    {
        var funcs = All(text, @"function\s+([\w.:]+)\s*\(([^)]*)\)", m => $"{m.Groups[1].Value}({m.Groups[2].Value.Trim()})");
        if (funcs.Count > 0) list.Add(new Candidate(file, Path.GetFileNameWithoutExtension(file), null, new List<string>(), funcs, new List<string>()));
    }
}
