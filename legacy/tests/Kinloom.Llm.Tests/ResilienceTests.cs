using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json.Nodes;
using Kinloom.Llm;

namespace Kinloom.Llm.Tests;

/// <summary>Answers with a scripted sequence of (status, body); the last one repeats.</summary>
internal sealed class SequenceHandler : HttpMessageHandler
{
    private readonly (HttpStatusCode status, string body)[] _answers;
    public SequenceHandler(params (HttpStatusCode, string)[] answers) { _answers = answers; }
    public int Calls { get; private set; }
    public List<string> Bodies { get; } = new List<string>();

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        Bodies.Add(request.Content == null ? "" : await request.Content.ReadAsStringAsync(cancellationToken));
        var (status, body) = _answers[Math.Min(Calls, _answers.Length - 1)];
        Calls++;
        if (status == 0) throw new HttpRequestException("connection reset");
        return new HttpResponseMessage(status) { Content = new StringContent(body, Encoding.UTF8, "application/json") };
    }
}

public class ResilienceTests
{
    private const string OpenAiOk = """{"choices":[{"message":{"content":"{\"actions\":[]}"},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":3}}""";
    private const string AnthropicOk = """{"content":[{"type":"text","text":"{\"actions\":[]}"}],"stop_reason":"end_turn","usage":{"input_tokens":10,"output_tokens":3}}""";
    private static LlmRequest Req() => new LlmRequest("role:x", "You are a test.", "Hello");

    [Theory]
    [InlineData(HttpStatusCode.TooManyRequests)]
    [InlineData(HttpStatusCode.InternalServerError)]
    [InlineData(HttpStatusCode.BadGateway)]
    [InlineData(HttpStatusCode.ServiceUnavailable)]
    [InlineData((HttpStatusCode)0)]
    public async Task OpenAi_retries_a_transient_failure_once(HttpStatusCode first)
    {
        var handler = new SequenceHandler((first, """{"error":"busy"}"""), (HttpStatusCode.OK, OpenAiOk));
        var client = new OpenAiCompatibleClient("https://x.test/v1", "k", "m", http: new HttpClient(handler));
        var r = await client.CompleteAsync(Req());
        Assert.True(r.Ok, r.Error);
        Assert.Equal(2, handler.Calls);
    }

    [Fact]
    public async Task OpenAi_does_not_retry_a_bad_request()
    {
        var handler = new SequenceHandler((HttpStatusCode.BadRequest, """{"error":"bad"}"""), (HttpStatusCode.OK, OpenAiOk));
        var client = new OpenAiCompatibleClient("https://x.test/v1", "k", "m", http: new HttpClient(handler));
        var r = await client.CompleteAsync(Req());
        Assert.False(r.Ok);
        Assert.Equal(1, handler.Calls);
    }

    [Fact]
    public async Task OpenAi_gives_up_after_one_retry()
    {
        var handler = new SequenceHandler((HttpStatusCode.ServiceUnavailable, """{"error":"down"}"""));
        var client = new OpenAiCompatibleClient("https://x.test/v1", "k", "m", http: new HttpClient(handler));
        var r = await client.CompleteAsync(Req());
        Assert.False(r.Ok);
        Assert.Contains("503", r.Error);
        Assert.Equal(2, handler.Calls);
    }

    [Fact]
    public async Task Anthropic_retries_a_transient_failure_once()
    {
        var handler = new SequenceHandler((HttpStatusCode.TooManyRequests, """{"error":"busy"}"""), (HttpStatusCode.OK, AnthropicOk));
        var client = new AnthropicClient("k", "claude-opus-5", http: new HttpClient(handler));
        var r = await client.CompleteAsync(Req());
        Assert.True(r.Ok, r.Error);
        Assert.Equal(2, handler.Calls);
    }

    [Fact]
    public async Task Anthropic_marks_the_stable_system_prompt_for_caching()
    {
        var handler = new SequenceHandler((HttpStatusCode.OK, AnthropicOk));
        var client = new AnthropicClient("k", "claude-opus-5", http: new HttpClient(handler));
        await client.CompleteAsync(Req());
        var body = JsonNode.Parse(handler.Bodies[0])!;
        var system = body["system"]!.AsArray();
        Assert.Equal("text", system[0]!["type"]!.GetValue<string>());
        Assert.StartsWith("You are a test.", system[0]!["text"]!.GetValue<string>());
        Assert.Equal("ephemeral", system[0]!["cache_control"]!["type"]!.GetValue<string>());
    }

    [Fact]
    public async Task Json_mode_requests_always_mention_json()
    {
        // DeepSeek (and OpenAI) reject json_object mode unless the prompt contains the word "json".
        var handler = new SequenceHandler((HttpStatusCode.OK, OpenAiOk));
        var client = new OpenAiCompatibleClient("https://x.test/v1", "k", "m", http: new HttpClient(handler));
        await client.CompleteAsync(new LlmRequest("doctor", "You check connectivity.", "Answer with {\"ok\": true}."));
        var body = JsonNode.Parse(handler.Bodies[0])!;
        Assert.Equal("json_object", body["response_format"]!["type"]!.GetValue<string>());
        string prompt = body["messages"]![0]!["content"]!.GetValue<string>() + body["messages"]![1]!["content"]!.GetValue<string>();
        Assert.Contains("json", prompt, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Odd_usage_fields_do_not_turn_a_good_answer_into_a_failure()
    {
        var handler = new SequenceHandler((HttpStatusCode.OK, """{"choices":[{"message":{"content":"{\"actions\":[]}"}}],"usage":{"prompt_tokens":null,"completion_tokens":"3"}}"""));
        var client = new OpenAiCompatibleClient("https://x.test/v1", "k", "m", http: new HttpClient(handler));
        var r = await client.CompleteAsync(Req());
        Assert.True(r.Ok, r.Error);
    }
}
