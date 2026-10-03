extends RefCounted
## Python's text and number rules for the native SDK: the prompts must be the same, byte for byte, in every SDK.
## (Godot's regex has no Unicode \w, \d, \s; its str() of a float is not Python's; its JSON reads every number as a
## float: this file has the exact versions.)

## Python's whitespace (str.isspace) as a regex class, and its inside.
const SPACE_IN := "\\t\\n\\x{0b}\\x{0c}\\r\\x{1c}-\\x{1f} \\x{85}\\x{a0}\\x{1680}\\x{2000}-\\x{200a}\\x{2028}\\x{2029}\\x{202f}\\x{205f}\\x{3000}"
const SPACE := "[" + SPACE_IN + "]"
## Python's \w inside a class: letters, numbers and _.
const W := "\\p{L}\\p{N}_"
const _SPACES := [9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 0x85, 0xa0, 0x1680, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000]

static var _res := {}


## A compiled pattern, kept (flags: "i" for case-insensitive, ASCII letters only).
static func re(pattern: String) -> RegEx:
	if not _res.has(pattern):
		var r := RegEx.new()
		if r.compile(pattern) != OK:
			push_error("[kinloom] bad pattern: " + pattern)
		_res[pattern] = r
	return _res[pattern]


## Text matched literally inside a pattern.
static func escape(text: String) -> String:
	var out := ""
	for c in text:
		if "\\.^$|?*+()[]{}-/".contains(c):
			out += "\\"
		out += c
	return out


static func is_space(c: int) -> bool:
	return c in _SPACES or (c >= 0x2000 and c <= 0x200a)


static func strip(s: String) -> String:
	var a := 0
	var b := s.length()
	while a < b and is_space(s.unicode_at(a)):
		a += 1
	while b > a and is_space(s.unicode_at(b - 1)):
		b -= 1
	return s.substr(a, b - a)


static func lstrip(s: String) -> String:
	var a := 0
	while a < s.length() and is_space(s.unicode_at(a)):
		a += 1
	return s.substr(a)


static func rstrip(s: String) -> String:
	var b := s.length()
	while b > 0 and is_space(s.unicode_at(b - 1)):
		b -= 1
	return s.substr(0, b)


static func strip_chars(s: String, chars: String) -> String:
	var a := 0
	var b := s.length()
	while a < b and chars.contains(s[a]):
		a += 1
	while b > a and chars.contains(s[b - 1]):
		b -= 1
	return s.substr(a, b - a)


static func rstrip_chars(s: String, chars: String) -> String:
	var b := s.length()
	while b > 0 and chars.contains(s[b - 1]):
		b -= 1
	return s.substr(0, b)


## str.split(): the words between whitespace.
static func split(s: String) -> Array:
	var out := []
	for m in re("[^" + SPACE_IN + "]+").search_all(s):
		out.append(m.get_string(0))
	return out


static func squash(s: String) -> String:
	return " ".join(split(s))


## s[:n] (code points, like Python).
static func head(s: String, n: int) -> String:
	return s.substr(0, n)


## str.lower(), as Python ("İ" becomes "i" and a combining dot).
static func lower(s: String) -> String:
	return s.replace("İ", "i̇").to_lower()


static func is_upper(c: String) -> bool:
	return c.to_lower() != c and c.to_upper() == c


static func is_number(v: Variant) -> bool:
	return typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT


## A finite number, or null (booleans are not numbers).
static func finite(v: Variant) -> Variant:
	if typeof(v) == TYPE_INT:
		return float(v)
	if typeof(v) == TYPE_FLOAT and not is_nan(v) and not is_inf(v):
		return v
	return null


static func num(v: Variant) -> float:
	if typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT:
		return float(v)
	if typeof(v) == TYPE_BOOL:
		return 1.0 if v else 0.0
	return 0.0


## Python's float(text), or null.
static func float_of(s: String) -> Variant:
	var t := strip(s)
	var bare := t.to_lower()
	var signs := 0
	while bare.begins_with("+") or bare.begins_with("-"):
		bare = bare.substr(1)
		signs += 1
	if signs <= 1 and bare in ["inf", "infinity", "nan"]:
		if bare == "nan":
			return NAN
		return -INF if t.begins_with("-") else INF
	if re("^[+-]?([0-9](_?[0-9])*(\\.([0-9](_?[0-9])*)?)?|\\.[0-9](_?[0-9])*)([eE][+-]?[0-9](_?[0-9])*)?$").search(t) == null:
		return null
	return t.replace("_", "").to_float()


## A finite number from a number or numeric text, or null.
static func number_of(v: Variant) -> Variant:
	var f = null
	if typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT:
		f = float(v)
	elif typeof(v) == TYPE_STRING:
		f = float_of(v)
	if f == null or is_nan(f) or is_inf(f):
		return null
	return f


# ---------- exact decimals ----------

static func _mul_small(v: Array, f: int) -> void:
	var carry := 0
	for i in v.size():
		var x: int = v[i] * f + carry
		v[i] = x % 1000000000
		carry = x / 1000000000
	while carry > 0:
		v.append(carry % 1000000000)
		carry = carry / 1000000000


static func _big_text(v: Array) -> String:
	var out := str(v[v.size() - 1])
	for i in range(v.size() - 2, -1, -1):
		out += "%09d" % v[i]
	return out


## The exact decimal of m * 2^e (m > 0): [digits without trailing zeros, point] with value = 0.digits x 10^point.
static func _exact_of(m: int, e: int) -> Array:
	while m % 2 == 0 and e < 0:
		m = m / 2
		e += 1
	var v := [m % 1000000000, (m / 1000000000) % 1000000000, m / 1000000000000000000]
	while v.size() > 1 and v[v.size() - 1] == 0:
		v.pop_back()
	var d := ""
	var point := 0
	if e >= 0:
		var left := e
		while left > 0:
			var step := mini(left, 30)
			_mul_small(v, 1 << step)
			left -= step
		d = _big_text(v)
		point = d.length()
	else:
		var left := -e
		while left > 0:
			var step := mini(left, 13)
			var p := 1
			for k in step:
				p *= 5
			_mul_small(v, p)
			left -= step
		d = _big_text(v)
		point = d.length() + e
	while d.length() > 1 and d.ends_with("0"):
		d = d.left(d.length() - 1)
	return [d, point]


static func _parts(x: float) -> Array:
	var b := PackedByteArray()
	b.resize(8)
	b.encode_double(0, absf(x))
	var bits := b.decode_u64(0)
	var field := (bits >> 52) & 0x7ff
	var frac := bits & ((1 << 52) - 1)
	if field == 0:
		return [frac, -1074, field]
	return [frac | (1 << 52), field - 1075, field]


## [negative, digits, point]: |x| = 0.digits x 10^point exactly.
static func exact(x: float) -> Array:
	var b := PackedByteArray()
	b.resize(8)
	b.encode_double(0, x)
	var neg := b.decode_u64(0) < 0
	if x == 0:
		return [neg, "0", 1]
	var p := _parts(x)
	var r := _exact_of(p[0], p[1])
	return [neg, r[0], r[1]]


## digits rounded to keep digits, half to even: [digits, point].
static func round_digits(digits: String, point: int, keep: int) -> Array:
	if keep >= digits.length():
		return [digits, point]
	if keep < 0:
		return ["0", point]
	var head_d := digits.substr(0, keep)
	var rest := digits.substr(keep)
	var r0 := rest.unicode_at(0)
	var up := r0 > 53 or (r0 == 53 and (rest.substr(1).replace("0", "") != "" or (keep > 0 and (head_d.unicode_at(keep - 1) - 48) % 2 == 1)))
	if not up:
		return ["0" if head_d == "" else head_d, point]
	if head_d == "":
		return ["1", point + 1]
	var chars := head_d.to_ascii_buffer()
	var i := chars.size()
	while true:
		if i == 0:
			return ["1" + chars.get_string_from_ascii(), point + 1]
		i -= 1
		if chars[i] == 57:
			chars[i] = 48
		else:
			chars[i] += 1
			break
	return [chars.get_string_from_ascii(), point]


## "%.{f}f" % x; plus: "%+.{f}f".
static func fixed(x: float, f: int, plus := false) -> String:
	if is_nan(x):
		return "nan"
	if is_inf(x):
		return "-inf" if x < 0 else ("+inf" if plus else "inf")
	var e := exact(x)
	var r := round_digits(e[1], e[2], e[2] + f)
	var all: String = r[0]
	var point: int = r[1]
	if point <= 0:
		all = "0".repeat(1 - point) + all
		point = 1
	while all.length() < point + f:
		all += "0"
	var integer := all.substr(0, point).lstrip("0")
	if integer == "":
		integer = "0"
	var body := integer + "." + all.substr(point, f) if f > 0 else integer
	return ("-" if e[0] else ("+" if plus else "")) + body


## round(x, n): the double nearest the correctly rounded decimal (ties to even).
static func round_to(x: float, n: int) -> float:
	if is_nan(x) or is_inf(x):
		return x
	return fixed(x, n).to_float()


static func _trim_zeros(s: String) -> String:
	if not s.contains("."):
		return s
	return s.rstrip("0").rstrip(".")


static func _exp(e: int) -> String:
	return ("e-" if e < 0 else "e+") + ("%02d" % absi(e))


## "%g" % x
static func g(x: float) -> String:
	if is_nan(x):
		return "nan"
	if is_inf(x):
		return "-inf" if x < 0 else "inf"
	if x == 0:
		return "-0" if exact(x)[0] else "0"
	var e := exact(x)
	var r := round_digits(e[1], e[2], 6)
	var exp10: int = r[1] - 1
	var d6: String = r[0]
	while d6.length() < 6:
		d6 += "0"
	d6 = d6.substr(0, 6)
	var sign := "-" if e[0] else ""
	if exp10 < -4 or exp10 >= 6:
		return sign + _trim_zeros(d6.substr(0, 1) + "." + d6.substr(1)) + _exp(exp10)
	var s := d6.substr(0, exp10 + 1) + "." + d6.substr(exp10 + 1) if exp10 >= 0 else "0." + "0".repeat(-exp10 - 1) + d6
	return sign + _trim_zeros(s)


static func _cmp(a: Array, b: Array) -> int:
	if a[1] != b[1]:
		return -1 if a[1] < b[1] else 1
	var x: String = a[0]
	var y: String = b[0]
	var n := maxi(x.length(), y.length())
	x = x.rpad(n, "0")
	y = y.rpad(n, "0")
	return 0 if x == y else (-1 if x < y else 1)


## repr(float): the shortest digits that read back as x, in Python's layout ("1.0", "1e-05", "1e+16").
static func repr(x: float) -> String:
	if is_nan(x):
		return "nan"
	if is_inf(x):
		return "-inf" if x < 0 else "inf"
	if x == 0:
		return "-0.0" if exact(x)[0] else "0.0"
	var p := _parts(x)
	var m: int = p[0]
	var e: int = p[1]
	var ex := _exact_of(m, e)
	var hi := _exact_of(2 * m + 1, e - 1)
	var lo := _exact_of(4 * m - 1, e - 2) if m == (1 << 52) and p[2] > 1 else _exact_of(2 * m - 1, e - 1)
	var even := m % 2 == 0
	var digits: String = ex[0]
	var point: int = ex[1]
	for keep in range(1, 18):
		var r := round_digits(ex[0], ex[1], keep)
		var d: String = r[0].rstrip("0")
		if d == "":
			d = "0"
		var cand := [d, r[1]]
		var cl := _cmp(cand, lo)
		var ch := _cmp(cand, hi)
		if (cl > 0 or (cl == 0 and even)) and (ch < 0 or (ch == 0 and even)):
			digits = d
			point = r[1]
			break
	var exp := point - 1
	var sign := "-" if x < 0 else ""
	if exp < -4 or exp >= 16:
		var mant := digits.substr(0, 1) + "." + digits.substr(1) if digits.length() > 1 else digits
		return sign + mant + _exp(exp)
	if exp < 0:
		return sign + "0." + "0".repeat(-exp - 1) + digits
	if digits.length() <= exp + 1:
		return sign + digits + "0".repeat(exp + 1 - digits.length()) + ".0"
	return sign + digits.substr(0, exp + 1) + "." + digits.substr(exp + 1)


## str(value) as Python prints it.
static func text_of(v: Variant) -> String:
	match typeof(v):
		TYPE_NIL:
			return "None"
		TYPE_BOOL:
			return "True" if v else "False"
		TYPE_STRING, TYPE_STRING_NAME:
			return str(v)
		TYPE_INT:
			return str(v)
		TYPE_FLOAT:
			return repr(v)
		TYPE_DICTIONARY, TYPE_ARRAY:
			return py_repr(v)
	return str(v)


## The text of a value: the string itself, else str().
static func text(v: Variant) -> String:
	return str(v) if typeof(v) == TYPE_STRING or typeof(v) == TYPE_STRING_NAME else text_of(v)


## repr() of plain values.
static func py_repr(v: Variant) -> String:
	if typeof(v) == TYPE_STRING or typeof(v) == TYPE_STRING_NAME:
		var s := str(v)
		var q := "\"" if s.contains("'") and not s.contains("\"") else "'"
		var out := q
		for c in s:
			var code := c.unicode_at(0)
			if c == "\\":
				out += "\\\\"
			elif c == "\n":
				out += "\\n"
			elif c == "\r":
				out += "\\r"
			elif c == "\t":
				out += "\\t"
			elif c == q:
				out += "\\" + c
			elif code < 0x20 or code == 0x7f:
				out += "\\x%02x" % code
			else:
				out += c
		return out + q
	if v is Dictionary:
		var parts := []
		for k in v:
			parts.append(py_repr(k) + ": " + py_repr(v[k]))
		return "{" + ", ".join(parts) + "}"
	if v is Array:
		var parts := []
		for x in v:
			parts.append(py_repr(x))
		return "[" + ", ".join(parts) + "]"
	return text_of(v)


static func _json_string(s: String, ascii: bool) -> String:
	var fast := s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
	if re("[\\x{00}-\\x{1f}]").search(fast) == null and not (ascii and re("[^\\x{00}-\\x{7e}]").search(fast) != null):
		return "\"" + fast + "\""
	var out := "\""
	for c in s:
		var code := c.unicode_at(0)
		match c:
			"\"":
				out += "\\\""
			"\\":
				out += "\\\\"
			"\n":
				out += "\\n"
			"\r":
				out += "\\r"
			"\t":
				out += "\\t"
			_:
				if code == 8:
					out += "\\b"
				elif code == 12:
					out += "\\f"
				elif code < 0x20 or (ascii and code > 0x7e):
					if code >= 0x10000:
						var u := code - 0x10000
						out += "\\u%04x\\u%04x" % [0xD800 + (u >> 10), 0xDC00 + (u & 0x3FF)]
					else:
						out += "\\u%04x" % code
				else:
					out += c
	return out + "\""


## json.dumps(value, ensure_ascii=ascii, sort_keys=sort): Python's spacing and numbers.
static func dumps(v: Variant, ascii := true, sort := false) -> String:
	match typeof(v):
		TYPE_NIL:
			return "null"
		TYPE_BOOL:
			return "true" if v else "false"
		TYPE_STRING, TYPE_STRING_NAME:
			return _json_string(str(v), ascii)
		TYPE_INT:
			return str(v)
		TYPE_FLOAT:
			if is_nan(v):
				return "NaN"
			if is_inf(v):
				return "-Infinity" if v < 0 else "Infinity"
			return repr(v)
		TYPE_DICTIONARY:
			var keys: Array = v.keys()
			if sort:
				keys = keys.duplicate()
				keys.sort()
			var parts := []
			for k in keys:
				parts.append(_json_string(str(k), ascii) + ": " + dumps(v[k], ascii, sort))
			return "{" + ", ".join(parts) + "}"
		TYPE_ARRAY:
			var parts := []
			for x in v:
				parts.append(dumps(x, ascii, sort))
			return "[" + ", ".join(parts) + "]"
	return _json_string(str(v), ascii)


## json.dumps(value, ensure_ascii=False)
static func dumps_text(v: Variant) -> String:
	return dumps(v, false, false)


## Compact JSON for HTTP bodies (keys in the order given).
static func compact(v: Variant) -> String:
	match typeof(v):
		TYPE_DICTIONARY:
			var parts := []
			for k in v:
				parts.append(_json_string(str(k), false) + ":" + compact(v[k]))
			return "{" + ",".join(parts) + "}"
		TYPE_ARRAY:
			var parts := []
			for x in v:
				parts.append(compact(x))
			return "[" + ",".join(parts) + "]"
		TYPE_FLOAT:
			if is_nan(v) or is_inf(v):
				return "null"
			return repr(v)
	return dumps(v, false, false)


# ---------- json.loads / raw_decode (ints stay ints) ----------

## raw_decode at index at: [ok, value, end].
static func decode(t: String, at: int) -> Array:
	var st := {"t": t, "i": at, "depth": 0}
	var v = _value(st)
	if st.has("error"):
		return [false, null, at]
	return [true, v, st.i]


static func _ws(st: Dictionary) -> void:
	var t: String = st.t
	while st.i < t.length() and t[st.i] in [" ", "\t", "\n", "\r"]:
		st.i += 1


static func _fail(st: Dictionary) -> Variant:
	st["error"] = true
	return null


static func _value(st: Dictionary) -> Variant:
	st.depth += 1
	if st.depth > 900:
		return _fail(st)
	var v = _inner(st)
	st.depth -= 1
	return v


static func _inner(st: Dictionary) -> Variant:
	var t: String = st.t
	if st.i >= t.length():
		return _fail(st)
	var ch := t[st.i]
	if ch == "{":
		st.i += 1
		var obj := {}
		_ws(st)
		if st.i < t.length() and t[st.i] == "}":
			st.i += 1
			return obj
		while true:
			_ws(st)
			if st.i >= t.length() or t[st.i] != "\"":
				return _fail(st)
			var k = _string(st)
			if st.has("error"):
				return null
			_ws(st)
			if st.i >= t.length() or t[st.i] != ":":
				return _fail(st)
			st.i += 1
			_ws(st)
			var v = _value(st)
			if st.has("error"):
				return null
			obj[k] = v
			_ws(st)
			if st.i < t.length() and t[st.i] == ",":
				st.i += 1
				continue
			if st.i < t.length() and t[st.i] == "}":
				st.i += 1
				return obj
			return _fail(st)
	if ch == "[":
		st.i += 1
		var arr := []
		_ws(st)
		if st.i < t.length() and t[st.i] == "]":
			st.i += 1
			return arr
		while true:
			_ws(st)
			var v = _value(st)
			if st.has("error"):
				return null
			arr.append(v)
			_ws(st)
			if st.i < t.length() and t[st.i] == ",":
				st.i += 1
				continue
			if st.i < t.length() and t[st.i] == "]":
				st.i += 1
				return arr
			return _fail(st)
	if ch == "\"":
		return _string(st)
	for word in [["true", true], ["false", false], ["null", null], ["NaN", NAN], ["Infinity", INF], ["-Infinity", -INF]]:
		if t.substr(st.i, word[0].length()) == word[0]:
			st.i += word[0].length()
			return word[1]
	var j: int = st.i
	var start := j
	if j < t.length() and t[j] == "-":
		j += 1
	if j < t.length() and t[j] == "0":
		j += 1
	elif j < t.length() and t[j] >= "0" and t[j] <= "9":
		while j < t.length() and t[j] >= "0" and t[j] <= "9":
			j += 1
	else:
		return _fail(st)
	var is_float := false
	if j + 1 < t.length() and t[j] == "." and t[j + 1] >= "0" and t[j + 1] <= "9":
		is_float = true
		j += 1
		while j < t.length() and t[j] >= "0" and t[j] <= "9":
			j += 1
	if j < t.length() and (t[j] == "e" or t[j] == "E"):
		var k := j + 1
		if k < t.length() and (t[k] == "-" or t[k] == "+"):
			k += 1
		if k < t.length() and t[k] >= "0" and t[k] <= "9":
			while k < t.length() and t[k] >= "0" and t[k] <= "9":
				k += 1
			is_float = true
			j = k
	st.i = j
	var number := t.substr(start, j - start)
	if not is_float and number.length() <= 18:
		return number.to_int()
	return number.to_float()


static func _hex4(t: String, at: int) -> int:
	if at + 4 > t.length():
		return -1
	var h := t.substr(at, 4)
	for c in h:
		if not "0123456789abcdefABCDEF".contains(c):
			return -1
	return h.hex_to_int()


static func _string(st: Dictionary) -> Variant:
	var t: String = st.t
	st.i += 1
	var out := ""
	while true:
		if st.i >= t.length():
			return _fail(st)
		var ch := t[st.i]
		if ch == "\"":
			st.i += 1
			return out
		if ch == "\\":
			if st.i + 1 >= t.length():
				return _fail(st)
			var n := t[st.i + 1]
			st.i += 2
			match n:
				"\"":
					out += "\""
				"\\":
					out += "\\"
				"/":
					out += "/"
				"b":
					out += char(8)
				"f":
					out += char(12)
				"n":
					out += "\n"
				"r":
					out += "\r"
				"t":
					out += "\t"
				"u":
					var code := _hex4(t, st.i)
					if code < 0:
						return _fail(st)
					st.i += 4
					if code >= 0xD800 and code < 0xDC00 and st.i + 1 < t.length() and t[st.i] == "\\" and t[st.i + 1] == "u":
						var low := _hex4(t, st.i + 2)
						if low >= 0xDC00 and low < 0xE000:
							code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
							st.i += 6
					if code >= 0xD800 and code < 0xE000:
						code = 0xFFFD
					if code != 0:                   # a Godot String cannot hold NUL: dropped (clean_text drops it too)
						out += char(code)
				_:
					return _fail(st)
			continue
		if ch.unicode_at(0) < 0x20:
			return _fail(st)
		out += ch
		st.i += 1
	return null


## json.loads: [ok, value].
static func loads(text: String) -> Array:
	var i := 0
	while i < text.length() and text[i] in [" ", "\t", "\n", "\r"]:
		i += 1
	var r := decode(text, i)
	if not r[0]:
		return [false, null]
	var end: int = r[2]
	while end < text.length() and text[end] in [" ", "\t", "\n", "\r"]:
		end += 1
	if end != text.length():
		return [false, null]
	return [true, r[1]]


## Python's == on JSON values (True == 1, 1 == 1.0, deep).
static func equal(a: Variant, b: Variant) -> bool:
	var na := typeof(a) in [TYPE_INT, TYPE_FLOAT, TYPE_BOOL]
	var nb := typeof(b) in [TYPE_INT, TYPE_FLOAT, TYPE_BOOL]
	if na and nb:
		return num(a) == num(b)
	if a is Array and b is Array:
		if a.size() != b.size():
			return false
		for i in a.size():
			if not equal(a[i], b[i]):
				return false
		return true
	if a is Dictionary and b is Dictionary:
		if a.size() != b.size():
			return false
		for k in a:
			if not b.has(k) or not equal(a[k], b[k]):
				return false
		return true
	if typeof(a) != typeof(b):
		return false
	return a == b


static func truthy(v: Variant) -> bool:
	match typeof(v):
		TYPE_NIL:
			return false
		TYPE_BOOL:
			return v
		TYPE_STRING, TYPE_STRING_NAME:
			return str(v) != ""
		TYPE_DICTIONARY, TYPE_ARRAY:
			return not v.is_empty()
		TYPE_INT, TYPE_FLOAT:
			return v != 0
	return true


## The items of a list as text ("" for null).
static func strings(v: Variant) -> Array:
	var out := []
	if v is Array:
		for x in v:
			out.append("" if x == null else text_of(x))
	return out


## A stable sort (Python's): less(a, b) is true when a goes first.
static func stable_sort(items: Array, less: Callable) -> Array:
	if items.size() < 2:
		return items.duplicate()
	var mid := items.size() / 2
	var a := stable_sort(items.slice(0, mid), less)
	var b := stable_sort(items.slice(mid), less)
	var out := []
	var i := 0
	var j := 0
	while i < a.size() and j < b.size():
		if less.call(b[j], a[i]):
			out.append(b[j])
			j += 1
		else:
			out.append(a[i])
			i += 1
	out.append_array(a.slice(i))
	out.append_array(b.slice(j))
	return out


# ---------- text cleaning and JSON found in model answers ----------

static func _control(c: int) -> bool:
	return c <= 8 or (c >= 0x0b and c <= 0x1f) or c == 0x7f or (c >= 0x202a and c <= 0x202e) or (c >= 0x2066 and c <= 0x2069)


## One tidy line: control characters removed, whitespace collapsed.
static func clean(s: String) -> String:
	if s.contains(char(0x1b)):
		s = re("\\x{1b}\\[[0-9;?]*[ -/]*[@-~]").sub(s, "", true)
	return squash(re("[\\x{00}-\\x{08}\\x{0b}-\\x{1f}\\x{7f}\\x{202a}-\\x{202e}\\x{2066}-\\x{2069}]").sub(s, "", true))


static func clean_value(v: Variant) -> String:
	return clean(text(v))


## The first JSON object or array in a model answer, or null.
static func find_json(text_in: Variant) -> Variant:
	if typeof(text_in) != TYPE_STRING:
		return null
	var t := strip(text_in)
	if t == "" or t.length() > 100000:
		return null
	var fence := t.find("```")
	if fence >= 0:
		var start := t.find("\n", fence)
		var end := t.find("```", start + 1) if start >= 0 else -1
		if start >= 0 and end > start:
			t = strip(t.substr(start + 1, end - start - 1))
	var whole := loads(t)
	if whole[0]:
		return whole[1]
	for open in ["{", "["]:
		var at := t.find(open)
		var tries := 0
		while at >= 0 and tries < 20:
			var r := decode(t, at)
			if r[0]:
				return r[1]
			at = t.find(open, at + 1)
			tries += 1
	return null
