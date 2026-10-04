extends Node
## Kinloom for Godot 4 (pure GDScript, no .NET). This autoload is "Kinloom".
##
##   Kinloom.character("VEGA", "an over-excited race commentator")
##   $Label.text = await Kinloom.say("VEGA", "overtake", {"who": "BLAZE", "whom": "NOVA"})
##   var plan = Kinloom.decide("BLAZE", {"gap": 0.4}, {"strategy": ["attack", "block"], "aggression": [0.0, 1.0]})
##   Kinloom.mind("raider", "a cunning raider", {"senses": {"hp": [0.0, 1.0], "dist": [0.0, 40.0]},
##       "actions": {"charge": {}, "retreat": {}}, "rules": {"retreat": ["hp low"], "charge": ["dist below 15"]}})
##   var a = Kinloom.think("raider", {"hp": 0.3, "dist": 12.0}, "raider-17")   # local, microseconds
##   Kinloom.reward("raider-17", 1.0)                                           # rewarded minds learn
##
## Every call has an offline answer (your lines, your examples, the first option / middle of a range),
## so the game never breaks: no server, no key, no network, a slow model.
##
## Three modes, the same calls:
##   relay (default): a `kinloom serve` at `url` calls the model (the key stays on your server: ship this way);
##   native: Kinloom.direct("https://openrouter.ai/api/v1", key, "deepseek/deepseek-v4.1-flash") or Kinloom.native({...})
##     calls the model from the game itself, no Python process (a key in a client build can be read by players);
##   offline: Kinloom.offline(): your lines, examples and offline replies answer.

signal said(character: String, text: String)
signal acted(character: String, tool: String, args: Dictionary)

const Brain = preload("native/brain.gd")
const Http = preload("native/http.gd")
const Py = preload("native/py.gd")

## Where `kinloom serve` runs. Project setting "kinloom/url" or env KINLOOM_URL override it.
var _voice_queue: Array = []
var _voice_busy := false
var _voice_player: AudioStreamPlayer = null
var url := "http://127.0.0.1:7717"
## For an online server started with --token (env KINLOOM_SERVER_TOKEN).
var token := ""
## One session per player or match (separate memory).
var session := "default"
## Seconds a chat or create may take before the offline answer is used.
var timeout := 12.0
## Start `kinloom serve` automatically when it is not running: a `kinloom bundle` folder (kinloom-server/) next to the
## game or in the project (any build), else an installed `kinloom` (editor and debug builds).
var autostart := true

var _chars := {}
var _decisions := {}
var _actions := {}
var _sources := {}
var _down_until := 0.0
var _up_until := 0.0              # the server at _up_url answered lately: no need to check it is there
var _up_url := ""
var _failures := 0                # connections refused in a row (the offline time grows: 2, 4, 8, 10 s)
var _tried_start := false
var _placeholder := RegEx.new()
var _minds := {}
var _units := {}
var _rewards: Array = []
var _reward_at := 0.0
var _flushing := false
var _tools = null                 # the game's tools, sent again after a restart
var _brain = null                 # the native brain (native and offline modes); null in relay mode


func _init() -> void:
	_placeholder.compile("\\{([A-Za-z_][A-Za-z0-9_]*)\\}")


func _ready() -> void:
	url = str(ProjectSettings.get_setting("kinloom/url", url))
	if OS.get_environment("KINLOOM_URL") != "":
		url = OS.get_environment("KINLOOM_URL")
	if OS.get_environment("KINLOOM_SERVER_TOKEN") != "":
		token = OS.get_environment("KINLOOM_SERVER_TOKEN")


func _exit_tree() -> void:
	if _brain != null:
		_brain.close()


# ---------------- modes ----------------

## Native mode: the game calls the model itself (no `kinloom serve`). options: provider ({"url", "key", "model"},
## {"kind": "anthropic", "key", "model"}, a list of them tried in order, "auto" = the environment's keys, null =
## offline), voice ({"url", "key", "speak_model", "listen_model"}, "auto"), config (a kinloom.json path or a
## Dictionary: characters, lore, tools, banned_words, max_cost_per_hour...), language, calls_per_minute, prices
## ({"input", "output", "cached_input"} in $ per million tokens, with their source), content_filter (Callable text ->
## bool), memory (default "user://kinloom-memory.json"; "" keeps nothing), call_timeout.
## Characters, tools and minds already declared are declared again in the new brain.
func native(options := {}) -> void:
	Http.stopping = false
	var o: Dictionary = options.duplicate()
	if not o.has("memory"):
		o["memory"] = "user://kinloom-memory.json"
	if not o.has("call_timeout"):
		o["call_timeout"] = timeout
	_brain = Brain.new(o)
	if _tools != null:
		await _post("tools", {"tools": _tools}, 5.0)
	for name in _chars:
		_fire("character", _chars[name])
	for name in _minds:
		_declare_mind(_minds[name])


## Native mode with one model: any chat-completions endpoint (OpenAI, OpenRouter, DeepSeek, Groq, Gemini, Mistral,
## Ollama, LM Studio...) or Claude (an https://api.anthropic.com URL). options: as native().
func direct(model_url: String, key: String, model: String, options := {}) -> void:
	var o: Dictionary = options.duplicate()
	o["provider"] = {"url": model_url, "key": key, "model": model}
	native(o)


## Offline mode: no model, ever. options: as native() (memory, config, language...).
func offline(options := {}) -> void:
	var o: Dictionary = options.duplicate()
	o["provider"] = null
	native(o)


## True when a model answers: native with a provider, or a relay that answered lately.
func online() -> bool:
	if _brain != null:
		return _brain.online()
	return _now() >= _down_until


## Calls, failures, tokens, offline answers, cost (with prices), average latency (native; {} in relay mode).
func stats() -> Dictionary:
	return _brain.stats() if _brain != null else {}


## What Kinloom did lately: calls, lines, replies, refusals, "empty" answers (native; [] in relay mode).
func journal(n := 100) -> Array:
	return _brain.journal(n) if _brain != null else []


## listener(entry) for everything Kinloom does (native). Returns the listener, for off().
func on(listener: Callable) -> Callable:
	if _brain != null:
		_brain.listeners.append(listener)
	return listener


func off(listener: Callable) -> void:
	if _brain != null:
		_brain.listeners.erase(listener)


## Saves memory now (native). Also done when the node leaves the tree.
func close() -> void:
	if _brain != null:
		_brain.close()


## Before quitting the game (native mode): closes the model requests still open, waits for them (at most `wait`
## seconds) and saves memory. Godot crashes on exit when an HTTP connection is freed during shutdown, so quit after:
##   await Kinloom.shutdown()
##   get_tree().quit()
func shutdown(wait := 2.0) -> void:
	Http.stopping = true
	var end := _now() + wait
	while Http.open > 0 and _now() < end:
		await get_tree().process_frame
	close()


# ---------------- the verbs ----------------

## Declares a character. options: lines ({"event": ["..."], "*": [...]} offline lines, may use {fact} placeholders,
## or {"event": {"when": "what is happening, in words", "lines": [...]}}), offline (offline chat reply), events
## (["overtake"] or {"overtake": ["who", "whom"]} to prepare lines at once), tools ({"boost": {"seconds": [0.5, 2.0]}},
## names of the game's tools ["open_door"], or "all"),
## max_words, max_chars (a text box's size: the model's text never goes past it), every (seconds between fresh
## decisions), language ("auto": answer in the speaker's language), soul, trust, invent, voice, group, warmth (their
## feeling for anyone before any talk, -1..1), warm_up (the most one conversation can win, 0.3), secret_trust (the
## feeling above which a secret of their card may be shared, 0.6).
func character(name: String, personality: String, options := {}) -> void:
	var d: Dictionary = options.duplicate(true)
	d["name"] = name
	d["personality"] = personality
	_chars[name] = d
	_fire("character", d)


## A line in character with the real facts filled in. Instant when prepared lines exist. fresh: a line the model
## writes now (slower); max_chars: the size of the box it goes in this time.
func say(name: String, event: String, facts := {}, fresh := false, max_chars := 0) -> String:
	var body := {"name": name, "event": event, "facts": facts}
	if fresh:
		body["fresh"] = true
	if max_chars > 0:
		body["max_chars"] = max_chars
	var r = await _post("say", body, timeout if fresh else 2.0)
	var text := ""
	_set_source(name, r)
	if r == null:
		text = _offline_line(name, event, facts)
	else:
		_redeclare(name, r)
		text = str(r.get("text", ""))
	if text != "":
		said.emit(name, text)
	return text


## Where name's last line or reply came from: "model" (written now), "prepared" (written earlier by the model),
## "offline" (your own lines and replies), or "" before the first one.
func source(name: String) -> String:
	return str(_sources.get(name, ""))


func _set_source(name: String, r: Variant) -> void:
	_sources[name] = "offline" if r == null else str(r.get("source", "model"))


## A conversation reply in character: facts, memory, mood and feelings for the speaker shape it (~1 s).
## message "": the speaker came up to the character, who speaks first. What they decide while talking comes out of
## act(name, {}, false) at once. image: a picture with the message (an Image, e.g.
## get_viewport().get_texture().get_image(), PNG/JPEG bytes, or base64), for a model that sees. on_piece: called with
## each piece of the reply as it is written (native mode streams; relay mode gives the whole reply once).
func chat(name: String, message: String, facts := {}, speaker := "player", image: Variant = null, on_piece := Callable()) -> String:
	var body := {"name": name, "message": message, "facts": facts, "speaker": speaker, "do": true}
	var picture := _image_b64(image)
	if picture != "":
		body["image"] = picture
	var r = null
	if _brain != null and on_piece.is_valid():
		var got: Array = await _brain.chat_stream(session, _plain(body), on_piece)
		r = got[1] if got[0] == 200 else null
		if got[0] != 200:
			push_warning("[kinloom] chat: " + str(got[1].get("error", "")))
	else:
		r = await _post("chat", body, timeout)
		if r != null and on_piece.is_valid() and str(r.get("text", "")) != "":
			on_piece.call(str(r["text"]))
	_set_source(name, r)
	if r == null:
		var o = _chars.get(name, {}).get("offline", "")
		if o is Array:                                  # several offline replies: one of them
			return str(o.pick_random()) if o.size() > 0 else ""
		return str(o)
	_redeclare(name, r)
	var decided = r.get("do", [])
	if decided is Array and decided.size() > 0:
		_pending(name).ready.append_array(decided)
	return str(r.get("text", ""))


func _pending(name: String) -> Dictionary:
	if not _actions.has(name):
		_actions[name] = {"ready": [], "pending": false, "at": -1.0}
	return _actions[name]


## Instant: the latest decision shaped like `choices` (the model refreshes it in the background). choices: an object
## of examples ({"strategy": ["attack", "block"], "aggression": [0.0, 1.0]}) gives an object; a list of options gives
## one of them.
func decide(name: String, situation: Dictionary, choices: Variant) -> Variant:
	var key := name + "|" + JSON.stringify(choices)
	if not _decisions.has(key):
		_decisions[key] = {"value": default_of(choices), "pending": false, "at": -1.0}
	var d: Dictionary = _decisions[key]
	var now := Time.get_ticks_msec() / 1000.0
	if not d.pending and now - d.at >= 0.25:
		d.pending = true
		d.at = now
		_refresh_decision(d, name, situation, choices)
	return d.value


## Who the character is and feels: card, mood {word, level}, bonds {speaker: {talks, feeling}}, memories,
## conversation (with speaker). null when the server is not running.
## World facts every character takes as true and never contradicts. Returns how many were kept (0 offline).
func lore(lines: Array) -> int:
	var r = await _post("lore", {"lines": lines}, 3.0)
	return int(r.get("lines", 0)) if r != null else 0


func soul(name: String, speaker := "player") -> Variant:
	return await _post("soul", {"name": name, "speaker": speaker}, 3.0)


## What the player could say now to name, for games without a keyboard: one reply per example, in its order, each
## keeping that example's intent, written for this moment. The examples are the offline answer.
func suggest(name: String, examples: Array, speaker := "player", facts := {}) -> Array:
	var r = await _post("suggest", {"name": name, "examples": examples, "speaker": speaker, "facts": facts}, timeout)
	if r is Dictionary and r.get("replies") is Array:
		var out := []
		for x in r.replies:
			out.append(Py.text_of(x))
		return out
	return examples.duplicate()


## What the game decides happens in name's next reply ("admit you were in the office at 12:30"): the model says it in
## the character's voice, even a secret of their card. Used by the next chat only; "" takes it back.
func steer(name: String, text: String) -> void:
	await _post("steer", {"name": name, "text": text}, 3.0)


## A short exchange between two characters (one model call), remembered by both: [{"who", "text"}] (empty offline).
func converse(a: String, b: String, about := "", turns := 4) -> Array:
	var r = await _post("converse", {"a": a, "b": b, "about": about, "turns": turns}, timeout)
	return r.lines if r is Dictionary and r.get("lines") is Array else []


## A snapshot for a debug overlay: characters (mood, feelings, last words, memories, waiting actions), minds; null when a
## relay cannot be reached.
func inspect() -> Variant:
	return await _post("inspect", {}, 3.0)


## Everything Kinloom knows about this session as one text for the game's own save slot ("" when a relay cannot be reached).
func save_state() -> String:
	var r = await _post("save", {}, 5.0)
	return str(r.data) if r is Dictionary and typeof(r.get("data")) == TYPE_STRING else ""


## Puts back what save_state() gave (this session's state is replaced).
func load_state(data: String) -> bool:
	if data == "":
		return false
	var r = await _post("load", {"data": data}, 10.0)
	return r is Dictionary and r.get("ok") == true


## Instant: the tool calls the character chose since the last call (on its own, or while talking), as
## [{"tool": ..., "args": {...}}]. think false: only what it decided while talking (no model call of its own).
func act(name: String, situation := {}, think := true) -> Array:
	var a: Dictionary = _pending(name)
	var ready: Array = a.ready
	a.ready = []
	var now := Time.get_ticks_msec() / 1000.0
	if not a.pending and now - a.at >= 0.25:
		a.pending = true
		a.at = now
		_refresh_actions(a, name, situation, think)
	for action in ready:
		acted.emit(name, str(action.get("tool", "")), action.get("args", {}))
	return ready


## Content shaped like the example (which is also the offline answer). count > 0 returns a list; instant = from a ready
## pool; image: a picture the model looks at (an Image, PNG/JPEG bytes, or base64).
func create(what: String, example: Variant, context := {}, count := 0, instant := false, image: Variant = null) -> Variant:
	if count > 0 and example is Array and example.size() == 1:
		example = example[0]            # [item] with count: count items like it
	var body := {"what": what, "example": example, "context": context, "instant": instant}
	var picture := _image_b64(image)
	if picture != "":
		body["image"] = picture
	if count > 0:
		body["count"] = count
	var r = await _post("create", body, 2.0 if instant else timeout)
	if r == null or not r.has("value"):
		var fallback = default_of(example)
		if count > 0:
			var many := []
			for i in count:
				many.append(fallback)
			return many
		return fallback
	return r["value"]


## What the game can do, declared once: {"open_door": {"door": "north"}}. Characters use them by name (options
## "tools": ["open_door"], or "all"); act() returns the calls. Returns the names.
func tools(game_tools: Dictionary) -> Array:
	_tools = game_tools
	var r = await _post("tools", {"tools": game_tools}, 5.0)
	if r != null and r.get("tools") is Array:
		return r["tools"]
	var names := game_tools.keys()
	names.sort()
	return names


## For a loading screen: waits (up to wait seconds) until what Kinloom writes ahead is ready (soul cards, first
## greetings, line banks): {"ready", "waiting", "online"}. Offline: ready at once.
func prepare(wait := 10.0) -> Dictionary:
	var r = await _post("prepare", {"timeout": wait}, wait + 5.0)
	if r != null and r.get("ready") is bool:
		return r
	return {"ready": true, "waiting": 0, "online": false}


## A picture as base64 for the server: an Image (sent as PNG), bytes (PNG, JPEG, GIF, WebP) or base64 text.
static func _image_b64(image: Variant) -> String:
	if image == null:
		return ""
	if image is Image:
		return Marshalls.raw_to_base64(image.save_png_to_buffer())
	if image is PackedByteArray:
		return Marshalls.raw_to_base64(image) if image.size() > 0 else ""
	return str(image)


## text said aloud in name's voice ("" name: a narrator voice), as WAV bytes; empty when no voice can speak.
func speak_wav(name: String, text: String) -> PackedByteArray:
	var r = await _post("speak", {"name": name if name != "" else null, "text": text}, max(timeout, 15.0))
	if r == null or str(r.get("audio", "")) == "":
		return PackedByteArray()
	return Marshalls.base64_to_raw(str(r["audio"]))


## text said aloud in name's voice: an AudioStreamWAV for an AudioStreamPlayer, or null when no voice can speak
## (show the text; speak_aloud() then uses the operating system's voice).
func speak(name: String, text: String) -> AudioStreamWAV:
	var wav := await speak_wav(name, text)
	return AudioStreamWAV.load_from_buffer(wav) if wav.size() > 44 else null


## Says text now in name's voice, after what is already being said: the voice provider's audio, else the operating
## system's voice (Project Settings > Audio > General > Text to Speech), else nothing.
func speak_aloud(name: String, text: String) -> void:
	_voice_queue.append([name, text])
	if _voice_busy:
		return
	_voice_busy = true
	while not _voice_queue.is_empty():
		var next: Array = _voice_queue.pop_front()
		var stream := await speak(next[0], next[1])
		if stream != null:
			if _voice_player == null:
				_voice_player = AudioStreamPlayer.new()
				add_child(_voice_player)
			_voice_player.stream = stream
			_voice_player.play()
			await _voice_player.finished
		elif ProjectSettings.get_setting("audio/general/text_to_speech", false):
			var voices := DisplayServer.tts_get_voices()
			if not voices.is_empty():
				DisplayServer.tts_speak(next[1], voices[0]["id"])
	_voice_busy = false


## Stops speak_aloud: the line being said and the ones waiting.
func stop_speaking() -> void:
	_voice_queue.clear()
	if _voice_player != null:
		_voice_player.stop()
	if ProjectSettings.get_setting("audio/general/text_to_speech", false):
		DisplayServer.tts_stop()


## What someone said in a recording (WAV bytes, e.g. from an AudioEffectRecord: see AIDialogue): the text, "" when
## nothing was understood (keep the keyboard).
func listen(audio: PackedByteArray, language := "") -> String:
	if audio.is_empty():
		return ""
	var body := {"audio": Marshalls.raw_to_base64(audio)}
	if language != "":
		body["language"] = language
	var r = await _post("listen", body, max(timeout, 20.0))
	return str(r.get("text", "")) if r != null else ""


## Something happened; the characters named in `about` (or in the text) remember it. options: by (who did it),
## seen_by (only these witnesses know), tag (for knows), impact (-1..1: how it changes the witnesses' opinion of by).
func event(text: String, about := [], options := {}) -> void:
	var body := {"text": text}
	if not about.is_empty():
		body["about"] = about
	for k in ["by", "seen_by", "tag", "impact"]:
		if options.has(k):
			body[k] = options[k]
	await _post("event", body, 5.0)


func remember(name: String, note: String) -> void:
	_fire("remember", {"name": name, "note": note})


## A live snapshot every call can see (so facts need not be repeated).
func state(values: Dictionary) -> void:
	_fire("state", {"state": values})


# ---------------- minds: utility AI the game runs locally ----------------

## Declares a mind. options: senses ({"hp": [0.0, 1.0], "armed": true, "mood": ["calm", "angry"]}),
## actions ({"charge": {"speed": [1.0, 3.0]}, "wait": {}}), rules (the offline mind: {"retreat": ["hp low"],
## "charge": {"score": 0.5, "when": ["dist below 15"], "args": {"speed": "dist high"}}}), variants (temperaments in a crowd),
## learn (seconds between learning steps when you call reward; 0: never).
func mind(name: String, personality: String, options: Dictionary) -> void:
	var decl := {"name": name, "personality": personality, "senses": options.get("senses", {}),
		"actions": options.get("actions", {}), "rules": options.get("rules", null),
		"variants": options.get("variants", 3), "learn": options.get("learn", 30)}
	var m := {"decl": decl, "compiled": compile_mind(decl), "units": {}, "checked": _now()}
	_minds[name] = m
	_declare_mind(m)


## Whether a mind with this name is declared (several AIMind nodes share one).
func has_mind(name: String) -> bool:
	return _minds.has(name)


## Instant, never calls a model: {"action", "args", "variant"} for this unit (who: a stable id per unit).
func think(name: String, senses: Dictionary, who := "") -> Dictionary:
	if not _minds.has(name):
		return {"action": null, "args": {}, "variant": 0}
	var m: Dictionary = _minds[name]
	var choice := run_mind(m.compiled, senses, who, m.units)
	if who != "":
		if _units.size() >= 10000 and not _units.has(who):
			_units.clear()
		var ids = m.compiled.get("ids")
		_units[who] = [name, choice.variant, ids[choice.variant] if ids is Array else null, choice.action, senses]
	var now := _now()
	if now - float(m.checked) >= 2.0:
		m.checked = now
		_refresh_mind(name, m)
	if not _rewards.is_empty() and now - _reward_at >= 1.0:
		flush()
	return choice


## How well the unit's last choice went (higher is better). Rewarded minds learn (in `kinloom serve`, key or not).
## done: the unit's fight, life or round is over (its next rewards start a new story).
func reward(who: String, value: float, done := false) -> bool:
	if not _units.has(who) or is_nan(value) or is_inf(value):
		return false
	var u: Array = _units[who]
	_rewards.append({"who": who, "mind": u[0], "variant": u[1], "id": u[2], "action": u[3], "senses": u[4], "reward": value,
		"done": done})
	if _rewards.size() > 1000:
		_rewards = _rewards.slice(_rewards.size() - 1000)
	if _rewards.size() >= 50 or _now() - _reward_at >= 1.0:
		flush()
	return true


## Sends pending rewards now; returns once everything reported so far is sent.
func flush() -> void:
	while _flushing:
		await get_tree().process_frame
	_reward_at = _now()
	if _rewards.is_empty():
		return
	var batch := _rewards
	_rewards = []
	_flushing = true
	var r = await _post("reward", {"rewards": batch}, 5.0)
	_flushing = false
	if r == null or not (r.get("versions") is Dictionary):
		return
	for name in r["versions"]:
		if _minds.has(name) and int(_minds[name].compiled.get("version", -1)) != int(r["versions"][name]):
			_refresh_mind(name, _minds[name])


## How a mind is doing (variants, mean rewards, generations), or null offline.
func report(name: String) -> Variant:
	var r = await _request("mind?name=" + name.uri_encode(), HTTPClient.METHOD_GET, "", 3.0)
	return r.get("report") if r != null else null


func _declare_mind(m: Dictionary) -> void:
	var r = await _post("mind", m.decl, 5.0)
	if r != null and r.get("mind") is Dictionary:
		m.compiled = _typed(r["mind"], m.decl)


func _refresh_mind(name: String, m: Dictionary) -> void:
	var r = await _request("mind?name=" + name.uri_encode(), HTTPClient.METHOD_GET, "", 3.0, true)
	if r == null:
		return
	if r.get("mind") is Dictionary:
		m.compiled = _typed(r["mind"], m.decl)
	elif r.get("missing", false):
		_declare_mind(m)


# ---------------- world: who knows what, who likes whom ----------------

## a and b tell each other what they know. Returns [{"from", "to", "text", "tag"}] ([] offline).
func meet(a: String, b: String) -> Array:
	var r = await _post("meet", {"a": a, "b": b}, 3.0)
	return r["shared"] if r != null and r.get("shared") is Array else []


## Rounds of talk inside a group (or among every character when group is "").
func spread(group := "", rounds := 1) -> Array:
	var r = await _post("spread", {"group": group if group != "" else null, "rounds": rounds}, 5.0)
	return r["shared"] if r != null and r.get("shared") is Array else []


## Whether name knows about the event tagged `tag` (false offline).
func knows(name: String, tag: String) -> bool:
	var r = await _post("knows", {"name": name, "tag": tag}, 3.0)
	return r != null and r.get("knows", false) == true


## What a thinks of b, -1..1 (0 offline).
func opinion(a: String, b: String) -> float:
	var r = await _post("opinion", {"a": a, "b": b}, 3.0)
	return float(r.get("opinion", 0.0)) if r != null else 0.0


## Moves a's opinion of b by change; returns the new opinion (0 offline).
func feel(a: String, b: String, change: float) -> float:
	var r = await _post("feel", {"a": a, "b": b, "change": change}, 3.0)
	return float(r.get("opinion", 0.0)) if r != null else 0.0


## A group's average opinion of target (0 offline).
func reputation(target: String, group: String) -> float:
	var r = await _post("reputation", {"target": target, "group": group}, 3.0)
	return float(r.get("reputation", 0.0)) if r != null else 0.0


func status() -> Dictionary:
	var r = await _http_get("status")
	return r if r != null else {"mode": "unreachable", "url": url}


# ---------------- offline answers ----------------

## The offline answer for an example: first option, middle of a range, the example itself.
static func default_of(example: Variant) -> Variant:
	if example is Dictionary:
		var out := {}
		for k in example:
			out[k] = default_of(example[k])
		return out
	if example is Array:
		if example.size() == 2 and _is_number(example[0]) and _is_number(example[1]):
			var lo: float = min(float(example[0]), float(example[1]))
			var hi: float = max(float(example[0]), float(example[1]))
			var mid := (lo + hi) / 2.0
			if typeof(example[0]) == TYPE_INT and typeof(example[1]) == TYPE_INT and hi - lo >= 2:
				return int(floor(mid + 0.5))
			return mid
		var all_text: bool = example.size() >= 2
		for x in example:
			if typeof(x) != TYPE_STRING:
				all_text = false
		if all_text:
			return example[0]
		var items := []
		for x in example:
			items.append(default_of(x))
		return items
	return example


static func _is_number(v: Variant) -> bool:
	return typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT


## An event's offline lines: ["..."], "...", or {"when": ..., "lines": [...]}.
static func _lines_of(v: Variant) -> Array:
	if v is Array:
		return v
	if v is Dictionary:
		var l = v.get("lines", [])
		return l if l is Array else []
	return [] if v == null else [v]


func _offline_line(name: String, event: String, facts: Dictionary) -> String:
	var lines = _chars.get(name, {}).get("lines", {})
	var options: Array = []
	if lines is Array:
		options = lines
	elif lines is Dictionary:
		options = _lines_of(lines.get(event))
		if options.is_empty():
			options = _lines_of(lines.get("*"))
	var usable := []
	for t in options:
		var ok := true
		for m in _placeholder.search_all(str(t)):
			if not facts.has(m.get_string(1)):
				ok = false
		if ok:
			usable.append(str(t))
	if usable.is_empty():
		return ""
	return fill(usable[randi() % usable.size()], facts)


## Replaces {name} placeholders with facts, numbers formatted for people.
func fill(template: String, facts: Dictionary) -> String:
	var out := template
	for m in _placeholder.search_all(template):
		out = out.replace(m.get_string(0), _fmt(facts.get(m.get_string(1), "")))
	return out


static func _fmt(v: Variant) -> String:
	if typeof(v) == TYPE_BOOL:
		return "yes" if v else "no"
	if typeof(v) == TYPE_FLOAT:
		if is_equal_approx(v, round(v)):
			return str(int(round(v)))
		if absf(v) >= 100.0:
			return str(int(round(v)))
		var s := "%.1f" % v
		if s == "0.0" or s == "-0.0":
			s = ("%.2f" % v).rstrip("0").rstrip(".")
		return s
	return str(v)


# ---------------- background refreshes ----------------

func _refresh_decision(d: Dictionary, name: String, situation: Dictionary, choices: Variant) -> void:
	var r = await _post("decide", {"name": name, "situation": situation, "choices": choices}, 2.0)
	if r != null and r.get("decision") != null:
		_redeclare(name, r)
		d.value = r["decision"]
	d.pending = false


func _refresh_actions(a: Dictionary, name: String, situation: Dictionary, think := true) -> void:
	var r = await _post("act", {"name": name, "situation": situation, "think": think}, 2.0)
	if r != null and r.get("actions") is Array:
		a.ready.append_array(r["actions"])
	a.pending = false


func _redeclare(name: String, r: Dictionary) -> void:
	# The server restarted and lost this character: declare it again (the answer already used a neutral one).
	if r.get("declared", true) == false and _chars.has(name):
		if _tools != null:                             # its tools first: the character may name them
			await _post("tools", {"tools": _tools}, 5.0)
		_fire("character", _chars[name])


# ---------------- HTTP ----------------

func _headers() -> PackedStringArray:
	var h := PackedStringArray(["Content-Type: application/json", "X-Kinloom-Session: " + session])
	if token != "":
		h.append("Authorization: Bearer " + token)
	return h


func _fire(verb: String, body: Dictionary) -> void:
	_post(verb, body, 5.0)


func _http_get(verb: String) -> Variant:
	return await _request(verb, HTTPClient.METHOD_GET, "", 3.0)


func _post(verb: String, body: Dictionary, seconds: float) -> Variant:
	if _brain != null:
		return await _native(verb, _plain(body))
	return await _request(verb, HTTPClient.METHOD_POST, JSON.stringify(body), seconds)


## A body as JSON would carry it (Godot values such as Vector2 become text, as on the wire).
static func _plain(body: Dictionary) -> Dictionary:
	var r := Py.loads(Py.dumps(body))
	return r[1] if r[0] and r[1] is Dictionary else {}


## The verb answered by the native brain: the JSON answer, or null (an error is told once in the output).
func _native(verb: String, body: Dictionary, missing_ok := false) -> Variant:
	var r: Array = await _brain.handle(verb, body, session)
	if r[0] == 404 and missing_ok:
		return {"missing": true}
	if r[0] != 200:
		push_warning("[kinloom] %s: %s" % [verb, str(r[1].get("error", ""))])
		return null
	var copy := Py.loads(Py.dumps(r[1]))
	return copy[1] if copy[0] else null


func _request(verb: String, method: int, data: String, seconds: float, missing_ok := false) -> Variant:
	if _brain != null:
		if verb.begins_with("mind?name="):
			return await _native("report", {"name": verb.substr(10).uri_decode()}, missing_ok)
		var parsed = Py.loads(data)[1] if data != "" else {}
		return await _native(verb, parsed if parsed is Dictionary else {}, missing_ok)
	if Time.get_ticks_msec() / 1000.0 < _down_until or not is_inside_tree():
		return null
	var target := url
	if not await _reachable(target):
		if url == target:                # the game may have changed url meanwhile: that one was not checked
			_mark_down()
		return null
	var req := HTTPRequest.new()
	req.timeout = seconds
	add_child(req)
	var err := req.request(target + "/v1/" + verb, _headers(), method, data)
	if err != OK:
		req.queue_free()
		_up_until = 0.0
		_mark_down()
		return null
	var res: Array = await req.request_completed
	req.queue_free()
	if res[0] != HTTPRequest.RESULT_SUCCESS:
		_up_until = 0.0                  # look again next time: the server may have gone
		if res[0] != HTTPRequest.RESULT_TIMEOUT and url == target:
			_mark_down()
		return null
	_up_url = target
	_up_until = _now() + 5.0
	_failures = 0
	if res[1] == 404 and missing_ok:
		return {"missing": true}
	if res[1] != 200:
		push_warning("[kinloom] %s: HTTP %d %s" % [verb, res[1], res[3].get_string_from_utf8().left(200)])
		return null
	var parsed = JSON.parse_string(res[3].get_string_from_utf8())
	return parsed if parsed is Dictionary else null


## Whether the server takes connections, checked in at most 1 s (3 s for a remote one). Without it, a request to a
## server that is not running waited its whole timeout on Windows (12 s for chat, measured in the conformance run):
## the connection refused was not seen, so the offline answer came that late.
func _reachable(target: String) -> bool:
	if _now() < _up_until and _up_url == target:
		return true
	var address := target.get_slice("://", 1).get_slice("/", 0)
	var host := address
	var port := 443 if target.begins_with("https") else 80
	if address.begins_with("["):
		host = address.get_slice("]", 0).trim_prefix("[")
		var rest := address.get_slice("]", 1)
		if rest.begins_with(":") and rest.substr(1).is_valid_int():
			port = int(rest.substr(1))
	elif address.count(":") == 1:
		host = address.get_slice(":", 0)
		if address.get_slice(":", 1).is_valid_int():
			port = int(address.get_slice(":", 1))
	if host == "localhost":
		host = "127.0.0.1"
	var tcp := StreamPeerTCP.new()
	if tcp.connect_to_host(host, port) != OK:
		return false
	var limit := _now() + (1.0 if host == "127.0.0.1" or host == "::1" else 3.0)
	while _now() < limit and is_inside_tree():
		tcp.poll()
		var status := tcp.get_status()
		if status == StreamPeerTCP.STATUS_CONNECTED:
			tcp.disconnect_from_host()
			return true
		if status == StreamPeerTCP.STATUS_ERROR or status == StreamPeerTCP.STATUS_NONE:
			return false
		await get_tree().process_frame
	tcp.disconnect_from_host()
	return false


func _mark_down() -> void:
	_failures = mini(_failures + 1, 10)
	_down_until = Time.get_ticks_msec() / 1000.0 + minf(10.0, 2.0 * pow(2.0, _failures - 1))
	var host := url.get_slice("://", 1).get_slice("/", 0).get_slice(":", 0)
	if autostart and not _tried_start and host in ["127.0.0.1", "localhost"]:
		_tried_start = true
		var args := ["serve", "--quiet"]
		var port := url.get_slice("://", 1).get_slice("/", 0).get_slice(":", 1)
		if port.is_valid_int():
			args += ["--port", port]
		var program := "kinloom.exe" if OS.get_name() == "Windows" else "kinloom"
		for folder in [OS.get_executable_path().get_base_dir().path_join("kinloom-server"),
				ProjectSettings.globalize_path("res://kinloom-server")]:
			var bundled: String = folder.path_join(program)
			if FileAccess.file_exists(bundled) and OS.create_process(bundled, args + ["--dir", folder]) > 0:
				print("[kinloom] started %s" % bundled)
				_down_until = Time.get_ticks_msec() / 1000.0 + 1.0
				return
		if not (OS.has_feature("editor") or OS.is_debug_build()):
			return
		for exe in ["kinloom", "kinloom.exe"]:
			if OS.create_process(exe, args) > 0:
				print("[kinloom] started `kinloom serve` (it keeps running after the game closes)")
				_down_until = Time.get_ticks_msec() / 1000.0 + 1.0
				return
		print("[kinloom] no server at %s: answering offline. Run `kinloom serve` for AI (pip install kinloom)." % url)


func _now() -> float:
	return Time.get_ticks_msec() / 1000.0


# ---------------- minds (the same rules and numbers as kinloom/minds.py) ----------------

## FNV-1a 32-bit over UTF-8: which variant a unit gets, identical in every client.
static func fnv1a(text: String) -> int:
	var h := 0x811C9DC5
	for b in text.to_utf8_buffer():
		h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
	return h


static func _senses_of(example: Dictionary) -> Dictionary:
	var out := {}
	for name in example:
		var ex = example[name]
		if typeof(ex) == TYPE_BOOL:
			out[name] = ["flag"]
		elif ex is Array and ex.size() == 2 and _is_number(ex[0]) and _is_number(ex[1]) and float(ex[0]) != float(ex[1]):
			out[name] = ["range", minf(float(ex[0]), float(ex[1])), maxf(float(ex[0]), float(ex[1]))]
		elif ex is Array and ex.size() >= 2:
			var all_text := true
			for x in ex:
				if typeof(x) != TYPE_STRING:
					all_text = false
			if all_text:
				out[name] = ["options", ex]
	return out


static func _is_ident(c: String, first: bool) -> bool:
	var code := c.unicode_at(0)
	var letter := (code >= 65 and code <= 90) or (code >= 97 and code <= 122) or code == 95
	return letter or (not first and code >= 48 and code <= 57)


## "hp low", "dist below 12", "armed", "not armed", "mood is angry" -> [sense, op, p1, p2], or null.
static func parse_rule(text: Variant, senses: Dictionary) -> Variant:
	if typeof(text) != TYPE_STRING or String(text).length() > 120:
		return null
	var t := String(text).strip_edges()
	var neg := false
	if t.begins_with("!"):
		neg = true
		t = t.substr(1).strip_edges()
	elif t.length() > 4 and t.substr(0, 3).to_lower() == "not" and (t[3] == " " or t[3] == "\t"):
		neg = true
		t = t.substr(4).strip_edges()
	var i := 0
	while i < t.length() and _is_ident(t[i], i == 0):
		i += 1
	if i == 0:
		return null
	var word := t.substr(0, i).to_lower()
	var rest := t.substr(i).strip_edges()
	var sense = null
	for k in senses:
		if String(k).to_lower() == word:
			sense = k
	if sense == null:
		return null
	var kind: Array = senses[sense]
	if rest == "":
		return [sense, "not" if neg else "flag", 0, 0] if kind[0] == "flag" else null
	if neg or kind[0] == "flag":
		return null
	var op := ""
	for sym in [">=", "<=", "==", ">", "<", "~", "="]:
		if rest.begins_with(sym):
			op = {">=": "above", "<=": "below", "==": "is", ">": "above", "<": "below", "~": "around", "=": "is"}[sym]
			rest = rest.substr(sym.length()).strip_edges()
			break
	if op == "":
		var cut := rest.find(" ")
		op = (rest if cut < 0 else rest.substr(0, cut)).to_lower()
		rest = "" if cut < 0 else rest.substr(cut).strip_edges()
		if not (op in ["high", "low", "above", "below", "around", "is"]):
			return null
	if kind[0] == "options":
		if op != "is":
			return null
		for o in kind[1]:
			if String(o).to_lower() == rest.to_lower():
				return [sense, "is", o, 0]
		return null
	var lo: float = kind[1]
	var hi: float = kind[2]
	if op == "high" or op == "low":
		return [sense, op, lo, hi] if rest == "" else null
	if op == "is" or not rest.is_valid_float():
		return null
	var v := roundf(clampf(rest.to_float(), lo, hi) * 1000.0) / 1000.0
	return [sense, op, v, (hi - lo) * (0.15 if op == "around" else 0.05)]


## 0..1; a missing or wrong-typed sense is neutral (0.5).
static func rule_value(rule: Array, senses: Dictionary) -> float:
	var op: String = rule[1]
	var v = senses.get(rule[0])
	if op == "flag" or op == "not":
		var on := false
		if typeof(v) == TYPE_BOOL:
			on = v
		elif _is_number(v) and not is_nan(float(v)) and not is_inf(float(v)):
			on = float(v) != 0.0
		else:
			return 0.5
		return 1.0 if on == (op == "flag") else 0.0
	if op == "is":
		if typeof(v) != TYPE_STRING and typeof(v) != TYPE_STRING_NAME:
			return 0.5
		return 1.0 if String(v) == String(rule[2]) else 0.0
	if not _is_number(v) or is_nan(float(v)) or is_inf(float(v)):
		return 0.5
	var x := float(v)
	var p1 := float(rule[2])
	var p2 := float(rule[3])
	if op == "high" or op == "low":
		var y := clampf((x - p1) / (p2 - p1), 0.0, 1.0)
		return y if op == "high" else 1.0 - y
	if op == "around":
		var z := (x - p1) / p2
		return exp(-z * z)
	var zz := clampf((x - p1) / p2, -60.0, 60.0)
	var up := 1.0 / (1.0 + exp(-zz))
	return up if op == "above" else 1.0 - up


static func _whole_range(ex) -> bool:
	return ex is Array and ex.size() == 2 and typeof(ex[0]) == TYPE_INT and typeof(ex[1]) == TYPE_INT and absi(ex[1] - ex[0]) >= 2


## The offline mind: the game's rules compiled like the server does (no rules: every action scores 1).
static func compile_mind(decl: Dictionary) -> Dictionary:
	var senses := _senses_of(decl.get("senses", {}))
	var actions: Dictionary = decl.get("actions", {})
	var rules = decl.get("rules")
	if not (rules is Dictionary) or rules.is_empty():
		rules = null
	var program := {}
	for action in actions:
		var shapes: Dictionary = actions[action] if actions[action] is Dictionary else {}
		var spec = {"score": 1.0}
		if rules != null:
			spec = null
			for k in rules:
				if String(k).to_lower() == String(action).to_lower():
					spec = rules[k]
		if typeof(spec) == TYPE_STRING or spec is Array:
			spec = {"when": spec}
		var out := {"score": 0.0, "when": [], "args": {}}
		for arg in shapes:
			out.args[arg] = default_of(shapes[arg])
		if spec is Dictionary:
			var when = spec.get("when", [])
			if typeof(when) == TYPE_STRING:
				when = [when]
			var parsed := []
			var ok: bool = when is Array
			if ok:
				for r in when.slice(0, 6):
					var rule = parse_rule(r, senses)
					if rule == null:
						ok = false
					parsed.append(rule)
			var score = spec.get("score", 1.0)
			if ok and _is_number(score):
				out.score = clampf(float(score), 0.0, 3.0)
				out.when = parsed
				var given: Dictionary = spec.get("args", {}) if spec.get("args") is Dictionary else {}
				for arg in given:
					if not shapes.has(arg):
						continue
					var ex = shapes[arg]
					var v = given[arg]
					var is_range: bool = ex is Array and ex.size() == 2 and _is_number(ex[0]) and _is_number(ex[1])
					if is_range and typeof(v) == TYPE_STRING:
						var r2 = parse_rule(v, senses)
						if r2 != null:
							out.args[arg] = r2 + [minf(float(ex[0]), float(ex[1])), maxf(float(ex[0]), float(ex[1])), _whole_range(ex)]
					elif is_range and _is_number(v):
						var c := clampf(float(v), minf(float(ex[0]), float(ex[1])), maxf(float(ex[0]), float(ex[1])))
						out.args[arg] = int(floor(c + 0.5)) if _whole_range(ex) else c
					elif typeof(v) == typeof(default_of(ex)):
						out.args[arg] = v
		program[action] = out
	var variants := []
	for i in clampi(int(decl.get("variants", 1)), 1, 8):
		variants.append(program)
	return {"name": decl.get("name", ""), "version": 0, "order": actions.keys(), "stick": 0.1, "variants": variants, "ids": null}


## A mind from the server, with whole numbers where the game declared whole numbers (JSON has only floats here).
static func _typed(compiled: Dictionary, decl: Dictionary) -> Dictionary:
	var actions: Dictionary = decl.get("actions", {})
	compiled["version"] = int(compiled.get("version", 0))
	if compiled.get("ids") is Array:
		var ids := []
		for x in compiled["ids"]:
			ids.append(int(x))
		compiled["ids"] = ids
	for program in compiled.get("variants", []):
		for action in program:
			var shapes: Dictionary = actions.get(action, {}) if actions.get(action) is Dictionary else {}
			var args: Dictionary = program[action].get("args", {})
			for arg in args:
				var ex = shapes.get(arg)
				if _is_number(args[arg]) and (typeof(ex) == TYPE_INT or _whole_range(ex)):
					args[arg] = int(args[arg])
	return compiled


## One decision from a compiled mind. units: who -> last action (hysteresis).
static func run_mind(compiled: Dictionary, senses: Dictionary, who: String, units: Dictionary) -> Dictionary:
	var variants: Array = compiled["variants"]
	var index := 0
	if variants.size() > 1:
		index = fnv1a(who) % variants.size()
	var program: Dictionary = variants[index]
	var last = units.get(who) if who != "" else null
	var best = null
	var best_score := -1.0
	for action in compiled["order"]:
		var spec: Dictionary = program[action]
		var s := float(spec["score"])
		var when: Array = spec["when"]
		if not when.is_empty():
			var product := 1.0
			for r in when:
				product *= rule_value(r, senses)
			s = float(spec["score"]) * pow(product, 1.0 / when.size()) if product > 0.0 else 0.0
		if action == last:
			s *= 1.0 + float(compiled["stick"])
		if s > best_score + 1e-12:
			best = action
			best_score = s
	var args := {}
	var given: Dictionary = program[best]["args"]
	for k in given:
		var v = given[k]
		if v is Array and v.size() == 7 and v[0] is String and v[6] is bool:   # set by the senses; other lists as they are
			var x: float = float(v[4]) + rule_value(v, senses) * (float(v[5]) - float(v[4]))
			args[k] = int(floor(x + 0.5)) if v[6] else x
		else:
			args[k] = v
	if who != "":
		if units.size() >= 10000 and not units.has(who):
			units.clear()
		units[who] = best
	return {"action": best, "args": args, "variant": index}
