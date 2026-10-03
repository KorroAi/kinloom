using System.Text.Json.Nodes;
using Kinloom.Cli;
using Kinloom.Cli.Mcp;

namespace Kinloom.Cli.Tests;

public class McpTests
{
    private static JsonNode Call(McpServer server, string json) => JsonNode.Parse(server.Handle(json).GetAwaiter().GetResult()!)!;

    private static JsonNode Tool(McpServer server, string name, JsonObject args) =>
        Call(server, new JsonObject { ["jsonrpc"] = "2.0", ["id"] = 9, ["method"] = "tools/call", ["params"] = new JsonObject { ["name"] = name, ["arguments"] = args } }.ToJsonString())["result"]!;

    private static string Text(JsonNode result) => string.Join("\n", result["content"]!.AsArray().Select(c => c!["text"]!.GetValue<string>()));

    [Theory]
    [InlineData("2025-06-18", "2025-06-18")]
    [InlineData("2024-11-05", "2024-11-05")]
    [InlineData("1999-01-01", "2025-11-25")]
    public void Initialize_negotiates_the_protocol_version(string asked, string expected)
    {
        var server = new McpServer(_ => null);
        var request = new JsonObject
        {
            ["jsonrpc"] = "2.0", ["id"] = 1, ["method"] = "initialize",
            ["params"] = new JsonObject { ["protocolVersion"] = asked, ["capabilities"] = new JsonObject(), ["clientInfo"] = new JsonObject { ["name"] = "t", ["version"] = "1" } },
        };
        var r = Call(server, request.ToJsonString());
        Assert.Equal(expected, r["result"]!["protocolVersion"]!.GetValue<string>());
        Assert.Equal("kinloom", r["result"]!["serverInfo"]!["name"]!.GetValue<string>());
        Assert.NotNull(r["result"]!["capabilities"]!["tools"]);
    }

    [Fact]
    public async Task Notifications_get_no_answer()
    {
        Assert.Null(await new McpServer(_ => null).Handle("""{"jsonrpc":"2.0","method":"notifications/initialized"}"""));
    }

    [Fact]
    public void All_tools_are_listed_with_input_schemas()
    {
        var r = Call(new McpServer(_ => null), """{"jsonrpc":"2.0","id":2,"method":"tools/list"}""");
        var tools = r["result"]!["tools"]!.AsArray();
        var names = tools.Select(t => t!["name"]!.GetValue<string>()).ToList();
        foreach (var n in new[] { "scan_project", "validate", "simulate_role", "attack_guardrails", "attach", "estimate_cost", "run_tests" })
            Assert.Contains(n, names);
        Assert.All(tools, t => Assert.Equal("object", t!["inputSchema"]!["type"]!.GetValue<string>()));
    }

    [Fact]
    public void Validate_returns_the_manifest_errors()
    {
        using var p = new TempProject();
        p.Write("kinloom/game.json", """{"things":[{"id":"a","type":"Nope"}]}""");
        var result = Tool(new McpServer(_ => null), "validate", new JsonObject { ["dir"] = p.Dir });
        Assert.Contains("things[0].type", Text(result));
        Assert.True(result["isError"]?.GetValue<bool>() ?? false);
    }

    [Fact]
    public void Simulate_role_without_a_model_shows_the_prompt_and_tools()
    {
        using var p = new TempProject();
        p.Write("kinloom/game.json", Samples.Game);
        var result = Tool(new McpServer(_ => null), "simulate_role", new JsonObject
        {
            ["dir"] = p.Dir, ["role"] = "keeper",
            ["situation"] = new JsonObject { ["time"] = 5, ["things"] = new JsonObject { ["door_1"] = new JsonObject { ["open"] = true } }, ["events"] = new JsonArray(new JsonObject { ["type"] = "knock" }) },
        });
        string text = Text(result);
        Assert.Contains("You guard the door", text);
        Assert.Contains("set_param", text);
        Assert.Contains("knock", text);
        Assert.Contains("open=true", text);
    }

    [Fact]
    public void Attack_guardrails_finds_no_escape()
    {
        using var p = new TempProject();
        p.Write("kinloom/game.json", Samples.Game);
        var result = Tool(new McpServer(_ => null), "attack_guardrails", new JsonObject { ["dir"] = p.Dir, ["role"] = "keeper" });
        string text = Text(result);
        Assert.Contains("escapes: 0", text);
        Assert.Contains("blocked:", text);
    }

    [Fact]
    public void Estimate_cost_refuses_to_invent_prices()
    {
        using var p = new TempProject();
        p.Write("kinloom/game.json", Samples.Game);
        var result = Tool(new McpServer(_ => null), "estimate_cost", new JsonObject { ["dir"] = p.Dir });
        Assert.Contains("prices", Text(result));
        Assert.True(result["isError"]?.GetValue<bool>() ?? false);
    }

    [Fact]
    public void Estimate_cost_uses_declared_prices()
    {
        using var p = new TempProject();
        p.Write("kinloom/game.json", Samples.Game);
        p.Write("kinloom.json", """{"prices":{"input":1,"cachedInput":0.1,"output":2,"source":"test prices"}}""");
        var result = Tool(new McpServer(_ => null), "estimate_cost", new JsonObject { ["dir"] = p.Dir, ["callsPerHour"] = 60 });
        string text = Text(result);
        Assert.Contains("keeper", text);
        Assert.Contains("test prices", text);
    }

    [Fact]
    public void Unknown_tools_are_errors()
    {
        var r = Call(new McpServer(_ => null), """{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"fly","arguments":{}}}""");
        Assert.NotNull(r["error"]);
    }

    [Fact]
    public void Scan_project_lists_candidates_across_engines()
    {
        using var p = new TempProject();
        p.Write("project.godot", "config_version=5\n");
        p.Write("enemies/slime.gd", "extends CharacterBody2D\nclass_name Slime\n@export var speed: float = 40.0\n@export var hp := 3\nsignal died\nfunc hop(height: float) -> void:\n\tpass\n");
        p.Write("unity/Door.cs", "using UnityEngine;\npublic class Door : MonoBehaviour {\n  public bool open;\n  [SerializeField] private float speed = 2f;\n  public void Creak(float volume) {}\n}\n");
        p.Write("unreal/Car.h", "UCLASS()\nclass ACar : public APawn {\n  UPROPERTY(EditAnywhere)\n  float MaxSpeed;\n  UFUNCTION(BlueprintCallable)\n  void Honk(float Volume);\n};\n");
        var result = Tool(new McpServer(_ => null), "scan_project", new JsonObject { ["dir"] = p.Dir });
        string text = Text(result);
        Assert.Contains("Slime", text);
        Assert.Contains("speed", text);
        Assert.Contains("hop", text);
        Assert.Contains("Door", text);
        Assert.Contains("Creak", text);
        Assert.Contains("ACar", text);
        Assert.Contains("MaxSpeed", text);
        Assert.Contains("Honk", text);
    }

    [Fact]
    public void Run_tests_reports_through_mcp()
    {
        using var p = new TempProject();
        p.Write("kinloom/game.json", Samples.Game);
        p.Write("kinloom/tests/t.test.json", """{"script":{"*":["{\"actions\":[]}"]},"steps":[{"time":1,"event":{"type":"knock"}}],"expect":[{"noEffect":{"kind":"destroy"}}]}""");
        var result = Tool(new McpServer(_ => null), "run_tests", new JsonObject { ["dir"] = p.Dir });
        Assert.Contains("PASS", Text(result));
    }
}
