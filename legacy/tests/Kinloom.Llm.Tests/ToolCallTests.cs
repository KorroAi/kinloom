using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json.Nodes;
using Kinloom.Llm;

namespace Kinloom.Llm.Tests;

/// <summary>Captures the request body and answers with a canned JSON response.</summary>
internal sealed class FakeHandler : HttpMessageHandler
{
    private readonly string _response;
    public FakeHandler(string response) { _response = response; }
    public string? Body { get; private set; }
    public HttpRequestMessage? Request { get; private set; }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        Request = request;
        Body = request.Content == null ? null : await request.Content.ReadAsStringAsync(cancellationToken);
        return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(_response, Encoding.UTF8, "application/json") };
    }
}

public class ToolCallTests
{
    private static readonly LlmTool SetParam = new LlmTool("set_param", "Change a parameter of a thing.",
        JsonNode.Parse("""{"type":"object","properties":{"thing":{"type":"string"},"param":{"type":"string"},"value":{}},"required":["thing","param","value"]}""")!.AsObject());

    private static LlmRequest WithTools() => new LlmRequest("role:rex", "sys", "user", tools: new[] { SetParam });

    [Fact]
    public async Task OpenAi_sends_tools_and_no_json_mode_when_tools_are_given()
    {
        var handler = new FakeHandler("""{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}""");
        var client = new OpenAiCompatibleClient("https://x.test/v1", "k", "m", http: new HttpClient(handler));
        await client.CompleteAsync(WithTools());
        var body = JsonNode.Parse(handler.Body!)!;
        Assert.Equal("function", body["tools"]![0]!["type"]!.GetValue<string>());
        Assert.Equal("set_param", body["tools"]![0]!["function"]!["name"]!.GetValue<string>());
        Assert.Null(body["response_format"]);
    }

    [Fact]
    public async Task OpenAi_keeps_json_mode_without_tools()
    {
        var handler = new FakeHandler("""{"choices":[{"message":{"content":"{}"},"finish_reason":"stop"}]}""");
        var client = new OpenAiCompatibleClient("https://x.test/v1", "k", "m", http: new HttpClient(handler));
        await client.CompleteAsync(new LlmRequest("t", "sys", "user"));
        var body = JsonNode.Parse(handler.Body!)!;
        Assert.Equal("json_object", body["response_format"]!["type"]!.GetValue<string>());
        Assert.Null(body["tools"]);
    }

    [Fact]
    public async Task OpenAi_tool_calls_become_canonical_json()
    {
        var handler = new FakeHandler("""
            {"choices":[{"message":{"content":"Watch this.","tool_calls":[
              {"id":"c1","type":"function","function":{"name":"set_param","arguments":"{\"thing\":\"truck_2\",\"param\":\"aggression\",\"value\":0.9}"}}]},
              "finish_reason":"tool_calls"}],"usage":{"prompt_tokens":10,"completion_tokens":5}}
            """);
        var client = new OpenAiCompatibleClient("https://x.test/v1", "k", "m", http: new HttpClient(handler));
        var response = await client.CompleteAsync(WithTools());
        Assert.True(response.Ok, response.Error);
        var canon = JsonNode.Parse(response.Text)!;
        Assert.Equal("Watch this.", canon["thought"]!.GetValue<string>());
        Assert.Equal("set_param", canon["actions"]![0]!["tool"]!.GetValue<string>());
        Assert.Equal(0.9, canon["actions"]![0]!["args"]!["value"]!.GetValue<double>());
        Assert.Equal(10, response.InputTokens);
    }

    [Fact]
    public async Task OpenAi_broken_tool_arguments_are_kept_as_raw_text_for_repair()
    {
        var handler = new FakeHandler("""
            {"choices":[{"message":{"content":null,"tool_calls":[
              {"id":"c1","type":"function","function":{"name":"set_param","arguments":"{not json"}}]},"finish_reason":"tool_calls"}]}
            """);
        var client = new OpenAiCompatibleClient("https://x.test/v1", "k", "m", http: new HttpClient(handler));
        var response = await client.CompleteAsync(WithTools());
        Assert.True(response.Ok);
        var canon = JsonNode.Parse(response.Text)!;
        Assert.Equal("{not json", canon["actions"]![0]!["args"]!["_raw"]!.GetValue<string>());
    }

    [Fact]
    public async Task Anthropic_sends_tools_with_input_schema()
    {
        var handler = new FakeHandler("""{"content":[{"type":"text","text":"hi"}],"stop_reason":"end_turn","usage":{"input_tokens":3,"output_tokens":1}}""");
        var client = new AnthropicClient("k", "claude-test", http: new HttpClient(handler));
        await client.CompleteAsync(WithTools());
        var body = JsonNode.Parse(handler.Body!)!;
        Assert.Equal("set_param", body["tools"]![0]!["name"]!.GetValue<string>());
        Assert.Equal("object", body["tools"]![0]!["input_schema"]!["type"]!.GetValue<string>());
    }

    [Fact]
    public async Task Anthropic_tool_use_blocks_become_canonical_json()
    {
        var handler = new FakeHandler("""
            {"content":[{"type":"text","text":"Boost!"},{"type":"tool_use","id":"t1","name":"set_param","input":{"thing":"truck_2","param":"aggression","value":1}}],
             "stop_reason":"tool_use","usage":{"input_tokens":3,"output_tokens":1}}
            """);
        var client = new AnthropicClient("k", "claude-test", http: new HttpClient(handler));
        var response = await client.CompleteAsync(WithTools());
        Assert.True(response.Ok, response.Error);
        var canon = JsonNode.Parse(response.Text)!;
        Assert.Equal("Boost!", canon["thought"]!.GetValue<string>());
        Assert.Equal("truck_2", canon["actions"]![0]!["args"]!["thing"]!.GetValue<string>());
    }

    [Fact]
    public async Task Text_only_answers_pass_through_unchanged()
    {
        var handler = new FakeHandler("""{"choices":[{"message":{"content":"{\"say\":\"x\"}"},"finish_reason":"stop"}]}""");
        var client = new OpenAiCompatibleClient("https://x.test/v1", "k", "m", http: new HttpClient(handler));
        var response = await client.CompleteAsync(WithTools());
        Assert.Equal("{\"say\":\"x\"}", response.Text);
    }

    [Fact]
    public void Canonical_json_without_text_has_no_thought()
    {
        var canon = JsonNode.Parse(ToolCanon.Canonical(null, new[] { ("say", "{\"text\":\"a\"}") }))!;
        Assert.Null(canon["thought"]);
        Assert.Equal("a", canon["actions"]![0]!["args"]!["text"]!.GetValue<string>());
    }
}
