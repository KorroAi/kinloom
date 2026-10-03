using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace Kinloom.Media
{
    /// <summary>A request for a generated asset. Kinds are free (image, audio, voice, model3d, or anything the game's tools make).</summary>
    public sealed class MediaRequest
    {
        public MediaRequest(string kind, string prompt, JsonObject? spec = null)
        {
            Kind = kind;
            Prompt = prompt;
            Spec = spec ?? new JsonObject();
        }

        public string Kind { get; }
        public string Prompt { get; }
        /// <summary>Format, size, voice... whatever the developer's tool understands. <c>format</c> is checked against the file.</summary>
        public JsonObject Spec { get; }
        public string? Format => Spec["format"] is JsonValue v && v.TryGetValue(out string? f) ? f?.TrimStart('.').ToLowerInvariant() : null;

        public JsonObject ToJson() => new JsonObject { ["kind"] = Kind, ["prompt"] = Prompt, ["spec"] = Spec.DeepClone() };
    }

    public sealed class MediaResult
    {
        private MediaResult(bool ok, string? path, string? format, string? error, bool cached)
        {
            Ok = ok; Path = path; Format = format; Error = error; Cached = cached;
        }

        public bool Ok { get; }
        public string? Path { get; }
        public string? Format { get; }
        public string? Error { get; }
        public bool Cached { get; }

        public static MediaResult Success(string path, string? format, bool cached = false) => new MediaResult(true, path, format, null, cached);
        public static MediaResult Failure(string error) => new MediaResult(false, null, null, error, false);

        public JsonObject ToJson() => new JsonObject { ["ok"] = Ok, ["path"] = Path, ["format"] = Format, ["error"] = Error, ["cached"] = Cached };
    }

    /// <summary>A developer-supplied generation tool. Kinloom ships none: the game registers its own, or declares a command or HTTP endpoint.</summary>
    public interface IMediaProvider
    {
        IReadOnlyCollection<string> Kinds { get; }
        /// <summary>File extension used when the request does not specify a format.</summary>
        string DefaultFormat { get; }
        /// <summary>Writes the asset to <paramref name="outputPath"/>.</summary>
        Task<MediaResult> Create(MediaRequest request, string outputPath, CancellationToken ct);
    }

    /// <summary>Routes media requests to the registered providers, caches results by request, and checks each file is really what was asked.</summary>
    public sealed class MediaPort
    {
        private readonly List<IMediaProvider> _providers = new List<IMediaProvider>();
        private readonly object _lock = new object();

        public const int MaxPromptLength = 4000;

        public MediaPort(string cacheDir) { CacheDir = cacheDir; }

        public string CacheDir { get; }
        public TimeSpan Timeout { get; set; } = TimeSpan.FromSeconds(120);

        public void Register(IMediaProvider provider) { lock (_lock) _providers.Add(provider); }

        public IReadOnlyCollection<string> Kinds { get { lock (_lock) return _providers.SelectMany(p => p.Kinds).Distinct().ToList(); } }

        public async Task<MediaResult> Request(MediaRequest request)
        {
            string? invalid = CheckPrompt(request.Prompt);
            if (invalid != null) return MediaResult.Failure(invalid);
            IMediaProvider? provider;
            lock (_lock) provider = _providers.LastOrDefault(p => p.Kinds.Contains(request.Kind, StringComparer.OrdinalIgnoreCase));
            if (provider == null) return MediaResult.Failure($"no media provider for '{request.Kind}'");
            string format = request.Format ?? provider.DefaultFormat.TrimStart('.').ToLowerInvariant();
            // The format becomes a file extension, and a model can choose it: letters and digits only, so the file stays in the cache.
            if (!SafeFormat(format)) return MediaResult.Failure($"invalid media format '{Clip(format)}' (letters and digits only, at most 8)");
            Directory.CreateDirectory(CacheDir);
            string path = System.IO.Path.Combine(CacheDir, Key(request) + "." + format);
            string root = System.IO.Path.GetFullPath(CacheDir).TrimEnd(System.IO.Path.DirectorySeparatorChar) + System.IO.Path.DirectorySeparatorChar;
            if (!System.IO.Path.GetFullPath(path).StartsWith(root, StringComparison.OrdinalIgnoreCase)) return MediaResult.Failure("invalid media format");
            if (File.Exists(path) && new FileInfo(path).Length > 0) return MediaResult.Success(path, format, cached: true);

            string temp = path + ".part" + Guid.NewGuid().ToString("N").Substring(0, 6);
            try
            {
                using var cts = new CancellationTokenSource(Timeout);
                var result = await provider.Create(request, temp, cts.Token).ConfigureAwait(false);
                if (!result.Ok) return result;
                string produced = result.Path != null && File.Exists(result.Path) ? result.Path : temp;
                string? problem = MediaFormats.Check(produced, format);
                if (problem != null) return MediaResult.Failure(problem);
                if (produced != path)
                {
                    if (File.Exists(path)) File.Delete(path);
                    if (produced == temp) File.Move(temp, path); else File.Copy(produced, path);
                }
                return MediaResult.Success(path, format);
            }
            catch (OperationCanceledException) { return MediaResult.Failure($"the {request.Kind} provider took longer than {Timeout.TotalSeconds:0} s"); }
            catch (Exception e) { return MediaResult.Failure($"the {request.Kind} provider failed: {e.Message}"); }
            finally { if (File.Exists(temp)) try { File.Delete(temp); } catch (IOException) { } }
        }

        /// <summary>Null when a prompt may be handed to a provider. Prompts starting with '-' are refused because a provider
        /// command could read them as options.</summary>
        public static string? CheckPrompt(string? prompt)
        {
            string p = (prompt ?? "").Trim();
            if (p.Length == 0) return "a media request needs a prompt";
            if (p.Length > MaxPromptLength) return $"a media prompt must be at most {MaxPromptLength} characters";
            if (p[0] == '-') return "a media prompt cannot start with '-'";
            return null;
        }

        private static bool SafeFormat(string format) =>
            format.Length > 0 && format.Length <= 8 && format.All(c => (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'));

        private static string Clip(string s) => s.Length > 40 ? s.Substring(0, 40) + "..." : s;

        private static string Key(MediaRequest r)
        {
            using var sha = SHA256.Create();
            var hash = sha.ComputeHash(Encoding.UTF8.GetBytes(r.Kind + "\n" + r.Prompt + "\n" + r.Spec.ToJsonString()));
            return BitConverter.ToString(hash, 0, 16).Replace("-", "").ToLowerInvariant();
        }
    }

    /// <summary>File checks: exists, not empty, and magic bytes for common formats.</summary>
    internal static class MediaFormats
    {
        public static string? Check(string path, string format)
        {
            if (!File.Exists(path)) return "the provider produced no file";
            var info = new FileInfo(path);
            if (info.Length == 0) return "the provider produced an empty file";
            byte[] head = new byte[12];
            using (var f = File.OpenRead(path)) f.Read(head, 0, head.Length);
            bool Starts(params byte[] sig) => head.Take(sig.Length).SequenceEqual(sig);
            bool Ascii(int at, string s) => Encoding.ASCII.GetString(head, at, Math.Min(s.Length, head.Length - at)) == s;
            bool ok = format switch
            {
                "png" => Starts(0x89, 0x50, 0x4E, 0x47),
                "jpg" or "jpeg" => Starts(0xFF, 0xD8, 0xFF),
                "gif" => Ascii(0, "GIF8"),
                "webp" => Ascii(0, "RIFF") && Ascii(8, "WEBP"),
                "wav" => Ascii(0, "RIFF") && Ascii(8, "WAVE"),
                "ogg" => Ascii(0, "OggS"),
                "mp3" => Ascii(0, "ID3") || (head[0] == 0xFF && (head[1] & 0xE0) == 0xE0),
                "glb" => Ascii(0, "glTF"),
                _ => true,
            };
            return ok ? null : $"the file is not a valid {format} (its first bytes do not match)";
        }
    }
}
