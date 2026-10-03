extends RefCounted
## The native brain: every verb in this process, the same answers as `kinloom serve` (kinloom/brain.py + server.py).
## Coroutines with await: background work (line banks, decisions, pools, cards, greetings, learning) never blocks.

const Py = preload("py.gd")
const ShapeLib = preload("shape.gd")
const Souls = preload("souls.gd")
const Stream = preload("stream.gd")
const Prompts = preload("prompts.gd")
const Mem = preload("memory.gd")
const Rules = preload("rules.gd")
const Minds = preload("minds.gd")
const Lines = preload("lines.gd")
const Http = preload("http.gd")
const P = preload("providers.gd")
const M = preload("model.gd")

const SEP := "\u0001"
const MAX_NAME := 48
const MAX_CHARACTERS := 5000
const MAX_WAITING := 50
const MAX_SPEAKERS := 500
const BANK_SIZE := 8
const POOL_SIZE := 5
const MAX_TOOLS := 100
const MAX_AUDIO := 25 * 1024 * 1024
const DEFAULT_LANGUAGE := "English"
const AUTO := "auto"
const MAX_SUGGESTIONS := 6
const CHAT_KINDS := ["chat", "greet", "converse", "suggest", "deeds", "line"]
const MIN_SAMPLES := 12
const MIN_EPISODES := 6
const GAMMA := 0.8
const COMPOUND := 0.4
const BUFFER := 4000
const HEARSAY := 0.5
const RUMOR_DECAY := 0.8
const MIN_RUMOR := 0.1
const CONFIG_KEYS := ["personality", "soul", "lines", "offline", "events", "tools", "max_words", "max_chars", "every", "language",
	"group", "trust", "invent", "voice"]

var hedge_after := 2.5
var stall_after := 3.0
var inner_grace := 1.5
var listeners: Array = []
var spent: Array = []
var calls: Array = []
var characters := {}
var declared := {}
var game_declared := {}
var cfg_declared := {}
var banks := {}
var decisions := {}
var pending := {}
var pools := {}
var history := {}
var state_of := {}
var minds := {}
var opinions_by := {}
var moods := {}
var gestures := {}
var gesture_seen := {}
var lore_by := {}
var cfg_chars := {}
var cfg_lore: Array = []
var cfg_tools := {}
var tool_sets := {}
var blind_told := false
var card_waiters := {}
var greetings := {}
var greeting_busy := {}
var bonds := {}
var said_by := {}
var switches := 0
var rises := {}
var events := 0
var spreads := 0
var empty_told := {}
var journal_entries: Array = []
var stats_of := {"calls": 0, "failures": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "latency": 0.0,
	"offline_answers": 0, "by_kind": {}, "hedged": 0, "cut_replies": 0}
var busy := 0
var running := 0
var queue: Array = []
var voice_cache := {}
var closed := false
var provider = null
var models := {}
var rating = null
var voice = null
var language := DEFAULT_LANGUAGE
var voice_language = null
var limit := 30
var prices = null
var banned = null
var content_filter = null
var memory
var call_timeout := 12.0
var max_cost_per_hour = null
var max_cost_per_day = null
var _fault := ""
var _fault_type := false


static func clock() -> float:
	return Http.now()


static func wall() -> float:
	return Time.get_unix_time_from_system()


## o: provider (null, "auto", a spec {url, key, model, kind}, a Callable, an object with complete()), voice, config (a
## kinloom.json path or a Dictionary), language, calls_per_minute, prices, content_filter (Callable text -> bool),
## memory (a file path such as "user://kinloom-memory.json", or ""), call_timeout.
func _init(o := {}) -> void:
	var cfg := {"language": "English", "calls_per_minute": 30}
	var given = o.get("config")
	if typeof(given) == TYPE_STRING and given != "" and FileAccess.file_exists(given):
		var r := Py.loads(FileAccess.get_file_as_string(given))
		if r[0] and r[1] is Dictionary:
			cfg.merge(r[1], true)
	elif given is Dictionary:
		cfg.merge(given, true)
	provider = P.provider_of(o.get("provider"))
	# models: {"chat" | "background": a model id on the same endpoint, or a provider}; rating: a rule in every prompt
	var mr := _models_of(o["models"] if o.get("models") != null else cfg.get("models"), provider)
	models = mr[0]
	if mr[1] != "":
		_log("refused", "kinloom", mr[1])
	var rr := _rating_of(o["rating"] if o.get("rating") != null else cfg.get("rating"))
	rating = rr[0]
	if rr[1] != "":
		_log("refused", "kinloom", rr[1])
	var v = o["voice"] if o.has("voice") else ("auto" if typeof(o.get("provider")) == TYPE_STRING and o.get("provider") == "auto" else null)
	if typeof(v) == TYPE_STRING and v == "auto":
		voice = _voice_from_env()
	elif v is Object:
		voice = v
	elif v is Dictionary:
		voice = P.OpenAIVoice.new(v)
	var lang = o.get("language")
	language = str(lang) if Py.truthy(lang) else (str(cfg["language"]) if Py.truthy(cfg.get("language")) else DEFAULT_LANGUAGE)
	voice_language = str(lang) if Py.truthy(lang) else (str(cfg["language"]) if Py.truthy(cfg.get("language")) and str(cfg["language"]) != DEFAULT_LANGUAGE else null)
	var per_minute = o.get("calls_per_minute") if Py.truthy(o.get("calls_per_minute")) else cfg.get("calls_per_minute", 30)
	limit = maxi(1, int(Py.num(per_minute)) if Py.truthy(per_minute) else 30)
	prices = o.get("prices") if o.get("prices") is Dictionary else (cfg.get("prices") if cfg.get("prices") is Dictionary else null)
	var words := []
	if cfg.get("banned_words") is Array:
		for w in cfg["banned_words"]:
			if typeof(w) == TYPE_STRING and Py.strip(w) != "":
				words.append(Py.escape(Py.lower(Py.strip(w))))
	if not words.is_empty():
		banned = Py.re("(?<![" + Py.W + "])(" + "|".join(words) + ")(?![" + Py.W + "])")
	content_filter = o.get("content_filter") if o.get("content_filter") is Callable else null
	var path = o.get("memory")
	memory = Mem.Memory.new(str(path) if typeof(path) == TYPE_STRING else "", wall)
	if o.get("call_timeout") != null:
		call_timeout = float(o["call_timeout"])
	max_cost_per_hour = Py.finite(cfg.get("max_cost_per_hour"))
	max_cost_per_day = Py.finite(cfg.get("max_cost_per_day"))
	if cfg.get("characters") is Dictionary:
		for name in cfg["characters"]:
			var spec = cfg["characters"][name]
			if not (spec is Dictionary):
				_log("refused", str(name).substr(0, MAX_NAME), "kinloom.json: a character must be an object")
				continue
			var kept := {}
			for k in spec:
				if k in CONFIG_KEYS:
					kept[k] = spec[k]
			cfg_chars[Py.clean(str(name)).substr(0, MAX_NAME)] = [kept, Py.dumps(kept, true, true)]
	if cfg.get("lore") is Array:
		for x in cfg["lore"]:
			cfg_lore.append(Py.text_of(x))
	elif typeof(cfg.get("lore")) == TYPE_STRING:
		cfg_lore = [cfg["lore"]]
	var pt := Lines.parse_tools(cfg["tools"] if cfg.get("tools") is Dictionary else {})
	if pt[0] == null:
		_log("refused", "kinloom.json", "tools: " + pt[1])
	else:
		cfg_tools = pt[0]
	for name in cfg_chars:
		_from_config("default", name)
	if provider != null and "base_url" in provider and provider.has_method("warm") and Engine.get_main_loop() is SceneTree:
		provider.warm()
	if provider != null and OS.has_feature("web") and not (provider is P.Scripted) and "base_url" in provider and not Http.is_local(provider.base_url, provider.name):
		_log("warning", "kinloom", "a model key is used inside a web page: players can read it. Ship with a relay (url: your kinloom serve) or let players bring their own key.")


static func _voice_from_env() -> Variant:
	var force := Py.lower(Py.strip(OS.get_environment("KINLOOM_VOICE")))
	if force in ["off", "none", "0", "false", "no", "system"]:
		return null
	var e := func(n: String) -> String: return OS.get_environment(n)
	if e.call("KINLOOM_VOICE_BASE_URL") != "" and (e.call("KINLOOM_SPEAK_MODEL") != "" or e.call("KINLOOM_LISTEN_MODEL") != ""):
		return P.OpenAIVoice.new({"url": e.call("KINLOOM_VOICE_BASE_URL"), "key": e.call("KINLOOM_VOICE_API_KEY"),
			"speak_model": e.call("KINLOOM_SPEAK_MODEL") if e.call("KINLOOM_SPEAK_MODEL") != "" else null,
			"listen_model": e.call("KINLOOM_LISTEN_MODEL") if e.call("KINLOOM_LISTEN_MODEL") != "" else null, "name": "custom"})
	if e.call("OPENAI_API_KEY") != "":
		return P.OpenAIVoice.new({"url": e.call("OPENAI_BASE_URL") if e.call("OPENAI_BASE_URL") != "" else "https://api.openai.com/v1",
			"key": e.call("OPENAI_API_KEY"),
			"speak_model": e.call("KINLOOM_SPEAK_MODEL") if e.call("KINLOOM_SPEAK_MODEL") != "" else "gpt-4o-mini-tts",
			"listen_model": e.call("KINLOOM_LISTEN_MODEL") if e.call("KINLOOM_LISTEN_MODEL") != "" else "gpt-4o-mini-transcribe"})
	return null


# ---------------- plumbing ----------------

func _raise(message: String, type_error := false) -> void:
	if _fault == "":
		_fault = message
		_fault_type = type_error


func _from_config(session: String, name: String) -> void:
	var entry = cfg_chars.get(name)
	var key := session + SEP + name
	if entry == null or game_declared.has(key) or cfg_declared.get(key) == entry[1]:
		return
	cfg_declared[key] = entry[1]
	var spec: Dictionary = entry[0]
	var saved := _fault
	_fault = ""
	character(session, name, spec, true)
	if _fault != "":
		_log("refused", name, "kinloom.json: " + _fault)
		_fault = ""
		var safe := {}
		for k in spec:
			if k in ["personality", "offline", "soul", "language", "group", "voice"]:
				safe[k] = spec[k]
		character(session, name, safe, true)
	_fault = saved


func char_of(session: String, name: Variant) -> Variant:
	var n := Py.clean(Py.text_of(name)).substr(0, MAX_NAME)
	if n == "":
		n = "?"
	_from_config(session, n)
	var key := session + SEP + n
	var c = characters.get(key)
	if c == null:
		c = Lines.character(n, {})[0]
		if characters.size() < MAX_CHARACTERS:
			characters[key] = c
	return c


func _log(kind: String, name: Variant, text: Variant, detail := {}) -> void:
	var entry := {"time": wall(), "kind": kind, "name": name, "text": text}
	entry.merge(detail, true)
	journal_entries.append(entry)
	if journal_entries.size() > 500:
		journal_entries.pop_front()
	for listener in listeners.duplicate():
		if listener is Callable and listener.is_valid():
			listener.call(entry)


func _allow(foreground: bool) -> bool:
	var now := clock()
	while not spent.is_empty() and now - spent[0][0] > 86400:
		spent.pop_front()
	for cap in [[max_cost_per_hour, 3600.0, "hour"], [max_cost_per_day, 86400.0, "day"]]:
		if cap[0] != null and prices != null:
			var total := 0.0
			for s in spent:
				if now - s[0] <= cap[1]:
					total += s[1]
			if total >= cap[0]:
				_log("budget", "kinloom", "cost cap reached ($" + Py.fixed(cap[0], 2) + " per " + cap[2] + "): answered offline")
				return false
	while not calls.is_empty() and now - calls[0] > 60:
		calls.pop_front()
	var cap := limit if foreground else limit - maxi(1, ceili(0.3 * limit))
	if calls.size() >= cap:
		return false
	calls.append(now)
	return true


## One model call, never longer than its timeout: the reply {ok, text, error, input, cached, output, latency, cut, blind}.
func _ask(kind: String, name: String, system: String, user: String, json: bool, foreground: bool, max_tokens := 400,
		on_text: Variant = null, timeout := 0.0, images: Array = []) -> Dictionary:
	if provider == null:
		return M.reply(false, "", "offline")
	if not _allow(foreground):
		_log("budget", name, "over budget: answered offline")
		return M.reply(false, "", "over budget")
	var limit_s := timeout if timeout > 0 else call_timeout
	var o := {"json": json, "max_tokens": max_tokens, "timeout": limit_s, "images": images if not images.is_empty() else null}
	if on_text is Callable:
		o["on_text"] = on_text
	var box := {"r": null}
	_complete_into(box, _provider_for(kind), _rated(system), user, o)
	var end := clock() + limit_s + 0.25
	while box.r == null and clock() < end:
		await Http.frame()
	var r: Dictionary = box.r if box.r != null else M.reply(false, "", "timed out after " + Py.fixed(limit_s, 1) + " s")
	_account(kind, name, r)
	return r


static func _complete_into(box: Dictionary, used, system: String, user: String, o: Dictionary) -> void:
	box.r = await used.complete(system, user, o)


func _account(kind: String, name: String, r: Dictionary) -> void:
	var s := stats_of
	s.calls += 1
	s.by_kind[kind] = s.by_kind.get(kind, 0) + 1
	s.input_tokens += int(r.input)
	s.cached_tokens += int(r.cached)
	s.output_tokens += int(r.output)
	s.latency += float(r.latency)
	if not r.ok:
		s.failures += 1
	spent.append([clock(), _price(r)])
	_log("call", name, kind + " ok" if r.ok else kind + " failed: " + str(r.error), {"latency": Py.round_to(r.latency, 3), "tokens": int(r.input) + int(r.output)})
	if r.blind and not blind_told:
		blind_told = true
		_log("refused", name, kind + ": this model cannot see pictures; it answered from the text (use a model that reads images to send image=)")
	var switched: Array = provider.switched if provider != null and "switched" in provider else []
	var fresh := switched.slice(switches)
	switches = switched.size()
	for x in fresh:
		_log("provider", name, "switched " + x)


func _price(r: Dictionary) -> float:
	if prices == null:
		return 0.0
	var fresh := maxi(0, int(r.input) - int(r.cached))
	var cached_price = prices.get("cached_input") if prices.get("cached_input") != null else prices.get("input", 0)
	return (fresh * Py.num(prices.get("input", 0)) + int(r.cached) * Py.num(cached_price) + int(r.output) * Py.num(prices.get("output", 0))) / 1e6


## A streamed reply raced against silence: a second request after hedge_after seconds of nothing, a reply cut once its
## words are all said and the inner part is late, or when it stalls.
func _race(kind: String, name: String, system0: String, user: String, max_tokens: int, show: Variant, deadline: float, images: Array) -> Dictionary:
	if provider == null:
		return M.reply(false, "", "offline")
	var system := _rated(system0)
	if not _allow(true):
		_log("budget", name, "over budget: answered offline")
		return M.reply(false, "", "over budget")
	var runs := []
	var st := {"winner": null}
	var start := clock()
	_launch(runs, st, kind, name, system, user, max_tokens, show, deadline, images)
	while true:
		await Http.frame()
		var now := clock()
		if st.winner == null:
			for r in runs:
				if r.done and r.reply.ok and r.reply.text != "":
					st.winner = r
					if show is Callable:
						show.call(r.reply.text)
					break
		var w = st.winner
		if w != null:
			if w.done:
				return w.reply
			var said_all: bool = w.mark != null and now - w.mark >= _grace()
			if said_all or now - w.last >= stall_after or now - start >= deadline:
				stats_of.cut_replies += 1
				var why := "inner part late" if said_all else ("stalled" if now - start < deadline else "deadline")
				_log("cut", name, kind + ": " + why + " after " + Py.fixed(now - start, 1) + " s; kept what was said")
				var cut := M.reply(true, w.text, null, 0, 0, 0, now - start)
				cut.cut = true
				return cut
			continue
		var all_done := true
		for r in runs:
			if not r.done:
				all_done = false
		if all_done:
			return runs[runs.size() - 1].reply
		if runs.size() == 1 and now - start >= hedge_after and now - start < deadline - 1 and not _patient() and _allow(true):
			stats_of.hedged += 1
			_log("hedge", name, kind + ": nothing said after " + Py.fixed(now - start, 1) + " s, asking again")
			_launch(runs, st, kind, name, system, user, max_tokens, show, deadline, images)
		if now - start >= deadline:
			return M.reply(false, "", "timed out after " + Py.fixed(deadline, 1) + " s", 0, 0, 0, now - start)
	return M.reply(false)


func _launch(runs: Array, st: Dictionary, kind: String, name: String, system: String, user: String, max_tokens: int, show: Variant,
		deadline: float, images: Array) -> void:
	var run := {"text": "", "last": 0.0, "mark": null, "reply": null, "done": false}
	runs.append(run)
	var on_text := func(piece: String) -> void:
		run.text += piece
		run.last = clock()
		if run.mark == null and run.text.contains(Souls.MARK):
			run.mark = run.last
		if st.winner == null:
			st.winner = run
		if is_same(st.winner, run) and show is Callable:
			show.call(piece)
	_run_into(run, kind, name, system, user, {"json": false, "max_tokens": max_tokens, "timeout": deadline, "on_text": on_text,
		"images": images if not images.is_empty() else null})


func _run_into(run: Dictionary, kind: String, name: String, system: String, user: String, o: Dictionary) -> void:
	var r: Dictionary = await _provider_for(kind).complete(system, user, o)
	_account(kind, name, r)
	run.reply = r
	run.done = true


func _patient() -> bool:
	return provider != null and provider.has_method("patient") and provider.patient()


func _grace() -> float:
	return maxf(inner_grace, 5.0) if _patient() else inner_grace


func _reply_deadline() -> float:
	return minf(call_timeout, 8.0) if not _patient() else maxf(minf(call_timeout, 8.0), 15.0)


func _pictures(name: String, image: Variant) -> Array:
	var r := M.picture_of(image)
	if r[1] != "":
		_log("refused", name, "image: " + r[1])
		return []
	return [r[0]] if r[0] != null else []


func _background(task: Callable) -> void:
	busy += 1
	queue.append(task)
	_pump()


func _pump() -> void:
	while running < 3 and not queue.is_empty() and not closed:
		var task: Callable = queue.pop_front()
		running += 1
		_run_task(task)


func _run_task(task: Callable) -> void:
	await task.call()
	running -= 1
	busy -= 1
	_pump()


## Waits until background work (banks, decisions, pools, cards) is done; false when it timed out.
func wait_idle(timeout := 10.0) -> bool:
	var end := clock() + timeout
	while busy > 0 and clock() < end:
		await Http.frame()
	return busy <= 0


func _context(session: String, name: Variant, query := "", personal := true) -> String:
	var st = state_of.get(session)
	var notes: Array = memory.recall(session, [name, "world"] if name != null else ["world"], query, 6, personal)
	return Prompts.context(notes, st, opinions(session, name) if name != null else null)


# ---------------- character ----------------

func character(session: String, name: Variant, spec := {}, from_config := false) -> Variant:
	var made := Lines.character(name, spec)
	if made[0] == null:
		_raise(made[1])
		return null
	var c = made[0]
	var key: String = session + SEP + c.name
	if not characters.has(key) and characters.size() >= MAX_CHARACTERS:
		_log("refused", c.name, "too many characters (" + str(MAX_CHARACTERS) + "): not stored")
		return c
	characters[key] = c
	declared[key] = true
	if not from_config:
		game_declared[key] = true
	_log("character", c.name, c.personality)
	if not c.tool_refs.is_empty():
		_bind_tools(session, c, not _game_tools(session).is_empty())
	_give_soul(session, c, spec.get("soul"))
	for event in c.events:
		_refill(session, c, event, c.events[event])
	return c


func _game_tools(session: String) -> Dictionary:
	return tool_sets.get(session, cfg_tools)


func _bind_tools(session: String, c, tell := false) -> void:
	var shapes := _game_tools(session)
	var names: Array = shapes.keys() if c.tool_refs.has("*") else c.tool_refs.filter(func(n): return n != "*")
	var tools: Dictionary = c.own_tools.duplicate()
	var missing := []
	for n in names:
		if c.own_tools.has(n):
			continue
		if shapes.has(n):
			tools[n] = shapes[n]
		else:
			missing.append(n)
	c.tools = tools
	c.trust = {}
	for k in c.trust_wanted:
		if tools.has(k):
			c.trust[k] = c.trust_wanted[k]
	if not missing.is_empty() and tell:
		_log("refused", c.name, "tools: " + ", ".join(missing) + " not declared by the game (kl.tools({...}) or \"tools\" in kinloom.json)")


static func _sorted_keys(d: Dictionary) -> Array:
	var keys := d.keys()
	keys.sort()
	return keys


func tools(session: String, given: Variant = null) -> Array:
	if given == null:
		return _sorted_keys(_game_tools(session))
	var pt := Lines.parse_tools(given)
	if pt[0] == null:
		_raise(pt[1])
		return []
	tool_sets[session] = pt[0]
	for key in characters:
		if key.begins_with(session + SEP) and not characters[key].tool_refs.is_empty():
			_bind_tools(session, characters[key], true)
	var names := _sorted_keys(pt[0])
	_log("tools", "game", ", ".join(names) if not names.is_empty() else "none")
	return names


func prepare(session: String, timeout := 10.0) -> Dictionary:
	var t = Py.finite(timeout)
	var done: bool = await wait_idle(clampf(t if t != null else 0.0, 0.0, 300.0))
	var writing := false
	for key in characters:
		var c = characters[key]
		if key.begins_with(session + SEP) and c.card != null and not c.card_ready:
			writing = true
	return {"ready": done and not writing, "waiting": busy, "online": provider != null}


# ---------------- souls ----------------

func _give_soul(session: String, c, soul: Variant) -> void:
	if soul == null or (typeof(soul) == TYPE_BOOL and not soul):
		return
	if soul is Dictionary:
		var card := Souls.card(soul, c.personality)
		if not _allowed(card):
			_log("refused", c.name, "soul: blocked by the content filter")
			card = Souls.card({}, c.personality)
		c.card = card
		c.card_ready = true
		c.soul_key = Souls.seed_key(Py.dumps(card, true, true))
		if c.personality == "":
			c.personality = card.summary
		_prepare_greeting(session, c)
		return
	var seed: String = c.personality if typeof(soul) == TYPE_BOOL else Py.clean(Py.text_of(soul)).substr(0, 600)
	if seed == "":
		return
	if c.personality == "":
		c.personality = seed
	var key := Souls.seed_key(seed + "|" + " / ".join(lore(session)))
	c.soul_key = key
	var saved = memory.get_value("souls", key)
	if saved is Dictionary and saved.get("card") is Dictionary:
		c.card = Souls.card(saved.card, seed)
		c.card_ready = true
		_prepare_greeting(session, c)
		return
	c.card = Souls.card({}, seed)
	c.card_ready = provider == null
	if provider == null:
		return
	if not card_waiters.has(key):
		card_waiters[key] = []
	card_waiters[key].append([session, c])
	if card_waiters[key].size() > 1:
		return
	_background(_write_card.bind(session, c, seed, key))


func _write_card(session: String, c, seed: String, key: String) -> void:
	var card = null
	var r: Dictionary = await _ask("soul", c.name, Prompts.soul_system(c, _lang(c)), Prompts.soul_user(seed, lore(session)), true, false, 900)
	var data = Py.find_json(r.text) if r.ok else null
	if not (data is Dictionary):
		_log("refused", c.name, "soul: no usable card (" + (str(r.error) if r.error != null else "not JSON") + ")")
	else:
		card = Souls.card(data, seed)
		if not _allowed(card):
			_log("refused", c.name, "soul: blocked by the content filter")
			card = null
		else:
			memory.put("souls", key, {"card": card})
			_log("soul", c.name, card.summary)
	var all: Array = card_waiters.get(key, [])
	card_waiters.erase(key)
	for w in all:
		if card != null:
			w[1].card = card
		w[1].card_ready = true
		_prepare_greeting(w[0], w[1])


func _prepare_greeting(session: String, c) -> void:
	if provider == null or c.card == null or c.soul_key == null:
		return
	var key: String = c.name + SEP + str(c.soul_key)
	if greetings.has(key) or greeting_busy.has(key):
		return
	greeting_busy[key] = true
	_background(_write_greeting.bind(session, c, key))


func _write_greeting(session: String, c, key: String) -> void:
	var m := _mood(session, c)
	var system := Prompts.chat_system(c, _lang(c, true), _card_lines(c), lore(session), "greet")
	var secrets := not Souls.secrets(c.card).is_empty()
	var user := _context(session, c.name, "", false) + Prompts.bond_block("this stranger", null, "", 0.0, [], m[0], Souls.strength(m[1]) if m[1] else "", "", secrets) + \
		Prompts.message_block("A stranger", "")
	var r: Dictionary = await _ask("greet", c.name, system, user, false, false, 400)
	if r.ok:
		var parts := Souls.split(r.text)
		var said: String = Souls.drop_narrated(parts[0], Souls.inner_of_reply(parts[1]).gesture, Souls.quirks(c.card))[0]
		var text := Stream.cap(_clean_reply(said, c.name), c.reply_words, c.max_chars)
		var allowed := Lines.allowed_numbers([state_of.get(session), c.personality, Souls.texts(c.card)])
		if text != "" and Lines.bad_numbers(text, allowed).is_empty() and greetings.size() < MAX_CHARACTERS:
			greetings[key] = [text, parts[1]]
	greeting_busy.erase(key)


## World facts every character takes as true (lines: a list or a text, one per line); null reads them.
func lore(session: String, given: Variant = null) -> Variant:
	if given == null:
		if not lore_by.has(session):
			var saved = memory.get_value("lore", session)
			if saved is Array:
				var l := []
				for x in saved:
					l.append(Py.text_of(x))
				lore_by[session] = l
			else:
				lore_by[session] = false
		var cached = lore_by[session]
		if typeof(cached) == TYPE_BOOL:
			return cfg_lore.duplicate()
		return cached.duplicate()
	var items: Array = []
	if typeof(given) == TYPE_STRING:
		items = Array(given.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
	elif given is Array:
		items = given
	var clean := []
	for i in items:
		var t := Py.squash(Py.clean(Py.text_of(i))).substr(0, 300)
		if t != "":
			clean.append(t)
	clean = clean.slice(0, 60)
	lore_by[session] = clean
	memory.put("lore", session, clean)
	_log("lore", "world", str(clean.size()) + " facts")
	return clean.size()


func _card_lines(c) -> Array:
	if c.card == null:
		return []
	var lines := Souls.describe(c.card)
	if not lines.is_empty() and c.card.summary == c.personality:
		lines = lines.slice(1)
	return lines


func _mood(session: String, c) -> Array:
	return Souls.mood_now(moods.get(session + SEP + c.name), clock(), Souls.field(c.card, "mood"))


func _bond_table(session: String) -> Dictionary:
	if not bonds.has(session):
		var saved = memory.get_value("bonds", session)
		var table := {}
		if saved is Dictionary:
			for a in saved:
				var row = saved[a]
				if not (row is Dictionary):
					continue
				var out := {}
				for b in row:
					var v = row[b]
					if v is Dictionary and Py.finite(v.get("last")) != null:
						out[b] = {"talks": int(Py.num(v.get("talks", 1))), "first": Py.num(v.get("first", 0)), "last": Py.num(v.get("last", 0))}
				table[a] = out
		bonds[session] = table
	return bonds[session]


func _known(session: String, name: String, speaker: String, k := 6) -> Array:
	var notes := []
	for n in memory.notes(session, name):
		if n.get("about") == speaker and Py.num(n.importance) >= 0.6:
			notes.append(n)
	notes = Py.stable_sort(notes, func(a, b): return a.importance > b.importance or (a.importance == b.importance and a.t > b.t))
	notes = Py.stable_sort(notes.slice(0, k), func(a, b): return a.t < b.t)
	var out := []
	for n in notes:
		out.append(n.text)
	return out


## What changed inside after a reply: mood, feelings, memories, gesture, the actions decided while talking.
func _inner(session: String, c, speaker: String, data: Variant) -> Array:
	var i := Souls.inner_of_reply(data)
	var key: String = session + SEP + c.name
	if i.mood != null and _allowed(i.mood):
		moods[key] = {"word": i.mood, "level": i.intensity, "t": clock()}
	if i.feel != null and i.feel != 0:
		var change: float = i.feel
		if change > 0:
			var now := wall()
			var rkey := key + SEP + speaker
			var rise: Array = rises.get(rkey, [now, 0.0, -1e18])
			if now - rise[2] > Souls.NEW_TALK:
				rise = [now, 0.0, rise[2]]
			change = maxf(0.0, minf(change, Souls.TALK_RISE - rise[1]))
			rises[rkey] = [rise[0], rise[1] + change, now]
			if change < i.feel:
				_log("refused", c.name, "feel: " + speaker + " already won " + Py.fixed(Souls.TALK_RISE, 1, true) + " this conversation")
		if change != 0:
			feel(session, c.name, speaker, change)
	if i.self != "" and _allowed(i.self):
		memory.add(session, c.name, i.self, 0.9, {"about": Lines.SELF})
	if i.remember != "":
		if _allowed(i.remember):
			memory.add(session, c.name, i.remember, 0.8, {"about": speaker})
		else:
			_log("refused", c.name, "remember: blocked by the content filter")
	var fresh: bool = i.gesture != "" and _allowed(i.gesture) and not Souls.same_action(i.gesture, gesture_seen.get(key, ""))
	gesture_seen[key] = Py.lower(i.gesture)
	if fresh:
		gestures[key] = i.gesture
	else:
		gestures.erase(key)
	if not i.do.is_empty() and not c.tools.is_empty():
		var actions := _valid_actions(c, Py.dumps({"actions": i.do}))
		var feeling := opinion(session, c.name, speaker)
		var kept := []
		for a in actions:
			var need: float = c.trust.get(a[0], -2.0)
			if feeling < need:
				_log("refused", c.name, a[0] + ": needs a feeling of " + Py.fixed(need, 1, true) + " for " + speaker + " (has " + Py.fixed(feeling, 2, true) + ")")
			else:
				kept.append(a)
		if not kept.is_empty():
			var decided := []
			for a in kept:
				decided.append({"tool": a[0], "args": a[1], "taken": false})
			if not pending.has(key):
				pending[key] = {"actions": [], "at": null, "thinking": false}
			var entry: Dictionary = pending[key]
			var waiting: Array = entry.actions.filter(func(a): return not a.taken)
			if decided.size() < MAX_WAITING:
				waiting = waiting.slice(maxi(0, waiting.size() - (MAX_WAITING - decided.size())))
				waiting.append_array(decided)
				entry.actions = waiting
			else:
				entry.actions = decided
			for a in kept:
				_log("act", c.name, a[0] + "(" + Py.dumps(a[1]) + ") while talking to " + speaker)
			return decided
	return []


func _recollect(session: String, c, speaker: String, said: Array) -> void:
	if provider == null or said.is_empty():
		return
	_background(_write_recollection.bind(session, c, speaker, said))


func _write_recollection(session: String, c, speaker: String, said: Array) -> void:
	var l := []
	for x in said:
		l.append(str(x[0]) + ": " + str(x[1]))
	var user := "Conversation with " + speaker + ":\n" + "\n".join(l) + "\n"
	var r: Dictionary = await _ask("recollect", c.name, Prompts.recollect_system(c, _lang(c)), user, true, false, 250)
	var data = Py.find_json(r.text) if r.ok else null
	var summary := Souls.soul_text(data.get("summary"), 280) if data is Dictionary else ""
	if summary != "" and _allowed(summary):
		memory.add(session, c.name, "Earlier with " + speaker + ": " + summary, 0.65, {"about": speaker})


func soul(session: String, name: Variant, speaker: Variant = null) -> Dictionary:
	var c = char_of(session, name)
	var m := _mood(session, c)
	var table := _bond_table(session)
	var row := {}
	var mine: Dictionary = table.get(c.name, {})
	for who in mine:
		var b: Dictionary = mine[who].duplicate()
		b["feeling"] = opinion(session, c.name, who)
		row[who] = b
	var sp = Lines.name_of(speaker)
	var talk := []
	if Py.truthy(speaker):
		for x in history.get(session + SEP + c.name + SEP + str(sp if sp != null else ""), []):
			talk.append(x.duplicate())
	var memories: Array = memory.all(session, c.name)
	return {"name": c.name, "personality": c.personality, "card": c.card.duplicate() if c.card != null else null,
		"ready": c.card_ready if c.card != null else true, "mood": {"word": m[0], "level": m[1]}, "bonds": row,
		"memories": memories.slice(maxi(0, memories.size() - 20)), "tools": _sorted_keys(c.tools),
		"gesture": gestures.get(session + SEP + c.name, ""), "lore": lore(session).size(), "conversation": talk}


# ---------------- say ----------------

func _mapping(value: Variant, what: String) -> Dictionary:
	if value == null:
		return {}
	if value is Dictionary:
		return value.duplicate()
	var kind := "list" if value is Array else ("str" if typeof(value) == TYPE_STRING else type_string(typeof(value)))
	_raise(what + ": an object {name: value}, got " + kind, true)
	return {}


## {text, source, actions}.
func say(session: String, name: Variant, event: Variant, facts0: Variant = null, fresh := false, max_chars: Variant = null) -> Dictionary:
	var c = char_of(session, name)
	var facts := _mapping(facts0, "facts")
	if _fault != "":
		return {}
	var ev := Lines.event_key(event)
	var box := Lines.box_limit(max_chars)
	var limit_c: int = box if box > 0 else c.max_chars
	if fresh and provider != null:
		var r: Dictionary = await _ask("line", c.name, Prompts.line_system(c, c.moment(ev), _sorted_keys(facts), _lang(c), limit_c),
			_context(session, c.name, ev) + Prompts.facts_block(facts), false, true, 120)
		if r.ok:
			var t = Py.find_json(r.text)
			var line = t.get("line") if t is Dictionary else r.text
			var v := _valid_line(Py.text_of(line), facts.keys(), c)
			if v[0]:
				var said := Stream.fit_chars(Lines.fill(v[1], facts), limit_c)
				_log("say", c.name, said, {"event": ev, "source": "fresh"})
				return {"text": said, "source": "model", "actions": []}
	var key: String = session + SEP + c.name + SEP + ev
	var names := facts.keys()
	if not banks.has(key):
		banks[key] = {"templates": [], "unused": [], "recent": [], "filling": false, "failures": 0}
	var bank: Dictionary = banks[key]
	var usable := []
	for t in bank.unused:
		if _all_in(Lines.placeholders(t), names):
			usable.append(t)
	var known := []
	for t in bank.templates:
		if _all_in(Lines.placeholders(t), names):
			known.append(t)
	var template = null
	var fresh_ones := _fitting(usable, facts, limit_c)
	var old_ones := _fitting(known, facts, limit_c)
	if not fresh_ones.is_empty() or (not usable.is_empty() and old_ones.is_empty()):
		var from: Array = fresh_ones if not fresh_ones.is_empty() else usable
		template = from[randi() % from.size()]
		bank.unused.erase(template)
	elif not old_ones.is_empty() or not known.is_empty():
		var pool: Array = old_ones if not old_ones.is_empty() else known
		var not_recent := pool.filter(func(t): return not bank.recent.has(t))
		var from: Array = not_recent if not not_recent.is_empty() else pool
		template = from[randi() % from.size()]
	if template != null:
		bank.recent.append(template)
		if bank.recent.size() > 3:
			bank.recent.pop_front()
	var low := usable.size() - (1 if template != null and usable.has(template) else 0) < 3
	if low:
		var sorted_names := names.duplicate()
		sorted_names.sort()
		_refill(session, c, ev, sorted_names, limit_c)
	if template != null:
		var said := Stream.fit_chars(Lines.fill(template, facts), limit_c)
		_log("say", c.name, said, {"event": ev, "source": "bank"})
		return {"text": said, "source": "prepared", "actions": []}
	var said := _offline_line(c, ev, facts, limit_c)
	stats_of.offline_answers += 1
	_log("say", c.name, said, {"event": ev, "source": "offline"})
	if said == "":
		_tell_empty(session, c.name, "say " + ev, c.name + " has no line for " + Py.py_repr(ev) + ": say() answered \"\" (give it lines " +
			"for this event, or \"*\" lines, that only use the facts passed)")
	return {"text": said, "source": "offline", "actions": []}


static func _all_in(items: Array, names: Array) -> bool:
	for p in items:
		if not names.has(p):
			return false
	return true


static func _fitting(templates: Array, facts: Dictionary, limit_c: int) -> Array:
	if limit_c <= 0:
		return templates
	return templates.filter(func(t): return Lines.fill(t, facts).length() <= limit_c)


func _tell_empty(session: String, name: String, what: String, text: String) -> void:
	var key := session + SEP + name + SEP + what
	if empty_told.has(key):
		return
	if empty_told.size() < 2000:
		empty_told[key] = true
	_log("empty", name, text)


func _offline_line(c, event: String, facts: Dictionary, limit_c := 0) -> String:
	var ek := Lines.event_key(event)
	var options: Array = c.lines[ek] if c.lines.has(ek) and not c.lines[ek].is_empty() else c.lines.get("*", [])
	var names := facts.keys()
	var usable := []
	for t in options:
		if _all_in(Lines.placeholders(t), names):
			usable.append(t)
	var fits: Array = usable.filter(func(t): return Lines.fill(t, facts).length() <= limit_c) if limit_c > 0 else []
	var from: Array = fits if not fits.is_empty() else usable
	return Lines.fill(from[randi() % from.size()], facts) if not usable.is_empty() else ""


func _written() -> String:
	return DEFAULT_LANGUAGE if Py.lower(Py.strip(language)) == AUTO else language


func _lang(c, chat := false) -> String:
	var lang: String = c.language if c.language != "" else language
	if Py.lower(Py.strip(lang)) == AUTO:
		return AUTO if chat else DEFAULT_LANGUAGE
	return lang


## False when any text in the value is blocked by the content filter.
func _allowed(value: Variant) -> bool:
	if banned == null and content_filter == null:
		return true
	var texts := []
	_texts_in(value, texts)
	for t in texts:
		if banned != null and banned.search(Py.lower(t)) != null:
			return false
		if content_filter != null and not content_filter.call(t):
			return false
	return true


static func _texts_in(x: Variant, out: Array) -> void:
	if typeof(x) == TYPE_STRING:
		out.append(x)
	elif x is Array:
		for v in x:
			_texts_in(v, out)
	elif x is Dictionary:
		for k in x:
			_texts_in(x[k], out)


## [ok, line]. fact_names: null (any) or a list.
func _valid_line(line0: String, fact_names: Variant, c) -> Array:
	var line := Py.strip(Py.strip_chars(Py.strip(Py.clean(line0)), "\""))
	if not _allowed(line):
		return [false, null]
	if line == "" or line.length() > Lines.MAX_LINE or Py.split(line).size() > c.line_words + 6:
		return [false, null]
	var rest := Py.re(Lines.PLACEHOLDER).sub(line, "", true)
	if c.max_chars > 0 and rest.length() > c.max_chars:
		return [false, null]
	if fact_names != null and not _all_in(Lines.placeholders(line), fact_names):
		return [false, null]
	if Py.re(Lines.DIGIT).search(rest) != null or rest.contains("{") or rest.contains("}") or Py.re(Lines.META).search(rest) != null:
		return [false, null]
	return [true, line]


func _refill(session: String, c, event: String, names: Variant, chars := 0) -> void:
	var key: String = session + SEP + c.name + SEP + event
	if provider == null:
		return
	if not banks.has(key):
		banks[key] = {"templates": [], "unused": [], "recent": [], "filling": false, "failures": 0}
	var bank: Dictionary = banks[key]
	if bank.filling or bank.failures >= 3:
		return
	bank.filling = true
	_background(_write_lines.bind(session, c, event, names, chars, bank))


func _write_lines(session: String, c, event: String, names: Variant, chars: int, bank: Dictionary) -> void:
	var r: Dictionary = await _ask("lines", c.name, Prompts.lines_system(c, c.moment(event), names, BANK_SIZE, _lang(c), chars),
		_context(session, c.name, event), true, false, 700)
	var added := 0
	if r.ok:
		var data = Py.find_json(r.text)
		var got = data.get("lines") if data is Dictionary else (data if data is Array else null)
		for line in (got if got is Array else []).slice(0, BANK_SIZE * 2):
			var v := _valid_line(Py.text_of(line), names, c)
			if v[0] and not bank.templates.has(v[1]):
				bank.templates.append(v[1])
				bank.unused.append(v[1])
				added += 1
	bank.failures = 0 if added > 0 else bank.failures + 1
	_log("bank", c.name, str(added) + " new lines for " + event, {"event": event})
	bank.filling = false


# ---------------- decide ----------------

func decide(session: String, name: Variant, situation0: Variant, choices: Variant, every: Variant = null) -> Variant:
	var c = char_of(session, name)
	var made: Array = ShapeLib.Shape.of(choices if choices is Dictionary else {"choice": choices})
	if made[0] == null:
		_raise(made[1])
		return null
	var shape = made[0]
	var key: String = session + SEP + c.name + SEP + shape.signature()
	var situation: Dictionary = situation0 if situation0 is Dictionary else {"situation": situation0}
	var ev: float = c.every
	if every != null:
		var r := Lines.arg_num(every, "every")
		if r[0] == null:
			_raise(r[1])
			return null
		ev = maxf(0.2, r[0])
	var now := clock()
	if not decisions.has(key):
		decisions[key] = {"value": shape.default_value(), "at": null, "situation": null, "thinking": false}
	var d: Dictionary = decisions[key]
	var due: bool = not d.thinking and (d.at == null or now - d.at >= ev or (now - d.at >= ev / 4 and Lines.changed_situation(d.situation, situation)))
	if due:
		d.thinking = true
		d.situation = situation.duplicate()
	var value = d.value
	if due and provider != null:
		_background(_write_decision.bind(session, c, shape, situation, choices, d))
	elif due:
		d.thinking = false
		d.at = now
	if choices is Dictionary or not (value is Dictionary):
		return value
	return value.get("choice", value) if value.has("choice") and value["choice"] != null else value


func _write_decision(session: String, c, shape, situation: Dictionary, choices: Variant, d: Dictionary) -> void:
	var system := Prompts.decide_system(c, shape, _lang(c))
	var user := _context(session, c.name, Py.dumps(situation)) + Prompts.situation_block(situation)
	var result = await _structured("decide", c.name, system, user, shape, false)
	if result != null:
		d.value = result if choices is Dictionary else result.choice
		_log("decide", c.name, Py.dumps(d.value))
	d.at = clock()
	d.thinking = false


func _structured(kind: String, name: String, system: String, user: String, shape, foreground: bool, max_tokens := 500,
		timeout := 0.0, images: Array = []) -> Variant:
	var r: Dictionary = await _ask(kind, name, system, user, true, foreground, max_tokens, null, timeout, images)
	if not r.ok:
		return null
	var p: Array = shape.parse(r.text)
	if p[0] and not _allowed(p[1]):
		_log("refused", name, kind + ": blocked by the content filter")
		return null
	if p[0]:
		return p[1]
	_log("repair", name, kind + ": " + str(p[2]))
	r = await _ask(kind, name, system, user + Prompts.repair(str(p[2])), true, foreground, max_tokens, null, timeout, images)
	if not r.ok:
		return null
	p = shape.parse(r.text)
	if not p[0]:
		_log("refused", name, kind + ": " + str(p[2]))
		return null
	if not _allowed(p[1]):
		_log("refused", name, kind + ": blocked by the content filter")
		return null
	return p[1]


# ---------------- voice ----------------

func _voice_of(session: String, name: Variant) -> Dictionary:
	if name == null:
		return {"seed": "narrator", "describe": "", "id": null, "language": null}
	var c = char_of(session, name)
	var parts := [c.voice] if c.voice != "" else []
	var talk := Souls.field(c.card, "voice")
	if talk != "":
		parts.append("speaks like this: " + talk.substr(0, 200))
	var word = _mood(session, c)[0] if c.voice != "" or c.card != null else null
	if word != null and word != "calm" and word != "neutral":
		parts.append("right now: " + word)
	return {"seed": c.name, "describe": "; ".join(parts), "id": c.voice_id, "language": c.language if c.language != "" else voice_language}


## {data: WAV bytes, seconds, text} or null.
func speak(session: String, name: Variant, text0: Variant) -> Variant:
	var text := Py.squash(Py.clean(Py.text_of(text0) if text0 != null else "")).substr(0, P.VOICE_MAX_TEXT)
	var who: String = "voice" if name == null else Py.clean(Py.text_of(name)).substr(0, MAX_NAME)
	if text == "" or voice == null or not voice.can_speak():
		return null
	if not _allowed(text):
		_log("refused", who, "speak: blocked by the content filter")
		return null
	var spec := _voice_of(session, name)
	var key := Souls.seed_key(Py.dumps([voice.describe(), spec, text], true, true))
	if voice_cache.has(key):
		return {"data": voice_cache[key], "seconds": M.wav_seconds(voice_cache[key]), "text": text}
	if not _allow(true):
		_log("budget", who, "over budget: not spoken")
		return null
	var start := clock()
	var got: Array = await voice.speak(text, spec, maxf(call_timeout, 15.0))
	stats_of.by_kind["speak"] = stats_of.by_kind.get("speak", 0) + 1
	if got[0] == null:
		stats_of.failures += 1
		_log("error", who, "speak: " + str(got[1]))
		return null
	voice_cache[key] = got[0]
	if voice_cache.size() > 200:
		voice_cache.erase(voice_cache.keys()[0])
	var seconds := M.wav_seconds(got[0])
	_log("speak", who, text.substr(0, 80) + " (" + Py.fixed(seconds, 1) + " s of audio in " + Py.fixed(clock() - start, 2) + " s, " + voice.name + ")")
	return {"data": got[0], "seconds": seconds, "text": text}


func listen(_session: String, audio: Variant, lang: Variant = null) -> String:
	var data = null
	if typeof(audio) == TYPE_STRING:
		data = M.b64decode(audio.substr(audio.find(",") + 1) if audio.begins_with("data:") else audio)
	elif audio is PackedByteArray:
		data = audio
	if data == null or data.is_empty() or voice == null or not voice.can_listen():
		return ""
	if data.size() > MAX_AUDIO:
		_log("refused", "listen", "recording larger than " + str(MAX_AUDIO) + " bytes")
		return ""
	if not _allow(true):
		_log("budget", "listen", "over budget: not heard")
		return ""
	var fmt = M.audio_format(data)
	var start := clock()
	var got: Array = await voice.listen(data, fmt, lang if Py.truthy(lang) else voice_language, maxf(call_timeout, 20.0))
	stats_of.by_kind["listen"] = stats_of.by_kind.get("listen", 0) + 1
	if got[0] == null:
		stats_of.failures += 1
		_log("error", "listen", "listen: " + str(got[1]))
		return ""
	var text := Py.squash(Py.clean(got[0])).substr(0, 2000)
	_log("listen", "listen", Py.py_repr(text.substr(0, 80)) + " (" + (fmt if fmt != null else "audio") + ", " +
		Py.fixed(M.wav_seconds(data) if fmt == "wav" else 0.0, 1) + " s of audio in " + Py.fixed(clock() - start, 2) + " s)")
	return text


# ---------------- act ----------------

## [[tool, args], ...]: what the character decided since the last call.
func act(session: String, name: Variant, situation0: Variant = null, think_now := true) -> Array:
	var c = char_of(session, name)
	if c.tools.is_empty():
		return []
	var key: String = session + SEP + c.name
	var situation: Dictionary = situation0 if situation0 is Dictionary else ({"situation": situation0} if situation0 != null else {})
	var now := clock()
	if not pending.has(key):
		pending[key] = {"actions": [], "at": null, "thinking": false}
	var entry: Dictionary = pending[key]
	var ready := []
	for a in entry.actions:
		if not a.taken:
			ready.append([a.tool, a.args])
		a.taken = true
	entry.actions = []
	var due: bool = think_now and not entry.thinking and (entry.at == null or now - entry.at >= c.every)
	if due:
		entry.thinking = true
	if due and provider != null:
		_background(_write_actions.bind(session, c, situation, entry))
	elif due:
		entry.thinking = false
		entry.at = now
	return ready


func _write_actions(session: String, c, situation: Dictionary, entry: Dictionary) -> void:
	var system := Prompts.act_system(c, _lang(c))
	var user := _context(session, c.name, Py.dumps(situation)) + Prompts.situation_block(situation)
	var r: Dictionary = await _ask("act", c.name, system, user, true, false, 500)
	var actions := _valid_actions(c, r.text) if r.ok else []
	var kept: Array = entry.actions.slice(maxi(0, entry.actions.size() - MAX_WAITING))
	for a in actions:
		kept.append({"tool": a[0], "args": a[1], "taken": false})
	entry.actions = kept
	entry.at = clock()
	for a in actions:
		_log("act", c.name, a[0] + "(" + Py.dumps(a[1]) + ")")
	entry.thinking = false


func _valid_actions(c, text: String) -> Array:
	var data = Py.find_json(text)
	var items = data.get("actions") if data is Dictionary else (data if data is Array else [])
	var out := []
	for item in (items if items is Array else []).slice(0, 5):
		if not (item is Dictionary):
			continue
		var tool = item.get("tool") if Py.truthy(item.get("tool")) else item.get("name")
		if typeof(tool) != TYPE_STRING or not c.tools.has(tool):
			_log("refused", c.name, "unknown tool " + Py.py_repr(tool))
			continue
		var shape = c.tools[tool][0]
		var args: Dictionary = item.args if item.get("args") is Dictionary else {}
		if shape == null:
			out.append([tool, {}])
			continue
		var r: Array = shape.check(args)
		if r[0] and not _allowed(r[1]):
			_log("refused", c.name, tool + ": blocked by the content filter")
		elif r[0]:
			out.append([tool, r[1]])
		else:
			_log("refused", c.name, tool + ": " + str(r[2]))
	return out


# ---------------- minds ----------------

func mind(session: String, name: Variant, personality: Variant = "", senses: Variant = null, actions: Variant = null, rules: Variant = null,
		variants: Variant = 3, learn: Variant = 30.0) -> Variant:
	var made := Minds.declaration(Py.text_of(name), Py.text_of(personality) if Py.truthy(personality) else "", senses, actions, rules,
		3 if variants == null else variants)
	if made[0] == null:
		_raise(made[1])
		return null
	var decl = made[0]
	var key: String = session + SEP + decl.name
	var sig := "%08x" % Rules.fnv1a(Py.dumps([senses, actions, rules, decl.variants, decl.personality], true, true))
	var old = minds.get(key)
	if old != null and old.sig == sig:
		old.learn = Lines.learn_every(learn)
		return _compiled_of(old)
	if old == null and minds.size() >= MAX_CHARACTERS:
		_raise("too many minds (" + str(MAX_CHARACTERS) + ")")
		return null
	for e in decl.rule_errors:
		_log("refused", decl.name, "rules: " + e)
	var saved = memory.get_value("minds", session + "/" + decl.name)
	var programs = null
	if saved is Dictionary and saved.get("sig") == sig and saved.get("variants") is Array:
		var progs := []
		for v in saved.variants.slice(0, decl.variants):
			var p = Rules.validate(v, decl)[0]
			if p != null:
				progs.append(p)
		if not progs.is_empty():
			for i in decl.variants:
				progs.append(decl.offline)
			programs = progs.slice(0, decl.variants)
	var st := Lines.MindState.new(decl, Minds.Mind.new(decl, programs), sig, Lines.learn_every(learn))
	st.args = [personality, senses, actions, rules, variants, learn]
	if programs != null:
		st.generation = int(Py.num(saved.get("generation", 0)))
		var curve := []
		if saved.get("curve") is Array:
			for x in saved.curve:
				if typeof(x) in [TYPE_INT, TYPE_FLOAT]:
					curve.append(x)
		st.curve = curve.slice(maxi(0, curve.size() - 200))
	minds[key] = st
	_log("mind", decl.name, str(decl.order.size()) + " actions, " + str(decl.senses.size()) + " senses, " + str(decl.variants) + " variants" +
		(" (learned, generation " + str(st.generation) + ")" if programs != null else ""))
	var count: int = decl.variants - (1 if Py.truthy(decl.rules) else 0)
	if programs == null and count > 0 and provider != null:
		st.busy = true
		_background(_write_variants.bind(session, st, count))
	return _compiled_of(st)


func _compiled_of(st) -> Dictionary:
	var c: Dictionary = st.mind.compiled().duplicate()
	c["ids"] = st.ids.duplicate()
	return c


func mind_compiled(session: String, name: Variant) -> Variant:
	var st = minds.get(session + SEP + Py.clean(Py.text_of(name)).substr(0, MAX_NAME))
	return _compiled_of(st) if st != null else null


func _mind_programs(name: String, decl, user: String) -> Array:
	var system := Prompts.mind_system(decl, _written())
	for attempt in 2:
		var r: Dictionary = await _ask("mind", name, system, user, true, false, 1500)
		if not r.ok:
			return []
		var data = Py.find_json(r.text)
		var raw = null
		if data is Dictionary and data.has("variants"):
			raw = data.variants
		elif data is Dictionary and data.has("mind"):
			raw = [data.mind]
		elif data is Array:
			raw = data
		else:
			raw = [data]
		var good := []
		var errors := []
		for p in (raw if raw is Array else []).slice(0, Rules.MAX_VARIANTS):
			var v := Rules.validate(p, decl)
			errors.append_array(v[1])
			if v[0] != null and _allowed(v[0]):
				good.append(v[0])
		if not errors.is_empty():
			_log("refused", name, "mind: " + "; ".join(errors.slice(0, 3)))
		if not good.is_empty():
			return good
		var why := "; ".join(errors.slice(0, 6))
		user = user + Prompts.repair(why if why != "" else "no valid variant")
	return []


func _write_variants(session: String, st, count: int) -> void:
	var decl = st.decl
	var progs: Array = await _mind_programs(decl.name, decl, Prompts.minds_user(decl, count, decl.rules))
	if not progs.is_empty():
		var programs := [decl.offline] if Py.truthy(decl.rules) else []
		programs.append_array(progs.slice(0, count))
		for i in decl.variants:
			programs.append(decl.offline)
		programs = programs.slice(0, decl.variants)
		st.mind.set_variants(programs)
		st.ids = []
		for p in programs:
			st.ids.append(st.new_id())
		st.reset_stats(programs.size())
		_log("mind", decl.name, "the model wrote " + str(progs.slice(0, count).size()) + " variants")
		_save_mind(session, st)
	st.busy = false


func think(session: String, name: Variant, senses: Variant, who: Variant = null) -> Dictionary:
	var st = minds.get(session + SEP + Py.text_of(name))
	if st == null:
		st = minds.get(session + SEP + Py.clean(Py.text_of(name)).substr(0, MAX_NAME))
	if st == null:
		return {"action": null, "args": {}, "variant": 0}
	var choice: Dictionary = st.mind.think(senses, who)
	if who != null:
		if st.units.size() >= Rules.MAX_UNITS and not st.units.has(who):
			st.units.clear()
		st.units[who] = [choice.variant, st.ids[choice.variant], choice.action, senses.duplicate() if senses is Dictionary else {}]
	return choice


func explain(session: String, name: Variant, senses: Variant, who: Variant = null) -> Variant:
	var st = minds.get(session + SEP + Py.clean(Py.text_of(name)).substr(0, MAX_NAME))
	return st.mind.explain(senses, who) if st != null else null


func reward(session: String, who: Variant, value: Variant, mind_name: Variant = null, variant: Variant = null, vid: Variant = null,
		action: Variant = null, senses: Variant = null, done := false) -> bool:
	var v = Py.finite(value)
	if v == null:
		return false
	v = clampf(v, -1000.0, 1000.0)
	var st = null
	var unit = null
	for k in minds:
		if not k.begins_with(session + SEP) or (mind_name != null and k != session + SEP + str(mind_name)):
			continue
		var s = minds[k]
		if variant != null and mind_name != null:
			st = s
			unit = [variant, vid, action, senses if senses is Dictionary else {}]
			break
		if s.units.has(who):
			st = s
			unit = s.units[who]
			break
	if st == null or unit == null:
		return false
	var index = unit[0]
	if typeof(index) != TYPE_INT or index < 0 or index >= st.ids.size():
		return false
	if unit[1] != null and not Py.equal(unit[1], st.ids[index]):
		return false
	var sens = unit[3]
	var act_name = unit[2]
	var stat: Array = st.stats[index]
	stat[0] += 1
	stat[1] += v
	stat[2] += v * v
	st.window[0] += 1
	st.window[1] += v
	st.samples[index].append([sens, act_name, v])
	if st.samples[index].size() > 12:
		st.samples[index].pop_front()
	_credit(st, who, sens, act_name, v, done)
	var ep = st.open.get(who)
	if ep == null:
		if st.open.size() >= Rules.MAX_UNITS:
			st.open.clear()
		ep = [index, st.ids[index], 0.0]
		st.open[who] = ep
	ep[2] += v
	if done:
		st.episodic = true
		st.open.erase(who)
		if ep[1] == st.ids[ep[0]]:
			var e: Array = st.episodes[ep[0]]
			e[0] += 1
			e[1] += ep[2]
			e[2] += ep[2] * ep[2]
	var now := clock()
	if st.last_learn == null:
		st.last_learn = now
	var need := MIN_EPISODES if st.episodic else MIN_SAMPLES
	var enough := true
	for sc in st.scores():
		if sc[0] < need:
			enough = false
	if st.learn > 0 and not st.busy and st.ids.size() >= 2 and now - st.last_learn >= st.learn and enough:
		st.busy = true
		_learn_step(session, st)
	return true


func _credit(st, who: Variant, senses: Variant, action: Variant, v: float, done: bool) -> void:
	var trace = st.trace.get(who)
	if trace == null:
		if st.trace.size() >= Rules.MAX_UNITS:
			st.trace.clear()
		trace = []
		st.trace[who] = trace
	var last = trace[trace.size() - 1] if not trace.is_empty() else null
	if last == null or Py.dumps(last[0], true, true) != Py.dumps(senses, true, true) or last[1] != action:
		trace.append([senses, action, 0.0, 1.0])
	for e in trace:
		e[2] += e[3] * v
		e[3] *= GAMMA
	var cutoff := pow(GAMMA, 10)
	while not trace.is_empty() and (done or trace[0][3] < cutoff):
		var e: Array = trace.pop_front()
		st.buffer.append([e[0], e[1], e[2]])
		if st.buffer.size() > BUFFER:
			st.buffer.pop_front()


func _learn_step(session: String, st) -> void:
	var decl = st.decl
	var scores: Array = st.scores()
	var means := []
	for sc in scores:
		means.append(sc[1] / sc[0])
	var best := 0
	for i in range(1, means.size()):
		if Lines.bound(scores[i], -1) > Lines.bound(scores[best], -1):
			best = i
	var worst := -1
	for i in means.size():
		if i != best and (worst < 0 or Lines.bound(scores[i], 1) <= Lines.bound(scores[worst], 1)):
			worst = i
	st.curve.append(Py.round_to(st.window[1] / st.window[0], 4) if st.window[0] else 0.0)
	st.curve = st.curve.slice(maxi(0, st.curve.size() - 200))
	st.window = [0, 0.0]
	var best_prog: Dictionary = st.mind.variants[best]
	var worst_prog: Dictionary = st.mind.variants[worst]
	var samples: Array = Py.stable_sort(st.samples[worst].duplicate(), func(a, b): return a[2] < b[2]).slice(0, 6)
	var n_best: int = scores[best][0]
	var n_worst: int = scores[worst][0]
	var moments: Array = st.buffer.duplicate()
	var plan := {"st": st, "best": best, "worst": worst, "means": means}
	if provider == null:
		var made := _local_change(st, best_prog, moments)
		_replace_variant(session, plan, made[0], made[1])
		return
	_background(_write_learning.bind(session, plan, best_prog, worst_prog, samples, n_best, n_worst, moments))


func _local_change(st, best_prog: Dictionary, moments: Array) -> Array:
	var prog := best_prog
	var hows := []
	var times := 2 if st.rnd.random() < COMPOUND else 1
	for i in times:
		var step = Rules.propose(prog, st.decl, moments, st.rnd) if st.rnd.random() < 0.6 else null
		if step != null:
			prog = step
			hows.append("a change the data supports")
		else:
			prog = Rules.mutate(prog, st.decl, st.rnd)
			hows.append("a mutation")
	return [prog, " and ".join(hows)]


func _write_learning(session: String, plan: Dictionary, best_prog: Dictionary, worst_prog: Dictionary, samples: Array, n_best: int,
		n_worst: int, moments: Array) -> void:
	var st = plan.st
	var decl = st.decl
	var user := Prompts.mind_learn_user(best_prog, plan.means[plan.best], worst_prog, plan.means[plan.worst], samples, n_best, n_worst,
		Rules.evidence(decl, moments))
	var progs: Array = await _mind_programs(decl.name, decl, user)
	var chosen = null
	for p in progs:
		if not Rules.same_program(p, best_prog):
			chosen = p
			break
	if chosen != null:
		_replace_variant(session, plan, chosen, "the model's rewrite")
	else:
		var made := _local_change(st, best_prog, moments)
		_replace_variant(session, plan, made[0], made[1])
	st.busy = false


func _replace_variant(session: String, plan: Dictionary, prog: Dictionary, how: String) -> void:
	var st = plan.st
	var worst: int = plan.worst
	st.mind.set_variant(worst, prog)
	st.ids[worst] = st.new_id()
	st.stats[worst] = [0, 0.0, 0.0]
	st.episodes[worst] = [0, 0.0, 0.0]
	st.samples[worst] = []
	st.generation += 1
	st.last_learn = clock()
	st.busy = false
	_log("learn", st.decl.name, "generation " + str(st.generation) + ": variant " + str(worst) + " (mean " + Py.fixed(plan.means[worst], 3) +
		") replaced by " + how + " of the best (mean " + Py.fixed(plan.means[plan.best], 3) + ")", {"generation": st.generation})
	_save_mind(session, st)


func _save_mind(session: String, st) -> void:
	memory.put("minds", session + "/" + st.decl.name, {"sig": st.sig, "variants": st.mind.variants.duplicate(), "generation": st.generation,
		"curve": st.curve.duplicate()})


func mind_report(session: String, name: Variant) -> Variant:
	var st = minds.get(session + SEP + Py.clean(Py.text_of(name)).substr(0, MAX_NAME))
	if st == null:
		return null
	var scores: Array = st.scores()
	var variants := []
	for i in st.stats.size():
		variants.append({"id": st.ids[i], "rewards": st.stats[i][0], "episodes": st.episodes[i][0],
			"mean": Py.round_to(scores[i][1] / scores[i][0], 4) if scores[i][0] else null, "rules": st.mind.variants[i].duplicate(true)})
	return {"name": st.decl.name, "version": st.mind.version, "generation": st.generation, "curve": st.curve.duplicate(),
		"per": "episode" if st.episodic else "decision", "variants": variants}


func mind_names(session: String) -> Array:
	var out := []
	for k in minds:
		if k.begins_with(session + SEP):
			out.append(k.substr(session.length() + 1))
	return out


# ---------------- create ----------------

func create(session: String, what0: Variant, example: Variant, ctx: Variant = null, count: Variant = null, instant := false,
		timeout := 0.0, image: Variant = null) -> Variant:
	if Py.truthy(count) and example is Array and example.size() == 1:
		example = example[0]
	var made: Array = ShapeLib.Shape.of(example)
	if made[0] == null:
		_raise(made[1])
		return null
	var shape = made[0]
	var what := Py.clean(Py.text_of(what0)).substr(0, 200)
	var pictures: Array = _pictures(what, image) if image != null else []
	if instant:
		if not pictures.is_empty():
			_log("refused", what, "image: not used with instant=True (those items are made ahead)")
		return _from_pool(session, what, shape, ctx)
	if Py.truthy(count):
		var r := Lines.arg_num(count, "count")
		if r[0] == null:
			_raise(r[1])
			return null
		var n := clampi(int(r[0]), 1, 50)
		var items: Array = await _create_many(session, what, shape, ctx, n, true, timeout, pictures)
		while items.size() < n:
			items.append(shape.default_value())
		return items
	if provider == null:
		return shape.default_value()
	var system := Prompts.create_system(what, shape, _written())
	var user := _context(session, null, what) + Prompts.context_block(ctx) + Prompts.picture_block(not pictures.is_empty())
	var value = await _structured("create", what, system, user, shape, true, 800, timeout, pictures)
	if value == null:
		stats_of.offline_answers += 1
		return shape.default_value()
	_log("create", what, Py.dumps(value).substr(0, 300))
	return value


func _create_many(session: String, what: String, shape, ctx: Variant, count: int, foreground: bool, timeout := 0.0, pictures: Array = []) -> Array:
	if provider == null:
		return []
	var system := Prompts.create_many_system(what, shape, count, _written())
	var user := _context(session, null, what) + Prompts.context_block(ctx) + Prompts.picture_block(not pictures.is_empty())
	var r: Dictionary = await _ask("create", what, system, user, true, foreground, mini(4000, 200 + 150 * count), null, timeout, pictures)
	if not r.ok:
		return []
	var data = Py.find_json(r.text)
	var raw = data.get("items") if data is Dictionary else (data if data is Array else [])
	var items := []
	for item in (raw if raw is Array else []):
		var c: Array = shape.check(item)
		if c[0] and _allowed(c[1]):
			items.append(c[1])
		if items.size() >= count:
			break
	_log("create", what, str(items.size()) + " items")
	return items


func _from_pool(session: String, what: String, shape, ctx: Variant) -> Variant:
	var key: String = session + SEP + what + SEP + shape.signature()
	if not pools.has(key):
		pools[key] = {"items": [], "filling": false, "failures": 0}
	var pool: Dictionary = pools[key]
	var has_item: bool = not pool.items.is_empty()
	var item = pool.items.pop_front() if has_item else null
	if pool.items.size() < 2 and not pool.filling and pool.failures < 3 and provider != null:
		pool.filling = true
		_background(_fill_pool.bind(session, what, shape, ctx, pool))
	return item if has_item else shape.default_value()


func _fill_pool(session: String, what: String, shape, ctx: Variant, pool: Dictionary) -> void:
	var items: Array = await _create_many(session, what, shape, ctx, POOL_SIZE, false)
	pool.items.append_array(items)
	pool.failures = 0 if not items.is_empty() else pool.failures + 1
	pool.filling = false


# ---------------- chat ----------------

## {text, source, actions}. stream: a Callable given each piece of the reply as it is written (null: no streaming).
func chat(session: String, name: Variant, message0: Variant, facts0: Variant = null, speaker0: Variant = "player", stream: Variant = null,
		timeout := 0.0, max_chars: Variant = null, image: Variant = null) -> Dictionary:
	var c = char_of(session, name)
	var pictures: Array = _pictures(c.name, image) if image != null else []
	var box := Lines.box_limit(max_chars)
	var limit_c: int = box if box > 0 else c.max_chars
	var message := Py.clean(Py.text_of(message0) if Py.truthy(message0) else "").substr(0, 1000)
	var sp = Lines.name_of(speaker0)
	var speaker: String = sp if sp != null and sp != "" else "player"
	var facts := _mapping(facts0, "facts")
	if _fault != "":
		return {}
	var hkey: String = session + SEP + c.name + SEP + speaker
	var now := wall()
	var table := _bond_table(session)
	_from_config(session, speaker)
	var talk: Array = history.get(hkey, []).duplicate()
	var st = state_of.get(session)
	var bond = table[c.name][speaker].duplicate() if table.has(c.name) and table[c.name].has(speaker) else null
	var other = characters.get(session + SEP + speaker)
	var who := ""
	if other != null and other != c:
		who = Souls.field(other.card, "summary")
		if who == "":
			who = other.personality
	var reply = null
	var inner = {}
	var prepared = null
	var source := "model"
	if message == "" and facts.is_empty() and bond == null and who == "" and pictures.is_empty():
		var gkey: String = c.name + SEP + str(c.soul_key)
		prepared = greetings.get(gkey)
		greetings.erase(gkey)
	if prepared != null:
		reply = Stream.fit_chars(prepared[0], limit_c)
		inner = prepared[1]
		source = "prepared"
		if stream is Callable:
			stream.call(reply)
	elif provider != null:
		var m := _mood(session, c)
		var system := Prompts.chat_system(c, _lang(c, true), _card_lines(c), lore(session))
		var mine_said := []
		for h in talk:
			if h[0] == c.name:
				mine_said.append(h[1])
		var w := Souls.worn(mine_said)
		var secrets := not Souls.secrets(c.card).is_empty()
		var user := Prompts.history_block(talk, Souls.KEEP) + _context(session, c.name, message) + Prompts.facts_block(facts) + \
			Prompts.bond_block(speaker, bond, Souls.ago(now - bond.last) if bond != null else "", opinion(session, c.name, speaker),
				_known(session, c.name, speaker), m[0], Souls.strength(m[1]) if m[1] != 0.0 else "", who, secrets) + \
			Prompts.worn_block(w[0], w[1]) + Prompts.picture_block(not pictures.is_empty(), speaker) + Prompts.message_block(speaker, message) + \
			Prompts.box_block(box)
		var allowed := Lines.allowed_numbers([facts, st, message, c.personality, Souls.texts(c.card),
			memory.recall(session, [c.name, "world"], message), _known(session, c.name, speaker)])
		var repair := ""
		var flow := {"streamed": false}
		var recent: Array = said_by.get(session + SEP + c.name, [])
		var mine: Array = recent.slice(maxi(0, recent.size() - 6))
		var hidden: Array = Souls.secrets(c.card) if opinion(session, c.name, speaker) < Souls.SECRET_TRUST else []
		var pub := Souls.public_texts(c.card)
		pub.append(c.personality)
		for attempt in 2:
			var streaming: bool = stream is Callable and not flow.streamed
			var splitter = Stream.Splitter.new() if streaming else null
			var guard = Stream.Guard.new(Py.re(Lines.META)) if streaming else null
			var unstager := Stream.Unstage.new()
			var echo = Stream.Echo.new(mine) if streaming else null
			var cut := Stream.Cap.new(c.reply_words, limit_c)
			var gate := {"shown": "", "shut": false}
			var show = null
			if streaming:
				show = func(piece: String) -> void:
					var shown := cut.feed(echo.feed(unstager.feed(guard.feed(splitter.feed(piece)))))
					if shown != "" and not gate.shut:
						if not hidden.is_empty() and Souls.leaks(gate.shown + shown, hidden, pub, 0.5, message) != null:
							gate.shut = true
							return
						gate.shown += shown
						flow.streamed = true
						stream.call(shown)
			var r: Dictionary = await _race("chat", c.name, system, user + repair, 500, show, timeout if timeout > 0 else _reply_deadline(), pictures)
			if streaming:
				var tail := cut.feed(echo.feed(unstager.feed(guard.feed(splitter.finish()[2]) + guard.finish()) + unstager.finish()) + echo.finish())
				tail += cut.finish()
				if not hidden.is_empty() and Souls.leaks(gate.shown + tail, hidden, pub, 0.5, message) != null:
					tail = ""
				if tail != "" and r.ok and not r.cut and not gate.shut:
					flow.streamed = true
					stream.call(tail)
			if not r.ok:
				break
			var parts := Souls.split(r.text)
			var inn = parts[1]
			var dn := Souls.drop_narrated(parts[0], Souls.inner_of_reply(inn).gesture, Souls.quirks(c.card))
			var said: String = dn[0]
			if dn[1] != "" and Souls.inner_of_reply(inn).gesture == "":
				inn = inn.duplicate()
				inn["gesture"] = dn[1]
			if r.cut and not r.text.contains(Souls.MARK):
				said = Souls.whole_sentences(said)
				inn = {}
				if said == "":
					break
			inner = inn
			var why := []
			var text := _clean_reply(said, c.name, why)
			if text != "":
				var turn := Py.re("(^|" + Py.SPACE + ")" + Py.escape(speaker) + Py.SPACE + "*:").search(text)
				if turn != null:
					text = Py.strip(text.substr(0, turn.get_start(0)))
			text = Stream.cap(text, c.reply_words, limit_c)
			if text != "":
				var de := Stream.drop_echoes(text, mine)
				if de[1] and attempt == 0:
					repair = Prompts.say_new()
					_log("repair", c.name, "chat: only said again what was said before; asked again")
					continue
				text = text if de[1] else de[0]
			if not hidden.is_empty() and text != "" and Souls.leaks(text, hidden, pub, 0.5, message) != null:
				if attempt == 0:
					repair = Prompts.keep_secret(c.name, speaker)
					_log("repair", c.name, "chat: gave a secret away to " + speaker + "; asked again")
					continue
				text = Souls.keep_secrets(text, hidden, pub, message)
				_log("refused", c.name, "chat: a secret was cut out of the reply")
			if why.has("character") and attempt == 0:
				repair = Prompts.stay_in_character(c.name)
				_log("repair", c.name, "chat: stepped out of character; asked again")
				continue
			var bad := Lines.bad_numbers(text, allowed)
			if bad.is_empty() and text != "":
				reply = text
				break
			if text == "":
				break
			if flow.streamed:
				_log("repair", c.name, "chat: numbers the game did not give; the reply shown will change")
			repair = Prompts.numbers_repair()
			if not bad.is_empty() and attempt == 1:
				var kept := []
				for s in Py.re(Lines.SENTENCE).search_all(text):
					var t := Py.strip(s.get_string(0))
					if t != "" and Lines.bad_numbers(t, allowed).is_empty():
						kept.append(t)
				reply = " ".join(kept) if not kept.is_empty() else null
				_log("refused", c.name, "chat: numbers the game did not give (" + ", ".join(bad) + ")")
	var stored: bool = characters.get(session + SEP + c.name) == c
	var decided := []
	if reply != null and stored:
		if not c.tools.is_empty() and source == "model" and Souls.inner_of_reply(inner).do.is_empty():
			var found: Array = await _deeds(c, speaker, message, reply)
			if not found.is_empty():
				inner = (inner if inner is Dictionary else {}).duplicate()
				inner["do"] = found
		decided = _inner(session, c, speaker, inner)
		if source == "prepared":
			_prepare_greeting(session, c)
	elif reply == null:
		inner = null
		source = "offline"
		reply = _offline_line(c, "greet", facts, limit_c) if message == "" else ""
		if reply == "":
			reply = _next_offline(c)
		stats_of.offline_answers += 1
		if reply == "":
			_tell_empty(session, c.name, "chat", c.name + " has no offline reply: chat() answered \"\" (give it offline=\"...\" or a list of replies, said when no model answers)")
	var row: Dictionary = {}
	if stored:
		if not table.has(c.name):
			table[c.name] = {}
		row = table[c.name]
	var known_speaker: bool = stored and (row.has(speaker) or row.size() < MAX_SPEAKERS)
	if known_speaker:
		if not row.has(speaker):
			row[speaker] = {"talks": 0, "first": now, "last": now}
		var b: Dictionary = row[speaker]
		if b.talks == 0 or now - b.last > Souls.NEW_TALK:
			b.talks += 1
		b.last = now
	var snapshot := table.duplicate(true)
	var h := []
	if known_speaker:
		if not history.has(hkey):
			history[hkey] = []
		h = history[hkey]
	if message != "":
		h.append([speaker, message])
	var old := []
	if reply != "":
		h.append([c.name, reply])
		if inner != null and stored:
			var key: String = session + SEP + c.name
			if not said_by.has(key):
				said_by[key] = []
			said_by[key].append(reply)
			if said_by[key].size() > 8:
				said_by[key].pop_front()
	if h.size() > Souls.KEEP:
		old = h.slice(0, Souls.SUMMARIZE)
		var rest := h.slice(Souls.SUMMARIZE)
		h.clear()
		h.append_array(rest)
	if stored:
		memory.put("bonds", session, snapshot)
	_recollect(session, c, speaker, old)
	if reply != "" and message != "" and inner != null and stored:
		memory.add(session, c.name, speaker + " said: " + message.substr(0, 120) + " / I answered: " + reply.substr(0, 160), 0.35, {"about": speaker})
	var detail := {"message": message, "speaker": speaker}
	if inner == null:
		detail["offline"] = true
	_log("chat", c.name, reply, detail)
	return {"text": reply, "source": source, "actions": decided}


func _deeds(c, speaker: String, message: String, reply: String) -> Array:
	var r: Dictionary = await _ask("deeds", c.name, Prompts.deeds_system(c), Prompts.deeds_user(c.name, speaker, message, reply), true, true, 150,
		null, minf(call_timeout, 5.0))
	var data = Py.find_json(r.text) if r.ok else null
	var found = data.get("do") if data is Dictionary else null
	var out := []
	if found is Array:
		for x in found:
			if x is Dictionary and out.size() < 3:
				out.append(x)
	return out


func _next_offline(c) -> String:
	if c.offlines.size() < 2:
		return c.offline
	c.offline_turn += 1
	return c.offlines[c.offline_turn % c.offlines.size()]


## The spoken reply, cleaned; "" when unusable (why gets "filter" or "character").
func _clean_reply(text0: String, name: String, why: Array = []) -> String:
	var text := Py.strip(Py.strip_chars(Py.strip(Lines.speech_only(Py.strip(Py.clean(text0)))), "\""))
	text = Py.squash(Lines.unstage(text))
	text = Py.re(Py.SPACE + "+([.,!?])").sub(text, "$1", true)
	if not _allowed(text):
		_log("refused", name, "chat: blocked by the content filter")
		why.append("filter")
		return ""
	if Py.lower(text).begins_with(Py.lower(name) + ":"):
		text = Py.strip(text.substr(name.length() + 1))
	elif Py.re(Lines.PREFIX).search(text) != null and Py.lower(Py.strip(text.split(":")[0])) in ["assistant", "ai", "i", "me", Py.lower(name)]:
		text = Py.re(Lines.PREFIX).sub(text, "", false)
	if Py.re(Lines.META).search(text) != null or Py.re(Lines.PROMPTISH).search(text) != null:
		why.append("character")
		return ""
	return text.substr(0, Lines.MAX_REPLY)


# ---------------- the world: events, opinions, rumors ----------------

func event(session: String, text0: Variant, about: Variant = null, importance: Variant = 0.5, by0: Variant = null, seen_by: Variant = null,
		tag0: Variant = null, impact: Variant = null) -> void:
	var text := Py.clean(Py.text_of(text0)).substr(0, 300)
	if text == "":
		return
	var by = Lines.name_of(by0)
	var tag = Lines.name_of(tag0)
	var names := []
	for k in characters:
		if k.begins_with(session + SEP):
			names.append(k.substr(session.length() + 1))
	events += 1
	var eid := "e" + ("%x" % Rules.fnv1a(text + Py.text_of(wall()))) + "-" + str(events)
	var impact_value = Py.finite(impact)
	if impact_value != null:
		impact_value = Py.round_to(clampf(impact_value, -1.0, 1.0), 4)
	var meta := {"eid": eid, "tag": tag, "by": by, "src": "seen", "orig": text, "impact": impact_value}
	var imp = importance if typeof(importance) in [TYPE_INT, TYPE_FLOAT] else 0.5
	if typeof(seen_by) == TYPE_STRING:
		seen_by = [seen_by]
	if seen_by != null and not (seen_by is Array):
		_raise("seen_by: a list of names, got " + type_string(typeof(seen_by)), true)
		return
	var witnesses := []
	if seen_by is Array:
		for x in seen_by.slice(0, 100):
			var n = Lines.name_of(x)
			if n != null and n != "":
				witnesses.append(n)
		var knowers := witnesses.duplicate()
		if by != null and by != "" and not witnesses.has(by):
			knowers.append(by)
		for n in Souls.ordered_set(knowers):
			memory.add(session, n, text, imp, meta)
	else:
		var targets := []
		if about is Array and not about.is_empty():
			for x in about.slice(0, 100):
				var n = Lines.name_of(x)
				if n != null and n != "":
					targets.append(n)
		else:
			var low := Py.lower(text)
			for n in names:
				if Py.re("(?<![" + Py.W + "])" + Py.escape(Py.lower(n)) + "(?![" + Py.W + "])").search(low) != null:
					targets.append(n)
		var all := targets.duplicate()
		if by != null and by != "" and not targets.has(by):
			all.append(by)
		for n in Souls.ordered_set(all):
			memory.add(session, n, text, imp, meta)
		var public := meta.duplicate()
		public["src"] = "public"
		memory.add(session, "world", text, imp, public)
		witnesses = names
	var others := []
	for w in Souls.ordered_set(witnesses):
		if w != by:
			others.append(w)
	_log("event", ",".join(others.slice(0, 8)) if seen_by is Array else "world", text, {"tag": tag, "by": by})
	if by == null or by == "" or others.is_empty():
		return
	if impact_value != null:
		for w in others:
			feel(session, w, by, impact_value)
	elif provider != null:
		_background(_estimate_impact.bind(session, text, by, others.slice(0, 12), eid))


func _estimate_impact(session: String, text: String, by: String, witnesses: Array, eid: String) -> void:
	var people := []
	var fields := {}
	for w in witnesses:
		var other = characters.get(session + SEP + w)
		people.append([w, other.personality if other != null else "", opinion(session, w, by)])
		var between = ShapeLib.Shape.bare("range", [-1.0, 1.0])
		between.lo = -1.0
		between.hi = 1.0
		between.whole = false
		fields[w] = between
	var inner_shape = ShapeLib.Shape.bare("object", {})
	inner_shape.fields = fields
	var shape = ShapeLib.Shape.bare("object", {})
	shape.fields = {"impact": inner_shape}
	var value = await _structured("impact", by, Prompts.impact_system(_written()), Prompts.impact_user(text, by, people), shape, false, 300)
	if value == null:
		return
	for w in value.impact:
		var v := Py.round_to(value.impact[w], 4)
		if v != 0:
			feel(session, w, by, v)
			memory.annotate(session, w, eid, {"impact": v})
	_log("impact", by, Py.dumps(value.impact))


func _opinion_table(session: String) -> Dictionary:
	if not opinions_by.has(session):
		var saved = memory.get_value("opinions", session)
		var table := {}
		if saved is Dictionary:
			for a in saved:
				var row = saved[a]
				if row is Dictionary:
					var out := {}
					for b in row:
						var f = Py.finite(row[b])
						if f != null:
							out[b] = clampf(f, -1.0, 1.0)
					table[a] = out
		opinions_by[session] = table
	return opinions_by[session]


# ---------------- models per task, the content rating ----------------

## The model of a task: conversations and what players wait for use "chat", the rest "background".
func _provider_for(kind: String) -> Variant:
	return models.get("chat" if kind in CHAT_KINDS else "background", provider)


func _rated(system: String) -> String:
	var line := Prompts.rating_line(rating)
	return system if line == "" else system + "\n" + line


## [{bucket: provider}, why refused or ""].
static func _models_of(given: Variant, p: Variant) -> Array:
	var out := {}
	if not Py.truthy(given):
		return [out, ""]
	if not (given is Dictionary):
		return [{}, "models: an object like {\"background\": \"a-cheaper-model\"}"]
	for bucket in given:
		if not (str(bucket) in ["chat", "background"]):
			return [{}, "models: \"" + str(bucket) + "\" is not a task group (use \"chat\" and \"background\")"]
		var spec = given[bucket]
		if spec == null:
			continue
		if typeof(spec) == TYPE_STRING:
			var id := Py.strip(spec)
			if p == null or id == "":
				continue
			var q = p.with_model(id) if p is Object and p.has_method("with_model") else null
			if q == null:
				return [{}, "models: a model id needs a known provider to share (give {\"url\", \"key\", \"model\"} instead)"]
			out[str(bucket)] = q
		elif spec is Dictionary or (spec is Object and spec.has_method("complete")):
			var q = P.provider_of(spec)
			if q != null:
				out[str(bucket)] = q
		else:
			return [{}, "models." + str(bucket) + ": a model id or a provider"]
	return [out, ""]


## [rating or null, why refused or ""].
static func _rating_of(value: Variant) -> Array:
	if value == null or (typeof(value) == TYPE_STRING and value == ""):
		return [null, ""]
	var v := Py.lower(Py.strip(Py.text_of(value)))
	if Prompts.RATINGS.has(v):
		return [v, ""]
	return [null, "rating: \"everyone\", \"teen\" or \"mature\", got " + Py.py_repr(value)]


# ---------------- v1: the player's choices, characters talking together, a snapshot, saves ----------------

## What the player could say now to name, one reply per example and in its order. Offline: the examples.
func suggest(session: String, name: Variant, examples: Variant, speaker0: Variant = "player", facts0: Variant = null) -> Array:
	var c = char_of(session, name)
	var facts := _mapping(facts0, "facts")
	if _fault != "":
		return []
	if not (examples is Array):
		_raise("examples: a list of short replies the player could say, like [\"Ask about her past\", \"Leave\"]")
		return []
	var given := []
	for x in examples.slice(0, MAX_SUGGESTIONS):
		if x == null:
			continue
		var t := Py.clean(Py.text_of(x))
		if t != "":
			given.append(t.substr(0, 80))
	if given.is_empty():
		_raise("examples: give at least one reply, like [\"Ask about her past\", \"Leave\"]")
		return []
	var sp = Lines.name_of(speaker0)
	var speaker: String = sp if sp != null and sp != "" else "player"
	if provider == null:
		return given
	var talk: Array = history.get(session + SEP + c.name + SEP + speaker, []).duplicate()
	var r: Dictionary = await _ask("suggest", c.name, Prompts.suggest_system(c, given.size(), speaker), Prompts.suggest_user(talk, facts, given),
		true, true, 60 + 40 * given.size())
	var data = Py.find_json(r.text) if r.ok else null
	var got = data.get("replies") if data is Dictionary else (data if data is Array else null)
	var out := []
	for i in given.size():
		var raw: String = got[i] if got is Array and i < got.size() and typeof(got[i]) == TYPE_STRING else ""
		var t := Py.strip(Py.strip_chars(Py.strip(Py.clean(raw)), "\""))
		if t == "" or t.length() > 80 or Py.split(t).size() > 14 or Py.re(Lines.META).search(t) != null or Py.re(Lines.PROMPTISH).search(t) != null \
				or not _allowed(t):
			t = given[i]
		out.append(t)
	if r.ok and out == given:
		_log("refused", c.name, "suggest: no usable replies; the examples were used")
	return out


## A short exchange between two characters (one model call), remembered by both: [{who, text}]. Offline: [].
func converse(session: String, a: Variant, b: Variant, about0: Variant = "", turns: Variant = 4) -> Array:
	var ca = char_of(session, a)
	var cb = char_of(session, b)
	var t = 4.0 if turns == null else Py.number_of(turns)
	if t == null or typeof(turns) == TYPE_BOOL or is_nan(t) or is_inf(t):
		_raise("turns: a number, got " + Py.py_repr(turns))
		return []
	var n := clampi(int(t), 2, 8)
	var about := Py.clean("" if about0 == null else Py.text_of(about0)).substr(0, 300)
	if provider == null or is_same(ca, cb):
		return []
	var system := Prompts.converse_system(ca, cb, n, _lang(ca), lore(session))
	var user := Prompts.converse_user(ca.name, _context(session, ca.name, about if about != "" else cb.name), cb.name,
		_context(session, cb.name, about if about != "" else ca.name), about)
	var r: Dictionary = await _ask("converse", ca.name, system, user, true, true, 80 + 70 * n)
	var data = Py.find_json(r.text) if r.ok else null
	var items = data.get("lines") if data is Dictionary else (data if data is Array else null)
	var allowed := Lines.allowed_numbers([state_of.get(session), ca.personality, cb.personality, about, Souls.texts(ca.card), Souls.texts(cb.card)])
	var out := []
	for item in items if items is Array else []:
		if out.size() >= n:
			break
		if not (item is Dictionary):
			continue
		var w = Lines.name_of(item.get("who"))
		var who: String = Py.lower(w) if w != null else ""
		var c = ca if who == Py.lower(ca.name) else (cb if who == Py.lower(cb.name) else null)
		if c == null or typeof(item.get("text")) != TYPE_STRING:
			continue
		var said := Stream.cap(_clean_reply(item.text, c.name), c.reply_words, c.max_chars)
		if said != "" and Lines.bad_numbers(said, allowed).is_empty():
			out.append({"who": c.name, "text": said})
	if out.is_empty():
		_log("refused", ca.name, "converse: no usable lines" + ("" if r.ok else " (" + str(r.error) + ")"))
		return []
	var parts := []
	for x in out:
		parts.append(x.who + ": " + x.text)
	var all_said := " / ".join(parts)
	memory.add(session, ca.name, "Talked with " + cb.name + ": " + all_said.substr(0, 240), 0.4, {"about": cb.name})
	memory.add(session, cb.name, "Talked with " + ca.name + ": " + all_said.substr(0, 240), 0.4, {"about": ca.name})
	_log("converse", ca.name, all_said.substr(0, 300), {"other": cb.name})
	return out


## Everything a debug overlay shows.
func inspect(session: String) -> Dictionary:
	var prefix := session + SEP
	var names := []
	for k in characters:
		if k.begins_with(prefix):
			names.append(k.substr(prefix.length()))
	names.sort()
	var mind_list := []
	for k in minds:
		if k.begins_with(prefix):
			mind_list.append(k.substr(prefix.length()))
	mind_list.sort()
	var chars := {}
	for name in names:
		var s := soul(session, name)
		var said: Array = said_by.get(prefix + name, [])
		var waiting := []
		var entry = pending.get(prefix + name)
		if entry != null:
			for act_ in entry.actions:
				if not act_.taken:
					waiting.append(act_.tool)
		var feelings := {}
		var ops := opinions(session, name)
		for k in _sorted_keys(ops):
			feelings[k] = ops[k]
		var talks := {}
		for k in _sorted_keys(s.bonds):
			talks[k] = s.bonds[k].get("talks", 0)
		var memories: Array = s.memories
		chars[name] = {"personality": s.personality, "mood": s.mood, "gesture": s.gesture, "feelings": feelings, "talks": talks,
			"last_words": said[-1] if not said.is_empty() else "", "memories": memories.slice(maxi(0, memories.size() - 5)), "waiting": waiting}
	var out_minds := {}
	for name in mind_list:
		var report = mind_report(session, name)
		if report == null:
			report = {}
		out_minds[name] = {"generation": report.get("generation", 0), "variants": report.get("variants", []).size(), "per": report.get("per", "decision")}
	var st := stats()
	return {"online": provider != null, "characters": chars, "minds": out_minds, "calls": st.calls, "failures": st.failures, "cost": st.get("cost")}


## Everything known about this session, as one JSON text for the game's save slot.
func save_state(session: String) -> String:
	var prefix := session + SEP
	var mood_out := {}
	for k in moods:
		if k.begins_with(prefix):
			var m := Souls.mood_now(moods[k], clock(), "")
			if m[1]:
				mood_out[k.substr(prefix.length())] = {"word": m[0], "level": m[1]}
	var hkeys := []
	for k in history:
		if k.begins_with(prefix) and not history[k].is_empty():
			hkeys.append(k)
	hkeys.sort()
	var talk := []
	for k in hkeys:
		var parts: PackedStringArray = k.substr(prefix.length()).split(SEP)
		if parts.size() != 2:
			continue
		talk.append([parts[0], parts[1], history[k].duplicate(true)])
	var said := {}
	for k in said_by:
		if k.begins_with(prefix) and not said_by[k].is_empty():
			said[k.substr(prefix.length())] = said_by[k].duplicate()
	var learned := {}
	for k in minds:
		if k.begins_with(prefix):
			var saved = memory.get_value("minds", session + "/" + k.substr(prefix.length()))
			if saved != null:
				learned[k.substr(prefix.length())] = saved
	var data := {"kinloom": 1, "notes": memory.session_notes(session), "bonds": memory.get_value("bonds", session),
		"opinions": memory.get_value("opinions", session), "lore": memory.get_value("lore", session), "minds": learned, "moods": mood_out,
		"history": talk, "said": said, "state": state_of.get(session)}
	return Py.dumps(data, false, true)


## Puts back what save_state gave (this session's state is replaced).
func load_state(session: String, text: Variant) -> bool:
	var data = text
	if typeof(text) == TYPE_STRING:
		var r := Py.loads(text)
		data = r[1] if r[0] else null
	if not (data is Dictionary) or not (typeof(data.get("kinloom")) in [TYPE_INT, TYPE_FLOAT]) or Py.num(data.get("kinloom")) != 1:
		_raise("data: not a Kinloom save (give what save() returned)")
		return false
	var notes: Dictionary = data["notes"] if data.get("notes") is Dictionary else {}
	memory.replace_session(session, notes)
	for section in ["bonds", "opinions", "lore"]:
		if data.get(section) == null:
			memory.remove(section, session)
		else:
			memory.put(section, session, data[section])
	var learned: Dictionary = data["minds"] if data.get("minds") is Dictionary else {}
	var prefix := session + SEP
	var now := clock()
	for table in [moods, said_by, gestures, gesture_seen, history, rises]:
		for k in table.keys():
			if k.begins_with(prefix):
				table.erase(k)
	bonds.erase(session)
	opinions_by.erase(session)
	lore_by.erase(session)
	if data.get("moods") is Dictionary:
		for name in data.moods:
			var m = data.moods[name]
			if m is Dictionary and typeof(m.get("word")) == TYPE_STRING and typeof(m.get("level")) in [TYPE_INT, TYPE_FLOAT]:
				moods[prefix + str(name)] = {"word": m.word, "level": clampf(float(m.level), 0.0, 1.0), "t": now}
	if data.get("history") is Array:
		for item in data.history:
			if item is Array and item.size() == 3 and item[2] is Array:
				var kept := []
				for x in item[2]:
					if x is Array and x.size() == 2 and typeof(x[0]) == TYPE_STRING and typeof(x[1]) == TYPE_STRING:
						kept.append([x[0], x[1]])
				history[prefix + Py.text_of(item[0]) + SEP + Py.text_of(item[1])] = kept.slice(maxi(0, kept.size() - Souls.KEEP))
	if data.get("said") is Dictionary:
		for name in data.said:
			var v = data.said[name]
			if v is Array:
				var l := []
				for x in v:
					if typeof(x) == TYPE_STRING:
						l.append(x)
				said_by[prefix + str(name)] = l.slice(maxi(0, l.size() - 8))
	if data.get("state") is Dictionary:
		state_of[session] = data.state
	else:
		state_of.erase(session)
	var redo := []
	for k in minds:
		if k.begins_with(prefix) and minds[k].args != null:
			redo.append([k.substr(prefix.length()), minds[k].args])
	for key in memory.keys("minds"):
		if str(key).begins_with(session + "/"):
			memory.remove("minds", key)
	for name in learned:
		if learned[name] is Dictionary:
			memory.put("minds", session + "/" + str(name), learned[name])
	for item in redo:
		minds.erase(prefix + item[0])
		var a: Array = item[1]
		mind(session, item[0], a[0], a[1], a[2], a[3], a[4], a[5])
	var count := 0
	for k in notes:
		if notes[k] is Array:
			count += notes[k].size()
	_log("load", "kinloom", "save loaded: %d memories, %d minds" % [count, learned.size()])
	return true


func opinion(session: String, a: Variant, b: Variant) -> float:
	var t := _opinion_table(session)
	var na = Lines.name_of(a)
	var nb = Lines.name_of(b)
	if na == null or nb == null or not t.has(na):
		return 0.0
	return float(t[na].get(nb, 0.0))


func opinions(session: String, a: Variant) -> Dictionary:
	var na = Lines.name_of(a)
	return _opinion_table(session).get(na, {}).duplicate() if na != null else {}


func feel(session: String, a0: Variant, b0: Variant, change: Variant) -> float:
	var a = Lines.name_of(a0)
	var b = Lines.name_of(b0)
	var table := _opinion_table(session)
	var v = Py.finite(change)
	var old: float = float(table[a].get(b, 0.0)) if a != null and b != null and table.has(a) else 0.0
	if v == null or a == null or a == "" or b == null or b == "" or a == b:
		return old
	if not table.has(a) and table.size() >= MAX_CHARACTERS:
		return old
	var next := Py.round_to(clampf(old + v, -1.0, 1.0), 4)
	if not table.has(a):
		table[a] = {}
	table[a][b] = next
	memory.put("opinions", session, table.duplicate(true))
	return next


func reputation(session: String, target: Variant, group: Variant) -> float:
	var g = Lines.name_of(group)
	var members := []
	for c in _character_list(session):
		if c.group == g:
			members.append(c.name)
	if members.is_empty():
		return 0.0
	var total := 0.0
	for m in members:
		total += opinion(session, m, target)
	return Py.round_to(total / members.size(), 4)


func knowledge(session: String, name0: Variant, tag: Variant = null) -> Array:
	var name = Lines.name_of(name0)
	var out := []
	for scope in [name, "world"]:
		if scope == null:
			continue
		for n in memory.notes(session, scope):
			if not Py.truthy(n.get("eid")) or (tag != null and tag != n.get("tag") and tag != n.get("eid")):
				continue
			if scope == "world" and out.any(func(o): return o.eid == n.eid):
				continue
			out.append({"text": n.get("orig") if Py.truthy(n.get("orig")) else n.text, "tag": n.get("tag"), "source": n.get("src"),
				"by": n.get("by"), "importance": n.importance, "impact": n.get("impact"), "eid": n.eid})
	return out


func meet(session: String, a0: Variant, b0: Variant, k: Variant = 3) -> Array:
	var a = Lines.name_of(a0)
	var b = Lines.name_of(b0)
	var shared := []
	if a == null or b == null or a == "" or b == "" or a == b:
		return shared
	var kn := Lines.arg_num(k, "k")
	if kn[0] == null:
		_raise(kn[1])
		return shared
	var top := clampi(int(kn[0]), 1, 10)
	for pair in [[a, b], [b, a]]:
		var teller: String = pair[0]
		var listener: String = pair[1]
		var known := {}
		for n in memory.notes(session, listener):
			if Py.truthy(n.get("eid")):
				known[n.eid] = true
		var news := []
		for n in memory.notes(session, teller):
			if Py.truthy(n.get("eid")) and not known.has(n.eid) and Py.num(n.importance) >= MIN_RUMOR:
				news.append(n)
		news = Py.stable_sort(news, func(x, y): return x.importance > y.importance or (x.importance == y.importance and x.t > y.t))
		for n in news.slice(0, top):
			var orig: String = n.get("orig") if Py.truthy(n.get("orig")) else n.text
			memory.add(session, listener, teller + " told me: " + orig, Py.round_to(Py.num(n.importance) * RUMOR_DECAY, 4),
				{"eid": n.eid, "tag": n.get("tag"), "by": n.get("by"), "src": teller, "orig": orig, "impact": n.get("impact")})
			var doer = n.get("by")
			var impact = Py.finite(n.get("impact"))
			if Py.truthy(doer) and impact != null and doer != listener:
				var trust := (1.0 + opinion(session, listener, teller)) / 2.0
				if trust > 0:
					feel(session, listener, doer, impact * HEARSAY * trust)
			shared.append({"from": teller, "to": listener, "text": orig, "tag": n.get("tag")})
	if not shared.is_empty():
		var l := []
		for s in shared:
			l.append(s.from + " -> " + s.to + ": " + s.text)
		_log("meet", a + "+" + b, "; ".join(l).substr(0, 300))
	return shared


func spread(session: String, group: Variant = null, rounds: Variant = 1) -> Array:
	var g = Lines.name_of(group) if group != null else null
	var members := []
	for c in _character_list(session):
		if group == null or c.group == g:
			members.append(c.name)
	var shared := []
	var n := members.size()
	if n < 2:
		return shared
	var times := 1
	if rounds != null:                             # a number or numeric text; anything else: a 400
		var r := Lines.arg_num(rounds, "rounds")
		if r[0] == null:
			_raise(r[1])
			return shared
		times = clampi(int(r[0]), 1, 20)
	for i in times:
		spreads += 1
		var offset := ((spreads - 1) % (n - 1)) + 1
		for j in n:
			shared.append_array(meet(session, members[j], members[(j + offset) % n], 1))
	return shared


func remember(session: String, name: Variant, note: Variant, importance: Variant = 0.6) -> void:
	memory.add(session, Py.text_of(name), Py.text_of(note), importance if typeof(importance) in [TYPE_INT, TYPE_FLOAT] else 0.6)


func set_state(session: String, values: Variant) -> void:
	var m := _mapping(values, "state")
	if _fault == "":
		state_of[session] = m


func _character_list(session: String) -> Array:
	var out := []
	for k in characters:
		if k.begins_with(session + SEP):
			out.append(characters[k])
	return out


func is_declared(session: String, name: Variant) -> bool:
	var n := Py.clean(Py.text_of(name)).substr(0, MAX_NAME)
	if n == "":
		n = "?"
	_from_config(session, n)
	return declared.has(session + SEP + n)


# ---------------- reporting ----------------

func stats() -> Dictionary:
	var s := stats_of.duplicate(true)
	s["cost"] = null
	if prices != null:
		var fresh := maxi(0, s.input_tokens - s.cached_tokens)
		var cached_price = prices.get("cached_input") if prices.get("cached_input") != null else prices.get("input", 0)
		s["cost"] = Py.round_to((fresh * Py.num(prices.get("input", 0)) + s.cached_tokens * Py.num(cached_price) + s.output_tokens * Py.num(prices.get("output", 0))) / 1e6, 6)
		s["price_source"] = prices.get("source")
	s["avg_latency"] = Py.round_to(s.latency / s.calls, 3) if s.calls > 0 else 0.0
	return s


func online() -> bool:
	return provider != null


func status() -> Dictionary:
	var named := {}
	for k in _sorted_keys(models):
		named[k] = models[k].model
	return {"mode": "online" if provider != null else "offline", "provider": provider.name if provider != null else null,
		"model": provider.model if provider != null else null, "calls_per_minute": limit, "language": language, "memory": null,
		"voice": voice.describe() if voice != null else null, "native": true, "models": named, "rating": rating}


func journal(n := 100) -> Array:
	return journal_entries.slice(maxi(0, journal_entries.size() - n))


## Saves memory now and stops background work.
func close() -> void:
	if closed:
		return
	closed = true
	memory.save()


# ---------------- the HTTP contract, in process (what `kinloom serve` answers, verb by verb) ----------------

static func _missing(body: Dictionary, keys: Array) -> String:
	for k in keys:
		if not body.has(k) or body[k] == null or (typeof(body[k]) == TYPE_STRING and body[k] == ""):
			return "missing '" + k + "'"
	return ""


## [status, answer]: 200 and the verb's answer, or 400/404 and {"error": why}.
func handle(verb: String, body: Dictionary, session := "default") -> Array:
	_fault = ""
	_fault_type = false
	var r: Array = await _verb(verb, body, session)
	if r[0] != 200:
		return r
	if _fault != "":
		var label := "choices" if verb == "decide" else ("example" if verb == "create" else verb)
		var why := verb + ": a field has the wrong type (" + _fault + ")" if _fault_type else label + ": " + _fault
		_fault = ""
		return [400, {"error": why}]
	return r


static func _err(status: int, why: String) -> Array:
	return [status, {"error": why}]


func _verb(verb: String, body: Dictionary, session: String) -> Array:
	var name = body.get("name")
	var facts = body.get("facts")
	if facts != null and not (facts is Dictionary) and verb in ["say", "chat"]:
		return _err(400, "'facts' must be an object {name: value}")
	var image = body.get("image")
	if image != null and typeof(image) == TYPE_STRING and image == "":
		image = null
	if image != null and typeof(image) != TYPE_STRING and verb in ["chat", "create"]:
		return _err(400, "'image' must be base64 or a data URI (PNG, JPEG, GIF, WebP)")
	var miss := ""
	match verb:
		"character":
			miss = _missing(body, ["name"])
			if miss != "":
				return _err(400, miss)
			character(session, name, {"personality": body.get("personality") if Py.truthy(body.get("personality")) else "", "lines": body.get("lines"),
				"offline": body.get("offline"), "events": body.get("events"), "tools": body.get("tools"), "max_words": body.get("max_words"),
				"every": body.get("every") if body.get("every") != null else 8.0, "language": body.get("language"), "group": body.get("group"),
				"soul": body.get("soul"), "trust": body.get("trust"), "invent": not (typeof(body.get("invent")) == TYPE_BOOL and body.invent == false),
				"voice": body.get("voice"), "max_chars": body.get("max_chars")})
			return [200, {"ok": true}]
		"say":
			miss = _missing(body, ["name", "event"])
			if miss != "":
				return _err(400, miss)
			var s: Dictionary = await say(session, name, body.event, facts, Py.truthy(body.get("fresh")), body.get("max_chars"))
			if _fault != "":
				return [200, {}]
			return [200, {"text": s.text, "source": s.source, "declared": is_declared(session, name)}]
		"chat":
			miss = _missing(body, ["name"])
			if miss != "":
				return _err(400, miss)
			if typeof(body.get("message")) != TYPE_STRING:
				return _err(400, "missing 'message' (\"\" when the character speaks first)")
			var speaker = body.get("speaker") if Py.truthy(body.get("speaker")) else "player"
			var s: Dictionary = await chat(session, name, body.message, facts, speaker, null, 0.0, body.get("max_chars"), image)
			if _fault != "":
				return [200, {}]
			var out := {"text": s.text, "declared": is_declared(session, name)}
			out.merge(_feelings(session, name, speaker), true)
			out.merge(_reply_extra(s, body), true)
			return [200, out]
		"lore":
			if not body.has("lines") and not body.has("text"):
				return [200, {"lore": lore(session)}]
			return [200, {"lines": lore(session, body["lines"] if body.has("lines") else body["text"])}]
		"soul":
			miss = _missing(body, ["name"])
			if miss != "":
				return _err(400, miss)
			return [200, soul(session, name, body.get("speaker"))]
		"decide":
			miss = _missing(body, ["name", "choices"])
			if miss != "":
				return _err(400, miss)
			var value = decide(session, name, body.get("situation") if Py.truthy(body.get("situation")) else {}, body.choices, body.get("every"))
			return [200, {"decision": value, "declared": is_declared(session, name)}]
		"act":
			miss = _missing(body, ["name"])
			if miss != "":
				return _err(400, miss)
			var acts := []
			for a in act(session, name, body.get("situation"), not (typeof(body.get("think")) == TYPE_BOOL and body.think == false)):
				acts.append({"tool": a[0], "args": a[1]})
			return [200, {"actions": acts, "declared": is_declared(session, name)}]
		"create":
			miss = _missing(body, ["what"])
			if miss != "":
				return _err(400, miss)
			if not body.has("example"):
				return _err(400, "missing 'example' (an example answer: it is also the offline answer)")
			var value = await create(session, body.what, body.example, body.get("context"), body.get("count"), Py.truthy(body.get("instant")), 0.0, image)
			return [200, {"value": value}]
		"tools":
			if not body.has("tools"):
				return [200, {"tools": tools(session)}]
			if not (body.tools is Dictionary):
				return _err(400, "'tools' must be an object {name: example args}")
			return [200, {"tools": tools(session, body.tools)}]
		"prepare":
			var t = body.get("timeout", 10.0)
			if t == null:
				t = 10.0
			if not (typeof(t) in [TYPE_INT, TYPE_FLOAT]):
				return _err(400, "'timeout' must be a number of seconds")
			return [200, await prepare(session, clampf(t, 0.0, 30.0))]
		"event":
			miss = _missing(body, ["text"])
			if miss != "":
				return _err(400, miss)
			if body.get("seen_by") != null and not (body.seen_by is Array):
				return _err(400, "'seen_by' must be a list of names")
			event(session, body.text, body.get("about"), body.get("importance", 0.5), body.get("by"), body.get("seen_by"), body.get("tag"), body.get("impact"))
			return [200, {"ok": true}]
		"mind":
			miss = _missing(body, ["name", "senses", "actions"])
			if miss != "":
				return _err(400, miss)
			var actions = body.actions
			if actions is Dictionary and body.get("order") is Array:
				var ordered := {}
				for k in body.order:
					if typeof(k) == TYPE_STRING and actions.has(k):
						ordered[k] = actions[k]
				for k in actions:
					if not ordered.has(k):
						ordered[k] = actions[k]
				actions = ordered
			var compiled = mind(session, name, body.get("personality") if Py.truthy(body.get("personality")) else "", body.senses, actions,
				body.get("rules"), body.get("variants", 3), body.get("learn", 30))
			return [200, {"mind": compiled}]
		"report":
			miss = _missing(body, ["name"])
			if miss != "":
				return _err(400, miss)
			var compiled = mind_compiled(session, name)
			if compiled == null:
				return [200, {"missing": true}]
			return [200, {"mind": compiled, "report": mind_report(session, name)}]
		"think":
			miss = _missing(body, ["name"])
			if miss != "":
				return _err(400, miss)
			return [200, think(session, Py.text_of(name), body.get("senses") if Py.truthy(body.get("senses")) else {}, body.get("who"))]
		"explain":
			miss = _missing(body, ["name"])
			if miss != "":
				return _err(400, miss)
			var e = explain(session, name, body.get("senses") if Py.truthy(body.get("senses")) else {}, body.get("who"))
			return [200, e if e != null else {"error": "unknown mind"}]
		"reward":
			var rewards = body.get("rewards")
			if rewards == null and body.has("who"):
				rewards = [body]
			if not (rewards is Array):
				return _err(400, "missing 'rewards' (a list of {who, mind, variant, id, reward})")
			for rw in rewards.slice(0, 1000):
				if rw is Dictionary and rw.get("who") != null:
					var variant = rw.variant if typeof(rw.get("variant")) == TYPE_INT else null
					reward(session, Py.text_of(rw.who).substr(0, 64), rw.get("reward"), rw.get("mind"), variant, rw.get("id"), rw.get("action"),
						rw.senses if rw.get("senses") is Dictionary else null, typeof(rw.get("done")) == TYPE_BOOL and rw.done)
			var versions := {}
			for m in mind_names(session):
				var c = mind_compiled(session, m)
				if c != null:
					versions[m] = c.version
			return [200, {"versions": versions}]
		"meet":
			miss = _missing(body, ["a", "b"])
			if miss != "":
				return _err(400, miss)
			return [200, {"shared": meet(session, body.a, body.b, body.get("k", 3))}]
		"spread":
			return [200, {"shared": spread(session, body.get("group"), body.get("rounds", 1))}]
		"knows":
			miss = _missing(body, ["name", "tag"])
			if miss != "":
				return _err(400, miss)
			var notes := knowledge(session, name, Py.text_of(body.tag))
			return [200, {"knows": not notes.is_empty(), "notes": notes}]
		"opinion":
			miss = _missing(body, ["a", "b"])
			if miss != "":
				return _err(400, miss)
			return [200, {"opinion": opinion(session, body.a, body.b)}]
		"opinions":
			miss = _missing(body, ["name"])
			if miss != "":
				return _err(400, miss)
			return [200, {"opinions": opinions(session, name)}]
		"feel":
			miss = _missing(body, ["a", "b"])
			if miss != "":
				return _err(400, miss)
			return [200, {"opinion": feel(session, body.a, body.b, body.get("change"))}]
		"reputation":
			miss = _missing(body, ["target", "group"])
			if miss != "":
				return _err(400, miss)
			return [200, {"reputation": reputation(session, body.target, body.group)}]
		"remember":
			miss = _missing(body, ["name", "note"])
			if miss != "":
				return _err(400, miss)
			remember(session, name, body.note, body.get("importance", 0.6))
			return [200, {"ok": true}]
		"speak":
			if typeof(body.get("text")) != TYPE_STRING:
				return _err(400, "missing 'text' (what to say aloud)")
			var audio = await speak(session, name, body.text)
			if audio == null:
				return [200, {"audio": "", "format": "", "text": body.text}]
			return [200, {"audio": Marshalls.raw_to_base64(audio.data), "format": "wav", "seconds": Py.round_to(audio.seconds, 3), "text": audio.text}]
		"listen":
			if typeof(body.get("audio")) != TYPE_STRING:
				return _err(400, "missing 'audio' (the recording, base64)")
			return [200, {"text": await listen(session, body.audio, body.get("language"))}]
		"suggest":
			miss = _missing(body, ["name"])
			if miss != "":
				return _err(400, miss)
			if not body.has("examples"):
				return _err(400, "missing 'examples' (the replies the player could say: also the offline answer)")
			if facts != null and not (facts is Dictionary):
				return _err(400, "'facts' must be an object {name: value}")
			var suggested: Array = await suggest(session, name, body.examples, body.get("speaker") if Py.truthy(body.get("speaker")) else "player", facts)
			return [200, {"replies": suggested}]
		"converse":
			miss = _missing(body, ["a", "b"])
			if miss != "":
				return _err(400, miss)
			var exchanged: Array = await converse(session, body.a, body.b, body.get("about") if Py.truthy(body.get("about")) else "", body.get("turns"))
			return [200, {"lines": exchanged}]
		"inspect":
			return [200, inspect(session)]
		"save":
			return [200, {"data": save_state(session)}]
		"load":
			miss = _missing(body, ["data"])
			if miss != "":
				return _err(400, miss)
			return [200, {"ok": load_state(session, body.data)}]
		"state":
			if not (body.get("state") is Dictionary):
				return _err(400, "missing 'state' (an object)")
			set_state(session, body.state)
			return [200, {"ok": true}]
		"status":
			return [200, status()]
		"stats":
			return [200, stats()]
		"journal":
			var n = Py.finite(body.get("n"))
			return [200, {"entries": journal(int(n) if n != null and int(n) != 0 else 100)}]
	return _err(404, "unknown verb '" + verb + "'")


## chat() with the reply streamed: pieces as they are written, then what the server's "done" event carries.
func chat_stream(session: String, body: Dictionary, on_piece: Callable) -> Array:
	_fault = ""
	_fault_type = false
	var speaker = body.get("speaker") if Py.truthy(body.get("speaker")) else "player"
	var image = body.get("image") if Py.truthy(body.get("image")) else null
	var s: Dictionary = await chat(session, body.get("name"), body.get("message"), body.get("facts"), speaker, on_piece, 0.0, body.get("max_chars"), image)
	if _fault != "":
		var why := "chat: a field has the wrong type (" + _fault + ")" if _fault_type else "chat: " + _fault
		_fault = ""
		return [400, {"error": why}]
	var out := {"done": true, "text": s.text}
	out.merge(_feelings(session, body.get("name"), speaker), true)
	out.merge(_reply_extra(s, body), true)
	return [200, out]


func _feelings(session: String, name: Variant, speaker: Variant) -> Dictionary:
	var s := soul(session, name)
	return {"mood": s.mood.word, "feeling": opinion(session, name, speaker), "gesture": s.gesture}


func _reply_extra(s: Dictionary, body: Dictionary) -> Dictionary:
	var out := {"source": s.source}
	if typeof(body.get("do")) == TYPE_BOOL and body["do"]:
		var acts := []
		for a in s.actions:
			if not a.taken:
				acts.append({"tool": a.tool, "args": a.args})
			a.taken = true
		out["do"] = acts
	return out
