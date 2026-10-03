using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Kinloom.Llm;
using Kinloom.Media;

namespace Kinloom.Runtime.Tests;

public class MediaTests : IDisposable
{
    internal static readonly byte[] Png = { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52 };
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "kinloom-media-" + Guid.NewGuid().ToString("N"));

    public void Dispose() { try { Directory.Delete(_dir, true); } catch (IOException) { } }

    private sealed class FakeProvider : IMediaProvider
    {
        private readonly byte[] _bytes;
        public FakeProvider(byte[] bytes, params string[] kinds) { _bytes = bytes; Kinds = kinds; }
        public IReadOnlyCollection<string> Kinds { get; }
        public string DefaultFormat => "png";
        public int Calls;
        public Task<MediaResult> Create(MediaRequest request, string outputPath, CancellationToken ct)
        {
            Calls++;
            File.WriteAllBytes(outputPath, _bytes);
            return Task.FromResult(MediaResult.Success(outputPath, "png"));
        }
    }

    private static MediaRequest Image(string prompt = "a red truck") => new MediaRequest("image", prompt, new JsonObject { ["format"] = "png" });

    [Fact]
    public async Task A_provider_result_is_validated_and_cached()
    {
        var port = new MediaPort(_dir);
        var fake = new FakeProvider(Png, "image");
        port.Register(fake);
        var first = await port.Request(Image());
        Assert.True(first.Ok, first.Error);
        Assert.True(File.Exists(first.Path));
        Assert.False(first.Cached);
        var second = await port.Request(Image());
        Assert.True(second.Cached);
        Assert.Equal(1, fake.Calls);
    }

    [Fact]
    public async Task A_file_that_is_not_what_it_claims_is_rejected()
    {
        var port = new MediaPort(_dir);
        port.Register(new FakeProvider(System.Text.Encoding.UTF8.GetBytes("<html>error</html>"), "image"));
        var r = await port.Request(Image());
        Assert.False(r.Ok);
        Assert.Contains("png", r.Error);
    }

    [Fact]
    public async Task A_missing_provider_gives_a_clear_error()
    {
        var r = await new MediaPort(_dir).Request(new MediaRequest("voice", "hello", new JsonObject()));
        Assert.False(r.Ok);
        Assert.Equal("no media provider for 'voice'", r.Error);
    }

    [Fact]
    public async Task A_command_provider_runs_the_developer_tool_without_a_shell()
    {
        Directory.CreateDirectory(_dir);
        string source = Path.Combine(_dir, "source.png");
        File.WriteAllBytes(source, Png);
        string command = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? $"cmd /c copy /Y \"{source}\" {{out}}"
            : $"cp \"{source}\" {{out}}";
        var port = new MediaPort(Path.Combine(_dir, "cache"));
        port.Register(new CommandMediaProvider("image", command, "png"));
        var r = await port.Request(Image("anything & echo hacked"));
        Assert.True(r.Ok, r.Error);
        Assert.Equal(Png.Length, new FileInfo(r.Path!).Length);
    }

    [Fact]
    public void Command_templates_keep_the_prompt_as_one_argument()
    {
        var args = CommandMediaProvider.Arguments("gen --prompt {prompt} --out \"{out}\"", "a \"quoted\" prompt; rm -rf /", "C:/x y/out.png", "C:/spec.json");
        Assert.Equal(new[] { "gen", "--prompt", "a \"quoted\" prompt; rm -rf /", "--out", "C:/x y/out.png" }, args);
    }

    [Fact]
    public async Task An_http_provider_posts_the_request_and_saves_the_bytes()
    {
        int port = FreePort();
        using var listener = new HttpListener();
        listener.Prefixes.Add($"http://localhost:{port}/");
        listener.Start();
        string? body = null;
        var serve = Task.Run(async () =>
        {
            var ctx = await listener.GetContextAsync();
            using (var reader = new StreamReader(ctx.Request.InputStream)) body = await reader.ReadToEndAsync();
            ctx.Response.ContentType = "image/png";
            await ctx.Response.OutputStream.WriteAsync(Png);
            ctx.Response.Close();
        });
        var media = new MediaPort(_dir);
        media.Register(new HttpMediaProvider("image", $"http://localhost:{port}/make", "png"));
        var r = await media.Request(Image("a castle"));
        await serve;
        Assert.True(r.Ok, r.Error);
        Assert.Contains("a castle", body);
    }

    [Fact]
    public async Task A_role_request_is_delivered_to_the_game_as_a_media_effect()
    {
        var llm = new ScriptedLlmClient("""{"actions":[{"tool":"request_media","args":{"kind":"image","prompt":"a poster of Rex","spec":{"format":"png"}}}]}""");
        var s = new KinloomSession(new SessionOptions { Fast = llm, MediaCache = _dir });
        Assert.Empty(s.Declare(TestData.Trucks.Replace("\"remember\"]", "\"remember\", \"media:image\"]")));
        s.Media.Register(new FakeProvider(Png, "image"));
        var ask = s.Ask("rex", "make a poster");
        var effects = new List<Effect>();
        for (int i = 0; i < 200 && !effects.Any(e => e.Kind == EffectKind.Media); i++) { effects.AddRange(s.Pump(i)); await Task.Delay(10); }
        var m = effects.Single(e => e.Kind == EffectKind.Media);
        Assert.Equal("truck_2", m.Thing);
        Assert.Equal("image", m.Member);
        Assert.True(File.Exists(m.Args["path"]!.GetValue<string>()));
        await ask;
    }

    internal static int FreePort()
    {
        var l = new TcpListener(IPAddress.Loopback, 0);
        l.Start();
        int port = ((IPEndPoint)l.LocalEndpoint).Port;
        l.Stop();
        return port;
    }
}
