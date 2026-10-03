-- Kinloom inside a real LÖVE game: offline, relay (kinloom serve) and native (the game calls the model itself), all
-- through LÖVE's own transport (love.thread + LuaSocket). Run by proof/engines/love/run.py:
--   lovec <this folder> <serve port> <model url> <results file>
local Kinloom = require("kinloom")

local results, pending, started = {}, 0, 0
local out_path
local function log(line) results[#results + 1] = line end

local function exercise(kl, mode)
  log(mode .. " transport: " .. (kl._pump and "love.thread" or "other"))
  kl:character("MIRA", "a gruff smith", { offline = "Busy." })
  local plan = kl:decide("BLAZE", { gap = 0.4 }, { strategy = { "attack", "block" } })
  log(mode .. " decide now: " .. tostring(plan.strategy))
  pending = pending + 2
  kl:chat("MIRA", "Is that the king's sword?", { gold = 3 }, function(reply)
    log(mode .. " chat: " .. tostring(reply) .. " (" .. tostring(kl:source("MIRA")) .. ")")
    pending = pending - 1
  end, "Ana")
  kl:create("an item found in a cave", { name = "Glowcap", value = { 1, 50 } }, nil, function(item)
    log(mode .. " create: " .. tostring(item and item.name) .. " " .. tostring(item and item.value))
    pending = pending - 1
  end)
end

local clients = {}

function love.load(arg)
  local port, model, path = arg[1], arg[2], arg[3]
  out_path = path
  started = love.timer.getTime()
  clients.offline = Kinloom.new({ offline = true })
  clients.relay = Kinloom.new({ url = "http://127.0.0.1:" .. port })
  clients.native = Kinloom.new({ provider = { url = model, key = "fake-key", model = "fake-model" } })
  for _, mode in ipairs({ "offline", "relay", "native" }) do exercise(clients[mode], mode) end
end

function love.update(dt)
  for _, kl in pairs(clients) do kl:update() end
  local elapsed = love.timer.getTime() - started
  if pending == 0 or elapsed > 30 then
    log("pending at the end: " .. pending .. ", " .. string.format("%.1f", elapsed) .. " s")
    local f = assert(io.open(out_path, "w"))
    f:write(table.concat(results, "\n") .. "\n")
    f:close()
    love.event.quit()
  end
end
