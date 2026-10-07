# The calls in each language, for the brief. Sections are read by `init.brief`; names and values are placeholders.

## python
# Any name: a character, a system ("WEATHER"), a group. The example is the shape of the answer AND the offline answer.
sky = kl.decide("WEATHER", {"season": "winter", "day": 12}, {"sky": ["sun", "snow"], "wind": [0.0, 1.0]})
#   -> {"sky": "snow", "wind": 0.7}: instant every frame, refreshed in the background
item = kl.create("an item found in a cave", {"name": "Glowcap", "value": [1, 50], "story": "Found under a cold stone."}, context={"depth": 3})
#   -> a dict like the example (~1-2 s); count=5 -> a list of 5; instant=True -> from a pool
kl.character("ROVER", "the player's dog", tools={"sit": {}, "fetch": {"item": "stick"}})   # or Python functions: they run
for tool, args in kl.act("ROVER", {"order": typed_text}):   # instant: validated calls since the last time
    run(tool, args)
kl.tools({"open_door": {"door": "north"}})   # the game's tools, once; characters name them: tools=["open_door"]
seen = kl.create("what the screen shows", {"danger": [0.0, 1.0]}, image=png_bytes)   # it looks: bytes, a path, base64
kl.character("VEGA", "a short, excited announcer", lines={"built": ["{who} built a {what}!"]}, events={"built": ["who", "what"]})
line = kl.say("VEGA", "built", {"who": "Ana", "what": "bridge"})   # instant, only your facts in it
reply = kl.chat("MIRA", typed_text, {"gold": 3}, speaker="Ana")   # a free answer in character, ~1 s (not per frame)
kl.steer("MIRA", "admit the sword")   # the game decides her next reply
for tool, args in reply.do: run(tool, args)   # with tools: what she decided in this reply
audio = kl.speak("MIRA", reply)          # her voice: audio.data (WAV), audio.path, or None
if audio: play(audio.path)               # None: no voice, the text is enough
said = kl.listen(wav_bytes)              # what the player said ("" if nothing)
kl.event("the player stole bread", by="PLAYER", seen_by=["BAKER"], tag="theft")   # only witnesses know
kl.meet("BAKER", "GUARD")        # they share it; then kl.knows("GUARD", "theft"), kl.opinion("GUARD", "PLAYER") -1..1
kl.mind("RAIDER", "a cautious raider", senses={"hp": [0.0, 1.0], "allies": [0, 20]}, actions={"flee": {}, "flank": {}},
        rules={"flee": ["hp low"], "flank": ["allies above 2"]})     # once
a = kl.think("RAIDER", {"hp": 0.3, "allies": 5}, who="raider-7")     # every frame, every unit, no model call: a["action"]
picks = kl.suggest("MIRA", ["Ask about the sword", "Leave"], speaker="Ana")   # choices to show, one per example
talk = kl.converse("MIRA", "BAKER", about="the smoke")   # they talk: [{"who", "text"}] ([] offline)
slot = kl.save(); kl.load(slot)       # the AI's state as one string, in the game's save file
seen_by_ai = kl.inspect()             # a debug overlay: moods, feelings, last words
# People talking to a character, ready-made: kinloom.talk.PygameTalkBox (pygame) or Talk (any engine); voice=True
# says replies sentence by sentence and records while Tab is held.

## gdscript
# Any name: a character, a system ("WEATHER"), a group. The example is the shape of the answer AND the offline answer.
var sky = Kinloom.decide("WEATHER", {"season": "winter", "day": 12}, {"sky": ["sun", "snow"], "wind": [0.0, 1.0]})
#   -> {"sky": "snow", "wind": 0.7}: instant every frame, refreshed in the background
var item = await Kinloom.create("an item found in a cave", {"name": "Glowcap", "value": [1, 50], "story": "Found under a cold stone."}, {"depth": 3})
#   -> one Dictionary like the example (~1-2 s); create(what, example, {}, 5) -> an Array of 5
Kinloom.character("ROVER", "the player's dog", {"tools": {"sit": {}, "fetch": {"item": "stick"}}})
for a in Kinloom.act("ROVER", {"order": typed_text}):        # instant: validated calls, a.tool and a.args
	run(a.tool, a.args)
Kinloom.tools({"open_door": {"door": "north"}})    # the game's tools, once: characters name them, {"tools": ["open_door"]}
var seen = await Kinloom.create("what the screen shows", {"danger": [0.0, 1.0]}, {}, 0, false, get_viewport().get_texture().get_image())
await Kinloom.prepare(10.0)                         # a loading screen: what Kinloom writes ahead is ready
Kinloom.character("VEGA", "a short, excited announcer", {"lines": {"built": ["{who} built a {what}!"]}, "events": {"built": ["who", "what"]}})
var line: String = await Kinloom.say("VEGA", "built", {"who": "Ana", "what": "bridge"})      # instant
var reply: String = await Kinloom.chat("MIRA", typed_text, {"gold": 3}, "Ana")                # free answer, ~1 s
Kinloom.steer("MIRA", "admit you sold the king's sword")   # the game decides her next reply (even a secret)
Kinloom.speak_aloud("MIRA", reply)          # her voice (or the system's); speak() gives the AudioStreamWAV
var said: String = await Kinloom.listen(wav_bytes)                                            # microphone -> text
Kinloom.event("the player stole bread", [], {"by": "PLAYER", "seen_by": ["BAKER"]})          # then knows / opinion / reputation
Kinloom.mind("RAIDER", "a cautious raider", {"senses": {"hp": [0.0, 1.0], "allies": [0, 20]},
	"actions": {"flee": {}, "flank": {}}, "rules": {"flee": ["hp low"], "flank": ["allies above 2"]}})   # once (or an AIMind node)
var t := Kinloom.think("RAIDER", {"hp": 0.3, "allies": 5}, "raider-7")    # every frame, no model call: t.action
var picks: Array = await Kinloom.suggest("MIRA", ["Ask about the sword", "Leave"], "Ana")   # choices for gamepads: one per example
for turn in await Kinloom.converse("MIRA", "BAKER", "the smoke"): print(turn.who, ": ", turn.text)   # they talk together
var slot: String = await Kinloom.save_state()      # the AI's whole state as one string in your save file; load_state(slot)
var seen_by_ai = await Kinloom.inspect()           # a debug overlay: moods, feelings, last words, waiting actions
# People talking to a character, ready-made: an AIDialogue node (character_name, soul, tools, voice; open()).

## csharp
// Any name: a character, a system ("WEATHER"), a group. The example is the shape of the answer AND the offline answer.
var sky = kl.Decide("WEATHER", new Dictionary<string, object> { ["season"] = "winter" },
    new Dictionary<string, object> { ["sky"] = new List<object> { "sun", "snow" }, ["wind"] = new List<object> { 0.0, 1.0 } });
//   -> instant every frame, refreshed in the background: sky["sky"], sky["wind"]
var item = await kl.Create("an item found in a cave", new Dictionary<string, object> { ["name"] = "Glowcap",
    ["value"] = new List<object> { 1, 50 } }, new Dictionary<string, object> { ["depth"] = 3 });   // ~1-2 s; count: 5 -> a list
kl.Character("ROVER", "the player's dog", new Dictionary<string, object> { ["tools"] = new Dictionary<string, object> {
    ["sit"] = new Dictionary<string, object>(), ["fetch"] = new Dictionary<string, object> { ["item"] = "stick" } } });
foreach (var a in kl.Act("ROVER", new Dictionary<string, object> { ["order"] = typedText })) Run(a.Tool, a.Args);  // instant
await kl.Tools(new Dictionary<string, object> { ["open_door"] = new Dictionary<string, object> { ["door"] = "north" } });
//   the game's tools, once: characters name them, ["tools"] = new List<object> { "open_door" }
var seen = await kl.Create("what the screen shows", new Dictionary<string, object> { ["danger"] = new List<object> { 0.0, 1.0 } },
    null, 0, false, pngBytes);                // image: PNG/JPEG bytes (Unity: texture.EncodeToPNG())
await kl.Prepare(10);                         // a loading screen: what Kinloom writes ahead is ready
string line = await kl.Say("VEGA", "built", new Dictionary<string, object> { ["who"] = "Ana" });   // instant (lines declared once)
string reply = await kl.Chat("MIRA", typedText, null, "Ana");                                        // free answer, ~1 s
await kl.Steer("MIRA", "admit you sold the king's sword");   // the game decides her next reply (even a secret)
byte[]? wav = await kl.Speak("MIRA", reply);    // WAV or null; KinloomClient.WavSamples(wav, ...) -> AudioClip
string said = await kl.Listen(wavBytes);        // microphone -> text (KinloomClient.Wav(samples, ch, hz) makes the WAV)
await kl.Event("the player stole bread", by: "PLAYER", seenBy: new[] { "BAKER" });                  // who knows it
kl.Mind("RAIDER", "a cautious raider", new Dictionary<string, object> { ["hp"] = new List<object> { 0.0, 1.0 } },
    new Dictionary<string, object> { ["flee"] = new Dictionary<string, object>(), ["hold"] = new Dictionary<string, object>() },
    new Dictionary<string, object> { ["flee"] = new List<object> { "hp low" } });                    // once: senses, actions, rules
var t = kl.Think("RAIDER", new Dictionary<string, object> { ["hp"] = 0.3 }, "raider-7");         // every frame, no model call: t.Action
var picks = await kl.Suggest("MIRA", new[] { "Ask about the sword", "Leave" }, "Ana");          // choices for gamepads: one per example
foreach (var turn in await kl.Converse("MIRA", "BAKER", "the smoke")) Show(turn["who"], turn["text"]);   // they talk together
string slot = await kl.Save(); await kl.Load(slot);   // the AI's whole state as one string in your save file
var seenByAi = await kl.Inspect();                    // a debug overlay: moods, feelings, last words, waiting actions
// People talking to a character in Unity, ready-made: the KinloomDialogue component (name, soul, reply choices, events).

## js
// Any name: a character, a system ("WEATHER"), a group. The example is the shape of the answer AND the offline answer.
const sky = kl.decide("WEATHER", { season: "winter", day: 12 }, { sky: ["sun", "snow"], wind: [0.0, 1.0] });
//   -> { sky: "snow", wind: 0.7 }: instant every frame, refreshed in the background
const item = await kl.create("an item found in a cave", { name: "Glowcap", value: [1, 50], story: "Found under a cold stone." }, { context: { depth: 3 } });
//   -> one object like the example (~1-2 s); { count: 5 } -> an array of 5; { instant: true } -> from a pool
kl.character("ROVER", "the player's dog", { tools: { sit: {}, fetch: { item: "stick" } } });
for (const a of kl.act("ROVER", { order: typedText })) run(a.tool, a.args);   // instant: validated calls
await kl.tools({ open_door: { door: "north" } });   // the game's tools, once: characters name them, { tools: ["open_door"] }
const seen = await kl.create("what the screen shows", { danger: [0.0, 1.0] }, { image: canvas.toDataURL() });
await kl.prepare(10);                                // a loading screen: what Kinloom writes ahead is ready
kl.character("VEGA", "a short, excited announcer", { lines: { built: ["{who} built a {what}!"] }, events: { built: ["who", "what"] } });
const line = await kl.say("VEGA", "built", { who: "Ana", what: "bridge" });   // instant
const reply = await kl.chat("MIRA", typedText, { gold: 3 }, "Ana");           // free answer, ~1 s (onPiece to stream)
await kl.steer("MIRA", "admit you sold the king's sword");    // the game decides her next reply (even a secret)
const voice = await kl.speak("MIRA", reply); if (voice) new Audio(voice.url).play();   // null: show the text only
const said = await kl.listen(recordedBlob);                                    // microphone (MediaRecorder) -> text
kl.event("the player stole bread", [], { by: "PLAYER", seenBy: ["BAKER"] });  // then knows / opinion / reputation
kl.mind("RAIDER", "a cautious raider", { senses: { hp: [0, 100], allies: [0, 20] }, actions: { flee: {}, flank: {} },
  rules: { flee: ["hp low"], flank: ["allies above 2"] } });                  // once: rules are the offline mind
const t = kl.think("RAIDER", { hp: 30, allies: 5 }, "raider-7");              // every frame, no model call: t.action
const picks = await kl.suggest("MIRA", ["Ask about the sword", "Leave"], "Ana");   // choices for gamepads: one per example
for (const turn of await kl.converse("MIRA", "BAKER", "the smoke")) show(turn.who, turn.text);   // they talk together
const slot = await kl.save(); await kl.load(slot);   // the AI's whole state as one string in your save file
const seenByAi = await kl.inspect();                  // a debug overlay: moods, feelings, last words, waiting actions
// People talking to a character, ready-made: talkBox(kl, "MIRA", { speaker: "Ana", voice: true }).open() from
// kinloom-talk.js (next to the client): replies said aloud, a hold-to-talk microphone button.

## lua
-- Any name: a character, a system ("WEATHER"), a group. The example is the shape of the answer AND the offline answer.
local sky = kl:decide("WEATHER", { season = "winter", day = 12 }, { sky = { "sun", "snow" }, wind = { 0, Kinloom.real(1) } })
--   -> instant table every frame, refreshed in the background
kl:create("an item found in a cave", { name = "Glowcap", value = { 1, 50 } }, { context = { depth = 3 } }, function(item) found = item end)
--   { count = 5 } -> a list of 5; the answer arrives in the callback (~1-2 s)
kl:character("ROVER", "the player's dog", { tools = { sit = {}, fetch = { item = "stick" } } })
for _, a in ipairs(kl:act("ROVER", { order = typed_text })) do run(a.tool, a.args) end   -- instant: validated calls
kl:tools({ open_door = { door = "north" } })   -- the game's tools, once: characters name them, tools = { "open_door" }
kl:create("what the screen shows", { danger = { 0, Kinloom.real(1) } }, { image = png_bytes }, function(seen) danger = seen end)
kl:prepare(10, function(ready) loading_done = ready.ready end)   -- a loading screen: what Kinloom writes ahead is ready
kl:say("VEGA", "built", { who = "Ana", what = "bridge" }, function(text) caption = text end)   -- lines declared once
kl:chat("MIRA", typed_text, { gold = 3 }, function(reply) dialogue = reply end, "Ana")      -- free answer, ~1 s
kl:steer("MIRA", "admit you sold the king's sword")   -- the game decides her next reply (even a secret)
kl:speak("MIRA", "Halt!", function(wav) if wav then play(wav) end end)   -- WAV bytes (a string), nil: text only
kl:listen(wav_bytes, nil, function(said) heard = said end)               -- microphone -> text
kl:event("the player stole bread", nil, { by = "PLAYER", seen_by = { "BAKER" } })           -- who knows it
kl:mind("RAIDER", "a cautious raider", { senses = { hp = { 0, 100 }, allies = { 0, 20 } }, actions = { flee = {}, flank = {} },
  order = { "flee", "flank" }, rules = { flee = { "hp low" }, flank = { "allies above 2" } } })   -- once
local t = kl:think("RAIDER", { hp = 30, allies = 5 }, "raider-7")               -- every frame, no model call: t.action
kl:suggest("MIRA", { "Ask about the sword", "Leave" }, "Ana", nil, function(picks) choices = picks end)   -- one per example
kl:converse("MIRA", "BAKER", "the smoke", 4, function(lines) overheard = lines end)   -- they talk together: { {who, text}, ... }
kl:save(function(slot) save_file.ai = slot end)   -- the AI's whole state as one string; kl:load(slot) puts it back
kl:inspect(function(seen) debug_view = seen end)  -- a debug overlay: moods, feelings, last words, waiting actions

## rust
// Any name: a character, a system ("WEATHER"), a group. The example is the shape of the answer AND the offline answer.
let sky = kl.decide("WEATHER", obj! { "season" => "winter" }, obj! { "sky" => vec!["sun", "snow"], "wind" => vec![0.0, 1.0] });
//   -> instant every frame, refreshed in the background
let item = kl.create("an item found in a cave", obj! { "name" => "Glowcap", "value" => vec![1, 50] }, obj! { "depth" => 3 }, 0, false);
//   blocking ~1-2 s (create_async off the frame); count 5 -> a list of 5
kl.character("ROVER", "the player's dog", obj! { "tools" => obj! { "sit" => obj! {}, "fetch" => obj! { "item" => "stick" } } });
for a in kl.act("ROVER", obj! { "order" => typed_text.as_str() }) { run(&a.tool, &a.args); }   // instant: validated calls
kl.tools(obj! { "open_door" => obj! { "door" => "north" } });   // the game's tools, once: characters name them
let seen = kl.create_image("what the screen shows", obj! { "danger" => vec![0.0, 1.0] }, obj! {}, 0, false, &png_bytes);
kl.prepare(10.0);                                                // a loading screen: what Kinloom writes ahead is ready
let line = kl.say("VEGA", "built", obj! { "who" => "Ana" });                 // fast (lines declared once)
let reply = kl.chat_as("MIRA", &typed_text, obj! { "gold" => 3 }, "Ana");     // free answer, ~1 s: on a thread
kl.steer("MIRA", "admit you sold the king's sword");   // the game decides her next reply (even a secret)
let wav = kl.speak("MIRA", &reply);           // WAV bytes; empty: show the text only
let said = kl.listen(&wav_bytes, "");         // microphone -> text
kl.event_with("the player stole bread", obj! { "by" => "PLAYER", "seen_by" => vec!["BAKER"] });
kl.mind("RAIDER", "a cautious raider", obj! { "hp" => vec![0.0, 1.0] }, obj! { "flee" => obj! {}, "hold" => obj! {} },
        obj! { "flee" => vec!["hp low"] }, 3, 30.0);                                   // once: senses, actions, rules
let t = kl.think("RAIDER", &obj! { "hp" => 0.3 }, "raider-7");                        // every frame, no model call: t.action
let picks = kl.suggest("MIRA", &["Ask about the sword", "Leave"], "Ana", Json::Null);   // choices for gamepads: one per example
for turn in kl.converse("MIRA", "BAKER", "the smoke", 4) { show(turn.get("who").as_str(), turn.get("text").as_str()); }
let slot = kl.save(); kl.load(&slot);   // the AI's whole state as one string in your save file
let seen_by_ai = kl.inspect();          // a debug overlay (Option<Json>): moods, feelings, last words, waiting actions

## java
// Any name: a character, a system ("WEATHER"), a group. The example is the shape of the answer AND the offline answer.
Map<String, Object> sky = kl.decide("WEATHER", map("season", "winter"), map("sky", list("sun", "snow"), "wind", list(0.0, 1.0)));
//   -> instant every frame, refreshed in the background
kl.createAsync("an item found in a cave", map("name", "Glowcap", "value", list(1, 50)), map("depth", 3), 0)
  .thenAccept(item -> found = (Map<String, Object>) item);                    // ~1-2 s; count 5 -> a list of 5
kl.character("ROVER", "the player's dog", map("tools", map("sit", map(), "fetch", map("item", "stick"))));
for (Kinloom.Action a : kl.act("ROVER", map("order", typedText))) run(a.tool, a.args);   // instant: validated calls
kl.tools(map("open_door", map("door", "north")));   // the game's tools, once: characters name them, "tools", list("open_door")
Object seen = kl.create("what the screen shows", map("danger", list(0.0, 1.0)), null, 0, false, pngBytes);   // image bytes
kl.prepare(10);                                      // a loading screen: what Kinloom writes ahead is ready
String line = kl.say("VEGA", "built", map("who", "Ana"));                     // fast (lines declared once)
String reply = kl.chat("MIRA", typedText, map("gold", 3), "Ana");             // free answer, ~1 s: chatAsync off the game thread
kl.steer("MIRA", "admit you sold the king's sword");   // the game decides her next reply (even a secret)
byte[] wav = kl.speak("MIRA", reply);           // WAV bytes; null: show the text only (speakAsync off the game thread)
String said = kl.listen(wavBytes);              // microphone -> text
kl.event("the player stole bread", map("by", "PLAYER", "seen_by", list("BAKER")));
kl.mind("RAIDER", "a cautious raider", map("hp", list(0.0, 1.0)), map("flee", map(), "hold", map()),
        map("flee", list("hp low")), 3, 30);                                           // once: senses, actions, rules
Kinloom.Thought t = kl.think("RAIDER", map("hp", 0.3), "raider-7");                   // every frame, no model call: t.action
List<String> picks = kl.suggest("MIRA", Arrays.asList("Ask about the sword", "Leave"), "Ana");   // choices: one per example
for (Map<String, Object> turn : kl.converse("MIRA", "BAKER", "the smoke")) show(turn.get("who"), turn.get("text"));
String slot = kl.save(); kl.load(slot);   // the AI's whole state as one string in your save file
Map<String, Object> seenByAi = kl.inspect();   // a debug overlay: moods, feelings, last words, waiting actions

## cpp
// Any name: a character, a system ("WEATHER"), a group. The example is the shape of the answer AND the offline answer.
kinloom::Json sky = kl.decide("WEATHER", obj({{"season", "winter"}}), obj({{"sky", arr({"sun", "snow"})}, {"wind", arr({0.0, 1.0})}}));
//   -> instant every frame, refreshed in the background
auto item = kl.create_async("an item found in a cave", obj({{"name", "Glowcap"}, {"value", arr({1, 50})}}), obj({{"depth", 3}}));
//   std::future (~1-2 s); count 5 -> a list of 5
kl.character("ROVER", "the player's dog", obj({{"tools", obj({{"sit", obj({})}, {"fetch", obj({{"item", "stick"}})}})}}));
for (auto& a : kl.act("ROVER", obj({{"order", typed_text}}))) run(a.tool, a.args);   // instant: validated calls
kl.tools(obj({{"open_door", obj({{"door", "north"}})}}));   // the game's tools, once: characters name them
auto seen = kl.create("what the screen shows", obj({{"danger", arr({0.0, 1.0})}}), obj({}), 0, false, png_bytes);
kl.prepare(10);                                              // a loading screen: what Kinloom writes ahead is ready
std::string line = kl.say("VEGA", "built", obj({{"who", "Ana"}}));            // fast (lines declared once)
std::string reply = kl.chat("MIRA", typed_text, obj({{"gold", 3}}), "Ana");   // free answer, ~1 s: chat_async off the loop
kl.steer("MIRA", "admit you sold the king's sword");   // the game decides her next reply (even a secret)
std::vector<unsigned char> wav = kl.speak("MIRA", reply);   // WAV bytes; empty: show the text only
std::string said = kl.listen(wav_bytes);                     // microphone -> text
kl.event_with("the player stole bread", obj({{"by", "PLAYER"}, {"seen_by", arr({"BAKER"})}}));
kl.mind("RAIDER", "a cautious raider", obj({{"hp", arr({0.0, 1.0})}}), obj({{"flee", obj({})}, {"hold", obj({})}}),
        obj({{"flee", arr({"hp low"})}}));                                              // once: senses, actions, rules
kinloom::Thought t = kl.think("RAIDER", obj({{"hp", 0.3}}), "raider-7");              // every frame, no model call: t.action
std::vector<std::string> picks = kl.suggest("MIRA", {"Ask about the sword", "Leave"}, "Ana");   // one per example
for (auto& turn : kl.converse("MIRA", "BAKER", "the smoke")) show(turn["who"].str(), turn["text"].str());   // they talk together
std::string slot = kl.save(); kl.load(slot);   // the AI's whole state as one string in your save file
kinloom::Json seen_by_ai = kl.inspect();       // a debug overlay: moods, feelings, last words, waiting actions

## http
Any name: a character, a system ("WEATHER"), a group. The example is the shape of the answer AND the offline answer.
POST /v1/decide {"name": "WEATHER", "situation": {"season": "winter"}, "choices": {"sky": ["sun", "snow"], "wind": [0.0, 1.0]}}
     -> {"decision": {"sky": "snow", "wind": 0.7}}   instant; call it in the background and keep the last answer
POST /v1/create {"what": "an item found in a cave", "example": {"name": "Glowcap", "value": [1, 50]}, "context": {"depth": 3}, "count": 0}
POST /v1/character {"name": "ROVER", "personality": "the player's dog", "tools": {"sit": {}, "fetch": {"item": "stick"}}}
POST /v1/act    {"name": "ROVER", "situation": {"order": "<typed text>"}}  -> {"actions": [{"tool", "args"}]}
POST /v1/tools  {"tools": {"open_door": {"door": "north"}}}   the game's tools, once; a character names them: "tools": ["open_door"]
POST /v1/create {..., "image": "<base64 PNG/JPEG>"}   (also /v1/chat): the model looks at it   POST /v1/prepare {"timeout": 10}
POST /v1/say    {"name": "VEGA", "event": "built", "facts": {"who": "Ana"}}   POST /v1/chat {"name", "message", "speaker", "facts"}
POST /v1/steer  {"name": "MIRA", "text": "admit you sold the king's sword"}   the game decides her next reply; "" takes it back
POST /v1/speak  {"name": "MIRA", "text": "Halt!"} -> {"audio": "<base64 WAV>" or ""}   POST /v1/listen {"audio": "<base64>"} -> {"text"}
POST /v1/event  {"text": "the player stole bread", "by": "PLAYER", "seen_by": ["BAKER"]}   then /v1/knows, /v1/opinion
Units every frame with no model call: POST /v1/mind once, then run the mind in the game, or POST /v1/think (see KINLOOM.md).
POST /v1/suggest {"name": "MIRA", "examples": ["Ask about the sword", "Leave"], "speaker": "Ana"} -> {"replies": [...]} (one per example)
POST /v1/converse {"a": "MIRA", "b": "BAKER", "about": "the smoke"} -> {"lines": [{"who", "text"}]}   POST /v1/inspect {} -> a snapshot
POST /v1/save {} -> {"data": "<string for your save file>"}   POST /v1/load {"data": "..."}   (per session: X-Kinloom-Session)
