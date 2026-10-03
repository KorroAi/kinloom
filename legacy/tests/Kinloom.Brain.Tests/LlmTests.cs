using System.IO;
using System.Linq;
using Kinloom.Brain;
using Kinloom.Llm;

namespace Kinloom.Brain.Tests;

public class LlmTests
{
    [Fact]
    public async Task A_cassette_records_then_replays_without_the_model()
    {
        string path = Path.Combine(Path.GetTempPath(), $"kinloom-cassette-{System.Guid.NewGuid():N}.jsonl");
        try
        {
            var live = new ScriptedLlmClient("{\"a\":1}", "{\"a\":2}");
            var recorder = new CassetteClient(path, live);
            var r1 = new LlmRequest("plan", "sys", "user one");
            var r2 = new LlmRequest("plan", "sys", "user two");
            Assert.Equal("{\"a\":1}", (await recorder.CompleteAsync(r1)).Text);
            Assert.Equal("{\"a\":2}", (await recorder.CompleteAsync(r2)).Text);
            Assert.Equal(2, recorder.Recorded);

            var replay = new CassetteClient(path, null);
            Assert.Equal("{\"a\":2}", (await replay.CompleteAsync(r2)).Text);
            Assert.Equal("{\"a\":1}", (await replay.CompleteAsync(r1)).Text);
            Assert.False((await replay.CompleteAsync(new LlmRequest("plan", "sys", "never seen"))).Ok);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Config_picks_the_provider_from_the_key_that_is_set()
    {
        var env = new System.Collections.Generic.Dictionary<string, string> { ["DEEPSEEK_API_KEY"] = "x" };
        var client = LlmConfig.FromEnvironment(k => env.TryGetValue(k, out var v) ? v : null);
        Assert.Equal("deepseek-flash", client!.Name);

        env = new() { ["ANTHROPIC_API_KEY"] = "y" };
        Assert.Equal("claude-opus-5", LlmConfig.FromEnvironment(k => env.TryGetValue(k, out var v) ? v : null)!.Name);

        env = new() { ["KINLOOM_PROVIDER"] = "ollama" };
        Assert.Null(LlmConfig.FromEnvironment(k => env.TryGetValue(k, out var v) ? v : null)); // no model given: no guessing

        Assert.Null(LlmConfig.FromEnvironment(_ => null));
    }

    [Theory]
    [InlineData("08:30", 510)]
    [InlineData("8", 480)]
    [InlineData("2pm", 840)]
    [InlineData("12am", 0)]
    [InlineData("25:00", null)]
    [InlineData("noon", null)]
    public void Times_from_models_are_read_leniently(string text, int? expected)
    {
        Assert.Equal(expected, Json.MinuteOfDay(text));
    }

    [Fact]
    public void Json_is_found_inside_code_fences_and_chatter()
    {
        using var doc = Json.Parse("Sure! ```json\n{\"reply\": \"Hi\"}\n```");
        Assert.NotNull(doc);
        Assert.Equal("Hi", Json.Str(doc!.RootElement, "reply"));
    }
}
