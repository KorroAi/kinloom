using System.Diagnostics;
using Kinloom.Cli.Mcp;
using Kinloom.Config;
using Kinloom.Protocol;
using Kinloom.Schema;

namespace Kinloom.Cli;

internal static class Program
{
    private const string Help = """
        kinloom — put AI anywhere in a game. Your coding agent does the integration; Kinloom gives it the runtime and the tools.

        usage: kinloom <command> [folder] [options]

          init [dir] [--engine godot|unity|unreal|other]   prepare a game project (config, starter manifest, agent kit, engine adapter)
          doctor [dir] [--ping]                            check config, API key presence, manifest, prices, media tools
          validate [dir]                                   check the manifest files (kinloom/*.json)
          test [dir]                                       run kinloom/tests/*.test.json with scripted models (no tokens)
          serve [dir] [--port 7717] [--no-manifest]        local WebSocket service for games in any language (+ inspector page)
          inspect [--port 7718]                            open the inspector of a running game (7718 embedded, 7717 serve)
          mcp [dir]                                        MCP server on stdio for coding agents (scan, validate, simulate, attack, attach, cost, tests)

        The API key is read from the environment variable named in kinloom.json (provider.keyEnv); it is never written anywhere.
        """;

    private static async Task<int> Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        if (args.Length == 0 || args[0] is "-h" or "--help" or "help") { Console.WriteLine(Help); return 0; }
        if (args[0] is "--version" or "-v") { Console.WriteLine(typeof(Program).Assembly.GetName().Version?.ToString(3)); return 0; }
        string command = args[0];
        var positional = args.Skip(1).Where(a => !a.StartsWith("--")).ToList();
        string Option(string name, string fallback)
        {
            int i = Array.IndexOf(args, "--" + name);
            return i >= 0 && i + 1 < args.Length ? args[i + 1] : fallback;
        }
        bool Flag(string name) => args.Contains("--" + name);
        string dir = Path.GetFullPath(positional.FirstOrDefault(p => p != Option("port", "\0") && p != Option("engine", "\0")) ?? ".");
        Func<string, string?> env = Environment.GetEnvironmentVariable;

        try
        {
            switch (command)
            {
                case "init":
                {
                    var r = Init.Run(dir, args.Contains("--engine") ? Option("engine", "") : null, env);
                    r.Lines.ForEach(Console.WriteLine);
                    return r.Ok ? 0 : 1;
                }
                case "doctor":
                {
                    var r = Doctor.Run(dir, env, Flag("ping"));
                    r.Lines.ForEach(Console.WriteLine);
                    return r.Ok ? 0 : 1;
                }
                case "validate":
                {
                    var config = KinloomConfig.Load(dir);
                    var errors = new List<ManifestError>();
                    var d = Manifest.LoadDirectory(config.ManifestDir(dir), errors);
                    if (errors.Count == 0) Manifest.Check(d, errors);
                    if (errors.Count == 0) { Console.WriteLine($"OK: {d.Types.Count} types, {d.Things.Count} things, {d.Roles.Count} roles, {d.Behaviors.Count} behaviors, {d.Generators.Count} generators"); return 0; }
                    errors.ForEach(e => Console.WriteLine(e));
                    return 1;
                }
                case "test":
                {
                    var r = TestRunner.Run(dir);
                    r.Lines.ForEach(Console.WriteLine);
                    return r.Passed ? 0 : 1;
                }
                case "serve":
                    return Serve(dir, int.Parse(Option("port", KinloomConfig.Load(dir).ServePort.ToString())), !Flag("no-manifest"), env);
                case "inspect":
                {
                    string url = $"http://localhost:{Option("port", KinloomConfig.Load(dir).DebugPort.ToString())}/";
                    Console.WriteLine("opening " + url);
                    Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
                    return 0;
                }
                case "mcp":
                {
                    Console.Error.WriteLine("kinloom MCP server ready on stdio");
                    using var cts = new CancellationTokenSource();
                    Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };
                    await new McpServer(env).RunStdio(Console.In, Console.Out, cts.Token);
                    return 0;
                }
                default:
                    Console.Error.WriteLine($"unknown command '{command}'\n");
                    Console.WriteLine(Help);
                    return 2;
            }
        }
        catch (InvalidOperationException e)
        {
            Console.Error.WriteLine("error: " + e.Message);
            return 1;
        }
    }

    private static int Serve(string dir, int port, bool loadManifest, Func<string, string?> env)
    {
        var config = KinloomConfig.Load(dir);
        var problem = config.CreateClients(env, dir).Problem;
        using var server = WsServer.ForService(port, () =>
        {
            var session = config.CreateSession(dir, env, out var errors, loadManifest);
            foreach (var e in errors) Console.Error.WriteLine("manifest: " + e);
            session.Journal.Added += e => { if (e.Kind is "refused" or "error" or "fallback") Console.WriteLine(e); };
            return session;
        });
        server.Log += Console.WriteLine;
        server.Start();
        Console.WriteLine($"kinloom serving on ws://localhost:{port}/ws — inspector: http://localhost:{port}/");
        Console.WriteLine(problem ?? "model: " + (config.ProviderKind ?? env("KINLOOM_PROVIDER") ?? "?") + " " + (config.FastModel ?? ""));
        Console.WriteLine(loadManifest ? $"each connection starts with {config.Manifest}/*.json declared (use --no-manifest if the game declares itself)" : "the game declares its manifest itself");
        Console.WriteLine("Ctrl+C to stop");
        var done = new ManualResetEventSlim();
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; done.Set(); };
        done.Wait();
        return 0;
    }
}
