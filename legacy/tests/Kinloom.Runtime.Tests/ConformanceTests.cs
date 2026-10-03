using System.Net.WebSockets;
using System.Text;
using System.Text.Json.Nodes;
using Kinloom.Llm;
using Kinloom.Protocol;

namespace Kinloom.Runtime.Tests;

[Collection("Perf")] // opens local ports; keep it out of the parallel pool
public class ConformanceTests
{
    private const string Generator = """
        , "generators": [ { "id": "name", "description": "A name for a truck.", "schema": { "type": "object", "fields": { "name": "string" }, "required": ["name"] } } ]
        """;

    private static string Manifest() => TestData.Trucks.TrimEnd().TrimEnd('}') + Generator + "}";

    private static ScriptedLlmClient Script() => new ScriptedLlmClient(req =>
        req.Task == "generator:name" ? """{"value":{"name":"Thunder"}}"""
        : req.User.Contains("says to you") ? """{"actions":[{"tool":"say","args":{"text":"Catch me if you can."}}]}"""
        : """{"actions":[{"tool":"set_param","args":{"thing":"self","param":"aggression","value":0.9}}]}""");

    private static SessionOptions Options() => new SessionOptions { Fast = Script() };

    /// <summary>The shared scenario: every implementation of IKinloomSession must produce the same observable results.</summary>
    private static async Task<List<string>> Scenario(IKinloomSession s)
    {
        var log = new List<string>();
        var errors = s.Declare(Manifest());
        log.Add("declare errors: " + errors.Count);
        log.Add("bad declare errors: " + (s.Declare("""{"things":[{"id":"x","type":"Ghost"}]}""").Count > 0));
        s.Update("player", JsonNode.Parse("""{"idle_seconds": 2}""")!.AsObject());
        s.Emit(new GameEvent("overtake", JsonNode.Parse("""{"who":"player"}""")!.AsObject()));

        var effects = new List<Effect>();
        for (int i = 0; i < 300 && effects.Count == 0; i++) { effects.AddRange(s.Pump(1)); await Task.Delay(10); }
        foreach (var e in effects)
        {
            log.Add($"effect {e.Kind} {e.Thing}.{e.Member} {e.Args["value"]?.ToJsonString()} from {e.Source}");
            s.Resolve(e.Id, EffectResult.Ok());
        }

        var ask = s.Ask("rex", "Nice truck.", "player");
        for (int i = 0; i < 300 && !ask.IsCompleted; i++) { s.Pump(2); await Task.Delay(10); }
        var reply = await ask;
        log.Add("reply: " + reply.Reply);

        var gen = s.Generate("name", new JsonObject { ["style"] = "loud" });
        for (int i = 0; i < 300 && !gen.IsCompleted; i++) { s.Pump(3); await Task.Delay(10); }
        var g = await gen;
        log.Add($"generated: {g.Ok} {g.Value?["name"]}");

        string state = s.Save();
        log.Add("saved: " + (state.Contains("\"version\":1")));
        s.Load(state);
        log.Add("loaded");
        return log;
    }

    [Fact]
    public async Task Embedded_and_websocket_sessions_behave_the_same()
    {
        var embedded = await Scenario(new KinloomSession(Options()));

        int port = MediaTests.FreePort();
        using var server = WsServer.ForService(port, () => new KinloomSession(Options()));
        server.Start();
        using var remote = await RemoteSession.Connect($"ws://localhost:{port}/ws");
        var overWire = await Scenario(remote);

        Assert.Equal(embedded, overWire);
        Assert.Contains("effect Set truck_2.aggression 0.9 from role:rex", embedded);
        Assert.Contains("reply: Catch me if you can.", embedded);
        Assert.Contains("generated: True Thunder", embedded);
    }

    [Fact]
    public async Task The_dispatcher_reports_json_rpc_errors()
    {
        var d = new ProtocolDispatcher(new KinloomSession(), _ => { });
        var parse = JsonNode.Parse((await d.Handle("{nope"))!)!;
        Assert.Equal(-32700, parse["error"]!["code"]!.GetValue<int>());
        var unknown = JsonNode.Parse((await d.Handle("""{"jsonrpc":"2.0","id":1,"method":"fly"}"""))!)!;
        Assert.Equal(-32601, unknown["error"]!["code"]!.GetValue<int>());
        Assert.Equal(1, unknown["id"]!.GetValue<int>());
        var bad = JsonNode.Parse((await d.Handle("""{"jsonrpc":"2.0","id":2,"method":"update","params":{"props":{}}}"""))!)!;
        Assert.Equal(-32602, bad["error"]!["code"]!.GetValue<int>());
        Assert.Null(await d.Handle("""{"jsonrpc":"2.0","method":"tick","params":{"time":1}}"""));
    }

    [Fact]
    public async Task Tick_requests_return_the_effects_directly()
    {
        var s = new KinloomSession();
        Assert.Empty(s.Declare(TestData.Trucks));
        s.EnqueueEffect(new Effect(EffectKind.Invoke, "truck_2", "honk", new JsonObject(), "test"), null);
        var d = new ProtocolDispatcher(s, _ => { });
        var r = JsonNode.Parse((await d.Handle("""{"jsonrpc":"2.0","id":7,"method":"tick","params":{"time":1}}"""))!)!;
        Assert.Equal("honk", r["result"]!["effects"]![0]!["member"]!.GetValue<string>());
    }

    [Fact]
    public async Task A_debug_connection_streams_the_journal_and_can_edit_missions()
    {
        var session = new KinloomSession();
        Assert.Empty(session.Declare(TestData.Trucks));
        int port = MediaTests.FreePort();
        using var server = WsServer.ForSession(port, session);
        server.Start();
        using var ws = new ClientWebSocket();
        await ws.ConnectAsync(new Uri($"ws://localhost:{port}/debug"), CancellationToken.None);

        var snapshot = await Request(ws, """{"jsonrpc":"2.0","id":1,"method":"snapshot"}""");
        Assert.Contains(snapshot["result"]!["things"]!.AsArray(), t => t!["id"]!.GetValue<string>() == "truck_2");
        Assert.Contains(snapshot["result"]!["roles"]!.AsArray(), r => r!["id"]!.GetValue<string>() == "rex");

        session.Emit(new GameEvent("crash"));
        JsonNode? entry = null;
        for (int i = 0; i < 20 && entry == null; i++)
        {
            var msg = await Receive(ws);
            if (msg["method"]?.GetValue<string>() == "journal" && msg["params"]!["kind"]!.GetValue<string>() == "event") entry = msg;
        }
        Assert.NotNull(entry);

        await Request(ws, """{"jsonrpc":"2.0","id":2,"method":"setMission","params":{"role":"rex","mission":"You are calm now."}}""");
        Assert.Equal("You are calm now.", session.MissionOf("rex"));
    }

    [Fact]
    public async Task A_debug_client_that_never_reads_cannot_stall_the_game()
    {
        var session = new KinloomSession();
        Assert.Empty(session.Declare(TestData.Trucks));
        int port = MediaTests.FreePort();
        using var server = WsServer.ForSession(port, session);
        server.Start();
        using var ws = new ClientWebSocket();
        await ws.ConnectAsync(new Uri($"ws://localhost:{port}/debug"), CancellationToken.None);
        await Task.Delay(200); // let the server subscribe to the journal
        var data = new JsonObject { ["blob"] = new string('x', 2000) };
        var emitting = Task.Run(() => { for (int i = 0; i < 5000; i++) session.Emit(new GameEvent("crash", (JsonObject)data.DeepClone())); });
        var finished = await Task.WhenAny(emitting, Task.Delay(TimeSpan.FromSeconds(15)));
        Assert.True(finished == emitting, "emitting 5000 events blocked on a debug client that does not read");
    }

    [Fact]
    public async Task The_inspector_page_is_served()
    {
        int port = MediaTests.FreePort();
        using var server = WsServer.ForSession(port, new KinloomSession());
        server.Start();
        using var http = new HttpClient();
        string html = await http.GetStringAsync($"http://localhost:{port}/");
        Assert.Contains("<title>", html);
        Assert.Contains("Kinloom", html);
    }

    private static async Task<JsonNode> Request(ClientWebSocket ws, string json)
    {
        int id = JsonNode.Parse(json)!["id"]!.GetValue<int>();
        await ws.SendAsync(Encoding.UTF8.GetBytes(json), WebSocketMessageType.Text, true, CancellationToken.None);
        for (int i = 0; i < 50; i++)
        {
            var msg = await Receive(ws);
            if (msg["id"] != null && msg["id"]!.GetValue<int>() == id) return msg;
        }
        throw new TimeoutException("no answer");
    }

    private static async Task<JsonNode> Receive(ClientWebSocket ws)
    {
        var buffer = new byte[1 << 16];
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var sb = new StringBuilder();
        WebSocketReceiveResult r;
        do
        {
            r = await ws.ReceiveAsync(buffer, cts.Token);
            sb.Append(Encoding.UTF8.GetString(buffer, 0, r.Count));
        } while (!r.EndOfMessage);
        return JsonNode.Parse(sb.ToString())!;
    }
}
