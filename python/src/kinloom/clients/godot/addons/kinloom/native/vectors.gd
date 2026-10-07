extends RefCounted
## The pure functions by the names of python/conformance/vectors.json: vector(fn, args) gives the Python reference's
## output. run_file(path) -> [passed, total, failures] (the SDK's proof, printed as "vectors: N/N").

const Py = preload("py.gd")
const ShapeLib = preload("shape.gd")
const Souls = preload("souls.gd")
const Stream = preload("stream.gd")
const Prompts = preload("prompts.gd")
const Mem = preload("memory.gd")
const Rules = preload("rules.gd")
const Minds = preload("minds.gd")
const Lines = preload("lines.gd")
const Brain = preload("brain.gd")
const M = preload("model.gd")

const ZERO := "(?<![\\d.])(-?\\d+)\\.0(?![\\d])"

static var _brain = null
static var _thinkers := {}


static func _arg(a: Array, i: int, default: Variant = null) -> Variant:
	return a[i] if i < a.size() and a[i] != null else default


static func _character(spec: Dictionary) -> Variant:
	return Lines.character(spec.get("name", "?"), spec)[0]


static func _declaration(d: Dictionary) -> Variant:
	return Minds.declaration(d.get("name"), d.get("personality", ""), d.get("senses"), d.get("actions"), d.get("rules"), d.get("variants", 3))[0]


static func _null_if_empty(r: Array) -> Array:
	return [r[0], r[1] if r[1] != "" else null]


static func vector(fn: String, args: Array) -> Variant:
	if _brain == null:
		_brain = Brain.new({"provider": null})
	match fn:
		"shape":
			var s = ShapeLib.Shape.of(args[0])[0]
			var r: Array = s.check(args[1])
			return {"ok": r[0], "value": r[1], "error": r[2], "describe": s.describe(), "default": s.default_value()}
		"shape_error":
			var r: Array = ShapeLib.Shape.of(args[0])
			return null if r[0] != null else r[1]
		"find_json":
			return Py.find_json(args[0])
		"parse":
			var r: Array = ShapeLib.Shape.of(args[0])[0].parse(args[1])
			return {"ok": r[0], "value": r[1], "error": r[2]}
		"clean_text":
			return Py.clean(Py.text_of(args[0]))
		"fill":
			return Lines.fill(args[0], args[1])
		"event_key":
			return Lines.event_key(args[0])
		"split":
			return Souls.split(args[0])
		"cap":
			return Stream.cap(args[0], args[1], _arg(args, 2, 0))
		"fit_chars":
			return Stream.fit_chars(args[0], _arg(args, 1, 0))
		"whole_sentences":
			return Souls.whole_sentences(args[0])
		"drop_echoes":
			return Stream.drop_echoes(args[0], args[1])
		"leaks":
			return Souls.leaks(args[0], args[1], args[2], 0.5, _arg(args, 3, ""))
		"keep_secrets":
			return Souls.keep_secrets(args[0], args[1], args[2], _arg(args, 3, ""))
		"worn":
			return Souls.worn(args[0])
		"drop_narrated":
			return Souls.drop_narrated(args[0], _arg(args, 1, ""), _arg(args, 2, []))
		"inner":
			return Souls.inner_of_reply(args[0])
		"reason":
			return Brain.reason(args[0])
		"refused_note":
			return Brain.refused_note(args[0], args[1], args[2])
		"items":
			var it = ShapeLib.Items.new()
			var got := []
			for p in args[0]:
				got.append_array(it.feed(p))
			return got
		"card":
			return Souls.card(args[0], _arg(args, 1, ""))
		"describe_card":
			return Souls.describe(args[0])
		"mood_now":
			return Souls.mood_now(args[0], args[1], _arg(args, 2, ""))
		"ago":
			return Souls.ago(args[0])
		"strength":
			return Souls.strength(args[0])
		"feeling":
			return Prompts.feeling(args[0])
		"feelings":
			var fc = _character(args[0])
			return [fc.warmth, fc.secret_trust, fc.warm_up]
		"stream":
			var splitter := Stream.Splitter.new()
			var guard := Stream.Guard.new(Py.re(Lines.META))
			var unstager := Stream.Unstage.new()
			var echo := Stream.Echo.new(args[1])
			var cut := Stream.Cap.new(args[2], _arg(args, 3, 0))
			var shown := []
			for p in args[0]:
				var x := cut.feed(echo.feed(unstager.feed(guard.feed(splitter.feed(p)))))
				if x != "":
					shown.append(x)
			var tail := cut.feed(echo.feed(unstager.feed(guard.feed(splitter.finish()[2]) + guard.finish()) + unstager.finish()) + echo.finish())
			tail += cut.finish()
			if tail != "":
				shown.append(tail)
			return shown
		"clean_reply":
			var why := []
			return [_brain._clean_reply(args[0], args[1], why), why]
		"valid_line":
			var c = _character({"name": "V", "max_words": null if args[2] == 14 else args[2], "max_chars": args[3]})
			return _brain._valid_line(args[0], args[1], c)
		"bad_numbers":
			return Lines.bad_numbers(args[0], Lines.allowed_numbers(args[1]))
		"speech_only":
			return Lines.speech_only(args[0])
		"changed":
			return Lines.changed_situation(args[0], args[1])
		"stable_pick":
			return M.stable_pick(args[0], args[1])
		"fnv1a":
			return Rules.fnv1a(args[0])
		"recall":
			var box := {"t": 0.0}
			var m = Mem.Memory.new("", func() -> float: return box.t)
			for n in args[0]:
				box.t = Py.num(n.t)
				m.add("s", "MIRA", n.text, n.importance, {"about": n.about} if Py.truthy(n.get("about")) else {})
			return m.recall("s", ["MIRA"], args[1], args[2], args[3])
		"prompt":
			return _prompt(args[0], args[1], args[2])
		"parse_rule":
			return _null_if_empty(Rules.parse_rule(args[0], Rules.senses_of(args[1])[0]))
		"rule_value":
			return Rules.rule_value(args[0], args[1])
		"validate":
			return Rules.validate(args[0], _declaration(args[1]))
		"compile":
			return Minds.Mind.new(_declaration(args[0])).compiled()
		"think", "explain":
			var key := Py.dumps(args[0], true, true)
			if not _thinkers.has(key):
				_thinkers[key] = Minds.Mind.new(_declaration(args[0]))
			var mind = _thinkers[key]
			return mind.think(args[1], _arg(args, 2)) if fn == "think" else mind.explain(args[1], _arg(args, 2))
		"evidence":
			return Rules.evidence(_declaration(args[0]), args[1])
		"senses_error":
			var r := Rules.senses_of(args[0])
			return null if r[0] != null else r[1]
	return "unknown vector " + fn


static func _prompt(name: String, spec: Variant, a: Array) -> Variant:
	var decl = _declaration(spec) if spec is Dictionary and spec.has("senses") else null
	var c = _character(spec) if spec is Dictionary and decl == null else null
	match name:
		"lines_system":
			return Prompts.lines_system(c, a[0], a[1], a[2], a[3], _arg(a, 4, 0))
		"line_system":
			return Prompts.line_system(c, a[0], a[1], a[2], _arg(a, 3, 0))
		"decide_system":
			return Prompts.decide_system(c, ShapeLib.Shape.of(a[0])[0], a[1])
		"chat_system":
			return Prompts.chat_system(c, a[0], _arg(a, 1, []), _arg(a, 2, []), _arg(a, 3, "chat"))
		"soul_system":
			return Prompts.soul_system(c, a[0])
		"recollect_system":
			return Prompts.recollect_system(c, a[0])
		"act_system":
			return Prompts.act_system(c, a[0])
		"deeds_system":
			return Prompts.deeds_system(c)
		"create_system":
			return Prompts.create_system(a[0], ShapeLib.Shape.of(a[1])[0], a[2])
		"create_many_system":
			return Prompts.create_many_system(a[0], ShapeLib.Shape.of(a[1])[0], a[2], a[3])
		"context":
			return Prompts.context(a[0], _arg(a, 1), _arg(a, 2))
		"facts_block":
			return Prompts.facts_block(a[0])
		"situation_block":
			return Prompts.situation_block(a[0])
		"context_block":
			return Prompts.context_block(a[0])
		"history_block":
			return Prompts.history_block(a[0], _arg(a, 1, 10))
		"worn_block":
			return Prompts.worn_block(a[0], _arg(a, 1, ""))
		"box_block":
			return Prompts.box_block(_arg(a, 0, 0))
		"picture_block":
			return Prompts.picture_block(Py.truthy(_arg(a, 0)), _arg(a, 1, ""))
		"message_block":
			return Prompts.message_block(a[0], _arg(a, 1, ""))
		"bond_block":
			return Prompts.bond_block(a[0], a[1], a[2], a[3], a[4], a[5], a[6], _arg(a, 7, ""), _arg(a, 8, false), _arg(a, 9, Souls.SECRET_TRUST))
		"steer_block":
			return Prompts.steer_block(_arg(a, 0, ""))
		"remark_system":
			return Prompts.remark_system(a[0], a[1], int(_arg(a, 2, 0)) if _arg(a, 2) != null else 0)
		"remark_user":
			return Prompts.remark_user(a[0])
		"refused_block":
			return Prompts.refused_block(_arg(a, 0, null))
		"deeds_user":
			return Prompts.deeds_user(a[0], a[1], _arg(a, 2, ""), a[3])
		"soul_user":
			return Prompts.soul_user(a[0], _arg(a, 1, []))
		"repair":
			return Prompts.repair(a[0])
		"stay_in_character":
			return Prompts.stay_in_character(a[0])
		"say_new":
			return Prompts.say_new()
		"keep_secret":
			return Prompts.keep_secret(a[0], a[1])
		"numbers_repair":
			return Prompts.numbers_repair()
		"write_in":
			return Prompts.write_in(a[0])
		"impact_system":
			return Prompts.impact_system(a[0])
		"impact_user":
			return Prompts.impact_user(a[0], a[1], a[2])
		"suggest_system":
			return Prompts.suggest_system(c, int(a[0]), a[1])
		"suggest_user":
			return Prompts.suggest_user(a[0], a[1], a[2])
		"converse_system":
			return Prompts.converse_system(c, _character(a[0]), int(a[1]), a[2], _arg(a, 3, []))
		"converse_user":
			return Prompts.converse_user(a[0], a[1], a[2], a[3], a[4])
		"rating_line":
			return Prompts.rating_line(_arg(a, 0))
		"mind_system":
			return Prompts.mind_system(decl, a[0])
		"minds_user":
			return Prompts.minds_user(decl, a[0], _arg(a, 1))
		"mind_learn_user":
			return Prompts.mind_learn_user(a[0], a[1], a[2], a[3], a[4], a[5], a[6], _arg(a, 7))
	return "unknown prompt " + name


## Python == with number spellings ignored (2.0 and 2 are the same number to a model).
static func same(a: Variant, b: Variant) -> bool:
	if typeof(a) == TYPE_STRING and typeof(b) == TYPE_STRING:
		return Py.re(ZERO).sub(a, "$1", true) == Py.re(ZERO).sub(b, "$1", true)
	var na := typeof(a) in [TYPE_INT, TYPE_FLOAT]
	var nb := typeof(b) in [TYPE_INT, TYPE_FLOAT]
	if na and nb:
		return float(a) == float(b) or absf(float(a) - float(b)) <= 1e-9 * maxf(1.0, maxf(absf(float(a)), absf(float(b))))
	if a is Array or b is Array:
		if not (a is Array and b is Array) or a.size() != b.size():
			return false
		for i in a.size():
			if not same(a[i], b[i]):
				return false
		return true
	if a is Dictionary and b is Dictionary:
		if a.size() != b.size():
			return false
		for k in a:
			if not b.has(k) or not same(a[k], b[k]):
				return false
		return true
	if typeof(a) != typeof(b):
		return false
	return a == b


## [passed, total, failures [{fn, args, want, got}]].
static func run_file(path: String) -> Array:
	var r := Py.loads(FileAccess.get_file_as_string(path))
	if not r[0] or not (r[1] is Array):
		return [0, 0, [{"fn": "read", "args": [path], "want": "vectors", "got": null}]]
	var passed := 0
	var failures := []
	for v in r[1]:
		var got = vector(v.fn, v.args)
		if same(got, v.out):
			passed += 1
		else:
			failures.append({"fn": v.fn, "args": v.args, "want": v.out, "got": got})
	return [passed, r[1].size(), failures]
