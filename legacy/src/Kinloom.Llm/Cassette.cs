using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Kinloom.Llm
{
    /// <summary>Records LLM traffic to a JSONL file and replays it: identical prompts get identical answers,
    /// so a good demo run can be replayed exactly, offline and for free. Unknown prompts go to the inner client (if any) and are recorded.</summary>
    public sealed class CassetteClient : ILlmClient
    {
        private readonly ILlmClient? _inner;
        private readonly string _path;
        private readonly Dictionary<string, Queue<string>> _tape = new Dictionary<string, Queue<string>>();
        private readonly object _lock = new object();

        public CassetteClient(string path, ILlmClient? inner)
        {
            _path = path;
            _inner = inner;
            if (!File.Exists(path)) return;
            foreach (var line in File.ReadAllLines(path))
            {
                if (string.IsNullOrWhiteSpace(line)) continue;
                using var doc = JsonDocument.Parse(line);
                string key = doc.RootElement.GetProperty("key").GetString()!;
                string text = doc.RootElement.GetProperty("text").GetString()!;
                if (!_tape.TryGetValue(key, out var q)) _tape[key] = q = new Queue<string>();
                q.Enqueue(text);
            }
        }

        public string Name => "cassette(" + (_inner?.Name ?? "replay only") + ")";
        public int Replayed { get; private set; }
        public int Recorded { get; private set; }

        public static string KeyOf(LlmRequest r)
        {
            using var sha = SHA256.Create();
            var hash = sha.ComputeHash(Encoding.UTF8.GetBytes(r.Task + "\n" + r.System + "\n" + r.User));
            return BitConverter.ToString(hash, 0, 12).Replace("-", "");
        }

        public async Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellation = default)
        {
            string key = KeyOf(request);
            lock (_lock)
            {
                if (_tape.TryGetValue(key, out var q) && q.Count > 0)
                {
                    Replayed++;
                    string text = q.Dequeue();
                    return LlmResponse.Success(text, 0, 0, 0);
                }
            }
            if (_inner == null) return LlmResponse.Failure("not on the cassette");
            var response = await _inner.CompleteAsync(request, cancellation).ConfigureAwait(false);
            if (!response.Ok) return response;
            lock (_lock)
            {
                Recorded++;
                using var stream = new MemoryStream();
                using (var w = new Utf8JsonWriter(stream))
                {
                    w.WriteStartObject();
                    w.WriteString("key", key);
                    w.WriteString("task", request.Task);
                    w.WriteString("text", response.Text);
                    w.WriteEndObject();
                }
                File.AppendAllText(_path, Encoding.UTF8.GetString(stream.ToArray()) + "\n");
            }
            return response;
        }
    }

    /// <summary>Builds a client from environment variables, so integrators only set a key.
    /// KINLOOM_PROVIDER = deepseek | openai | anthropic | ollama | custom | scripted (default: first key found); KINLOOM_SCRIPT = script file for "scripted";
    /// KINLOOM_API_KEY (or DEEPSEEK_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY); KINLOOM_MODEL (required for openai, ollama, custom); KINLOOM_BASE_URL;
    /// KINLOOM_THINKING = off: turn a reasoning model's thinking off on a "custom" endpoint (OpenRouter: reasoning.enabled=false);
    /// KINLOOM_CASSETTE = path to record/replay LLM traffic.</summary>
    public static class LlmConfig
    {
        /// <summary>KINLOOM_PRICE_INPUT / KINLOOM_PRICE_CACHED / KINLOOM_PRICE_OUTPUT: the provider's prices per million tokens (all three, or none).</summary>
        public static TokenPrices? PricesFromEnvironment(Func<string, string?>? env = null)
        {
            env ??= Environment.GetEnvironmentVariable;
            var ci = System.Globalization.CultureInfo.InvariantCulture;
            if (double.TryParse(env("KINLOOM_PRICE_INPUT"), System.Globalization.NumberStyles.Float, ci, out double input)
                && double.TryParse(env("KINLOOM_PRICE_CACHED"), System.Globalization.NumberStyles.Float, ci, out double cached)
                && double.TryParse(env("KINLOOM_PRICE_OUTPUT"), System.Globalization.NumberStyles.Float, ci, out double output))
                return new TokenPrices(input, cached, output);
            return null;
        }

        public static ILlmClient? FromEnvironment(Func<string, string?>? env = null)
        {
            env ??= Environment.GetEnvironmentVariable;
            string? provider = env("KINLOOM_PROVIDER")?.Trim().ToLowerInvariant();
            if (string.IsNullOrEmpty(provider))
            {
                if (!string.IsNullOrEmpty(env("DEEPSEEK_API_KEY"))) provider = "deepseek";
                else if (!string.IsNullOrEmpty(env("ANTHROPIC_API_KEY"))) provider = "anthropic";
                else if (!string.IsNullOrEmpty(env("OPENAI_API_KEY"))) provider = "openai";
            }
            string? model = env("KINLOOM_MODEL");
            string? baseUrl = env("KINLOOM_BASE_URL");
            string Key(string specific) => env("KINLOOM_API_KEY") ?? env(specific) ?? "";

            ILlmClient? client = provider switch
            {
                "deepseek" => new OpenAiCompatibleClient(baseUrl ?? "https://api.deepseek.com", Key("DEEPSEEK_API_KEY"), model ?? "deepseek-flash", disableThinking: true),
                "openai" => model == null ? null : new OpenAiCompatibleClient(baseUrl ?? "https://api.openai.com/v1", Key("OPENAI_API_KEY"), model),
                "ollama" => model == null ? null : new OpenAiCompatibleClient(baseUrl ?? "http://localhost:11434/v1", "", model),
                "custom" => baseUrl == null || model == null ? null : new OpenAiCompatibleClient(baseUrl, env("KINLOOM_API_KEY") ?? "", model, disableThinking: env("KINLOOM_THINKING") == "off"),
                "anthropic" => new AnthropicClient(Key("ANTHROPIC_API_KEY"), model ?? "claude-opus-5", baseUrl ?? "https://api.anthropic.com"),
                "scripted" => string.IsNullOrEmpty(env("KINLOOM_SCRIPT")) ? null : ScriptFile.Load(env("KINLOOM_SCRIPT")!),
                _ => null,
            };
            string? cassette = env("KINLOOM_CASSETTE");
            if (!string.IsNullOrEmpty(cassette)) return new CassetteClient(cassette!, client);
            return client;
        }
    }
}
