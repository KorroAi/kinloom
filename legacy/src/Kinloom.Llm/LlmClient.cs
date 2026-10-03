using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Kinloom.Llm
{
    /// <summary>One JSON-producing completion: a system prompt and a user prompt.</summary>
    public sealed class LlmRequest
    {
        public LlmRequest(string task, string system, string user, int maxTokens = 900, float temperature = 0.8f, IReadOnlyList<LlmTool>? tools = null)
        {
            Task = task;
            System = system;
            User = user;
            MaxTokens = maxTokens;
            Temperature = temperature;
            Tools = tools;
        }

        /// <summary>Native tools offered to the model. When the model calls them, the response text is canonical JSON (see <see cref="ToolCanon"/>).</summary>
        public IReadOnlyList<LlmTool>? Tools { get; }
        public bool HasTools => Tools != null && Tools.Count > 0;

        /// <summary>Cognition task name (plan, reflect, converse...), for stats and cassettes.</summary>
        public string Task { get; }
        public string System { get; }
        public string User { get; }
        public int MaxTokens { get; }
        public float Temperature { get; }
    }

    public sealed class LlmResponse
    {
        private LlmResponse(bool ok, string text, string? error, int inputTokens, int outputTokens, long latencyMs, int cachedInputTokens = 0)
        {
            CachedInputTokens = cachedInputTokens;
            Ok = ok;
            Text = text;
            Error = error;
            InputTokens = inputTokens;
            OutputTokens = outputTokens;
            LatencyMs = latencyMs;
        }

        public bool Ok { get; }
        public string Text { get; }
        public string? Error { get; }
        public int InputTokens { get; }
        public int OutputTokens { get; }
        public long LatencyMs { get; }
        /// <summary>Part of InputTokens served from the provider's prompt cache (cheaper), when the provider reports it.</summary>
        public int CachedInputTokens { get; }

        public static LlmResponse Success(string text, int inputTokens, int outputTokens, long latencyMs, int cachedInputTokens = 0) =>
            new LlmResponse(true, text, null, inputTokens, outputTokens, latencyMs, cachedInputTokens);

        public static LlmResponse Failure(string error, long latencyMs = 0) =>
            new LlmResponse(false, "", error, 0, 0, latencyMs);
    }

    /// <summary>A language model behind any provider. Implementations must be thread-safe and never throw for API errors.</summary>
    public interface ILlmClient
    {
        string Name { get; }
        Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellation = default);
    }

    /// <summary>Test double: answers with a function of the request (or a queue of canned answers).</summary>
    public sealed class ScriptedLlmClient : ILlmClient
    {
        private readonly Func<LlmRequest, string?> _answer;
        private readonly object _lock = new object();

        public ScriptedLlmClient(Func<LlmRequest, string?> answer) { _answer = answer; }

        public ScriptedLlmClient(params string[] answers)
        {
            var queue = new Queue<string>(answers);
            _answer = _ => queue.Count > 0 ? queue.Dequeue() : null;
        }

        public string Name => "scripted";
        public List<LlmRequest> Requests { get; } = new List<LlmRequest>();

        public Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellation = default)
        {
            string? text;
            lock (_lock)
            {
                Requests.Add(request);
                text = _answer(request);
            }
            return Task.FromResult(text == null
                ? LlmResponse.Failure("no scripted answer")
                : LlmResponse.Success(text, request.System.Length / 4 + request.User.Length / 4, text.Length / 4, 0));
        }
    }
}
