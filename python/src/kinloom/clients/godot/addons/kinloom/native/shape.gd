extends RefCounted
## Shapes by example: the developer shows an example answer; Kinloom validates model answers against it.

const Py = preload("py.gd")


class Shape:
	const MAX_DEPTH := 12
	const MAX_LIST := 50
	const MAX_TEXT := 200
	var kind := ""
	var example = null
	var lo := 0.0
	var hi := 0.0
	var whole := false
	var max_len := 0
	var options: Array = []
	var item = null
	var fields := {}

	static func bare(kind_: String, example_: Variant) -> Shape:
		var s := Shape.new()
		s.kind = kind_
		s.example = example_
		return s

	## The fields of an action's object shape whose example is a choice (options or a range) that args leave out
	## (absent in any letter case, or null). Data may take the example's value; an action must not get a decision
	## nobody made.
	static func missing_choices(shape: Variant, args: Variant) -> Array:
		var out := []
		if shape == null or shape.kind != "object" or not (args is Dictionary):
			return out
		var given := {}
		for k in args:
			given[Py.lower(str(k))] = args[k]
		for name in shape.fields:
			var f = shape.fields[name]
			if (f.kind == "options" or f.kind == "range") and given.get(Py.lower(str(name))) == null:
				out.append(name)
		return out

	static func fmt(n: float) -> String:
		if n == floorf(n) and absf(n) < 1e15:
			return str(int(n))
		return Py.g(n)

	## [shape, ""] or [null, why it cannot be one].
	static func of(example_: Variant, depth := 0) -> Array:
		if depth > MAX_DEPTH:
			return [null, "example nested too deeply (max %d levels)" % MAX_DEPTH]
		match typeof(example_):
			TYPE_BOOL:
				return [bare("boolean", example_), ""]
			TYPE_INT:
				return [bare("integer", example_), ""]
			TYPE_FLOAT:
				if is_nan(example_) or is_inf(example_):
					return [null, "examples must be finite numbers"]
				return [bare("number", example_), ""]
			TYPE_STRING, TYPE_STRING_NAME:
				var s := str(example_)
				if s.begins_with("#") and Py.re("^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$").search(s) != null:
					return [bare("color", Py.lower(s)), ""]
				var t := bare("text", s)
				var n := s.length()
				t.max_len = MAX_TEXT if n <= MAX_TEXT else mini(2000, n * 2)
				return [t, ""]
			TYPE_DICTIONARY:
				if example_.is_empty():
					return [null, "an empty object says nothing: give example fields"]
				var o := bare("object", example_)
				for k in example_:
					var r := of(example_[k], depth + 1)
					if r[0] == null:
						return r
					o.fields[str(k)] = r[0]
				return [o, ""]
			TYPE_ARRAY:
				var items: Array = example_
				if items.size() == 2 and Py.finite(items[0]) != null and Py.finite(items[1]) != null:
					var a := Py.num(items[0])
					var c := Py.num(items[1])
					var rg := bare("range", example_)
					rg.lo = minf(a, c)
					rg.hi = maxf(a, c)
					rg.whole = typeof(items[0]) == TYPE_INT and typeof(items[1]) == TYPE_INT and rg.hi - rg.lo >= 2
					return [rg, ""]
				var strs := items.size() >= 2
				for x in items:
					if typeof(x) != TYPE_STRING:
						strs = false
				if strs:
					var op := bare("options", example_)
					for x in items:
						if not op.options.has(x):
							op.options.append(x)
					return [op, ""]
				if items.size() >= 1:
					var l := bare("list", example_)
					var r := of(items[0], depth + 1)
					if r[0] == null:
						return r
					l.item = r[0]
					return [l, ""]
				return [null, "an empty list says nothing about its items: give one example item"]
		return [null, "unsupported example %s (use text, numbers, true/false, lists, ranges or objects)" % Py.py_repr(example_)]

	func default_value() -> Variant:
		match kind:
			"options":
				return options[0]
			"range":
				var mid := (lo + hi) / 2.0
				return int(floorf(mid + 0.5)) if whole else mid
			"object":
				var out := {}
				for k in fields:
					out[k] = fields[k].default_value()
				return out
			"list":
				var out := []
				for x in example:
					var r: Array = item.check(x, "value")
					out.append(r[1] if r[0] else item.default_value())
				return out
		return example

	## [ok, cleaned value, error].
	func check(value: Variant, path := "value") -> Array:
		match kind:
			"options":
				if typeof(value) == TYPE_STRING:
					var v := Py.strip(value)
					for o in options:
						if o == v or Py.lower(o) == Py.lower(v):
							return [true, o, null]
				var q := []
				for o in options:
					q.append("\"" + o + "\"")
				return [false, null, path + " must be one of " + ", ".join(q)]
			"range":
				var n = Py.number_of(value)
				if n == null:
					return [false, null, "%s must be a number from %s to %s" % [path, fmt(lo), fmt(hi)]]
				var c := minf(maxf(n, lo), hi)
				return [true, int(floorf(c + 0.5)) if whole else c, null]
			"integer":
				var n = Py.number_of(value)
				if n == null or absf(n - roundf(n)) > 1e-9 or absf(n) > 2147483647.0:
					return [false, null, path + " must be a whole number"]
				return [true, int(Py.round_to(n, 0)), null]
			"number":
				var n = Py.number_of(value)
				if n == null or absf(n) > 1e9:
					return [false, null, path + " must be a number"]
				return [true, float(n), null]
			"boolean":
				if typeof(value) == TYPE_BOOL:
					return [true, value, null]
				if typeof(value) == TYPE_STRING:
					var low := Py.lower(Py.strip(value))
					if low in ["true", "yes", "false", "no"]:
						return [true, low == "true" or low == "yes", null]
				return [false, null, path + " must be true or false"]
			"color":
				if typeof(value) == TYPE_STRING and Py.re("^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$").search(Py.strip(value)) != null:
					var v := Py.lower(Py.strip(value))
					return [true, v if v.begins_with("#") else "#" + v, null]
				return [false, null, path + " must be a color like \"#rrggbb\""]
			"text":
				var s := ""
				if typeof(value) == TYPE_STRING:
					s = value
				elif typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT:
					s = Py.text_of(value)
				else:
					return [false, null, path + " must be text"]
				var v := Py.clean(s)
				if v == "":
					return [false, null, path + " must not be empty"]
				if v.length() > max_len:
					return [false, null, "%s must be at most %d characters" % [path, max_len]]
				return [true, v, null]
			"list":
				if value is Dictionary:
					# JSON mode makes models wrap a list in an object ({"list": [...]}, {"stalls": [...]}) or answer one item
					var lists := []
					for x in value.values():
						if x is Array:
							lists.append(x)
					if not lists.is_empty():
						value = lists[0]          # the first list, as items stream it (Items)
					elif item.kind == "object":
						var one: Array = item.check(value, path + "[0]")
						if one[0]:
							return [true, [one[1]], null]
				if not (value is Array):
					return [false, null, path + " must be a list"]
				if value.size() > MAX_LIST:
					return [false, null, "%s must have at most %d items" % [path, MAX_LIST]]
				var out := []
				for i in value.size():
					var r: Array = item.check(value[i], "%s[%d]" % [path, i])
					if not r[0]:
						return r
					out.append(r[1])
				if out.is_empty():
					return [false, null, path + " must not be empty"]
				return [true, out, null]
			"object":
				if not (value is Dictionary):
					return [false, null, path + " must be an object with " + ", ".join(fields.keys())]
				# a key matched exactly, else case-insensitively (the first key of the answer with that lowercase)
				var lower := {}
				for key in value:
					var low := str(key).to_lower()
					if not lower.has(low):
						lower[low] = key
				var found := {}
				var none := true
				for k in fields:
					found[k] = k if value.has(k) else lower.get(str(k).to_lower())
					if found[k] != null:
						none = false
				if not fields.is_empty() and none:
					if value.size() == 1 and value.values()[0] is Dictionary:
						return check(value.values()[0], path)   # {"item": {...}}: the answer wrapped once
					return [false, null, path + " must be an object with " + ", ".join(fields.keys())]
				var out := {}
				for k in fields:
					if found[k] != null:
						var r: Array = fields[k].check(value[found[k]], k)
						if not r[0]:
							return r
						out[k] = r[1]
					else:
						out[k] = fields[k].default_value()
				return [true, out, null]
		return [false, null, "unknown shape"]

	## A model's answer read and checked: [ok, value, error].
	func parse(answer: String) -> Array:
		var data = Py.find_json(answer)
		if data == null:
			return [false, null, Py.CUT if Py.cut_off(answer) else "the answer was not JSON"]
		return check(data, "value")

	func describe(indent := "") -> String:
		match kind:
			"options":
				var q := []
				for o in options:
					q.append("\"" + o + "\"")
				return "one of " + ", ".join(q)
			"range":
				return "%s from %s to %s" % ["whole number" if whole else "number", fmt(lo), fmt(hi)]
			"integer":
				return "whole number, e.g. %d" % example
			"number":
				return "number, e.g. " + fmt(example)
			"boolean":
				return "true or false"
			"color":
				return "color like \"#rrggbb\""
			"text":
				return "short text (max %d characters), e.g. %s" % [max_len, Py.dumps(example)]
			"list":
				return "list (1 to %d items) of: %s" % [MAX_LIST, item.describe(indent)]
			"object":
				var inner := indent + "  "
				var lines := []
				for k in fields:
					lines.append(inner + "\"" + k + "\": " + fields[k].describe(inner))
				return "{\n" + ",\n".join(lines) + "\n" + indent + "}"
		return "anything"

	func signature() -> String:
		return Py.dumps(example, true, true)

## The elements of the first JSON list in a text that arrives in pieces (a list, or a list value of the top object:
## {"items": [...]}), each one as soon as it is complete. feed(piece) returns the texts of the new elements.
class Items:
	var buf := ""
	var i := 0
	var start := 0
	var level := -1
	var stack: Array = []
	var in_string := false
	var escape := false
	var done := false

	func feed(piece: String) -> Array:
		var out := []
		if done or piece == "":
			return out
		buf += piece
		while i < buf.length():
			var ch := buf[i]
			if in_string:
				if escape:
					escape = false
				elif ch == "\\":
					escape = true
				elif ch == '"':
					in_string = false
			elif ch == '"':
				in_string = true
			elif ch == "[" or ch == "{":
				stack.append(ch)
				if ch == "[" and level == -1 and (stack.size() == 1 or (stack.size() == 2 and stack[0] == "{")):
					level = stack.size()
					start = i + 1
			elif ch == "]" or ch == "}":
				if ch == "]" and level != -1 and stack.size() == level:
					_emit(buf.substr(start, i - start), out)
					done = true
					i += 1
					return out
				if not stack.is_empty():
					stack.pop_back()
			elif ch == "," and level != -1 and stack.size() == level:
				_emit(buf.substr(start, i - start), out)
				start = i + 1
			i += 1
		return out

	static func _emit(text: String, out: Array) -> void:
		var t := Py.strip(text)
		if t != "":
			out.append(t)
