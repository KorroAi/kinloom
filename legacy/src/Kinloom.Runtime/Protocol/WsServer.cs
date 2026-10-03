using System;
using System.IO;
using System.Net;
using System.Net.WebSockets;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Kinloom.Protocol
{
    /// <summary>Local HTTP/WebSocket server (localhost only). Service mode: each <c>/ws</c> connection gets its own session
    /// (a game written in any language). Session mode: serves one in-process session for tools (an embedded game's debug port).
    /// Both serve <c>/debug</c> (journal stream + snapshot + live mission edits) and <c>/</c> (the inspector page).</summary>
    public sealed class WsServer : IDisposable
    {
        private readonly HttpListener _listener = new HttpListener();
        private readonly Func<KinloomSession>? _factory;
        private readonly CancellationTokenSource _stop = new CancellationTokenSource();
        private KinloomSession? _latest;

        private WsServer(int port, Func<KinloomSession>? factory, KinloomSession? session)
        {
            Port = port;
            _factory = factory;
            _latest = session;
            _listener.Prefixes.Add($"http://localhost:{port}/");
        }

        public int Port { get; }
        /// <summary>The session <c>/debug</c> shows: the embedded one, or the most recent game connection.</summary>
        public KinloomSession? Current => _latest;
        public event Action<string>? Log;

        public static WsServer ForService(int port, Func<KinloomSession> factory) => new WsServer(port, factory, null);
        public static WsServer ForSession(int port, KinloomSession session) => new WsServer(port, null, session);

        public void Start()
        {
            _listener.Start();
            Task.Run(AcceptLoop);
        }

        public void Dispose()
        {
            _stop.Cancel();
            try { _listener.Stop(); _listener.Close(); } catch (ObjectDisposedException) { }
        }

        private async Task AcceptLoop()
        {
            while (!_stop.IsCancellationRequested)
            {
                HttpListenerContext ctx;
                try { ctx = await _listener.GetContextAsync().ConfigureAwait(false); }
                catch (Exception) when (_stop.IsCancellationRequested) { return; }
                catch (HttpListenerException) { return; }
                catch (ObjectDisposedException) { return; }
                _ = Task.Run(() => Route(ctx));
            }
        }

        private async Task Route(HttpListenerContext ctx)
        {
            string path = ctx.Request.Url?.AbsolutePath ?? "/";
            try
            {
                if (ctx.Request.IsWebSocketRequest && !OriginAllowed(ctx.Request.Headers["Origin"]))
                {
                    // Browsers let any web page open a WebSocket to localhost: only pages served from this machine may.
                    Log?.Invoke($"{path}: refused a connection from origin {ctx.Request.Headers["Origin"]}");
                    ctx.Response.StatusCode = 403;
                    ctx.Response.Close();
                    return;
                }
                if (path == "/ws" && ctx.Request.IsWebSocketRequest && _factory != null) await Game(ctx).ConfigureAwait(false);
                else if (path == "/debug" && ctx.Request.IsWebSocketRequest) await Debug(ctx).ConfigureAwait(false);
                else if (path == "/" || path == "/index.html") Page(ctx);
                else { ctx.Response.StatusCode = 404; ctx.Response.Close(); }
            }
            catch (Exception e) when (!(e is OutOfMemoryException))
            {
                Log?.Invoke($"{path}: {e.GetType().Name}: {e.Message}");
                try { ctx.Response.Abort(); } catch (Exception) { }
            }
        }

        /// <summary>Native clients send no Origin; browser pages may connect only when they were served from this machine.</summary>
        internal static bool OriginAllowed(string? origin)
        {
            if (string.IsNullOrEmpty(origin)) return true;
            if (!Uri.TryCreate(origin, UriKind.Absolute, out var uri) || (uri.Scheme != "http" && uri.Scheme != "https")) return false;
            return uri.Host == "localhost" || uri.Host == "127.0.0.1" || uri.Host == "[::1]" || uri.Host == "::1";
        }

        private static void Page(HttpListenerContext ctx)
        {
            byte[] html = Encoding.UTF8.GetBytes(InspectorHtml());
            ctx.Response.ContentType = "text/html; charset=utf-8";
            ctx.Response.ContentLength64 = html.Length;
            ctx.Response.OutputStream.Write(html, 0, html.Length);
            ctx.Response.Close();
        }

        internal static string InspectorHtml()
        {
            using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("Kinloom.Inspector.index.html");
            if (stream == null) return "<!doctype html><title>Kinloom</title><p>Kinloom inspector page missing from this build.</p>";
            using var reader = new StreamReader(stream);
            return reader.ReadToEnd();
        }

        private async Task Game(HttpListenerContext ctx)
        {
            var wsCtx = await ctx.AcceptWebSocketAsync(null).ConfigureAwait(false);
            var session = _factory!();
            _latest = session;
            using var conn = new Connection(wsCtx.WebSocket);
            var dispatcher = new ProtocolDispatcher(session, conn.Send);
            Log?.Invoke("game connected");
            var pumping = Task.Run(async () =>
            {
                // Finished model work produces effects between the game's ticks: push them as they come.
                while (conn.Open && !_stop.IsCancellationRequested)
                {
                    if (session.HasRoleWork || session.ReadyCount > 0) dispatcher.PushEffects(session.Pump(session.Now));
                    await Task.Delay(25).ConfigureAwait(false);
                }
            });
            await conn.Receive(message =>
            {
                var task = dispatcher.Handle(message);
                if (task.IsCompleted) { if (task.Result != null) conn.Send(task.Result); }
                else _ = task.ContinueWith(t => { if (t.Status == TaskStatus.RanToCompletion && t.Result != null) conn.Send(t.Result); }, TaskScheduler.Default);
            }, _stop.Token).ConfigureAwait(false);
            await pumping.ConfigureAwait(false);
            Log?.Invoke("game disconnected");
        }

        private async Task Debug(HttpListenerContext ctx)
        {
            var wsCtx = await ctx.AcceptWebSocketAsync(null).ConfigureAwait(false);
            using var conn = new Connection(wsCtx.WebSocket, lossy: true);
            var session = _latest;
            if (session == null)
            {
                conn.Send("{\"jsonrpc\":\"2.0\",\"method\":\"waiting\",\"params\":{\"text\":\"no game connected yet\"}}");
                for (int i = 0; i < 600 && _latest == null && conn.Open; i++) await Task.Delay(100).ConfigureAwait(false);
                session = _latest;
                if (session == null) return;
            }
            void OnEntry(JournalEntry e) => conn.Send(DebugFeed.JournalNotification(e));
            session.Journal.Added += OnEntry;
            try
            {
                var dispatcher = new ProtocolDispatcher(session, conn.Send);
                await conn.Receive(message =>
                {
                    var task = dispatcher.Handle(message);
                    _ = task.ContinueWith(t => { if (t.Status == TaskStatus.RanToCompletion && t.Result != null) conn.Send(t.Result); }, TaskScheduler.Default);
                }, _stop.Token).ConfigureAwait(false);
            }
            finally { session.Journal.Added -= OnEntry; }
        }

        /// <summary>One WebSocket. Sends are queued and written by a background loop, so a slow or stalled client never blocks
        /// the caller (journal events are raised while the session is locked). A debug connection keeps at most
        /// <see cref="MaxDebugBacklog"/> pending messages and drops the oldest; a game connection never drops.</summary>
        private sealed class Connection : IDisposable
        {
            public const int MaxDebugBacklog = 2000;
            /// <summary>Largest message accepted; a bigger one closes the connection.</summary>
            public const int MaxMessageBytes = 16 * 1024 * 1024;
            private readonly WebSocket _ws;
            private readonly bool _lossy;
            private readonly System.Collections.Concurrent.ConcurrentQueue<string> _outbox = new System.Collections.Concurrent.ConcurrentQueue<string>();
            private readonly SemaphoreSlim _signal = new SemaphoreSlim(0);
            private readonly CancellationTokenSource _closing = new CancellationTokenSource();

            public Connection(WebSocket ws, bool lossy = false)
            {
                _ws = ws;
                _lossy = lossy;
                Task.Run(SendLoop);
            }

            public bool Open => _ws.State == WebSocketState.Open;

            public void Send(string text)
            {
                if (!Open) return;
                _outbox.Enqueue(text);
                if (_lossy) while (_outbox.Count > MaxDebugBacklog && _outbox.TryDequeue(out _)) { }
                _signal.Release();
            }

            private async Task SendLoop()
            {
                try
                {
                    while (!_closing.IsCancellationRequested)
                    {
                        await _signal.WaitAsync(_closing.Token).ConfigureAwait(false);
                        while (_outbox.TryDequeue(out var text))
                        {
                            if (!Open) return;
                            byte[] bytes = Encoding.UTF8.GetBytes(text);
                            await _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _closing.Token).ConfigureAwait(false);
                        }
                    }
                }
                catch (OperationCanceledException) { }
                catch (WebSocketException) { }
                catch (ObjectDisposedException) { }
            }

            public async Task Receive(Action<string> onMessage, CancellationToken stop)
            {
                var buffer = new byte[1 << 16];
                var text = new StringBuilder();
                while (Open && !stop.IsCancellationRequested)
                {
                    WebSocketReceiveResult r;
                    try { r = await _ws.ReceiveAsync(new ArraySegment<byte>(buffer), stop).ConfigureAwait(false); }
                    catch (Exception) { return; }
                    if (r.MessageType == WebSocketMessageType.Close)
                    {
                        try { await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", CancellationToken.None).ConfigureAwait(false); } catch (Exception) { }
                        return;
                    }
                    text.Append(Encoding.UTF8.GetString(buffer, 0, r.Count));
                    if (text.Length > MaxMessageBytes)
                    {
                        try { await _ws.CloseAsync(WebSocketCloseStatus.MessageTooBig, "message too big", CancellationToken.None).ConfigureAwait(false); } catch (Exception) { }
                        return;
                    }
                    if (!r.EndOfMessage) continue;
                    string message = text.ToString();
                    text.Clear();
                    onMessage(message);
                }
            }

            public void Dispose()
            {
                _closing.Cancel();
                _ws.Dispose();
            }
        }
    }
}
