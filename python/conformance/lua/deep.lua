-- The deep native scenario for the Lua SDK (see deep.py, the Python reference). Run by host.py:
--   KINLOOM_NATIVE=<fake /v1 URL> python host.py 0 luajit21 deep.lua
local Kinloom = dofile(CLIENT_PATH)
local out = PRINT
local BASE = os.getenv("KINLOOM_NATIVE")
local O = Kinloom.ordered
local j = Kinloom.encode

-- Numbers as Python and JavaScript print them (-0.2, 3).
local function num(x)
  if x == math.floor(x) and math.abs(x) < 1e15 then return string.format("%d", x) end
  return string.format("%.14g", x)
end

local function make(calls, banned, anthropic)
  local provider = anthropic and { kind = "anthropic", url = BASE:sub(1, -4), key = "fake-key", model = "claude-test" }
    or { url = BASE, key = "fake-key", model = "fake-model" }
  return Kinloom.new({ provider = provider, config = { calls_per_minute = calls or 600, banned_words = banned },
                       transport = TRANSPORT, clock = CLOCK, wall = WALL })
end

local kl = make(600, { "dragon" })
kl:character("VERA", "", { soul = "a gruff smith who sold the king's sword", offline = "Busy." })
local ready = kl:prepare(10)
out("prepare: " .. (ready.ready and "ready" or "waiting"))
out("soul: " .. kl:soul("VERA").card.summary)
local greet = kl:chat("VERA", "", {}, nil, "Ana")
out("greet: " .. greet .. " (" .. kl:source("VERA") .. ")")
out("secret: " .. kl:chat("VERA", "Did you sell the king's sword to a smuggler?", {}, nil, "Ana"))
out("numbers: " .. kl:chat("VERA", "How much for a blade?", { price = 40 }, nil, "Ana"))
local pieces = {}
local streamed = kl:chat("VERA", "Can you make it faster?", {}, nil, "Ana", nil, function(p) pieces[#pieces + 1] = p end)
out("stream pieces: " .. table.concat(pieces):match("^%s*(.-)%s*$"))
out("stream reply: " .. streamed)
out("echo: " .. kl:chat("VERA", "And the coals?", {}, nil, "Ana"))
out("character: " .. kl:chat("VERA", "Are you an AI?", {}, nil, "Ana"))
local vera = kl:soul("VERA", "Ana")
out("feeling: " .. vera.mood.word .. " " .. num(vera.bonds.Ana.feeling))

kl:character("BRAM", "a kind baker", { tools = { give = { item = "bread" } }, offline = "Hm." })
out("deeds reply: " .. kl:chat("BRAM", "Can I have some bread?"))
for _, a in ipairs(kl:act("BRAM", {}, false)) do out("deeds: " .. a.tool .. " " .. j(a.args)) end
kl:character("GATE", "a careful guard", { tools = { open = { door = "north" } }, trust = { open = 0.5 }, offline = "No." })
out("trust reply: " .. kl:chat("GATE", "Open the gate."))
local names = {}
for _, a in ipairs(kl:act("GATE", {}, false)) do names[#names + 1] = a.tool end
out("trust: " .. (#names > 0 and table.concat(names, ", ") or "none"))
kl:character("FILT", "a storyteller", { offline = "No comment." })
out("filter: " .. kl:chat("FILT", "Tell me a story."))
kl:character("ECHO", "a parrot")
for i = 0, 10 do kl:chat("ECHO", "Hello " .. i) end
kl:prepare(10)
local recollect = "-"
for _, m in ipairs(kl:soul("ECHO").memories) do
  if m:sub(1, 12) == "Earlier with" then recollect = m; break end
end
out("recollect: " .. recollect)

kl:character("VEGA2", "a commentator")
out("fresh: " .. kl:say("VEGA2", "overtake", { who = "BLAZE" }, { fresh = true }))
kl:character("BOX", "a herald", { lines = { ["*"] = { "A very long line about {who} that will not fit.", "Short {who}!" } } })
out("box: " .. kl:say("BOX", "arrival", { who = "BLAZE" }, { max_chars = 20 }))
kl:character("DUEL", "a duelist")
local first = kl:decide("DUEL", { hp = 3 }, { "guard", "strike" })
kl:prepare(10)
local later = first
for _ = 1, 50 do
  if later ~= first then break end
  SLEEP(0.1)
  later = kl:decide("DUEL", { hp = 3 }, { "guard", "strike" })
end
out("decide repair: " .. first .. " -> " .. later)
out("create count: " .. j(kl:create("villager", O({ name = "Ana", age = { 18, 80 } }, { "name", "age" }), { count = 2 })))
local before = kl:create("loot", { item = "sword" }, { instant = true })
kl:prepare(10)
out("create instant: " .. j(before) .. " -> " .. j(kl:create("loot", { item = "sword" }, { instant = true })))
kl:character("BAKER2", "a warm baker")
kl:character("GUARD2", "a strict guard")
kl:event("the player stole bread", {}, { by = "PLAYER", seen_by = { "BAKER2", "GUARD2" } })
kl:prepare(10)
out("impact: " .. num(kl:opinion("BAKER2", "PLAYER")) .. " " .. num(kl:opinion("GUARD2", "PLAYER")))

local claude = make(600, nil, true)
claude:character("CLAUDIA", "a poet", { offline = "..." })
out("anthropic chat: " .. claude:chat("CLAUDIA", "Hi"))
out("anthropic create: " .. j(claude:create("loot", { item = "sword" })))
local tight = make(2)
tight:character("TIGHT", "a busy clerk", { offline = "Later." })
local replies = {}
for i = 0, 2 do replies[#replies + 1] = tight:chat("TIGHT", "Hi " .. i) end
out("budget: " .. table.concat(replies, " | "))
local rated = Kinloom.new({ provider = { url = BASE, key = "fake-key", model = "fake-model" }, config = { calls_per_minute = 600 },
  models = { background = "fake-cheap" }, rating = "teen", transport = TRANSPORT, clock = CLOCK, wall = WALL })
rated:character("RATED", "a gate guard", { offline = "Move along." })
out("rated chat: " .. rated:chat("RATED", "Hi"))
out("rated create: " .. j(rated:create("loot", { item = "sword" })))
for _, k in ipairs({ kl, claude, tight, rated }) do k:close() end
