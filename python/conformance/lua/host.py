"""Runs the Lua conformance scenario inside real Lua runtimes (LuaJIT 2.1 as in LÖVE, and Lua 5.4) through `lupa`.
The HTTP transport is a blocking POST, like LuaSocket's: the client's own JSON, caching, offline answers and
redeclaring are what is tested. In native mode (KINLOOM_NATIVE set) the same transport carries the client's own model
calls: every header, and bodies both ways as hex (pictures and audio are bytes).
Usage: python host.py <port> [luajit21|lua54] [scenario.lua]"""
import importlib
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT = os.path.join(HERE, "..", "..", "src", "kinloom", "clients", "lua", "kinloom.lua")


def http_post(url, body_hex, timeout, headers):
    # like the client's own LuaSocket transports (tested by transports.py): a short connect first, so a server that
    # is not running is seen at once (Windows takes 2-4 s to report a refused connection)
    u = urllib.parse.urlsplit(url)
    try:
        socket.create_connection((u.hostname, u.port or 80), 0.3).close()
    except OSError:
        return 0, ""
    sent = {"Content-Type": "application/json"}
    sent.update({str(k): str(v) for k, v in headers.items()})
    req = urllib.request.Request(url, data=bytes.fromhex(body_hex), method="POST", headers=sent)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().hex()
    except urllib.error.HTTPError as e:
        return e.code, e.read().hex()
    except (urllib.error.URLError, OSError):
        return 0, ""


def main(port, runtime="luajit21", scenario="scenario.lua"):
    lua = importlib.import_module("lupa." + runtime).LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    g.PORT = str(port)
    g.CLIENT_PATH = os.path.abspath(CLIENT).replace("\\", "/")
    g.SLEEP = time.sleep
    g.CLOCK = time.monotonic
    g.WALL = time.time
    g.PRINT = lambda s: print(s, flush=True)
    g.HTTP_POST = http_post
    g.TRANSPORT = lua.eval("""function(url, body, timeout, headers, done)
        local hex = body:gsub(".", function(c) return string.format("%02x", c:byte()) end)
        local status, text = HTTP_POST(url, hex, timeout, headers)
        done(status, (text:gsub("..", function(h) return string.char(tonumber(h, 16)) end)))
    end""")
    with open(os.path.join(HERE, scenario), encoding="utf-8") as f:
        lua.execute(f.read())


if __name__ == "__main__":
    main(*sys.argv[1:])
