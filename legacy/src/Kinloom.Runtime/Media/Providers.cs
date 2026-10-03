using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace Kinloom.Media
{
    /// <summary>Runs a developer-supplied command. Placeholders: <c>{prompt}</c>, <c>{out}</c> (file to write), <c>{spec}</c> (JSON file).
    /// The command is split into arguments once and run without a shell, so a prompt can never inject commands.</summary>
    public sealed class CommandMediaProvider : IMediaProvider
    {
        private readonly string _template;

        public CommandMediaProvider(string kind, string commandTemplate, string defaultFormat)
        {
            Kinds = new[] { kind };
            _template = commandTemplate;
            DefaultFormat = defaultFormat;
        }

        public IReadOnlyCollection<string> Kinds { get; }
        public string DefaultFormat { get; }

        public async Task<MediaResult> Create(MediaRequest request, string outputPath, CancellationToken ct)
        {
            string specPath = outputPath + ".spec.json";
            File.WriteAllText(specPath, request.ToJson().ToJsonString());
            try
            {
                var args = Arguments(_template, request.Prompt, outputPath, specPath);
                if (args.Count == 0) return MediaResult.Failure("empty media command");
                var info = new ProcessStartInfo(args[0]) { UseShellExecute = false, RedirectStandardError = true, RedirectStandardOutput = true, CreateNoWindow = true };
                for (int i = 1; i < args.Count; i++) info.ArgumentList.Add(args[i]);
                using var process = Process.Start(info) ?? throw new InvalidOperationException("could not start " + args[0]);
                var stderr = process.StandardError.ReadToEndAsync();
                var stdout = process.StandardOutput.ReadToEndAsync();
                while (!process.HasExited)
                {
                    if (ct.IsCancellationRequested) { try { process.Kill(); } catch (InvalidOperationException) { } ct.ThrowIfCancellationRequested(); }
                    await Task.Delay(50, CancellationToken.None).ConfigureAwait(false);
                }
                await Task.WhenAll(stderr, stdout).ConfigureAwait(false);
                if (process.ExitCode != 0)
                {
                    string err = stderr.Result.Trim();
                    return MediaResult.Failure($"media command exited with code {process.ExitCode}{(err.Length > 0 ? ": " + (err.Length > 300 ? err.Substring(0, 300) : err) : "")}");
                }
                return MediaResult.Success(outputPath, request.Format ?? DefaultFormat);
            }
            finally { if (File.Exists(specPath)) File.Delete(specPath); }
        }

        /// <summary>Splits the template like a shell would (quotes group words) and substitutes placeholders inside each argument.</summary>
        public static List<string> Arguments(string template, string prompt, string output, string spec)
        {
            var tokens = new List<string>();
            var current = new StringBuilder();
            bool inQuotes = false, any = false;
            foreach (char c in template)
            {
                if (c == '"') { inQuotes = !inQuotes; any = true; continue; }
                if (char.IsWhiteSpace(c) && !inQuotes)
                {
                    if (any) { tokens.Add(current.ToString()); current.Clear(); any = false; }
                    continue;
                }
                current.Append(c);
                any = true;
            }
            if (any) tokens.Add(current.ToString());
            for (int i = 0; i < tokens.Count; i++)
                tokens[i] = tokens[i].Replace("{prompt}", prompt).Replace("{out}", output).Replace("{spec}", spec);
            return tokens;
        }
    }

    /// <summary>Posts <c>{kind, prompt, spec}</c> to a developer-supplied endpoint. The response is the file itself, or JSON
    /// <c>{"path": "..."}</c> (a file on this machine) or <c>{"base64": "..."}</c>.</summary>
    public sealed class HttpMediaProvider : IMediaProvider
    {
        private static readonly HttpClient Shared = new HttpClient { Timeout = TimeSpan.FromMinutes(5) };
        private readonly string _url;

        public HttpMediaProvider(string kind, string url, string defaultFormat)
        {
            Kinds = new[] { kind };
            _url = url;
            DefaultFormat = defaultFormat;
        }

        public IReadOnlyCollection<string> Kinds { get; }
        public string DefaultFormat { get; }

        public async Task<MediaResult> Create(MediaRequest request, string outputPath, CancellationToken ct)
        {
            using var content = new StringContent(request.ToJson().ToJsonString(), Encoding.UTF8, "application/json");
            using var response = await Shared.PostAsync(_url, content, ct).ConfigureAwait(false);
            byte[] bytes = await response.Content.ReadAsByteArrayAsync().ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
                return MediaResult.Failure($"media endpoint answered HTTP {(int)response.StatusCode}");
            string? type = response.Content.Headers.ContentType?.MediaType;
            if (type != null && type.Contains("json"))
            {
                var o = JsonNode.Parse(Encoding.UTF8.GetString(bytes)) as JsonObject;
                if (o?["path"] is JsonValue p && p.TryGetValue(out string? path) && path != null)
                {
                    File.Copy(path, outputPath, true);
                    return MediaResult.Success(outputPath, request.Format ?? DefaultFormat);
                }
                if (o?["base64"] is JsonValue b && b.TryGetValue(out string? data) && data != null)
                {
                    File.WriteAllBytes(outputPath, Convert.FromBase64String(data));
                    return MediaResult.Success(outputPath, request.Format ?? DefaultFormat);
                }
                return MediaResult.Failure("media endpoint answered JSON without path or base64");
            }
            File.WriteAllBytes(outputPath, bytes);
            return MediaResult.Success(outputPath, request.Format ?? DefaultFormat);
        }
    }
}
