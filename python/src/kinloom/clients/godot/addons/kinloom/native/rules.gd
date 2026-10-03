extends RefCounted
## Minds as readable rules: senses, actions, rules, programs, mutations and evidence (kinloom/minds.py).

const Py = preload("py.gd")
const ShapeLib = preload("shape.gd")

const MIND_STICK := 0.1
const MAX_RULES := 6
const MAX_SENSES := 64
const MAX_ACTIONS := 32
const MAX_VARIANTS := 8
const MAX_SCORE := 3.0
const MAX_UNITS := 10000
const STEP := 0.05
const BELL := 0.15
const NAME := "^[A-Za-z_][A-Za-z0-9_]{0,47}$"
const S := Py.SPACE
const RULE := "(?i)^" + S + "*(?:(not)" + S + "+|(!)" + S + "*)?([A-Za-z_][A-Za-z0-9_]*)" + S + "*(?:(high|low|above|below|around|is|>=|<=|==|>|<|~|=)" + S + "*(.*?))?" + S + "*$"
const OP_WORDS := {">": "above", ">=": "above", "<": "below", "<=": "below", "~": "around", "=": "is", "==": "is"}


## FNV-1a 32-bit over UTF-8: which variant a unit gets, identical in every client.
static func fnv1a(text: String) -> int:
	var h := 0x811C9DC5
	for b in text.to_utf8_buffer():
		h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
	return h


static func num_text(x: float) -> String:
	if x == floorf(x) and absf(x) < 1e18:
		return str(int(x))
	return Py.rstrip_chars(Py.rstrip_chars(Py.fixed(x, 3), "0"), ".")


static func _finite(v: Variant) -> Variant:
	return Py.finite(v)


## [senses, ""] or [null, why].
static func senses_of(example: Variant) -> Array:
	if not (example is Dictionary) or example.is_empty():
		return [null, "senses: give an object like {\"hp\": [0, 1], \"armed\": true, \"mood\": [\"calm\", \"angry\"]}"]
	var out := {}
	var keys: Array = example.keys().slice(0, MAX_SENSES)
	for key in keys:
		var name := str(key)
		var ex = example[key]
		if Py.re(NAME).search(name) == null:
			return [null, "sense %s: use letters, digits and _ only" % Py.py_repr(name)]
		if typeof(ex) == TYPE_BOOL:
			out[name] = ["flag"]
		elif ex is Array and ex.size() == 2 and _finite(ex[0]) != null and _finite(ex[1]) != null:
			var lo := minf(Py.num(ex[0]), Py.num(ex[1]))
			var hi := maxf(Py.num(ex[0]), Py.num(ex[1]))
			if hi - lo <= 0:
				return [null, "sense %s: the range needs two different numbers" % Py.py_repr(name)]
			out[name] = ["range", lo, hi]
		elif ex is Array and ex.size() >= 2 and _all_text(ex):
			var opts := []
			for x in ex.slice(0, 32):
				opts.append(str(x).substr(0, 48))
			out[name] = ["options", opts]
		else:
			return [null, "sense %s: give a range [lo, hi], true/false, or a list of options" % Py.py_repr(name)]
	return [out, ""]


static func _all_text(items: Array) -> bool:
	for x in items:
		if typeof(x) != TYPE_STRING:
			return false
	return true


## [actions {name: {arg: Shape}}, ""] or [null, why].
static func actions_of(example: Variant) -> Array:
	if example is Array:
		var d := {}
		for a in example:
			d[Py.text_of(a)] = {}
		example = d
	if not (example is Dictionary) or example.is_empty():
		return [null, "actions: give an object like {\"attack\": {\"power\": [0, 1]}, \"wait\": {}}"]
	var out := {}
	for key in example.keys().slice(0, MAX_ACTIONS):
		var name := str(key)
		var args = example[key]
		if Py.re(NAME).search(name) == null:
			return [null, "action %s: use letters, digits and _ only" % Py.py_repr(name)]
		if args == null or (typeof(args) == TYPE_BOOL and args) or (args is Dictionary and args.is_empty()):
			out[name] = {}
		elif args is Dictionary:
			var a := {}
			for k in args:
				var r: Array = ShapeLib.Shape.of(args[k])
				if r[0] == null:
					return [null, r[1]]
				a[str(k)] = r[0]
			out[name] = a
		else:
			return [null, "action %s: give its arguments as an object of examples, or {}" % Py.py_repr(name)]
	return [out, ""]


## [compiled rule, ""] or [null, why]. Compiled: [sense, op, p1, p2].
static func parse_rule(text: Variant, senses: Dictionary) -> Array:
	if typeof(text) != TYPE_STRING or text.length() > 120:
		return [null, "a rule is short text like \"hp low\""]
	var m := Py.re(RULE).search(text)
	if m == null:
		return [null, "cannot read rule %s (examples: \"hp low\", \"dist below 12\", \"armed\", \"mood is angry\")" % Py.py_repr(text)]
	var neg := m.get_string(1) != "" or m.get_string(2) != ""
	var sense := m.get_string(3)
	var op := m.get_string(4).to_lower()
	var arg := Py.strip(m.get_string(5))
	var real = null
	for s in senses:
		if Py.lower(s) == Py.lower(sense):
			real = s
			break
	var r := Py.py_repr(text)
	if real == null:
		return [null, "rule %s: unknown sense %s (senses: %s)" % [r, Py.py_repr(sense), ", ".join(senses.keys())]]
	var kind: Array = senses[real]
	op = OP_WORDS.get(op, op)
	if kind[0] == "flag":
		if op != "" or arg != "":
			return [null, "rule %s: %s is true/false: write \"%s\" or \"not %s\"" % [r, real, real, real]]
		return [[real, "not" if neg else "flag", 0, 0], ""]
	if neg:
		return [null, "rule %s: \"not\" only goes with a true/false sense" % r]
	if kind[0] == "options":
		if op != "is":
			return [null, "rule %s: %s is one of %s: write \"%s is <option>\"" % [r, real, ", ".join(kind[1]), real]]
		for o in kind[1]:
			if Py.lower(o) == Py.lower(arg):
				return [[real, "is", o, 0], ""]
		return [null, "rule %s: %s is one of %s" % [r, real, ", ".join(kind[1])]]
	var lo: float = kind[1]
	var hi: float = kind[2]
	if op == "high" or op == "low":
		if arg != "":
			return [null, "rule %s: \"%s %s\" takes no number" % [r, real, op]]
		return [[real, op, lo, hi], ""]
	if op in ["above", "below", "around"]:
		var t = Py.float_of(arg)
		if t == null:
			return [null, "rule %s: \"%s %s\" needs a number from %s to %s" % [r, real, op, num_text(lo), num_text(hi)]]
		if is_nan(t) or is_inf(t):
			return [null, "rule %s: the number must be finite" % r]
		t = minf(maxf(t, lo), hi)
		t = float(num_text(t))
		return [[real, op, t, (hi - lo) * (BELL if op == "around" else STEP)], ""]
	return [null, "rule %s: %s is a number: use low, high, below N, above N or around N" % [r, real]]


static func rule_text(rule: Array) -> String:
	var sense: String = rule[0]
	var op: String = rule[1]
	if op == "high" or op == "low":
		return sense + " " + op
	if op in ["above", "below", "around"]:
		return sense + " " + op + " " + num_text(Py.num(rule[2]))
	if op == "flag":
		return sense
	if op == "not":
		return "not " + sense
	return sense + " is " + str(rule[2])


## 0..1; a missing or wrong-typed sense is neutral (0.5).
static func rule_value(rule: Array, senses: Variant) -> float:
	var op: String = rule[1]
	var v = senses.get(rule[0]) if senses is Dictionary else null
	if op == "flag" or op == "not":
		var on := false
		if typeof(v) == TYPE_BOOL:
			on = v
		elif _finite(v) != null:
			on = Py.num(v) != 0.0
		else:
			return 0.5
		return 1.0 if on == (op == "flag") else 0.0
	if op == "is":
		if typeof(v) != TYPE_STRING:
			return 0.5
		return 1.0 if v == str(rule[2]) else 0.0
	var xv = _finite(v)
	if xv == null:
		return 0.5
	var x: float = xv
	var p1 := Py.num(rule[2])
	var p2 := Py.num(rule[3])
	if op == "high" or op == "low":
		var y := clampf((x - p1) / (p2 - p1), 0.0, 1.0)
		return y if op == "high" else 1.0 - y
	if op == "around":
		var z := (x - p1) / p2
		return exp(-z * z)
	var zz := clampf((x - p1) / p2, -60.0, 60.0)
	var up := 1.0 / (1.0 + exp(-zz))
	return up if op == "above" else 1.0 - up


static func _empty_spec() -> Dictionary:
	return {"score": 0.0, "when": [], "args": {}}


## [clean program with every declared action, errors] or [null, errors].
static func validate(program: Variant, decl) -> Array:
	var errors := []
	if not (program is Dictionary) or program.is_empty():
		return [null, ["a mind is an object: {action: {\"score\": 1, \"when\": [rules], \"args\": {...}}}"]]
	var out := {}
	for a in decl.order:
		out[a] = _empty_spec()
	var given := 0
	for name in program.keys().slice(0, MAX_ACTIONS * 2):
		var spec = program[name]
		var action = null
		for a in decl.order:
			if Py.lower(a) == Py.lower(Py.text_of(name)):
				action = a
				break
		if action == null:
			errors.append("unknown action %s (actions: %s)" % [Py.py_repr(name), ", ".join(decl.order)])
			continue
		if spec is Array or typeof(spec) == TYPE_STRING:
			spec = {"when": spec}
		if not (spec is Dictionary):
			errors.append(action + ": give {\"score\", \"when\", \"args\"}")
			continue
		var score = _finite(spec.get("score", 1.0))
		if score == null:
			errors.append(action + ": score must be a number from 0 to 3")
			continue
		var when = spec.get("when", [])
		if typeof(when) == TYPE_STRING:
			when = [when]
		if not (when is Array):
			errors.append(action + ": when must be a list of rules")
			continue
		var rules := []
		var broken := false
		for text in when:
			var pr := parse_rule(text, decl.senses)
			if pr[1] != "":
				errors.append(action + ": " + pr[1])
				broken = true
				break
			var t := rule_text(pr[0])
			if not rules.has(t):
				rules.append(t)
		var ar := _args(spec.get("args"), decl.actions[action], decl.senses, action, errors)
		if broken or ar[1]:
			continue
		out[action] = {"score": Py.round_to(minf(maxf(score, 0.0), MAX_SCORE), 3), "when": rules.slice(0, MAX_RULES), "args": ar[0]}
		given += 1
	return [out if given > 0 else null, errors]


static func _args(given: Variant, shapes: Dictionary, senses: Dictionary, action: String, errors: Array) -> Array:
	if given == null or (given is Dictionary and given.is_empty()):
		return [{}, false]
	if not (given is Dictionary):
		errors.append(action + ": args must be an object")
		return [{}, true]
	var out := {}
	for name in given:
		var value = given[name]
		var shape = shapes.get(str(name))
		if shape == null:
			continue
		if typeof(value) == TYPE_STRING and shape.kind == "range":
			var pr := parse_rule(value, senses)
			if pr[1] != "":
				errors.append("%s.%s: %s" % [action, name, pr[1]])
				return [{}, true]
			out[str(name)] = rule_text(pr[0])
			continue
		var r: Array = shape.check(value, "%s.%s" % [action, name])
		if not r[0]:
			errors.append(r[2])
			return [{}, true]
		out[str(name)] = r[1]
	return [out, false]


## The form clients run: numbers and strings only, every argument filled.
static func compile_program(program: Dictionary, decl) -> Dictionary:
	var out := {}
	for action in decl.order:
		var spec = program.get(action)
		if not Py.truthy(spec):
			spec = _empty_spec()
		var rules := []
		for t in spec.get("when", []):
			var r = parse_rule(t, decl.senses)[0]
			if r != null:
				rules.append(r)
		var args := {}
		var shapes: Dictionary = decl.actions[action]
		for name in shapes:
			var shape = shapes[name]
			var v = spec.get("args", {}).get(name)
			if typeof(v) == TYPE_STRING and shape.kind == "range":
				var r: Array = parse_rule(v, decl.senses)[0]
				args[name] = r + [shape.lo, shape.hi, shape.whole]
			elif v == null:
				args[name] = shape.default_value()
			else:
				args[name] = v
		out[action] = {"score": Py.num(spec.get("score", 0.0)), "when": rules, "args": args}
	return out


static func score_action(spec: Dictionary, senses: Variant) -> float:
	var rules: Array = spec.when
	if rules.is_empty():
		return Py.num(spec.score)
	var product := 1.0
	for r in rules:
		product *= rule_value(r, senses)
	return Py.num(spec.score) * (pow(product, 1.0 / rules.size()) if product > 0 else 0.0)


## One decision from the compiled form. who: null or a name; units: {who: last action}.
static func run_compiled(compiled: Dictionary, senses: Variant, who: Variant, units: Dictionary) -> Dictionary:
	var variants: Array = compiled.variants
	var index: int = fnv1a("" if who == null else str(who)) % variants.size() if variants.size() > 1 else 0
	var program: Dictionary = variants[index]
	var last = units.get(who) if who != null else null
	var s0 = senses if senses is Dictionary else {}
	var best = null
	var best_score := -1.0
	for action in compiled.order:
		var s := score_action(program[action], s0)
		if last != null and action == last:
			s *= 1.0 + float(compiled.stick)
		if s > best_score + 1e-12:
			best = action
			best_score = s
	var args := {}
	var given: Dictionary = program[best].args
	for name in given:
		var v = given[name]
		if v is Array and v.size() == 7 and v[0] is String and v[6] is bool:   # set by the senses; other lists as they are
			var y := rule_value(v.slice(0, 4), s0)
			var x: float = Py.num(v[4]) + y * (Py.num(v[5]) - Py.num(v[4]))
			args[name] = int(floorf(x + 0.5)) if v[6] else x
		else:
			args[name] = v
	if who != null:
		if units.size() >= MAX_UNITS and not units.has(who):
			units.clear()
		units[who] = best
	return {"action": best, "args": args, "variant": index}


static func random_rule(decl, rnd) -> String:
	var sense: String = rnd.choice(decl.senses.keys())
	var kind: Array = decl.senses[sense]
	if kind[0] == "flag":
		return sense if rnd.random() < 0.5 else "not " + sense
	if kind[0] == "options":
		return sense + " is " + str(rnd.choice(kind[1]))
	var op: String = rnd.choice(["high", "low", "above", "below", "around"])
	if op == "high" or op == "low":
		return sense + " " + op
	return sense + " " + op + " " + num_text(Py.round_to(rnd.uniform(kind[1], kind[2]), 3))


static func copy_program(program: Dictionary) -> Dictionary:
	var out := {}
	for a in program:
		var s: Dictionary = program[a]
		out[a] = {"score": s.score, "when": s.when.duplicate(), "args": s.args.duplicate()}
	return out


static func same_program(a: Variant, b: Variant) -> bool:
	return Py.dumps(a, true, true) == Py.dumps(b, true, true)


static func _sense_of_rule(text: String) -> String:
	return text.replace("not ", "").split(" ")[0]


## A small random change (score, threshold, direction, a rule added or dropped, an argument). Always valid.
static func mutate(program: Dictionary, decl, rnd) -> Dictionary:
	for attempt in 12:
		var child := copy_program(program)
		var action: String = rnd.choice(decl.order)
		if not child.has(action):
			child[action] = _empty_spec()
		var spec: Dictionary = child[action]
		var move: float = rnd.random()
		if move < 0.25:
			var sc: float = Py.num(spec.score) * rnd.uniform(0.6, 1.5) if Py.num(spec.score) > 0.05 else rnd.uniform(0.2, 1.0)
			spec.score = Py.round_to(minf(MAX_SCORE, maxf(0.0, sc)), 3)
		elif move < 0.45 and not spec.when.is_empty():
			var i: int = rnd.randrange(spec.when.size())
			var rule: Array = parse_rule(spec.when[i], decl.senses)[0]
			if rule[1] in ["above", "below", "around"]:
				var k: Array = decl.senses[rule[0]]
				var step: float = rnd.choice([-1, 1]) * rnd.uniform(0.05, 0.25) * (k[2] - k[1])
				rule[2] = Py.round_to(minf(k[2], maxf(k[1], Py.num(rule[2]) + step)), 3)
			else:
				rule[1] = {"high": "low", "low": "high", "flag": "not", "not": "flag"}.get(rule[1], rule[1])
				if rule[1] == "is":
					rule[2] = rnd.choice(decl.senses[rule[0]][1])
			spec.when[i] = rule_text(rule)
		elif move < 0.55 and not spec.when.is_empty():
			var i: int = rnd.randrange(spec.when.size())
			var rule: Array = parse_rule(spec.when[i], decl.senses)[0]
			rule[1] = {"above": "below", "below": "above", "high": "low", "low": "high", "flag": "not", "not": "flag"}.get(rule[1], rule[1])
			spec.when[i] = rule_text(rule)
		elif move < 0.68 and not spec.when.is_empty():
			spec.when.remove_at(rnd.randrange(spec.when.size()))
		elif move < 0.88 and spec.when.size() < MAX_RULES:
			spec.when.append(random_rule(decl, rnd))
			if Py.num(spec.score) <= 0.05:
				spec.score = Py.round_to(rnd.uniform(0.3, 1.2), 3)
		elif not decl.actions[action].is_empty():
			var name: String = rnd.choice(decl.actions[action].keys())
			var shape = decl.actions[action][name]
			if shape.kind == "range" and rnd.random() < 0.5:
				var picks := []
				for n in 8:
					var r := random_rule(decl, rnd)
					if decl.senses[_sense_of_rule(r)][0] == "range":
						picks.append(r)
				var pick = rnd.choice(picks) if not picks.is_empty() else null
				if pick == null:
					spec.args.erase(name)
				else:
					spec.args[name] = pick
			elif shape.kind == "range":
				var v: float = rnd.uniform(shape.lo, shape.hi)
				spec.args[name] = int(floorf(v + 0.5)) if shape.whole else Py.round_to(v, 3)
			elif shape.kind == "options":
				spec.args[name] = rnd.choice(shape.options)
			elif shape.kind == "boolean":
				spec.args[name] = not Py.truthy(spec.args[name] if spec.args.has(name) else shape.default_value())
			else:
				continue
		else:
			continue
		var clean = validate(child, decl)[0]
		if clean != null and not same_program(clean, program):
			return clean
	return program


static func conditions(decl, samples: Array) -> Array:
	var out := []
	for name in decl.senses:
		var kind: Array = decl.senses[name]
		if kind[0] == "flag":
			out.append_array([name, "not " + name])
		elif kind[0] == "options":
			for o in kind[1]:
				out.append(name + " is " + o)
		else:
			var values := []
			for s in samples:
				var v = _finite(s[0].get(name)) if s[0] is Dictionary else null
				if v != null:
					values.append(v)
			values.sort()
			if values.size() < 20:
				continue
			for q in [0.2, 0.4, 0.6, 0.8]:
				var t := num_text(Py.round_to(values[int(q * (values.size() - 1))], 3))
				out.append_array([name + " above " + t, name + " below " + t])
	var unique := []
	for x in out:
		if not unique.has(x):
			unique.append(x)
	return unique


static func grid(decl) -> Array:
	var out := []
	for name in decl.senses:
		var kind: Array = decl.senses[name]
		if kind[0] == "range":
			for q in [0.1, 0.25, 0.5, 0.75, 0.9]:
				var t := num_text(Py.round_to(kind[1] + q * (kind[2] - kind[1]), 3))
				out.append_array([name + " above " + t, name + " below " + t])
		elif kind[0] == "flag":
			out.append_array([name, "not " + name])
		else:
			for o in kind[1]:
				out.append(name + " is " + o)
	return out


## Where an action did better or worse than the others: [z, action, rule, advantage, n], strongest first.
## samples: [[senses, action, reward], ...].
static func evidence(decl, samples: Array, min_n := 12, top := 8) -> Array:
	if samples.size() < 40:
		return []
	var mean := 0.0
	for s in samples:
		mean += Py.num(s[2])
	mean /= samples.size()
	var variance := 0.0
	for s in samples:
		variance += pow(Py.num(s[2]) - mean, 2)
	var std := sqrt(variance / samples.size())
	if std == 0.0:
		std = 1e-9
	var found := []
	for text in conditions(decl, samples):
		var rule = parse_rule(text, decl.senses)[0]
		if rule == null:
			continue
		var inside := []
		for s in samples:
			if rule_value(rule, s[0] if s[0] is Dictionary else {}) > 0.5:
				inside.append([s[1], Py.num(s[2])])
		if inside.size() < 2 * min_n:
			continue
		var base := 0.0
		for x in inside:
			base += x[1]
		base /= inside.size()
		var by_action := {}
		for x in inside:
			if not by_action.has(x[0]):
				by_action[x[0]] = [0, 0.0]
			by_action[x[0]][0] += 1
			by_action[x[0]][1] += x[1]
		for a in by_action:
			var n: int = by_action[a][0]
			if n >= min_n and decl.actions.has(a):
				var adv: float = by_action[a][1] / n - base
				found.append([adv * sqrt(n) / std, a, text, adv, n])
	found = Py.stable_sort(found, func(x, y): return absf(x[0]) > absf(y[0]))
	return found.slice(0, top)


static func negate_rule(text: String, decl) -> Variant:
	var rule: Array = parse_rule(text, decl.senses)[0]
	var flip = {"above": "below", "below": "above", "flag": "not", "not": "flag", "high": "low", "low": "high"}.get(rule[1])
	if flip == null:
		return null
	rule[1] = flip
	return rule_text(rule)


static func _with_rule(spec: Dictionary, text: String) -> void:
	var sense := _sense_of_rule(text)
	var kept := []
	for r in spec.when:
		if _sense_of_rule(r) != sense:
			kept.append(r)
	kept = kept.slice(maxi(0, kept.size() - (MAX_RULES - 1)))
	kept.append(text)
	spec.when = kept


static func prefer_rule(program: Dictionary, decl, action: String, text: String, rnd) -> Variant:
	var child := copy_program(program)
	if not child.has(action):
		child[action] = _empty_spec()
	var spec: Dictionary = child[action]
	_with_rule(spec, text)
	var top := 1.0
	var others := []
	for a in child:
		if a != action:
			others.append(Py.num(child[a].score))
	if not others.is_empty():
		top = others.max()
	spec.score = Py.round_to(minf(MAX_SCORE, maxf(maxf(Py.num(spec.score), top), 1.0) * rnd.uniform(1.05, 1.4)), 3)
	var clean = validate(child, decl)[0]
	return clean if clean != null and not same_program(clean, program) else null


## A change the data supports, or null.
static func propose(program: Dictionary, decl, samples: Array, rnd, min_z := 2.0) -> Variant:
	var tried := {}
	for s in samples:
		tried[s[1]] = tried.get(s[1], 0) + 1
	var untried := []
	for a in decl.order:
		if tried.get(a, 0) < 12:
			untried.append(a)
	if not untried.is_empty() and samples.size() >= 40 and rnd.random() < 0.5:
		var conds := conditions(decl, samples)
		conds.append_array(grid(decl))
		return prefer_rule(program, decl, rnd.choice(untried), rnd.choice(conds), rnd)
	var found := []
	for e in evidence(decl, samples, 12, 16):
		if absf(e[0]) >= min_z and (e[3] > 0 or Py.num(program.get(e[1], {}).get("score", 0)) > 0.05):
			found.append(e)
	if found.is_empty():
		return null
	var better := []
	for e in found:
		if e[3] > 0:
			better.append(e)
	var pick: Array = rnd.choice((better if not better.is_empty() else found).slice(0, 4))
	var action: String = pick[1]
	var text = pick[2]
	var adv: float = pick[3]
	if adv < 0:
		text = negate_rule(text, decl)
		if text == null:
			return null
	if adv > 0:
		return prefer_rule(program, decl, action, text, rnd)
	var child := copy_program(program)
	if not child.has(action):
		child[action] = _empty_spec()
	_with_rule(child[action], text)
	var clean = validate(child, decl)[0]
	return clean if clean != null and not same_program(clean, program) else null
