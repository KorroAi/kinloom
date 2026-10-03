using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Kinloom.Llm;
using Kinloom.Media;
using Kinloom.Schema;

namespace Kinloom.Config
{
    /// <summary>Model clients built from the config, or the reason there are none (the game then runs on rules and fallbacks).</summary>
    public sealed class ClientSet
    {
        public ClientSet(ILlmClient? fast, ILlmClient? deep, string? problem) { Fast = fast; Deep = deep; Problem = problem; }
        public ILlmClient? Fast { get; }
        public ILlmClient? Deep { get; }
        public string? Problem { get; }
    }

    /// <summary><c>kinloom.json</c> at the root of a game project. The API key itself never appears in it: only the name of the
    /// environment variable that holds it.</summary>
    public sealed class KinloomConfig
    {
        public const string FileName = "kinloom.json";

        /// <summary>Folder the config was loaded from; relative paths resolve against it.</summary>
        public string ProjectDir { get; set; } = ".";

        public string Manifest { get; set; } = "kinloom";
        public string? ProviderKind { get; set; }
        public string? KeyEnv { get; set; }
        public string? BaseUrl { get; set; }
        public string? FastModel { get; set; }
        public string? DeepModel { get; set; }
        public string? Script { get; set; }
        public TokenPrices? Prices { get; set; }
        public string? PricesSource { get; set; }
        public string Language { get; set; } = "English";
        public int MaxCallsPerMinute { get; set; } = 30;
        public double? MaxCostPerHour { get; set; }
        public bool RequireBind { get; set; }
        public int ServePort { get; set; } = 7717;
        public int DebugPort { get; set; } = 7718;
        public JsonObject Media { get; set; } = new JsonObject();

        public static string DefaultKeyEnv(string? kind) => (kind ?? "").ToLowerInvariant() switch
        {
            "deepseek" => "DEEPSEEK_API_KEY",
            "openai" => "OPENAI_API_KEY",
            "anthropic" => "ANTHROPIC_API_KEY",
            "custom" => "KINLOOM_API_KEY",
            _ => "",
        };

        public static KinloomConfig Load(string dir)
        {
            string path = Path.Combine(dir, FileName);
            var c = new KinloomConfig { ProjectDir = dir };
            if (!File.Exists(path)) return c;
            JsonObject o;
            try { o = JsonNode.Parse(File.ReadAllText(path), documentOptions: new JsonDocumentOptions { CommentHandling = JsonCommentHandling.Skip, AllowTrailingCommas = true }) as JsonObject ?? throw new JsonException("not an object"); }
            catch (JsonException e) { throw new InvalidOperationException($"{FileName} is not valid JSON: {e.Message}", e); }

            c.Manifest = S(o, "manifest") ?? c.Manifest;
            c.Language = S(o, "language") ?? c.Language;
            c.ServePort = (int)(N(o, "servePort") ?? c.ServePort);
            c.DebugPort = (int)(N(o, "debugPort") ?? c.DebugPort);
            c.RequireBind = o["requireBind"] is JsonValue rb && rb.TryGetValue(out bool b) && b;
            if (o["provider"] is JsonObject p)
            {
                c.ProviderKind = S(p, "kind")?.ToLowerInvariant();
                c.KeyEnv = S(p, "keyEnv");
                c.BaseUrl = S(p, "baseUrl");
                c.FastModel = S(p, "fast");
                c.DeepModel = S(p, "deep");
                c.Script = S(p, "script");
            }
            if (o["prices"] is JsonObject pr)
            {
                double? input = N(pr, "input"), cached = N(pr, "cachedInput"), output = N(pr, "output");
                if (input.HasValue && cached.HasValue && output.HasValue) c.Prices = new TokenPrices(input.Value, cached.Value, output.Value);
                c.PricesSource = S(pr, "source");
            }
            if (o["budget"] is JsonObject bu)
            {
                c.MaxCallsPerMinute = (int)(N(bu, "maxCallsPerMinute") ?? c.MaxCallsPerMinute);
                c.MaxCostPerHour = N(bu, "maxCostPerHour");
            }
            if (o["media"] is JsonObject m) c.Media = (JsonObject)m.DeepClone();
            return c;
        }

        private static string? S(JsonObject o, string key) => o[key] is JsonValue v && v.TryGetValue(out string? s) && !string.IsNullOrWhiteSpace(s) ? s : null;
        private static double? N(JsonObject o, string key) => o[key] is JsonValue v && v.TryGetValue(out double d) ? d : (double?)null;

        public string ManifestDir(string projectDir) => Path.GetFullPath(Path.Combine(projectDir, Manifest));

        /// <summary>Builds the fast/deep clients. <c>KINLOOM_PROVIDER</c> in the environment overrides the file (headless checks, CI).</summary>
        public ClientSet CreateClients(Func<string, string?>? env = null, string? projectDir = null)
        {
            env ??= Environment.GetEnvironmentVariable;
            if (!string.IsNullOrEmpty(env("KINLOOM_PROVIDER")))
            {
                var fromEnv = LlmConfig.FromEnvironment(env);
                return new ClientSet(fromEnv, fromEnv, fromEnv == null ? "KINLOOM_PROVIDER is set but incomplete (see kinloom docs)" : null);
            }
            string kind = ProviderKind ?? "";
            if (kind.Length == 0) return new ClientSet(null, null, "no provider in kinloom.json: running with rules and fallbacks only");
            if (kind == "scripted")
            {
                if (Script == null) return new ClientSet(null, null, "provider.script is required for the scripted provider");
                var scripted = ScriptFile.Load(Path.Combine(projectDir ?? ProjectDir, Script));
                return Wrap(env, scripted, scripted);
            }
            string keyEnv = KeyEnv ?? DefaultKeyEnv(kind);
            string key = keyEnv.Length > 0 ? env(keyEnv) ?? "" : "";
            if (kind != "ollama" && key.Length == 0)
                return new ClientSet(null, null, $"the environment variable {keyEnv} is not set: running with rules and fallbacks only");
            if (FastModel == null && DeepModel == null)
                return new ClientSet(null, null, "set provider.fast (and optionally provider.deep) to a model name from your provider");
            string fast = FastModel ?? DeepModel!, deep = DeepModel ?? FastModel!;
            ILlmClient Make(string model) => kind switch
            {
                "deepseek" => new OpenAiCompatibleClient(BaseUrl ?? "https://api.deepseek.com", key, model, disableThinking: true),
                "openai" => new OpenAiCompatibleClient(BaseUrl ?? "https://api.openai.com/v1", key, model),
                "ollama" => new OpenAiCompatibleClient(BaseUrl ?? "http://localhost:11434/v1", "", model),
                "anthropic" => new AnthropicClient(key, model, BaseUrl ?? "https://api.anthropic.com"),
                "custom" when BaseUrl != null => new OpenAiCompatibleClient(BaseUrl, key, model),
                _ => throw new InvalidOperationException($"unknown provider '{kind}' (expected deepseek, openai, anthropic, ollama, custom or scripted; custom needs baseUrl)"),
            };
            try
            {
                var f = Make(fast);
                return Wrap(env, f, fast == deep ? f : Make(deep));
            }
            catch (InvalidOperationException e) { return new ClientSet(null, null, e.Message); }
        }

        private static ClientSet Wrap(Func<string, string?> env, ILlmClient fast, ILlmClient deep)
        {
            string? cassette = env("KINLOOM_CASSETTE");
            if (string.IsNullOrEmpty(cassette)) return new ClientSet(fast, deep, null);
            var tape = new CassetteClient(cassette!, fast);
            return new ClientSet(tape, fast == deep ? tape : new CassetteClient(cassette!, deep), null);
        }

        public SessionOptions ToOptions(string projectDir, Func<string, string?>? env = null)
        {
            var clients = CreateClients(env, projectDir);
            return new SessionOptions
            {
                Fast = clients.Fast,
                Deep = clients.Deep,
                Prices = Prices,
                Language = Language,
                MaxCallsPerMinute = MaxCallsPerMinute,
                MaxCostPerHour = MaxCostPerHour,
                RequireBind = RequireBind,
                MediaCache = Path.Combine(projectDir, ".kinloom", "media"),
            };
        }

        /// <summary>A ready session: options from this config, media providers registered, manifest folder declared.</summary>
        public KinloomSession CreateSession(string projectDir, Func<string, string?>? env, out IReadOnlyList<ManifestError> errors, bool declareManifest = true)
        {
            var options = ToOptions(projectDir, env);
            var session = new KinloomSession(options);
            var problem = CreateClients(env, projectDir).Problem;
            if (problem != null) session.Log("note", "config", problem);
            RegisterMedia(session.Media, projectDir);
            errors = Array.Empty<ManifestError>();
            string dir = ManifestDir(projectDir);
            if (declareManifest && Directory.Exists(dir))
            {
                var list = new List<ManifestError>();
                var declared = Schema.Manifest.LoadDirectory(dir, list);
                errors = list.Count > 0 ? list : session.Declare(declared);
            }
            return session;
        }

        public void RegisterMedia(MediaPort port, string projectDir)
        {
            foreach (var entry in Media)
            {
                if (!(entry.Value is JsonObject m)) continue;
                string format = S(m, "format") ?? "bin";
                if (S(m, "command") is string command) port.Register(new CommandMediaProvider(entry.Key, command, format));
                else if (S(m, "http") is string url) port.Register(new HttpMediaProvider(entry.Key, url, format));
            }
        }
    }
}
