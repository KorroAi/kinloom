"""Kinloom client for Python games (Pygame, Ren'Py, Panda3D, Arcade, Blender, Ursina...).

Standard library only (a minimal WebSocket client is included), Python 3.8+. Talks JSON-RPC to `kinloom serve`
(docs/protocol.md). Effects are applied on *your* thread, inside tick()/frame()/poll(), so handlers may touch the game.

    from kinloom_client import Kinloom

    kl = Kinloom.connect()                                   # ws://localhost:7717/ws
    kl.handle("say", lambda e: show_subtitle(e["thing"], e["text"]))
    kl.handle("set", lambda e: setattr(things[e["thing"]], e["member"], e["args"]["value"]))
    errors = kl.declare(open("kinloom/game.json").read())
    # every frame:
    kl.update("player", {"health": player.health})
    kl.frame(game_time)                                      # sends the tick, applies effects that arrived
    reply = kl.ask("dispatcher", "Where is the depot?", "player")["reply"]   # or ask_async(...) to keep playing

A handler returns None or True (ok), False (failed), a string (refused, with that reason) or {"status", "reason", "value"}.
"""
import base64
import hashlib
import itertools
import json
import os
import queue
import socket
import struct
import threading
from concurrent.futures import Future
from urllib.parse import urlparse

DEFAULT_URL = "ws://localhost:7717/ws"
_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class KinloomError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def _mask(data, mask):
    # XOR with the repeated 4-byte key as one big integer: fast even for large manifests.
    n = len(data)
    if n == 0:
        return b""
    key = (mask * (n // 4 + 1))[:n]
    return (int.from_bytes(data, "big") ^ int.from_bytes(key, "big")).to_bytes(n, "big")


class _WebSocket:
    """Just enough RFC 6455 for a local client: text frames, fragmentation, ping/pong, close."""

    def __init__(self, url, timeout):
        u = urlparse(url)
        if u.scheme != "ws":
            raise KinloomError("only ws:// URLs are supported (Kinloom listens on localhost)")
        self._sock = socket.create_connection((u.hostname, u.port or 80), timeout=timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        key = base64.b64encode(os.urandom(16)).decode()
        path = (u.path or "/") + ("?" + u.query if u.query else "")
        self._sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {u.hostname}:{u.port or 80}\r\nUpgrade: websocket\r\n"
                            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self._sock.recv(1024)
            if not chunk:
                raise KinloomError("the server closed the connection during the handshake")
            head += chunk
        header, self._buffer = head.split(b"\r\n\r\n", 1)
        lines = header.decode("latin-1").split("\r\n")
        if " 101 " not in lines[0] + " ":
            raise KinloomError(f"WebSocket handshake refused: {lines[0]}")
        expected = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
        accept = next((l.split(":", 1)[1].strip() for l in lines[1:] if l.lower().startswith("sec-websocket-accept:")), "")
        if accept != expected:
            raise KinloomError("WebSocket handshake failed (bad Sec-WebSocket-Accept)")
        self._sock.settimeout(None)
        self._send_lock = threading.Lock()

    def _read(self, n):
        while len(self._buffer) < n:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ConnectionError("connection closed")
            self._buffer += chunk
        data, self._buffer = self._buffer[:n], self._buffer[n:]
        return data

    def send(self, opcode, payload):
        header = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        masked = _mask(payload, mask)
        with self._send_lock:
            self._sock.sendall(header + mask + masked)

    def send_text(self, text):
        self.send(0x1, text.encode("utf-8"))

    def receive_text(self):
        """The next text message, or None when the connection closed."""
        parts = []
        while True:
            b0, b1 = self._read(2)
            opcode, fin = b0 & 0x0F, b0 & 0x80
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b1 & 0x80 else None
            payload = self._read(n)
            if mask:
                payload = _mask(payload, mask)
            if opcode == 0x8:
                try:
                    self.send(0x8, b"")
                except OSError:
                    pass
                return None
            if opcode == 0x9:
                self.send(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            parts.append(payload)
            if fin:
                return b"".join(parts).decode("utf-8")

    def close(self):
        try:
            self.send(0x8, b"")
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass


class Kinloom:
    @staticmethod
    def connect(url=DEFAULT_URL, timeout=10.0, request_timeout=60.0):
        return Kinloom(_WebSocket(url, timeout), request_timeout)

    def __init__(self, ws, request_timeout=60.0):
        self._ws = ws
        self._ids = itertools.count(1)
        self._pending = {}
        self._lock = threading.Lock()
        self._effects = queue.Queue()
        self._handlers = {}
        self._fallback = None
        self.request_timeout = request_timeout
        self.closed = False
        self._reader = threading.Thread(target=self._read_loop, name="kinloom-reader", daemon=True)
        self._reader.start()

    # ---------- handlers ----------

    def handle(self, kind, handler):
        """Handles one effect kind: set, invoke, create, destroy, say, media, validate (or "generated")."""
        self._handlers[kind] = handler
        return self

    def on_effect(self, handler):
        """Handles every effect kind without its own handler."""
        self._fallback = handler
        return self

    # ---------- methods ----------

    def declare(self, manifest, source=None):
        params = {"manifest": manifest}
        if source:
            params["source"] = source
        return self._request("declare", params).get("errors", [])

    def update(self, thing, props):
        self._notify("update", {"thing": thing, "props": props})

    def event(self, type, data=None, perceived_by=None, time=None, importance=None):
        params = {"type": type, "data": data or {}}
        if perceived_by is not None:
            params["perceivedBy"] = list(perceived_by)
        if time is not None:
            params["time"] = time
        if importance is not None:
            params["importance"] = importance
        self._notify("event", params)

    def frame(self, time):
        """Game-loop tick: sends the time and applies the effects that already arrived. Returns how many were applied."""
        self._notify("tick", {"time": time})
        return self.poll()

    def tick(self, time):
        """Tick and wait: applies the returned effects (and any pushed ones) and returns the returned effects."""
        effects = self._request("tick", {"time": time}).get("effects", [])
        for e in effects:
            self._apply(e)
        self.poll()
        return effects

    def poll(self):
        """Applies effects pushed since the last call, on the calling thread. Returns how many."""
        n = 0
        while True:
            try:
                e = self._effects.get_nowait()
            except queue.Empty:
                return n
            self._apply(e)
            n += 1

    def ask(self, role, text, sender=None, timeout=None):
        return self.ask_async(role, text, sender).result(timeout or self.request_timeout)

    def ask_async(self, role, text, sender=None):
        params = {"role": role, "input": text}
        if sender:
            params["from"] = sender
        return self._request_async("ask", params)

    def generate(self, generator, context=None, timeout=None):
        return self.generate_async(generator, context).result(timeout or self.request_timeout)

    def generate_async(self, generator, context=None):
        return self._request_async("generate", {"generator": generator, "context": context or {}})

    def media(self, kind, prompt, spec=None, timeout=None):
        return self._request_async("media", {"kind": kind, "prompt": prompt, "spec": spec or {}}).result(timeout or self.request_timeout)

    def bind(self, thing):
        self._notify("bind", {"thing": thing})

    def unbind(self, thing):
        self._notify("unbind", {"thing": thing})

    def remove(self, thing):
        return self._request("remove", {"thing": thing}).get("removed", False)

    def save(self):
        return self._request("save", {})["state"]

    def load(self, state):
        self._request("load", {"state": state})

    def stats(self):
        return self._request("stats", {})

    def snapshot(self):
        return self._request("snapshot", {})

    def set_mission(self, role, mission):
        self._request("setMission", {"role": role, "mission": mission})

    def resolve(self, effect_id, status="ok", reason=None, value=None):
        params = {"id": effect_id, "status": status}
        if reason is not None:
            params["reason"] = reason
        if value is not None:
            params["value"] = value
        self._notify("resolve", params)

    def close(self):
        self.closed = True
        self._ws.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---------- internals ----------

    def _send(self, message):
        if self.closed:
            raise KinloomError("connection closed")
        message["jsonrpc"] = "2.0"
        self._ws.send_text(json.dumps(message))

    def _notify(self, method, params):
        self._send({"method": method, "params": params})

    def _request_async(self, method, params):
        future = Future()
        with self._lock:
            i = next(self._ids)
            self._pending[i] = future
        try:
            self._send({"id": i, "method": method, "params": params})
        except Exception as e:  # report send failures through the future like any other error
            with self._lock:
                self._pending.pop(i, None)
            future.set_exception(e)
        return future

    def _request(self, method, params):
        return self._request_async(method, params).result(self.request_timeout)

    def _read_loop(self):
        try:
            while True:
                text = self._ws.receive_text()
                if text is None:
                    break
                try:
                    msg = json.loads(text)
                except ValueError:
                    continue
                if msg.get("id") is not None:
                    with self._lock:
                        future = self._pending.pop(msg["id"], None)
                    if future is not None:
                        if "error" in msg:
                            future.set_exception(KinloomError(msg["error"].get("message", "error"), msg["error"].get("code")))
                        else:
                            future.set_result(msg.get("result") or {})
                        continue
                if msg.get("method") == "effects":
                    for e in (msg.get("params") or {}).get("items", []):
                        self._effects.put(e)
        except (OSError, ConnectionError):
            pass
        finally:
            self.closed = True
            with self._lock:
                pending, self._pending = self._pending, {}
            for f in pending.values():
                if not f.done():
                    f.set_exception(KinloomError("connection closed"))

    def _apply(self, effect):
        generated = effect.get("kind") == "invoke" and effect.get("thing") == "world" and effect.get("member") == "generated"
        handler = (self._handlers.get("generated") if generated else None) or self._handlers.get(effect.get("kind")) or self._fallback
        if handler is None:
            ok_by_default = effect.get("thing") == "world" and effect.get("kind") != "say"
            result = {"status": "ok"} if ok_by_default else {"status": "failed", "reason": f"the game has no handler for {effect.get('kind')} effects"}
        else:
            try:
                result = _to_result(handler(effect))
            except Exception as e:  # a handler bug is reported to the AI as a failed effect
                result = {"status": "failed", "reason": f"{type(e).__name__}: {e}"}
        if not self.closed:
            self.resolve(effect["id"], result.get("status", "ok"), result.get("reason"), result.get("value"))


def _to_result(r):
    if r is None or r is True:
        return {"status": "ok"}
    if r is False:
        return {"status": "failed"}
    if isinstance(r, str):
        return {"status": "refused", "reason": r}
    if isinstance(r, dict) and "status" in r:
        return r
    return {"status": "ok"}
