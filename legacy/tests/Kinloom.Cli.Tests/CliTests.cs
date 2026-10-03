using System.IO;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Kinloom.Cli;

namespace Kinloom.Cli.Tests;

/// <summary>A throwaway project folder.</summary>
public sealed class TempProject : IDisposable
{
    public TempProject() { Directory.CreateDirectory(Dir); }
    public string Dir { get; } = Path.Combine(Path.GetTempPath(), "kinloom-cli-" + Guid.NewGuid().ToString("N"));
    public string P(string relative) => Path.Combine(Dir, relative.Replace('/', Path.DirectorySeparatorChar));
    public void Write(string relative, string content) { Directory.CreateDirectory(Path.GetDirectoryName(P(relative))!); File.WriteAllText(P(relative), content); }
    public string Read(string relative) => File.ReadAllText(P(relative));
    public bool Exists(string relative) => File.Exists(P(relative));
    public void Dispose() { try { Directory.Delete(Dir, true); } catch (IOException) { } catch (UnauthorizedAccessException) { } }

    public Dictionary<string, string> Snapshot() =>
        Directory.GetFiles(Dir, "*", SearchOption.AllDirectories).ToDictionary(
            f => Path.GetRelativePath(Dir, f),
            f => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(f))));
}

internal static class Samples
{
    public const string Game = """
    {
      "types": {
        "Door": { "description": "A door.", "params": { "open": { "type": "boolean", "default": false } }, "functions": { "creak": {} } },
        "Hud": { "functions": { "show": { "args": { "text": { "type": "string", "max": 120 } } } } }
      },
      "things": [ { "id": "door_1", "type": "Door" }, { "id": "hud", "type": "Hud" } ],
      "events": { "knock": { "description": "Someone knocked.", "importance": 0.7 } },
      "roles": [
        { "id": "keeper", "mission": "You guard the door and speak through the HUD.", "sees": ["thing:door_1", "event:knock"],
          "can": ["set:door_1.open", "invoke:hud.show"], "wake": [ { "on": "event:knock" } ], "fallback": { "say": ["Who's there?"] } }
      ]
    }
    """;
}

public class EngineTests
{
    [Fact]
    public void Godot_projects_are_detected_with_their_version()
    {
        using var p = new TempProject();
        p.Write("project.godot", "config_version=5\n[application]\nconfig/name=\"Truck Town\"\nconfig/features=PackedStringArray(\"4.3\", \"Forward Plus\")\n");
        var e = EngineDetector.Detect(p.Dir);
        Assert.Equal(EngineKind.Godot, e.Kind);
        Assert.Equal("4.3", e.Version);
        Assert.Equal("Truck Town", e.Name);
    }

    [Fact]
    public void Unity_and_unreal_and_others_are_detected()
    {
        using var unity = new TempProject();
        unity.Write("ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 2022.3.10f1\n");
        Assert.Equal(EngineKind.Unity, EngineDetector.Detect(unity.Dir).Kind);
        Assert.Equal("2022.3.10f1", EngineDetector.Detect(unity.Dir).Version);

        using var unreal = new TempProject();
        unreal.Write("Racer.uproject", """{"EngineAssociation":"5.3"}""");
        Assert.Equal(EngineKind.Unreal, EngineDetector.Detect(unreal.Dir).Kind);
        Assert.Equal("5.3", EngineDetector.Detect(unreal.Dir).Version);

        using var other = new TempProject();
        other.Write("game/main.py", "print('hi')");
        other.Write("game/world.py", "x = 1");
        var e = EngineDetector.Detect(other.Dir);
        Assert.Equal(EngineKind.Other, e.Kind);
        Assert.Equal("Python", e.Language);
    }
}

public class InitTests
{
    private static TempProject GodotGame()
    {
        var p = new TempProject();
        p.Write("project.godot", "config_version=5\n\n[application]\n\nconfig/name=\"Tiny\"\nconfig/features=PackedStringArray(\"4.7\", \"Forward Plus\")\n");
        p.Write("player.gd", "extends CharacterBody2D\n@export var speed: float = 200.0\nfunc jump(height):\n\tpass\n");
        return p;
    }

    [Fact]
    public void Init_prepares_a_godot_project_for_the_agent()
    {
        using var p = GodotGame();
        var report = Init.Run(p.Dir, null, _ => null);
        Assert.True(report.Ok, string.Join("\n", report.Lines));
        foreach (var file in new[] { "kinloom.json", "kinloom/world.json", "kinloom/tests/example.test.json", "AGENTS.md", "CLAUDE.md",
                     ".claude/skills/kinloom-integrate/SKILL.md", ".cursor/rules/kinloom.mdc", "kinloom/docs/protocol.md",
                     "addons/kinloom/KinloomNode.cs", "addons/kinloom/GodotValues.cs", "addons/kinloom/bin/Kinloom.Runtime.dll", "addons/kinloom/bin/Kinloom.Llm.dll", "Tiny.csproj" })
            Assert.True(p.Exists(file), file + " missing");
        Assert.Contains("addons/kinloom/bin/Kinloom.Runtime.dll", p.Read("Tiny.csproj").Replace('\\', '/'));
        Assert.Contains("Godot.NET.Sdk/4.7", p.Read("Tiny.csproj"));
        string godot = p.Read("project.godot");
        Assert.Contains("Kinloom=\"*res://addons/kinloom/KinloomNode.cs\"", godot);
        Assert.Contains("\"C#\"", godot);
        Assert.DoesNotContain("sk-", p.Read("kinloom.json"));
    }

    [Fact]
    public void Init_is_idempotent()
    {
        using var p = GodotGame();
        Init.Run(p.Dir, null, _ => null);
        var before = p.Snapshot();
        var second = Init.Run(p.Dir, null, _ => null);
        Assert.True(second.Ok);
        Assert.Equal(before, p.Snapshot());
    }

    [Fact]
    public void Existing_agent_files_keep_their_content()
    {
        using var p = GodotGame();
        p.Write("AGENTS.md", "# My rules\nNever touch the save system.\n");
        Init.Run(p.Dir, null, _ => null);
        Init.Run(p.Dir, null, _ => null);
        string agents = p.Read("AGENTS.md");
        Assert.StartsWith("# My rules", agents);
        Assert.Equal(1, agents.Split("<!-- kinloom -->").Length - 1);
    }

    [Fact]
    public void The_provider_is_chosen_from_keys_that_exist_without_writing_them()
    {
        using var p = GodotGame();
        Init.Run(p.Dir, null, k => k == "DEEPSEEK_API_KEY" ? "sk-VERYSECRET" : null);
        var config = JsonNode.Parse(p.Read("kinloom.json"))!;
        Assert.Equal("deepseek", config["provider"]!["kind"]!.GetValue<string>());
        Assert.Equal("DEEPSEEK_API_KEY", config["provider"]!["keyEnv"]!.GetValue<string>());
        Assert.DoesNotContain("VERYSECRET", p.Read("kinloom.json"));
    }

    [Fact]
    public void Other_engines_get_the_kit_and_service_instructions()
    {
        using var p = new TempProject();
        p.Write("src/main.ts", "export const x = 1;");
        var report = Init.Run(p.Dir, null, _ => null);
        Assert.True(report.Ok);
        Assert.True(p.Exists("kinloom.json"));
        Assert.True(p.Exists("AGENTS.md"));
        Assert.False(p.Exists("addons/kinloom/bin/Kinloom.Runtime.dll"));
        Assert.Contains(report.Lines, l => l.Contains("kinloom serve"));
    }

    [Fact]
    public void A_javascript_or_typescript_game_gets_the_javascript_client()
    {
        using var p = new TempProject();
        p.Write("package.json", """{"name":"web-game","dependencies":{"phaser":"^3.80.0"}}""");
        p.Write("src/main.ts", "export const x = 1;");
        var report = Init.Run(p.Dir, null, _ => null);
        Assert.True(report.Ok);
        Assert.Contains("export class Kinloom", p.Read("kinloom/client/kinloom.js"));
        Assert.Contains("declare class Kinloom", p.Read("kinloom/client/kinloom.d.ts"));
        Assert.Contains(report.Lines, l => l.Contains("kinloom/client/kinloom.js"));
    }

    [Fact]
    public void A_python_game_gets_the_python_client()
    {
        using var p = new TempProject();
        p.Write("game.py", "import pygame");
        p.Write("sprites.py", "class Hero: pass");
        var report = Init.Run(p.Dir, null, _ => null);
        Assert.True(report.Ok);
        Assert.Contains("class Kinloom", p.Read("kinloom/client/kinloom_client.py"));
        Assert.Contains(report.Lines, l => l.Contains("kinloom/client/kinloom_client.py"));
    }

    [Fact]
    public void Other_languages_get_no_client_files()
    {
        using var p = new TempProject();
        p.Write("src/main.lua", "print('hi')");
        Init.Run(p.Dir, null, _ => null);
        Assert.False(Directory.Exists(p.P("kinloom/client")));
    }

    [Fact]
    public void The_example_test_passes_right_after_init()
    {
        using var p = GodotGame();
        Init.Run(p.Dir, null, _ => null);
        var result = TestRunner.Run(p.Dir);
        Assert.True(result.Passed, string.Join("\n", result.Lines));
    }
}

public class TestRunnerTests
{
    private static TempProject Project(string test)
    {
        var p = new TempProject();
        p.Write("kinloom/game.json", Samples.Game);
        p.Write("kinloom/tests/door.test.json", test);
        return p;
    }

    [Fact]
    public void A_good_test_passes()
    {
        using var p = Project("""
        {
          "description": "The keeper opens the door when someone knocks.",
          "script": { "role:keeper": ["{\"actions\":[{\"tool\":\"set_param\",\"args\":{\"thing\":\"door_1\",\"param\":\"open\",\"value\":true}},{\"tool\":\"invoke\",\"args\":{\"thing\":\"hud\",\"function\":\"show\",\"args\":{\"text\":\"Come in.\"}}}]}"] },
          "steps": [ { "time": 1, "event": { "type": "knock" } } ],
          "expect": [ { "effect": { "kind": "set", "thing": "door_1", "member": "open" } }, { "effect": { "kind": "invoke", "member": "show" } }, { "noEffect": { "kind": "destroy" } } ]
        }
        """);
        var result = TestRunner.Run(p.Dir);
        Assert.True(result.Passed, string.Join("\n", result.Lines));
        Assert.Contains(result.Lines, l => l.Contains("PASS") && l.Contains("door.test.json"));
    }

    [Fact]
    public void A_failing_expectation_is_explained()
    {
        using var p = Project("""
        {
          "script": { "*": ["{\"actions\":[]}"] },
          "steps": [ { "time": 1, "event": { "type": "knock" } } ],
          "expect": [ { "effect": { "kind": "set", "thing": "door_1", "member": "open" } } ]
        }
        """);
        var result = TestRunner.Run(p.Dir);
        Assert.False(result.Passed);
        Assert.Contains(result.Lines, l => l.Contains("FAIL") && l.Contains("set door_1.open"));
    }

    [Fact]
    public void Refusals_and_replies_can_be_expected()
    {
        using var p = Project("""
        {
          "script": { "role:keeper": ["{\"actions\":[{\"tool\":\"set_param\",\"args\":{\"thing\":\"hud\",\"param\":\"open\",\"value\":true}}]}", "{\"actions\":[]}"] },
          "steps": [ { "time": 1, "ask": { "role": "keeper", "input": "Open the HUD!" } } ],
          "expect": [ { "refused": "not a param" } ]
        }
        """);
        var result = TestRunner.Run(p.Dir);
        Assert.True(result.Passed, string.Join("\n", result.Lines));
    }
}

public class DoctorTests
{
    [Fact]
    public void The_key_is_reported_as_present_but_never_printed()
    {
        using var p = new TempProject();
        p.Write("kinloom.json", """{"provider":{"kind":"openai","keyEnv":"KINLOOM_TEST_KEY","fast":"m"}}""");
        p.Write("kinloom/game.json", Samples.Game);
        var report = Doctor.Run(p.Dir, k => k == "KINLOOM_TEST_KEY" ? "sk-VERYSECRET" : null, ping: false);
        string all = string.Join("\n", report.Lines);
        Assert.DoesNotContain("VERYSECRET", all);
        Assert.Contains("KINLOOM_TEST_KEY is set", all);
        Assert.True(report.Ok);
    }

    [Fact]
    public void A_missing_key_and_a_broken_manifest_are_reported()
    {
        using var p = new TempProject();
        p.Write("kinloom.json", """{"provider":{"kind":"deepseek","fast":"deepseek-flash"}}""");
        p.Write("kinloom/game.json", """{"things":[{"id":"a","type":"Nope"}]}""");
        var report = Doctor.Run(p.Dir, _ => null, ping: false);
        string all = string.Join("\n", report.Lines);
        Assert.Contains("DEEPSEEK_API_KEY is not set", all);
        Assert.Contains("things[0].type", all);
        Assert.False(report.Ok);
    }
}
