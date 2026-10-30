using System;
using System.Diagnostics;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Kinloom.Llm
{
    /// <summary>Any "chat completions" endpoint: DeepSeek, OpenAI, Ollama, LM Studio, vLLM, OpenRouter...</summary>
    public sealed class OpenAiCompatibleClient : ILlmClient
    {
        private readonly HttpClient _http;
        private readonly string _url;
        private readonly string _model;
        private readonly bool _disableThinking;

        public OpenAiCompatibleClient(string baseUrl, string apiKey, string model, bool disableThinking = false, HttpClient? http = null)
        {
            _http = http ?? new HttpClient { Timeout = TimeSpan.FromSeconds(60) };
            _url = baseUrl.TrimEnd('/') + "/chat/completions";
            _model = model;
            _disableThinking = disableThinking;
            if (!string.IsNullOrEmpty(apiKey)) _http.DefaultRequestHeaders.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", apiKey);
        }

        public string Name => _model;

        public async Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellation = default)
        {
            var watch = Stopwatch.StartNew();
            try
            {
                string body;
                using (var stream = new System.IO.MemoryStream())
                {
                    using (var w = new Utf8JsonWriter(stream))
                    {
                        w.WriteStartObject();
                        w.WriteString("model", _model);
                        w.WriteNumber("max_tokens", request.MaxTokens);
                        w.WriteNumber("temperature", request.Temperature);
                        if (request.HasTools)
                        {
                            w.WriteStartArray("tools");
                            foreach (var tool in request.Tools!)
                            {
                                w.WriteStartObject();
                                w.WriteString("type", "function");
                                w.WriteStartObject("function");
                                w.WriteString("name", tool.Name);
                                w.WriteString("description", tool.Description);
                                w.WritePropertyName("parameters"); tool.Parameters.WriteTo(w);
                                w.WriteEndObject();
                                w.WriteEndObject();
                            }
                            w.WriteEndArray();
                        }
                        else { w.WriteStartObject("response_format"); w.WriteString("type", "json_object"); w.WriteEndObject(); }
                        // JSON mode is refused unless the prompt says "json" (DeepSeek, OpenAI): make sure it does.
                        string system = request.HasTools || MentionsJson(request) ? request.System : request.System + "\nAnswer with a single JSON object.";
                        if (_disableThinking && _url.Contains("openrouter.ai")) { w.WriteStartObject("reasoning"); w.WriteBoolean("enabled", false); w.WriteEndObject(); }
                        else if (_disableThinking) { w.WriteStartObject("thinking"); w.WriteString("type", "disabled"); w.WriteEndObject(); }
                        w.WriteStartArray("messages");
                        w.WriteStartObject(); w.WriteString("role", "system"); w.WriteString("content", system); w.WriteEndObject();
                        w.WriteStartObject(); w.WriteString("role", "user"); w.WriteString("content", request.User); w.WriteEndObject();
                        w.WriteEndArray();
                        w.WriteEndObject();
                    }
                    body = Encoding.UTF8.GetString(stream.ToArray());
                }
                var (status, json) = await Transport.Post(_http, _url, body, cancellation).ConfigureAwait(false);
                if (status < 200 || status > 299) return LlmResponse.Failure($"HTTP {status}: {Trim(json)}", watch.ElapsedMilliseconds);

                using var doc = JsonDocument.Parse(json);
                var root = doc.RootElement;
                var choice = root.GetProperty("choices")[0];
                var message = choice.GetProperty("message");
                string text = message.TryGetProperty("content", out var c) && c.ValueKind == JsonValueKind.String ? c.GetString() ?? "" : "";
                if (message.TryGetProperty("tool_calls", out var calls) && calls.ValueKind == JsonValueKind.Array && calls.GetArrayLength() > 0)
                {
                    var list = new System.Collections.Generic.List<(string, string)>();
                    foreach (var call in calls.EnumerateArray())
                    {
                        if (!call.TryGetProperty("function", out var fn)) continue;
                        string name = fn.TryGetProperty("name", out var n) ? n.GetString() ?? "" : "";
                        string args = fn.TryGetProperty("arguments", out var a) ? (a.ValueKind == JsonValueKind.String ? a.GetString() ?? "" : a.GetRawText()) : "";
                        list.Add((name, args));
                    }
                    text = ToolCanon.Canonical(text, list);
                }
                int input = 0, output = 0, cached = 0;
                if (root.TryGetProperty("usage", out var usage) && usage.ValueKind == JsonValueKind.Object)
                {
                    input = Transport.Int(usage, "prompt_tokens");
                    output = Transport.Int(usage, "completion_tokens");
                    if (usage.TryGetProperty("prompt_cache_hit_tokens", out _)) cached = Transport.Int(usage, "prompt_cache_hit_tokens"); // DeepSeek
                    else if (usage.TryGetProperty("prompt_tokens_details", out var d) && d.ValueKind == JsonValueKind.Object) cached = Transport.Int(d, "cached_tokens"); // OpenAI
                }
                if (text.Length == 0) return LlmResponse.Failure("empty answer (finish_reason " + (choice.TryGetProperty("finish_reason", out var f) ? f.ToString() : "?") + ")", watch.ElapsedMilliseconds);
                return LlmResponse.Success(text, input, output, watch.ElapsedMilliseconds, cached);
            }
            catch (Exception e) when (!(e is OperationCanceledException && cancellation.IsCancellationRequested))
            {
                return LlmResponse.Failure(e.GetType().Name + ": " + e.Message, watch.ElapsedMilliseconds);
            }
        }

        internal static string Trim(string s) => s.Length > 300 ? s.Substring(0, 300) + "..." : s;

        private static bool MentionsJson(LlmRequest r) =>
            r.System.IndexOf("json", StringComparison.OrdinalIgnoreCase) >= 0 || r.User.IndexOf("json", StringComparison.OrdinalIgnoreCase) >= 0;
    }

    /// <summary>HTTP plumbing shared by the clients: one quick retry on transient failures, tolerant number reading.</summary>
    internal static class Transport
    {
        /// <summary>Statuses worth one more try: timeouts, rate limits, overload and server errors.</summary>
        public static bool Transient(int status) => status == 408 || status == 409 || status == 429 || status >= 500;

        /// <summary>POSTs JSON and returns (status, body). A transient status or a dropped connection is retried once after
        /// the server's Retry-After (at most 2 s) or 0.4 s; the caller's cancellation (its time limit) always wins.</summary>
        public static async Task<(int status, string body)> Post(HttpClient http, string url, string body, CancellationToken cancellation)
        {
            for (int attempt = 0; ; attempt++)
            {
                TimeSpan wait = TimeSpan.FromMilliseconds(400);
                try
                {
                    using var content = new StringContent(body, Encoding.UTF8, "application/json");
                    using var response = await http.PostAsync(url, content, cancellation).ConfigureAwait(false);
                    string text = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
                    int status = (int)response.StatusCode;
                    if (attempt > 0 || !Transient(status)) return (status, text);
                    if (response.Headers.RetryAfter?.Delta is TimeSpan delta) wait = delta;
                }
                catch (HttpRequestException) when (attempt == 0 && !cancellation.IsCancellationRequested) { }
                if (wait > TimeSpan.FromSeconds(2)) wait = TimeSpan.FromSeconds(2);
                await Task.Delay(wait, cancellation).ConfigureAwait(false);
            }
        }

        /// <summary>An integer field, or 0 when it is missing, null, not a number or out of range.</summary>
        public static int Int(JsonElement obj, string name) =>
            obj.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out int n) ? n : 0;
    }

    /// <summary>Claude through the Messages API (raw HTTP keeps this library dependency-free and engine-portable).</summary>
    public sealed class AnthropicClient : ILlmClient
    {
        private readonly HttpClient _http;
        private readonly string _model;

        public AnthropicClient(string apiKey, string model = "claude-opus-5", string baseUrl = "https://api.anthropic.com", HttpClient? http = null)
        {
            _http = http ?? new HttpClient { Timeout = TimeSpan.FromSeconds(120) };
            _http.BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/");
            _http.DefaultRequestHeaders.Add("x-api-key", apiKey);
            _http.DefaultRequestHeaders.Add("anthropic-version", "2023-06-01");
            _http.DefaultRequestHeaders.Add("anthropic-beta", "server-side-fallback-2026-07-01");
            _model = model;
        }

        public string Name => _model;

        public async Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellation = default)
        {
            var watch = Stopwatch.StartNew();
            try
            {
                string body;
                using (var stream = new System.IO.MemoryStream())
                {
                    using (var w = new Utf8JsonWriter(stream))
                    {
                        w.WriteStartObject();
                        w.WriteString("model", _model);
                        w.WriteNumber("max_tokens", Math.Max(request.MaxTokens * 4, 4000)); // room for adaptive thinking
                        w.WriteString("fallbacks", "default");
                        // The system prompt is stable per role (mission, rules, levers): mark it so repeated calls read it from the cache.
                        w.WriteStartArray("system");
                        w.WriteStartObject();
                        w.WriteString("type", "text");
                        w.WriteString("text", request.HasTools ? request.System : request.System + "\nAnswer with a single JSON object and nothing else.");
                        w.WriteStartObject("cache_control"); w.WriteString("type", "ephemeral"); w.WriteEndObject();
                        w.WriteEndObject();
                        w.WriteEndArray();
                        if (request.HasTools)
                        {
                            w.WriteStartArray("tools");
                            foreach (var tool in request.Tools!)
                            {
                                w.WriteStartObject();
                                w.WriteString("name", tool.Name);
                                w.WriteString("description", tool.Description);
                                w.WritePropertyName("input_schema"); tool.Parameters.WriteTo(w);
                                w.WriteEndObject();
                            }
                            w.WriteEndArray();
                        }
                        w.WriteStartArray("messages");
                        w.WriteStartObject(); w.WriteString("role", "user"); w.WriteString("content", request.User); w.WriteEndObject();
                        w.WriteEndArray();
                        w.WriteEndObject();
                    }
                    body = Encoding.UTF8.GetString(stream.ToArray());
                }
                var (status, json) = await Transport.Post(_http, "v1/messages", body, cancellation).ConfigureAwait(false);
                if (status < 200 || status > 299) return LlmResponse.Failure($"HTTP {status}: {OpenAiCompatibleClient.Trim(json)}", watch.ElapsedMilliseconds);

                using var doc = JsonDocument.Parse(json);
                var root = doc.RootElement;
                string stop = root.TryGetProperty("stop_reason", out var s) ? s.ToString() : "";
                if (stop == "refusal") return LlmResponse.Failure("refusal", watch.ElapsedMilliseconds);
                var text = new StringBuilder();
                var calls = new System.Collections.Generic.List<(string, string)>();
                foreach (var block in root.GetProperty("content").EnumerateArray())
                {
                    string type = block.GetProperty("type").GetString() ?? "";
                    if (type == "text") text.Append(block.GetProperty("text").GetString());
                    else if (type == "tool_use")
                        calls.Add((block.GetProperty("name").GetString() ?? "", block.TryGetProperty("input", out var toolInput) ? toolInput.GetRawText() : "{}"));
                }
                if (calls.Count > 0) { string canon = ToolCanon.Canonical(text.ToString(), calls); text.Clear().Append(canon); }
                int input = 0, output = 0, cached = 0;
                if (root.TryGetProperty("usage", out var usage) && usage.ValueKind == JsonValueKind.Object)
                {
                    input = Transport.Int(usage, "input_tokens") + Transport.Int(usage, "cache_creation_input_tokens");
                    output = Transport.Int(usage, "output_tokens");
                    cached = Transport.Int(usage, "cache_read_input_tokens");
                    input += cached;
                }
                if (text.Length == 0) return LlmResponse.Failure($"empty answer (stop_reason {stop})", watch.ElapsedMilliseconds);
                return LlmResponse.Success(text.ToString(), input, output, watch.ElapsedMilliseconds, cached);
            }
            catch (Exception e) when (!(e is OperationCanceledException && cancellation.IsCancellationRequested))
            {
                return LlmResponse.Failure(e.GetType().Name + ": " + e.Message, watch.ElapsedMilliseconds);
            }
        }
    }
}
