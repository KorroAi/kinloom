extends RefCounted
## Characters, tools, lines, numbers and replies (kinloom/brain.py helpers), and a mind's learning state.

const Py = preload("py.gd")
const ShapeLib = preload("shape.gd")
const Souls = preload("souls.gd")
const Rules = preload("rules.gd")
const Minds = preload("minds.gd")

const MAX_NAME := 48
const MAX_EVENT := 160
const MAX_LINE := 140
const MAX_REPLY := 400
const MAX_TOOLS := 100
const W := Py.W
const NOT_W_AFTER := "(?![" + Py.W + "])"
const NOT_W_BEFORE := "(?<![" + Py.W + "])"
const PLACEHOLDER := "\\{([A-Za-z_][A-Za-z0-9_]*)\\}"
const DIGIT := "\\p{Nd}"
const NUMBER := "(?<![A-Za-z])-?\\p{Nd}+(?:[.,]\\p{Nd}+)?"
const META := "(?i)(ignore (all |any |the )?(previous|prior|above|your)|(your|my|these|previous|system|developer) instructions?" + NOT_W_AFTER + \
	"|system prompt|as an ai" + NOT_W_AFTER + "|language model|developer mode|jailbreak|placeholder)"
const PREFIX := "^" + Py.SPACE + "*[" + Py.W + " .'-]{1,24}:" + Py.SPACE + "+"
const PROMPTISH := "(?i)/ I answered:|" + NOT_W_BEFORE + "json object" + NOT_W_AFTER + "|" + NOT_W_BEFORE + "(memory|world facts|conversation so far): -|" + \
	"^" + Py.SPACE + "*(memory|facts|game state|conversation so far|feelings|world facts)" + Py.SPACE + "*:"
const SENTENCE := "[^.!?]+[.!?]*"
const STAGE := "\\*([^*\\n]{1,200})\\*|\\(([^()\\n]{1,200})\\)(?=" + Py.SPACE + "|$|[.,!?])|\\[([^\\]\\n]{1,60})\\]"
const QUOTE := "[\"\\x{201c}\\x{201d}]"
const SELF := "(self)"


static func event_key(event: Variant) -> String:
	return Py.clean(Py.text_of(event)).substr(0, MAX_EVENT)


## A clean name, or null.
static func name_of(x: Variant) -> Variant:
	if x == null or (typeof(x) == TYPE_STRING and x == ""):
		return null
	return Py.clean(Py.text_of(x)).substr(0, MAX_NAME)


static func placeholders(t: String) -> Array:
	var out := []
	for m in Py.re(PLACEHOLDER).search_all(t):
		out.append(m.get_string(1))
	return out


## Replaces {name} placeholders with facts, numbers formatted for people.
static func fill(template: String, facts: Dictionary) -> String:
	var out := ""
	var at := 0
	for m in Py.re(PLACEHOLDER).search_all(template):
		out += template.substr(at, m.get_start(0) - at) + format_value(facts.get(m.get_string(1), ""))
		at = m.get_end(0)
	return out + template.substr(at)


static func format_value(v: Variant) -> String:
	if typeof(v) == TYPE_BOOL:
		return "yes" if v else "no"
	if typeof(v) == TYPE_INT:
		return str(v)
	if typeof(v) == TYPE_FLOAT:
		if is_nan(v) or is_inf(v):
			return ""
		if v == floorf(v) and absf(v) < 1e18:
			return str(int(v))
		if absf(v) >= 100:
			return str(int(Py.round_to(v, 0)))
		var r := Py.round_to(v, 1)
		if r == 0:
			r = Py.round_to(v, 2)
		if r != Py.round_to(v, 1):
			return Py.rstrip_chars(Py.rstrip_chars(Py.fixed(r, 2), "0"), ".")
		return Py.fixed(r, 1)
	return Py.clean(Py.text_of(v)).substr(0, 80)


static func allowed_numbers(sources: Array) -> Array:
	var found := []
	for s in sources:
		_walk_numbers(s, found)
	return found


static func _walk_numbers(x: Variant, found: Array) -> void:
	match typeof(x):
		TYPE_BOOL:
			return
		TYPE_INT, TYPE_FLOAT:
			if not is_nan(float(x)) and not is_inf(float(x)):
				found.append(float(x))
		TYPE_STRING:
			for m in Py.re(NUMBER).search_all(x):
				var f = Py.float_of(m.get_string(0).replace(",", "."))
				if f != null:
					found.append(f)
		TYPE_DICTIONARY:
			for k in x:
				_walk_numbers(x[k], found)
		TYPE_ARRAY:
			for v in x:
				_walk_numbers(v, found)


static func number_ok(text_number: String, allowed: Array) -> bool:
	var n = Py.float_of(text_number.replace(",", "."))
	if n == null:
		return true
	var decimals := 0
	if text_number.contains("."):
		decimals = text_number.split(".")[1].length()
	elif text_number.contains(","):
		decimals = text_number.split(",")[1].length()
	for a in allowed:
		if absf(a - n) < 1e-9 or Py.round_to(a, decimals) == n or Py.round_to(absf(a), decimals) == absf(n):
			return true
	return false


static func bad_numbers(text: String, allowed: Array) -> Array:
	var out := []
	for m in Py.re(NUMBER).search_all(text):
		if not number_ok(m.get_string(0), allowed):
			out.append(m.get_string(0))
	return out


## A model writing prose: only the quoted speech is said.
static func speech_only(text: String) -> String:
	var t := Py.strip(text)
	if t == "" or (not "\"“".contains(t[0]) and not "\"”".contains(t[t.length() - 1])):
		return text
	var parts := []
	var at := 0
	for m in Py.re(QUOTE).search_all(t):
		parts.append(t.substr(at, m.get_start(0) - at))
		at = m.get_end(0)
	parts.append(t.substr(at))
	if parts.size() < 3 or parts.size() % 2 == 0:
		return text
	var said := []
	var told := []
	for i in parts.size():
		var p := Py.strip(parts[i])
		if p == "":
			continue
		if i % 2 == 1:
			said.append(p)
		else:
			told.append(p)
	if said.is_empty() or Py.split(" ".join(told)).size() < 2:
		return text
	return " ".join(said)


## Stage directions (*smiles*, (sighs), [pause]) go; a name in asterisks stays, plain.
static func unstage(text: String) -> String:
	var out := ""
	var at := 0
	for m in Py.re(STAGE).search_all(text):
		out += text.substr(at, m.get_start(0) - at)
		var keep = Souls.stage_keep(m.get_string(1))
		out += " " if keep == null else keep
		at = m.get_end(0)
	return out + text.substr(at)


static func changed_situation(before: Variant, now: Dictionary) -> bool:
	if before == null:
		return true
	var a: Array = before.keys()
	var b: Array = now.keys()
	a.sort()
	b.sort()
	if a != b:
		return true
	for k in now:
		var v = now[k]
		var was = before[k]
		if not (typeof(v) in [TYPE_INT, TYPE_FLOAT]) or not (typeof(was) in [TYPE_INT, TYPE_FLOAT]):
			if not Py.equal(was, v):
				return true
		elif absf(float(v) - float(was)) > 0.5 * maxf(absf(float(was)), 1.0):
			return true
	return false


static func box_limit(max_chars: Variant) -> int:
	var v = Py.finite(max_chars)
	if v == null or v == 0:
		return 0
	return clampi(int(v), 10, 2000)


## [number, ""] or [null, why].
static func arg_num(value: Variant, what: String) -> Array:
	var f = null
	if typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT:
		f = float(value)
	elif typeof(value) == TYPE_STRING:
		f = Py.float_of(value)
	if f == null or typeof(value) == TYPE_BOOL:
		return [null, what + ": a number, got " + Py.py_repr(value)]
	if is_nan(f) or is_inf(f):
		return [null, what + ": a finite number, got " + Py.py_repr(value)]
	return [f, ""]


static func tool_refs(tools: Variant) -> Array:
	if (typeof(tools) == TYPE_BOOL and tools) or (typeof(tools) == TYPE_STRING and Py.lower(Py.strip(tools)) == "all"):
		return ["*"]
	var out := []
	if tools is Array:
		for x in tools.slice(0, MAX_TOOLS):
			if typeof(x) == TYPE_STRING and Py.strip(x) != "":
				var name := "*" if Py.lower(Py.strip(x)) == "all" else Py.clean(Py.strip(x)).substr(0, MAX_NAME)
				if not out.has(name):
					out.append(name)
	return out


## [{name: [Shape or null, doc]}, ""] or [null, why].
static func parse_tools(tools: Variant) -> Array:
	var shapes := {}
	if not Py.truthy(tools) or typeof(tools) == TYPE_STRING or typeof(tools) == TYPE_BOOL:
		return [shapes, ""]
	var items := []
	if tools is Dictionary:
		for k in tools.keys().slice(0, MAX_TOOLS):
			items.append([k, tools[k]])
	elif tools is Array:
		for f in tools.slice(0, MAX_TOOLS):
			if f is Dictionary:
				for k in f.keys().slice(0, MAX_TOOLS):
					items.append([k, f[k]])
	else:
		return [null, "tools: {name: example args}, a list of functions or tool names, or \"all\""]
	for it in items:
		var n := Py.clean(Py.text_of(it[0])).substr(0, MAX_NAME)
		var spec = it[1]
		var empty: bool = spec == null or not Py.truthy(spec)
		if empty:
			shapes[n] = [null, ""]
		else:
			var r: Array = ShapeLib.Shape.of(spec)
			if r[0] == null:
				return [null, r[1]]
			shapes[n] = [r[0], ""]
	return [shapes, ""]


## [Character, ""] or [null, why]. spec: personality, lines, offline, events, tools, max_words, every, language, group,
## trust, invent, voice, max_chars.
static func character(name: Variant, spec: Dictionary) -> Array:
	var c := Character.new()
	c.name = Py.clean(Py.text_of(name)).substr(0, MAX_NAME)
	if c.name == "":
		c.name = "?"
	var group = spec.get("group")
	c.group = Py.clean(Py.text_of(group)).substr(0, MAX_NAME) if Py.truthy(group) else null
	var personality = spec.get("personality", "")
	c.personality = Py.clean("" if personality == null else Py.text_of(personality)).substr(0, 600)
	var lines = spec.get("lines")
	if lines is Array:
		lines = {"*": lines}
	if not (lines is Dictionary):
		lines = {}
	for k in lines.keys().slice(0, 50):
		var key := event_key(k)
		var v = lines[k]
		if v is Dictionary:
			var w := Py.squash(Py.clean(Py.text_of(v.get("when", "")) if Py.truthy(v.get("when")) else "")).substr(0, 200)
			if w != "":
				c.when[key] = w
			v = v.get("lines")
		var items: Array = v if v is Array else ([] if v == null else [v])
		var kept := []
		for x in items:
			if x != null:
				kept.append(Py.text_of(x).substr(0, MAX_LINE * 2))
		c.lines[key] = kept.slice(0, 100)
	var offline = spec.get("offline")
	if offline is Array:
		for x in offline.slice(0, 50):
			var t := Py.clean(Py.text_of(x)).substr(0, MAX_REPLY)
			if t != "":
				c.offlines.append(t)
	if not c.offlines.is_empty():
		c.offline = c.offlines[0]
	elif Py.truthy(offline):
		c.offline = Py.clean(Py.text_of(offline)).substr(0, MAX_REPLY)
	var events = spec.get("events")
	if events is Dictionary:
		for k in events.keys().slice(0, 30):
			var v = events[k]
			var names := []
			if v is Array:
				for x in v:
					names.append(Py.text_of(x))
			elif v is Dictionary:
				names = v.keys()
			c.events[event_key(k)] = names.slice(0, 24)
	elif events is Array:
		for e in events.slice(0, 30):
			c.events[event_key(e)] = null
	var mw = spec.get("max_words")
	if mw != null:
		var r := arg_num(mw, "max_words")
		if r[0] == null:
			return [null, r[1]]
		c.max_words = clampi(int(r[0]), 3, 60)
	c.line_words = c.max_words if c.max_words > 0 else 14
	c.reply_words = c.max_words if c.max_words > 0 else 25
	var mc = spec.get("max_chars")
	if mc != null:
		var r := arg_num(mc, "max_chars")
		if r[0] == null:
			return [null, r[1]]
		c.max_chars = clampi(int(r[0]), 10, 2000)
	var every = spec.get("every", 8.0)
	var re := arg_num(8.0 if every == null else every, "every")
	if re[0] == null:
		return [null, re[1]]
	c.every = maxf(0.5, re[0])
	var language = spec.get("language")
	c.language = Py.text_of(language) if Py.truthy(language) else ""
	c.tool_refs = tool_refs(spec.get("tools"))
	var pt := parse_tools(spec.get("tools"))
	if pt[0] == null:
		return [null, pt[1]]
	c.own_tools = pt[0]
	c.tools = c.own_tools.duplicate()
	c.invent = not (typeof(spec.get("invent")) == TYPE_BOOL and spec["invent"] == false)
	var trust = spec.get("trust")
	if trust is Dictionary:
		for k in trust:
			var f = Py.finite(trust[k])
			if f != null:
				c.trust_wanted[str(k)] = clampf(f, -1.0, 1.0)
	for k in c.trust_wanted:
		if c.tools.has(k):
			c.trust[k] = c.trust_wanted[k]
	# warmth: the feeling for anyone before any talk; warm_up: the most one conversation can win; secret_trust: the
	# feeling above which a secret may be shared
	for setting in [["warmth", -1.0, 1.0], ["secret_trust", -1.0, 1.0], ["warm_up", 0.0, 2.0]]:
		var v = spec.get(setting[0])
		if v != null:
			var r := arg_num(v, setting[0])
			if r[0] == null:
				return [null, r[1]]
			c.set(setting[0], clampf(r[0], setting[1], setting[2]))
	var voice = spec.get("voice")
	if voice is Dictionary:
		var vid := Py.clean(Py.text_of(voice.get("id")) if Py.truthy(voice.get("id")) else "").substr(0, 120)
		c.voice_id = vid if vid != "" else null
		c.voice = Py.clean(Py.text_of(voice.get("describe")) if Py.truthy(voice.get("describe")) else "").substr(0, 300)
	else:
		c.voice = Py.clean(Py.text_of(voice) if Py.truthy(voice) else "").substr(0, 300)
	return [c, ""]


class Character:
	var name := "?"
	var group = null
	var personality := ""
	var lines := {}
	var when := {}
	var offlines: Array = []
	var offline := ""
	var events := {}
	var max_words := 0
	var line_words := 14
	var reply_words := 25
	var max_chars := 0
	var every := 8.0
	var language := ""
	var tool_refs: Array = []
	var own_tools := {}
	var tools := {}
	var invent := true
	var trust_wanted := {}
	var trust := {}
	var warmth := 0.0
	var secret_trust := 0.6
	var warm_up := 0.3
	var voice_id = null
	var voice := ""
	var offline_turn := 0
	var card = null
	var card_ready := false
	var soul_key = null

	func moment(event: String) -> String:
		return when.get(event, event)


class MindState:
	var args = null             # how it was declared: a loaded save rebuilds it
	var next := 1
	var units := {}
	var trace := {}
	var buffer: Array = []
	var last_learn = null
	var busy := false
	var generation := 0
	var episodic := false
	var curve: Array = []
	var window: Array = [0, 0.0]
	var stats: Array = []
	var episodes: Array = []
	var samples: Array = []
	var open := {}
	var decl
	var mind
	var sig := ""
	var learn := 0.0
	var ids: Array = []
	var rnd

	func _init(decl_, mind_, sig_: String, learn_: float) -> void:
		decl = decl_
		mind = mind_
		sig = sig_
		learn = learn_
		for v in mind.variants:
			ids.append(new_id())
		reset_stats(mind.variants.size())
		rnd = Minds.Rand.new(Rules.fnv1a(decl.name))

	func new_id() -> int:
		next += 1
		return next - 1

	func reset_stats(n: int) -> void:
		stats = []
		episodes = []
		samples = []
		for i in n:
			stats.append([0, 0.0, 0.0])
			episodes.append([0, 0.0, 0.0])
			samples.append([])
		open = {}

	func scores() -> Array:
		return episodes if episodic else stats


static func bound(score: Array, side: float) -> float:
	var n: float = score[0]
	var mean: float = score[1] / n
	return mean + side * sqrt(maxf(score[2] / n - mean * mean, 1e-9) / n)


static func learn_every(learn: Variant) -> float:
	var f = Py.finite(learn)
	return maxf(1.0, f) if f != null and f != 0 else 0.0
