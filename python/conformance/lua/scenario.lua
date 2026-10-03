-- Conformance scenario for the Lua client. The host provides: PORT, TRANSPORT (a blocking HTTP function like
-- LuaSocket's), SLEEP(seconds), CLOCK, WALL, CLIENT_PATH and PRINT.
local Kinloom = dofile(CLIENT_PATH)
local out = PRINT
-- Native mode (python conformance/native.py): the SDK calls the fake model itself; no kinloom serve. Objects whose
-- key order reaches a prompt are given in Python's order.
local NATIVE = os.getenv("KINLOOM_NATIVE")
if NATIVE == "" then NATIVE = nil end
local O = Kinloom.ordered
local host
if NATIVE then
  host = Kinloom.new({ provider = { url = NATIVE, key = "fake-key", model = "fake-model" }, config = { calls_per_minute = 600 },
    voice = { url = NATIVE, key = "fake-key", speak_model = "fake-tts", listen_model = "fake-stt", name = "custom" },
    transport = TRANSPORT, clock = CLOCK, wall = WALL })
end
local function connect()
  if host then return Kinloom.new({ brain = host.brain, clock = CLOCK }) end
  return Kinloom.new({ url = "http://127.0.0.1:" .. PORT, transport = TRANSPORT, clock = CLOCK })
end
local function unreachable()
  if NATIVE then return Kinloom.new({ offline = true, transport = TRANSPORT, clock = CLOCK, wall = WALL }) end
  return Kinloom.new({ url = "http://127.0.0.1:9", transport = TRANSPORT, clock = CLOCK })
end
local kl = connect()
kl:character("VEGA", "commentator", { lines = { ["*"] = { "What a race, {who}!" } }, events = { overtake = { "who", "whom" } } })
kl:character("THEO", "engineer", { offline = "Copy." })
kl:character("BLAZE", "rival", { tools = { boost = { seconds = { 0.5, 2.5 } } } })
local facts = { who = "BLAZE", whom = "NOVA" }
local line = ""
for _ = 1, 100 do
  line = kl:say("VEGA", "overtake", facts)
  if line:find("passes") then break end
  SLEEP(0.05)
end
out("say: " .. line)
out("chat: " .. kl:chat("THEO", "gap?", { position = 3 }))
local choices = O({ strategy = { "attack", "block" }, aggression = { Kinloom.real(0), Kinloom.real(1) } }, { "strategy", "aggression" })
local first = Kinloom.encode(kl:decide("BLAZE", { lap = 1 }, choices))
out("decide first: " .. first)
local later = first
for _ = 1, 100 do
  SLEEP(0.3)
  later = Kinloom.encode(kl:decide("BLAZE", { lap = 1 }, choices))
  if later ~= first then break end
end
out("decide later: " .. later)
for _ = 1, 100 do
  local actions = kl:act("BLAZE", { lap = 1 })
  if #actions > 0 then
    for _, a in ipairs(actions) do out("act later: " .. a.tool .. " " .. Kinloom.encode(a.args)) end
    break
  end
  SLEEP(0.3)
end
out("create: " .. Kinloom.encode(kl:create("race", { challenge = "Win clean", sky = "#ff7a45" })))
local offline = unreachable()
offline:character("VEGA", "commentator", { lines = { ["*"] = { "What a race, {who}!" } } })
offline:character("THEO", "engineer", { offline = "Copy." })
out("offline say: " .. offline:say("VEGA", "overtake", facts))
out("offline chat: " .. offline:chat("THEO", "gap?", { position = 3 }))
out("offline decide: " .. Kinloom.encode(offline:decide("BLAZE", { lap = 1 }, choices)))
out("offline create: " .. Kinloom.encode(offline:create("race", { challenge = "Win clean", sky = "#ff7a45" })))

-- Minds and the world (the depth layer).
local R = Kinloom.real
local raider = {
  senses = O({ hp = { 0, 1 }, dist = { 0, 40 }, armed = true, enemy = { "idle", "alert" } }, { "hp", "dist", "armed", "enemy" }),
  actions = O({ charge = { speed = { R(0.5), R(3) } }, shoot = { burst = { 1, 5 } }, retreat = {} }, { "charge", "shoot", "retreat" }),
  order = { "charge", "shoot", "retreat" },
  rules = O({ retreat = { "hp low" }, shoot = { "armed", "dist below 20" },
              charge = O({ score = R(0.5), args = { speed = "dist high" } }, { "score", "args" }) }, { "retreat", "shoot", "charge" }),
  variants = 1,
}
kl:mind("raider", "a cunning raider", raider)
kl:mind("scout", "a timid scout", { senses = { noise = { 0, 1 } }, actions = O({ run = {}, hide = {} }, { "run", "hide" }),
                                     order = { "run", "hide" }, variants = 2 })
for _ = 1, 100 do
  if kl:report("raider") then break end
  SLEEP(0.05)
end
out("think retreat: " .. Kinloom.encode(kl:think("raider", { hp = 0.1, dist = 30, armed = true }, "u1")))
out("think shoot: " .. Kinloom.encode(kl:think("raider", { hp = 0.9, dist = 8, armed = true, enemy = "alert" }, "u2")))
out("think charge: " .. Kinloom.encode(kl:think("raider", { hp = 0.9, dist = 10, armed = false }, "u3")))
out("think sticky: " .. kl:think("raider", { hp = 0.52, dist = 30, armed = true }, "u1").action)
out("think fresh: " .. Kinloom.encode(kl:think("raider", { hp = 0.52, dist = 30, armed = true }, "u4")))
local learned = ""
for _ = 1, 100 do
  learned = kl:think("scout", { noise = 0.5 }, "s1").action
  if learned == "hide" then break end
  SLEEP(0.1)
end
out("think learned: " .. learned)
kl:reward("u1", 1)
kl:reward("u2", 0.5)
kl:reward("u3", 0)
kl:flush()
local total = 0
for _, v in ipairs(kl:report("raider").variants) do total = total + v.rewards end
out("rewards: " .. string.format("%d", total))
kl:character("BAKER", "a warm baker", { group = "village" })
kl:character("GUARD", "a strict guard", { group = "guards" })
out("knows before: " .. tostring(kl:knows("GUARD", "theft")))
kl:event("the player stole bread", nil, { by = "PLAYER", seen_by = { "BAKER" }, tag = "theft", impact = -0.8 })
local shared = {}
for _ = 1, 50 do
  shared = kl:meet("BAKER", "GUARD")
  if #shared > 0 then break end
  SLEEP(0.1)
end
local pairs_ = {}
for _, x in ipairs(shared) do pairs_[#pairs_ + 1] = x.from .. " -> " .. x.to end
out("meet: " .. table.concat(pairs_, ", "))
out("knows after: " .. tostring(kl:knows("GUARD", "theft")))
out("opinion: " .. tostring(kl:opinion("GUARD", "PLAYER")))
out("reputation: " .. tostring(kl:reputation("PLAYER", "village")))
kl:character("MIRA", "", { soul = { summary = "a gruff smith", mood = "wary" }, offline = "Hm.",
                          tools = { give = { item = "wood" } } })
out("soul chat: " .. kl:chat("MIRA", "Nice toy hammer.", {}, nil, "Ana"))
local soul
for _ = 1, 50 do
  soul = kl:soul("MIRA", "Ana")
  if soul and type(soul.card) == "table" and soul.bonds.Ana then break end
  SLEEP(0.1)
end
out("lore: " .. tostring(kl:lore({ "The village is Brookmere.", "The king died last winter." })))
out("soul: " .. soul.mood.word .. " " .. (soul.bonds.Ana.feeling < 0 and "dislikes" or "likes") .. " " .. soul.card.summary)
local wav = kl:speak("GUARD", "Halt.")
out("speak: " .. ((wav and wav:sub(1, 4) == "RIFF") and "wav" or "?"))
out("listen: " .. kl:listen(wav))
offline:mind("raider", "a cunning raider", raider)
out("offline think: " .. Kinloom.encode(offline:think("raider", { hp = 0.1, dist = 30, armed = true }, "u1")))
out("offline think charge: " .. Kinloom.encode(offline:think("raider", { hp = 0.9, dist = 10, armed = false }, "u3")))
out("offline knows: " .. tostring(offline:knows("GUARD", "theft")))
offline:character("MIRA", "", { soul = { summary = "a gruff smith" }, offline = "Hm." })
out("offline soul chat: " .. offline:chat("MIRA", "Nice toy hammer.", {}, nil, "Ana"))
out("offline speak: " .. (offline:speak("GUARD", "Halt.") == nil and "none" or "audio"))
local heard = offline:listen(wav)
out("offline listen: " .. (heard ~= "" and heard or "-"))

-- What came back: where it came from, actions with the reply, events described in words.
local challenge = { challenge = { when = "challenging someone to a battle", lines = { "{other}, fight!" } } }
kl:character("ANA", "a trainer", { lines = challenge })
local said = ""
for _ = 1, 50 do
  said = kl:say("ANA", "challenge", { other = "BEN" })
  if said ~= "" then break end
  SLEEP(0.1)
end
out("when say: " .. said)
kl:say("VEGA", "overtake", facts)
out("say source: " .. kl:source("VEGA"))
out("chat source: " .. kl:source("MIRA"))
for _, a in ipairs(kl:act("MIRA", {}, false)) do out("chat do: " .. a.tool .. " " .. Kinloom.encode(a.args)) end
offline:character("ANA", "a trainer", { lines = challenge })
out("offline when say: " .. offline:say("ANA", "challenge", { other = "BEN" }))
out("offline source: " .. offline:source("ANA"))

-- The game's tools, pictures, ready before play.
local png = Kinloom.base64_decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGP4z8AARAwQCgAf7gP9i18U1AAAAABJRU5ErkJggg==")
out("tools: " .. table.concat(kl:tools({ open_door = { door = "north" } }), ", "))
kl:character("KEEPER", "a gatekeeper", { tools = { "open_door" } })
SLEEP(0.1)
for _ = 1, 100 do
  local acts = kl:act("KEEPER", {})
  if #acts > 0 then
    for _, a in ipairs(acts) do out("tools act: " .. a.tool .. " " .. Kinloom.encode(a.args)) end
    break
  end
  SLEEP(0.05)
end
kl:character("LOOK", "a painter", { offline = "Blind." })
SLEEP(0.1)
out("chat image: " .. kl:chat("LOOK", "What is this?", {}, nil, "player", png))
out("create image: " .. Kinloom.encode(kl:create("race", { challenge = "Win clean", sky = "#ff7a45" }, { image = png })))
local ready = kl:prepare(10)
out("prepare: " .. (ready.ready and "ready" or "waiting") .. " " .. (ready.online and "online" or "offline"))
out("offline tools: " .. table.concat(offline:tools({ open_door = { door = "north" } }), ", "))
offline:character("LOOK", "a painter", { offline = "Blind." })
out("offline chat image: " .. offline:chat("LOOK", "What is this?", {}, nil, "player", png))
out("offline create image: " .. Kinloom.encode(offline:create("race", { challenge = "Win clean", sky = "#ff7a45" }, { image = png })))
ready = offline:prepare(1)
out("offline prepare: " .. (ready.ready and "ready" or "waiting") .. " " .. (ready.online and "online" or "offline"))
local t0 = CLOCK()
local gone = unreachable()
gone:character("THEO", "engineer", { offline = "Copy." })
local fast = gone:chat("THEO", "gap?") == "Copy." and gone:chat("THEO", "gap?") == "Copy." and gone:say("THEO", "x") == ""
local took = CLOCK() - t0
out("offline fast: " .. ((fast and took < 1.5) and "yes" or string.format("no (%.1f s)", took)))
-- v1: the player's choices, characters talking together, a snapshot, saves
local reply_choices = { "Ask about the sword", "Buy something", "Leave" }
out("suggest: " .. table.concat(kl:suggest("MIRA", reply_choices, "Ana"), " | "))
out("offline suggest: " .. table.concat(offline:suggest("MIRA", reply_choices, "Ana"), " | "))
local talk = {}
for _, x in ipairs(kl:converse("MIRA", "BAKER", "the smoke", 4)) do talk[#talk + 1] = x.who .. ": " .. x.text end
out("converse: " .. table.concat(talk, " | "))
out("offline converse: " .. #offline:converse("MIRA", "BAKER", "", 4))
local snap = kl:inspect()
out("inspect: MIRA " .. snap.characters.MIRA.mood.word .. " " .. snap.characters.MIRA.last_words)
local slot2 = kl:with_session("slot2")
slot2:load(kl:save())
out("load: MIRA " .. (slot2:opinion("MIRA", "Ana") < 0 and "dislikes" or "likes") .. " Ana")
if NATIVE then
  local passed, total, failures = Kinloom.vectors.run_file(os.getenv("KINLOOM_VECTORS"))
  for i = 1, math.min(#failures, 40) do
    local f = failures[i]
    io.stderr:write("vector " .. tostring(f.fn) .. " " .. Kinloom.encode(f.args) .. "\n  want " .. Kinloom.encode(f.want) ..
      "\n  got  " .. (type(f.got) == "string" and f.got or Kinloom.encode(f.got)) .. "\n")
  end
  out(string.format("vectors: %d/%d", passed, total))
  host:close()
end
