using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Kinloom.Media;
using Kinloom.Schema;

namespace Kinloom.Protocol
{
    /// <summary>A C# client of <c>kinloom serve</c>, implementing the same contract as an in-process session.
    /// Also the reference for SDKs in other languages (see docs/protocol.md).</summary>
    public sealed class RemoteSession : IKinloomSession, IDisposable
    {
        private readonly ClientWebSocket _ws = new ClientWebSocket();
        private readonly ConcurrentDictionary<long, TaskCompletionSource<JsonNode?>> _pending = new ConcurrentDictionary<long, TaskCompletionSource<JsonNode?>>();
        private readonly ConcurrentQueue<Effect> _effects = new ConcurrentQueue<Effect>();
        private readonly SemaphoreSlim _sendLock = new SemaphoreSlim(1, 1);
        private readonly CancellationTokenSource _stop = new CancellationTokenSource();
        private long _nextId;

        private RemoteSession() { }

        public static async Task<RemoteSession> Connect(string url, CancellationToken ct = default)
        {
            var s = new RemoteSession();
            await s._ws.ConnectAsync(new Uri(url), ct).ConfigureAwait(false);
            _ = Task.Run(s.ReceiveLoop);
            return s;
        }

        public TimeSpan Timeout { get; set; } = TimeSpan.FromMinutes(3);

        private async Task ReceiveLoop()
        {
            var buffer = new byte[1 << 16];
            var text = new StringBuilder();
            while (_ws.State == WebSocketState.Open && !_stop.IsCancellationRequested)
            {
                WebSocketReceiveResult r;
                try { r = await _ws.ReceiveAsync(new ArraySegment<byte>(buffer), _stop.Token).ConfigureAwait(false); }
                catch (Exception) { break; }
                if (r.MessageType == WebSocketMessageType.Close) break;
                text.Append(Encoding.UTF8.GetString(buffer, 0, r.Count));
                if (!r.EndOfMessage) continue;
                var message = JsonNode.Parse(text.ToString()) as JsonObject;
                text.Clear();
                if (message == null) continue;
                if (message["id"] is JsonValue idv && idv.TryGetValue(out long id) && _pending.TryRemove(id, out var tcs))
                {
                    if (message["error"] is JsonObject err) tcs.TrySetException(new InvalidOperationException($"kinloom error {err["code"]}: {err["message"]}"));
                    else tcs.TrySetResult(message["result"]?.DeepClone());
                }
                else if (message["method"]?.GetValue<string>() == "effects")
                    foreach (var item in message["params"]?["items"] as JsonArray ?? new JsonArray())
                        if (item is JsonObject e) _effects.Enqueue(Wire.EffectFrom(e));
            }
            foreach (var p in _pending.Values) p.TrySetException(new InvalidOperationException("connection to kinloom closed"));
        }

        private async Task Send(JsonObject message)
        {
            byte[] bytes = Encoding.UTF8.GetBytes(message.ToJsonString());
            await _sendLock.WaitAsync().ConfigureAwait(false);
            try { await _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _stop.Token).ConfigureAwait(false); }
            finally { _sendLock.Release(); }
        }

        public async Task<JsonNode?> Request(string method, JsonObject? parameters = null)
        {
            long id = Interlocked.Increment(ref _nextId);
            var tcs = new TaskCompletionSource<JsonNode?>(TaskCreationOptions.RunContinuationsAsynchronously);
            _pending[id] = tcs;
            await Send(new JsonObject { ["jsonrpc"] = "2.0", ["id"] = id, ["method"] = method, ["params"] = parameters ?? new JsonObject() }).ConfigureAwait(false);
            var done = await Task.WhenAny(tcs.Task, Task.Delay(Timeout)).ConfigureAwait(false);
            if (done != tcs.Task) { _pending.TryRemove(id, out _); throw new TimeoutException($"kinloom did not answer '{method}'"); }
            return await tcs.Task.ConfigureAwait(false);
        }

        public void Notify(string method, JsonObject parameters) =>
            Send(new JsonObject { ["jsonrpc"] = "2.0", ["method"] = method, ["params"] = parameters }).GetAwaiter().GetResult();

        public IReadOnlyList<ManifestError> Declare(string json) =>
            Wire.ErrorsFrom(Request("declare", new JsonObject { ["manifest"] = json }).GetAwaiter().GetResult());

        public void Update(string thingId, JsonObject props) =>
            Notify("update", new JsonObject { ["thing"] = thingId, ["props"] = props.DeepClone() });

        public void Emit(GameEvent e)
        {
            var p = new JsonObject { ["type"] = e.Type, ["data"] = e.Data.DeepClone() };
            if (e.PerceivedBy != null) p["perceivedBy"] = new JsonArray(Array.ConvertAll(e.PerceivedBy, x => (JsonNode)JsonValue.Create(x)!));
            if (!double.IsNaN(e.Time)) p["time"] = e.Time;
            if (!double.IsNaN(e.Importance)) p["importance"] = e.Importance;
            Notify("event", p);
        }

        public IReadOnlyList<Effect> Pump(double gameTime)
        {
            Notify("tick", new JsonObject { ["time"] = gameTime });
            var batch = new List<Effect>();
            while (_effects.TryDequeue(out var e)) batch.Add(e);
            return batch;
        }

        public void Resolve(long effectId, EffectResult result)
        {
            var p = new JsonObject { ["id"] = effectId, ["status"] = result.Status.ToString().ToLowerInvariant() };
            if (result.Reason != null) p["reason"] = result.Reason;
            if (result.Value != null) p["value"] = result.Value.DeepClone();
            Notify("resolve", p);
        }

        public async Task<AskResult> Ask(string roleId, string input, string? from = null) =>
            Wire.AskFrom((await Request("ask", new JsonObject { ["role"] = roleId, ["input"] = input, ["from"] = from }).ConfigureAwait(false))!);

        public async Task<GenerateResult> Generate(string generatorId, JsonObject? context = null, string? source = null) =>
            Wire.GenerateFrom((await Request("generate", new JsonObject { ["generator"] = generatorId, ["context"] = context?.DeepClone(), ["source"] = source }).ConfigureAwait(false))!);

        public async Task<MediaResult> RequestMedia(MediaRequest request, string? source = null) =>
            Wire.MediaFrom((await Request("media", new JsonObject { ["kind"] = request.Kind, ["prompt"] = request.Prompt, ["spec"] = request.Spec.DeepClone(), ["source"] = source }).ConfigureAwait(false))!);

        public void Bind(string thingId) => Notify("bind", new JsonObject { ["thing"] = thingId });
        public void Unbind(string thingId) => Notify("unbind", new JsonObject { ["thing"] = thingId });

        public bool RemoveThing(string id) =>
            Request("remove", new JsonObject { ["thing"] = id }).GetAwaiter().GetResult()?["removed"]?.GetValue<bool>() ?? false;

        public string Save() => Request("save").GetAwaiter().GetResult()?["state"]?.GetValue<string>() ?? "";

        public void Load(string json) => Request("load", new JsonObject { ["state"] = json }).GetAwaiter().GetResult();

        public void Dispose()
        {
            try { _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", CancellationToken.None).Wait(1000); } catch (Exception) { }
            _stop.Cancel();
            _ws.Dispose();
        }
    }
}
