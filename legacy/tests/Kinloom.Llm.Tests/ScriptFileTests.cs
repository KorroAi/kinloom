using System.IO;
using Kinloom.Llm;

namespace Kinloom.Llm.Tests;

public class ScriptFileTests
{
    private static string Temp(string content)
    {
        string path = Path.Combine(Path.GetTempPath(), $"kinloom-script-{Guid.NewGuid():N}.json");
        File.WriteAllText(path, content);
        return path;
    }

    [Fact]
    public async Task Answers_are_queued_per_task_with_a_star_fallback()
    {
        string path = Temp("""{"role:rex":["a1","a2"],"*":["any"]}""");
        try
        {
            var client = ScriptFile.Load(path);
            Assert.Equal("a1", (await client.CompleteAsync(new LlmRequest("role:rex", "s", "u"))).Text);
            Assert.Equal("a2", (await client.CompleteAsync(new LlmRequest("role:rex", "s", "u"))).Text);
            Assert.Equal("any", (await client.CompleteAsync(new LlmRequest("role:rex", "s", "u"))).Text);
            Assert.False((await client.CompleteAsync(new LlmRequest("other", "s", "u"))).Ok);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public async Task Answers_may_be_json_objects_not_only_strings()
    {
        string path = Temp("""{"*":[{"say":"hello"}]}""");
        try
        {
            var client = ScriptFile.Load(path);
            Assert.Equal("{\"say\":\"hello\"}", (await client.CompleteAsync(new LlmRequest("x", "s", "u"))).Text);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Config_builds_a_scripted_client_from_the_environment()
    {
        string path = Temp("""{"*":["x"]}""");
        try
        {
            var env = new Dictionary<string, string> { ["KINLOOM_PROVIDER"] = "scripted", ["KINLOOM_SCRIPT"] = path };
            var client = LlmConfig.FromEnvironment(k => env.TryGetValue(k, out var v) ? v : null);
            Assert.NotNull(client);
            Assert.Equal("scripted", client!.Name);
        }
        finally { File.Delete(path); }
    }
}
