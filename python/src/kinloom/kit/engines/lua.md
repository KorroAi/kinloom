language: Lua (LÖVE, Defold, Solar2D, any Lua 5.1-5.4 / LuaJIT)
Setup: `kinloom init` copied `{client_path}`: `local Kinloom = require("{require_path}")`. While playing, run
`kinloom serve`. Or native, no server (the key from the environment): `Kinloom.new({ provider = "auto" })`. Call `kl:update()` every frame (LÖVE: in `love.update`): it delivers answers and runs background work. Defold / other
engines with their own HTTP: pass `transport` to `Kinloom.new` (see the top of the file). Answers arrive in callbacks.
---
```lua
local Kinloom = require("{require_path}")
local kl = Kinloom.new()  -- Kinloom.new({ session = "player-2" }) per player

-- Characters with a soul: one sentence, a person the player talks to (mood, feelings, memories, secrets, actions)
kl:character("MIRA", "", { soul = "a gruff blacksmith who secretly sold the king's sword", offline = "Busy.",
                           tools = { give = { item = "sword" } } })
kl:chat("MIRA", player_text, {}, function(reply) dialogue = reply end, "Ana")  -- "" = she speaks first
for _, a in ipairs(kl:act("MIRA", {}, false)) do if a.tool == "give" then add_item(a.args.item) end end
kl:soul("MIRA", "Ana", function(soul) mood = soul and soul.mood.word end)  -- card, mood, bonds, memories

kl:character("VEGA", "over-excited race commentator, max 10 words", {
  lines = { overtake = { "{who} passes {whom}!" }, ["*"] = { "What a race!" } },  -- offline lines
  events = { overtake = { "who", "whom", "gap" } },  -- prepare these lines now
})
kl:character("THEO", "calm race engineer", { offline = "Copy that." })
kl:character("RAX", "brutal rival", { tools = { ram = { force = { 0, Kinloom.real(1) } } } })

function love.update(dt)
  kl:update()  -- delivers answers
  local plan = kl:decide("RAX", { gap = gap, lap = lap },  -- instant table, refreshed in background
    { strategy = { "attack", "block" }, aggression = { 0, Kinloom.real(1) } })
  rax.aggression = plan.aggression
  for _, a in ipairs(kl:act("RAX", { gap = gap })) do  -- instant, validated tool calls
    if a.tool == "ram" then rax:ram(a.args.force) end
  end
end

kl:say("VEGA", "overtake", { who = "BLAZE", whom = "NOVA", gap = 0.4 }, function(text) caption = text end)
kl:chat("THEO", player_text, { gap_to_leader = 1.8 }, function(reply) radio = reply end)  -- ~1 s
kl:create("a short race challenge", { title = "Win clean", laps = { 2, 5 }, sky = "#ff7a45" }, {}, function(c) challenge = c end)
kl:event("BLAZE crashed on lap 3", { "BLAZE", "VEGA" })  -- they remember it
kl:state({ lap = 3, leader = "NOVA" })  -- facts every call sees

-- Minds: utility AI for crowds, run locally every frame (never a model call); rules are the offline mind
kl:mind("raider", "a cunning raider", {
  senses = { hp = { 0, Kinloom.real(1) }, dist = { 0, 40 }, armed = true },
  actions = { charge = { speed = { 1, Kinloom.real(3) } }, shoot = {}, retreat = {} },
  order = { "shoot", "charge", "retreat" },  -- Lua tables have no order: ties go to the first
  rules = { retreat = { "hp low" }, shoot = { "armed", "dist below 20" } },
})
local t = kl:think("raider", { hp = e.hp, dist = e.dist, armed = e.ammo > 0 }, e.id)  -- t.action, t.args
kl:reward(e.id, dealt - taken, died_or_won)  -- minds learn

-- World
kl:event("the player stole bread", nil, { by = "PLAYER", seen_by = { "BAKER" }, tag = "theft", impact = -0.6 })
kl:meet("BAKER", "GUARD", function(shared) end)
kl:knows("GUARD", "theft", function(yes) if yes then guard_alert() end end)
```
LuaJIT has no integers: `{0, 10}` is a whole-number range; use `Kinloom.real(10)` for decimals. A `nil` value drops
its key: `Kinloom.null` is JSON's null. An empty `{}` is an object: `Kinloom.array()` is an empty list.
