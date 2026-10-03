"""The Lua client's own transports (LuaSocket, and the LÖVE thread), which the conformance host replaces with its
own: compiled in LuaJIT 2.1 and Lua 5.4, and run against stand-in socket modules (a server that is there, one that
is not). Usage: python transports.py [luajit21|lua54]  (needs `lupa`, like host.py)"""
import importlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT = os.path.join(HERE, "..", "..", "src", "kinloom", "clients", "lua", "kinloom.lua")

FAKES = r"""
CONNECTS, REQUESTS = {}, 0
NOW = 100
package.preload["socket"] = function()
  return {
    gettime = function() return NOW end,
    tcp = function()
      local t = {}
      function t:settimeout(s) self.timeout = s end
      function t:connect(host, port)
        CONNECTS[#CONNECTS + 1] = host .. ":" .. port .. "@" .. self.timeout
        if port == 9 then return nil, "connection refused" end
        return 1
      end
      function t:close() end
      return t
    end,
  }
end
package.preload["socket.http"] = function()
  return { request = function(req)
    REQUESTS = REQUESTS + 1
    req.sink('{"text": "hi"}')
    return 1, 200
  end }
end
package.preload["ltn12"] = function()
  return { source = { string = function(s) return s end },
           sink = { table = function(t) return function(chunk) t[#t + 1] = chunk; return 1 end end } }
end
"""

SCENARIO = r"""
local results = {}
local up = Kinloom.new({ url = "http://127.0.0.1:7717", clock = function() return NOW end })
up:say("A", "e", {}, function(t) results[#results + 1] = "up: " .. tostring(t) end)
up:say("A", "e", {}, function(t) results[#results + 1] = "up again: " .. tostring(t) end)
local down = Kinloom.new({ url = "http://localhost:9", clock = function() return NOW end })
down:character("A", "", { lines = { ["*"] = { "offline line" } } })
down:say("A", "e", {}, function(t) results[#results + 1] = "down: " .. tostring(t) end)
results[#results + 1] = "down for: " .. string.format("%g", down._down_until - NOW)
NOW = NOW + 3
down:say("A", "e", {}, function(t) end)
results[#results + 1] = "down again for: " .. string.format("%g", down._down_until - NOW)
results[#results + 1] = "connects: " .. table.concat(CONNECTS, ", ")
results[#results + 1] = "requests: " .. REQUESTS
return table.concat(results, "\n")
"""


def main(runtime="luajit21"):
    lua = importlib.import_module("lupa." + runtime).LuaRuntime(unpack_returned_tuples=True)
    source = open(CLIENT, encoding="utf-8").read()
    thread = re.search(r"local THREAD = \[\[\r?\n(.*?)\r?\n\]\]", source, re.S).group(1)
    ok, err = lua.eval("function(s) local f, e = load(s, 'THREAD'); return f ~= nil, e end")(thread)
    assert ok, "the LÖVE thread does not compile: %s" % err
    lua.execute(FAKES)
    lua.globals().Kinloom = lua.execute("return dofile(%r)" % os.path.abspath(CLIENT).replace("\\", "/"))
    got = lua.execute(SCENARIO).splitlines()
    print("\n".join(got))
    # The character declaration is sent too (the down client): every connection to port 9 is checked in 0.3 s.
    assert got[:5] == ["up: hi", "up again: hi", "down: offline line", "down for: 2", "down again for: 4"], got
    connects = got[5][len("connects: "):].split(", ")
    assert connects[0] == "127.0.0.1:7717@0.3" and connects.count("127.0.0.1:7717@0.3") == 1, connects   # once while up
    assert all(c == "127.0.0.1:9@0.3" for c in connects[1:]) and len(connects) >= 3, connects
    assert got[6] == "requests: 2", got[6]
    print("lua transports (%s): PASS" % runtime)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "luajit21")
