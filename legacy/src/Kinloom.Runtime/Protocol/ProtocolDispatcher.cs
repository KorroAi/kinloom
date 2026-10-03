using System;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Kinloom.Media;

namespace Kinloom.Protocol
{
    /// <summary>Maps JSON-RPC 2.0 messages to a session. Transport-free: feed it text, send what it returns and what it pushes
    /// through <c>send</c> (effect notifications). Methods: declare, update, event, tick, resolve, ask, generate, media, bind,
    /// unbind, remove, save, load, stats, snapshot, setMission.</summary>
    public sealed class ProtocolDispatcher
    {
        private readonly KinloomSession _s;
        private readonly Action<string> _send;

        public ProtocolDispatcher(KinloomSession session, Action<string> send)
        {
            _s = session;
            _send = send;
        }

        public KinloomSession Session => _s;

        private sealed class RpcError : Exception
        {
            public RpcError(int code, string message) : base(message) { Code = code; }
            public int Code { get; }
        }

        /// <summary>The response to send back, or null for notifications.</summary>
        public async Task<string?> Handle(string message)
        {
            JsonObject request;
            try
            {
                request = JsonNode.Parse(message) as JsonObject ?? throw new JsonException("not an object");
            }
            catch (JsonException e) { return Error(null, -32700, "parse error: " + e.Message); }

            var id = request["id"]?.DeepClone();
            string? method = request["method"] is JsonValue m && m.TryGetValue(out string? name) ? name : null;
            var p = request["params"] as JsonObject ?? new JsonObject();
            try
            {
                if (method == null) throw new RpcError(-32600, "invalid request: no method");
                var result = await Invoke(method, p, notification: id == null).ConfigureAwait(false);
                return id == null ? null : new JsonObject { ["jsonrpc"] = "2.0", ["id"] = id, ["result"] = result ?? new JsonObject() }.ToJsonString();
            }
            catch (RpcError e) { return id == null && e.Code != -32700 ? null : Error(id, e.Code, e.Message); }
            catch (Exception e) when (!(e is OutOfMemoryException))
            {
                return id == null ? null : Error(id, -32603, e.GetType().Name + ": " + e.Message);
            }
        }

        private static string Error(JsonNode? id, int code, string message) =>
            new JsonObject { ["jsonrpc"] = "2.0", ["id"] = id, ["error"] = new JsonObject { ["code"] = code, ["message"] = message } }.ToJsonString();

        private static string Str(JsonObject p, string key)
        {
            if (p[key] is JsonValue v && v.TryGetValue(out string? s) && s != null) return s;
            throw new RpcError(-32602, $"missing or invalid param '{key}' (string)");
        }

        private static string? OptStr(JsonObject p, string key) => p[key] is JsonValue v && v.TryGetValue(out string? s) ? s : null;

        private static double Num(JsonObject p, string key)
        {
            if (p[key] is JsonValue v && v.TryGetValue(out double d)) return d;
            throw new RpcError(-32602, $"missing or invalid param '{key}' (number)");
        }

        private static JsonObject Obj(JsonObject p, string key) =>
            p[key] as JsonObject ?? throw new RpcError(-32602, $"missing or invalid param '{key}' (object)");

        private async Task<JsonNode?> Invoke(string method, JsonObject p, bool notification)
        {
            switch (method)
            {
                case "declare":
                {
                    string json = p["manifest"] is JsonObject o ? o.ToJsonString() : Str(p, "manifest");
                    return Wire.Errors(_s.Declare(json, OptStr(p, "source") ?? "protocol"));
                }
                case "update":
                    _s.Update(Str(p, "thing"), Obj(p, "props"));
                    return null;
                case "event":
                {
                    var perceived = (p["perceivedBy"] as JsonArray)?.Select(x => x?.GetValue<string>() ?? "").ToArray();
                    double? time = p["time"] is JsonValue t && t.TryGetValue(out double tv) ? tv : (double?)null;
                    double? importance = p["importance"] is JsonValue iv && iv.TryGetValue(out double ivv) ? ivv : (double?)null;
                    _s.Emit(new GameEvent(Str(p, "type"), p["data"]?.DeepClone() as JsonObject, perceived, time, importance));
                    return null;
                }
                case "tick":
                {
                    var effects = _s.Pump(Num(p, "time"));
                    if (notification) { PushEffects(effects); return null; }
                    return new JsonObject { ["effects"] = Wire.Effects(effects) };
                }
                case "resolve":
                {
                    long id = p["id"] is JsonValue v && v.TryGetValue(out long l) ? l : throw new RpcError(-32602, "missing or invalid param 'id' (number)");
                    _s.Resolve(id, Wire.ResultFrom(OptStr(p, "status") ?? "ok", OptStr(p, "reason"), p["value"]?.DeepClone()));
                    return null;
                }
                case "ask":
                    return Wire.Ask(await _s.Ask(Str(p, "role"), Str(p, "input"), OptStr(p, "from")).ConfigureAwait(false));
                case "generate":
                    return Wire.Generate(await _s.Generate(Str(p, "generator"), p["context"]?.DeepClone() as JsonObject, OptStr(p, "source")).ConfigureAwait(false));
                case "media":
                    return (await _s.RequestMedia(new MediaRequest(Str(p, "kind"), Str(p, "prompt"), p["spec"]?.DeepClone() as JsonObject), OptStr(p, "source")).ConfigureAwait(false)).ToJson();
                case "bind":
                    _s.Bind(Str(p, "thing"));
                    return null;
                case "unbind":
                    _s.Unbind(Str(p, "thing"));
                    return null;
                case "remove":
                    return new JsonObject { ["removed"] = _s.RemoveThing(Str(p, "thing")) };
                case "save":
                    return new JsonObject { ["state"] = _s.Save() };
                case "load":
                    try { _s.Load(Str(p, "state")); }
                    catch (InvalidOperationException e) { throw new RpcError(-32602, e.Message); }
                    return null;
                case "stats":
                    return Wire.Stats(_s.Stats);
                case "snapshot":
                    return DebugFeed.Snapshot(_s);
                case "setMission":
                    if (!_s.SetMission(Str(p, "role"), Str(p, "mission"))) throw new RpcError(-32602, "unknown role or empty mission");
                    return null;
                default:
                    throw new RpcError(-32601, $"unknown method '{method}'");
            }
        }

        /// <summary>Pushes effects produced between ticks (finished model work) to the client.</summary>
        public void PushEffects(System.Collections.Generic.IReadOnlyList<Effect> effects)
        {
            if (effects.Count == 0) return;
            _send(new JsonObject { ["jsonrpc"] = "2.0", ["method"] = "effects", ["params"] = new JsonObject { ["items"] = Wire.Effects(effects) } }.ToJsonString());
        }
    }
}
