using System.Text.Json.Nodes;
using Kinloom.Llm;

namespace Kinloom.Runtime.Tests;

public class GeneratorTests
{
    private const string Manifest = """
    {
      "types": { "Track": { "params": { "layout": "any" } } },
      "things": [ { "id": "track", "type": "Track" } ],
      "generators": [
        {
          "id": "section",
          "description": "A section of race track.",
          "schema": { "type": "object", "fields": { "segments": { "type": "list", "items": { "type": "enum", "options": ["straight", "left", "right"] } }, "name": "string" }, "required": ["segments"] },
          "constraints": ["len(value.segments) >= 4"],
          "fallback": { "segments": ["straight", "left", "straight", "right"], "name": "Default loop" }
        },
        {
          "id": "strict",
          "description": "A section with no fallback, checked by the game.",
          "schema": { "type": "object", "fields": { "segments": { "type": "list", "items": "string" } }, "required": ["segments"] },
          "gameValidate": true
        }
      ],
      "roles": [
        { "id": "designer", "mission": "You design tracks.", "sees": ["world"], "can": ["generate:section"] }
      ]
    }
    """;

    private static KinloomSession Make(ILlmClient? llm)
    {
        var s = new KinloomSession(new SessionOptions { Fast = llm });
        Assert.Empty(s.Declare(Manifest));
        return s;
    }

    private static async Task<GenerateResult> Run(KinloomSession s, string id, IEffectHandler? handler = null, JsonObject? context = null)
    {
        var task = s.Generate(id, context ?? new JsonObject { ["player_skill"] = "high" });
        for (int i = 0; i < 200 && !task.IsCompleted; i++)
        {
            if (handler != null) s.Pump(i, handler); else s.Pump(i);
            await Task.Delay(10);
        }
        if (!task.IsCompleted) throw new TimeoutException("generation never finished");
        return await task;
    }

    [Fact]
    public async Task A_valid_answer_is_accepted()
    {
        var llm = new ScriptedLlmClient("""{"value":{"segments":["straight","left","right","left"],"name":"Snake"}}""");
        var r = await Run(Make(llm), "section");
        Assert.True(r.Ok);
        Assert.Equal("Snake", r.Value!["name"]!.GetValue<string>());
        Assert.False(r.UsedFallback);
        Assert.Contains("player_skill", llm.Requests[0].User);
        Assert.Contains("\"segments\"", llm.Requests[0].System);
    }

    [Fact]
    public async Task The_value_may_come_without_a_wrapper()
    {
        var llm = new ScriptedLlmClient("""{"segments":["left","left","left","left"]}""");
        var r = await Run(Make(llm), "section");
        Assert.True(r.Ok);
    }

    [Fact]
    public async Task A_schema_error_is_repaired()
    {
        var llm = new ScriptedLlmClient("""{"value":{"segments":["up","left","right","left"]}}""", """{"value":{"segments":["straight","left","right","left"]}}""");
        var r = await Run(Make(llm), "section");
        Assert.True(r.Ok);
        Assert.Equal(2, llm.Requests.Count);
        Assert.Contains("must be one of", llm.Requests[1].User);
    }

    [Fact]
    public async Task A_constraint_violated_twice_falls_back()
    {
        var llm = new ScriptedLlmClient("""{"value":{"segments":["left"]}}""", """{"value":{"segments":["left","right"]}}""");
        var r = await Run(Make(llm), "section");
        Assert.True(r.Ok);
        Assert.True(r.UsedFallback);
        Assert.Equal("Default loop", r.Value!["name"]!.GetValue<string>());
        Assert.Contains(r.Errors, e => e.Contains("len(value.segments) >= 4"));
    }

    [Fact]
    public async Task Without_fallback_a_failure_reports_its_errors()
    {
        var llm = new ScriptedLlmClient("not json", "still not json");
        var r = await Run(Make(llm), "strict", new LambdaHandler(_ => EffectResult.Ok()));
        Assert.False(r.Ok);
        Assert.NotEmpty(r.Errors);
    }

    [Fact]
    public async Task The_game_can_refuse_and_its_reason_drives_the_repair()
    {
        var llm = new ScriptedLlmClient("""{"value":{"segments":["a"]}}""", """{"value":{"segments":["b"]}}""");
        int asked = 0;
        var handler = new LambdaHandler(e =>
        {
            if (e.Kind != EffectKind.Validate) return EffectResult.Ok();
            asked++;
            return e.Args["value"]!["segments"]![0]!.GetValue<string>() == "a" ? EffectResult.Refused("the track crosses itself") : EffectResult.Ok();
        });
        var r = await Run(Make(llm), "strict", handler);
        Assert.True(r.Ok);
        Assert.Equal(2, asked);
        Assert.Contains("the track crosses itself", llm.Requests[1].User);
    }

    [Fact]
    public async Task Without_a_model_the_fallback_is_used()
    {
        var r = await Run(Make(null), "section");
        Assert.True(r.Ok);
        Assert.True(r.UsedFallback);
    }

    [Fact]
    public async Task Unknown_generators_fail_cleanly()
    {
        var r = await Make(null).Generate("nope");
        Assert.False(r.Ok);
        Assert.Contains("unknown generator", r.Errors[0]);
    }

    [Fact]
    public async Task A_role_can_ask_a_generator_and_the_game_receives_the_result()
    {
        var llm = new ScriptedLlmClient(req => req.Task == "role:designer"
            ? """{"actions":[{"tool":"generate","args":{"generator":"section","brief":"something twisty"}}]}"""
            : """{"value":{"segments":["left","right","left","right"],"name":"Twister"}}""");
        var s = Make(llm);
        var ask = s.Ask("designer", "make me a track");
        var effects = new List<Effect>();
        for (int i = 0; i < 200 && !effects.Any(e => e.Member == "generated"); i++) { effects.AddRange(s.Pump(i)); await Task.Delay(10); }
        var delivered = effects.Single(e => e.Member == "generated");
        Assert.Equal("world", delivered.Thing);
        Assert.Equal("section", delivered.Args["generator"]!.GetValue<string>());
        Assert.Equal("Twister", delivered.Args["value"]!["name"]!.GetValue<string>());
        Assert.Contains("something twisty", llm.Requests.Single(r => r.Task == "generator:section").User);
        await ask;
    }
}
