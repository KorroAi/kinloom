extends RefCounted
## A mind's declaration, its variants and a seeded random generator (kinloom/minds.py).

const Py = preload("py.gd")
const Rules = preload("rules.gd")


## [Declaration, ""] or [null, why].
static func declaration(name: Variant, personality: Variant = "", senses: Variant = null, actions: Variant = null, rules: Variant = null,
		variants: Variant = 3) -> Array:
	var s := Rules.senses_of(senses)
	if s[0] == null:
		return [null, s[1]]
	var a := Rules.actions_of(actions)
	if a[0] == null:
		return [null, a[1]]
	var d := Declaration.new()
	d.name = Py.text_of(name).substr(0, 48)
	d.personality = ("" if not Py.truthy(personality) else Py.text_of(personality)).substr(0, 600)
	d.senses = s[0]
	d.actions = a[0]
	d.order = d.actions.keys()
	var n = Py.number_of(variants) if Py.truthy(variants) else 1
	d.variants = clampi(int(n) if n != null and not is_nan(n) and not is_inf(n) else 1, 1, Rules.MAX_VARIANTS)
	d.rules = rules
	var base = null
	if Py.truthy(rules):
		var v := Rules.validate(rules, d)
		base = v[0]
		d.rule_errors = v[1]
	if base == null:
		base = {}
		for x in d.order:
			base[x] = {"score": 1.0, "when": [], "args": {}}
	d.offline = base
	return [d, ""]


class Declaration:
	var name := ""
	var personality := ""
	var senses := {}
	var actions := {}
	var order: Array = []
	var variants := 3
	var rules = null
	var rule_errors: Array = []
	var offline := {}


## mulberry32: learning without a model is reproducible per mind.
class Rand:
	const M := 0xFFFFFFFF
	var s := 0

	func _init(seed: int) -> void:
		s = seed & M

	static func imul(a: int, b: int) -> int:
		a &= M
		b &= M
		return (a * (b & 0xFFFF) + (((a * (b >> 16)) & 0xFFFF) << 16)) & M

	func random() -> float:
		s = (s + 0x6d2b79f5) & M
		var t := s
		t = imul(t ^ (t >> 15), t | 1)
		t ^= (t + imul(t ^ (t >> 7), t | 61)) & M
		return float((t ^ (t >> 14)) & M) / 4294967296.0

	func uniform(a: float, b: float) -> float:
		return a + (b - a) * random()

	func randrange(n: int) -> int:
		return int(floorf(random() * n))

	func choice(items: Array) -> Variant:
		return items[randrange(items.size())]


class Mind:
	var version := 1
	var units := {}
	var cache = null
	var decl
	var variants: Array = []

	func _init(decl_, given: Variant = null) -> void:
		decl = decl_
		var progs := []
		if given is Array:
			for p in given:
				if p is Dictionary:
					progs.append(p)
		if progs.is_empty():
			for i in decl.variants:
				progs.append(decl.offline)
		variants = progs.slice(0, Rules.MAX_VARIANTS)

	func set_variant(index: int, program: Dictionary) -> void:
		variants[index] = program
		version += 1
		cache = null

	func set_variants(programs: Array) -> void:
		variants = programs.slice(0, Rules.MAX_VARIANTS)
		version += 1
		cache = null

	func compiled() -> Dictionary:
		if cache == null:
			var progs := []
			for p in variants:
				progs.append(Rules.compile_program(p, decl))
			cache = {"name": decl.name, "version": version, "order": decl.order.duplicate(), "stick": Rules.MIND_STICK, "variants": progs}
		return cache

	func think(senses: Variant, who: Variant = null) -> Dictionary:
		return Rules.run_compiled(compiled(), senses, who, units)

	func explain(senses: Variant, who: Variant = null) -> Dictionary:
		var c := compiled()
		var index: int = Rules.fnv1a("" if who == null else str(who)) % c.variants.size() if c.variants.size() > 1 else 0
		var prog: Dictionary = variants[index]
		var s0 = senses if senses is Dictionary else {}
		var scores := {}
		for action in decl.order:
			var spec: Dictionary = c.variants[index][action]
			var values := []
			for r in spec.when:
				values.append(Py.round_to(Rules.rule_value(r, s0), 4))
			var given = prog.get(action, {})
			scores[action] = {"score": Py.round_to(Rules.score_action(spec, s0), 4),
				"rules": (given.get("when", []) if given is Dictionary else []).duplicate(), "values": values}
		var best = decl.order[0]
		for a in decl.order:
			if scores[a].score > scores[best].score:
				best = a
		return {"action": best, "variant": index, "scores": scores}
