extends RefCounted
## Souls: the card, the reply format, caps, echoes, secrets (the reference is kinloom/souls.py).

const Py = preload("py.gd")

const W := Py.W
const TEXT_FIELDS := ["summary", "voice", "backstory", "mood"]
const LIST_FIELDS := ["values", "fears", "desires", "secrets", "goals", "quirks", "likes", "dislikes"]
const MAX_TEXT := 300
const MAX_ITEM := 200
const MAX_ITEMS := 6
const KEEP := 20
const SUMMARIZE := 12
const MARK := "~~~"
const HALF_LIFE := 300.0
const FADED := 0.15
const MAX_FEEL := 0.3
const SECRET_TRUST := 0.6
const TALK_RISE := 0.3
const NEW_TALK := 600.0
const INNER_KEYS := ["mood", "intensity", "feel", "remember", "gesture", "do"]
const MOOD_WORD := "^[\\p{L}\\p{Nl}\\p{No}]{2,20}$"
const CLOSERS := "[\"'\\x{201d}\\x{2019})\\]]"
const KEY_LINE := "(?:^|\\n)[ \\t]*(mood|intensity|feel|remember|gesture|do)[ \\t]*:[ \\t]*([^\\n]*)"


static func card_example() -> Dictionary:
	return {"summary": "who they are, in one sentence", "voice": "how they talk: rhythm, words they use, verbal tics",
		"backstory": "their past in two or three sentences", "values": ["what they care about"], "fears": ["what scares them"],
		"desires": ["what they want in life"], "secrets": ["what they hide"], "goals": ["what they are trying to do these days"],
		"quirks": ["a habit"], "likes": ["something they like"], "dislikes": ["something they dislike"],
		"mood": "their usual mood, one word"}


static func soul_text(v: Variant, limit: int) -> String:
	if v == null or typeof(v) in [TYPE_BOOL, TYPE_DICTIONARY, TYPE_ARRAY]:
		return ""
	return Py.head(Py.squash(Py.clean(Py.text_of(v))), limit)


static func mood_ok(mood: String) -> bool:
	return Py.re(MOOD_WORD).search(mood) != null and not mood.contains("\n")


## A clean card from anything: known fields only, bounded, never the example's placeholder texts.
static func card(value: Variant, seed: String) -> Dictionary:
	var given: Dictionary = value if value is Dictionary else {}
	var example := card_example()
	var out := {}
	for k in TEXT_FIELDS:
		var t := soul_text(given.get(k), MAX_TEXT)
		out[k] = "" if t == example[k] else t
	for k in LIST_FIELDS:
		var raw = given.get(k)
		var items: Array = raw if raw is Array else ([raw] if typeof(raw) == TYPE_STRING else [])
		var clean := []
		for i in mini(items.size(), MAX_ITEMS * 2):
			var t := soul_text(items[i], MAX_ITEM)
			if t != "" and not example[k].has(t) and not clean.has(t):
				clean.append(t)
		out[k] = clean.slice(0, MAX_ITEMS)
	if out["summary"] == "":
		out["summary"] = soul_text(seed, MAX_TEXT)
	var mood := Py.lower(out["mood"])
	out["mood"] = mood if mood_ok(mood) else ""
	return out


static func field(c: Variant, k: String) -> String:
	if c is Dictionary and typeof(c.get(k)) == TYPE_STRING:
		return c[k]
	return ""


static func secrets(c: Variant) -> Array:
	return Py.strings(c.get("secrets")) if c is Dictionary else []


static func quirks(c: Variant) -> Array:
	return Py.strings(c.get("quirks")) if c is Dictionary else []


static func texts(c: Variant) -> Array:
	var out := []
	for k in TEXT_FIELDS:
		if field(c, k) != "":
			out.append(field(c, k))
	if c is Dictionary:
		for k in LIST_FIELDS:
			out.append_array(Py.strings(c.get(k)))
	return out


static func public_texts(c: Variant) -> Array:
	var out := []
	for k in TEXT_FIELDS:
		if field(c, k) != "":
			out.append(field(c, k))
	if c is Dictionary:
		for k in LIST_FIELDS:
			if k != "secrets":
				out.append_array(Py.strings(c.get(k)))
	return out


static func seed_key(seed: String) -> String:
	return ("soul1|" + seed).sha1_text().substr(0, 16)


static func describe(c: Dictionary) -> Array:
	var labels := [["voice", "How you talk"], ["backstory", "Your past"], ["values", "You care about"], ["fears", "You fear"],
		["desires", "You want"], ["goals", "These days you are trying to"], ["secrets", "Your secrets (you hide them)"],
		["quirks", "Your habits"], ["likes", "You like"], ["dislikes", "You dislike"]]
	var lines := []
	if field(c, "summary") != "":
		lines.append("Who you are: " + field(c, "summary"))
	for l in labels:
		var v = c.get(l[0])
		if v is Array:
			if not v.is_empty():
				lines.append(l[1] + ": " + "; ".join(Py.strings(v)))
		elif typeof(v) == TYPE_STRING and v != "":
			lines.append(l[1] + ": " + v)
	return lines


## [said, inner or null] when the text ends with the inner JSON object.
static func _trailing_json(text: String) -> Array:
	var t := Py.rstrip(text)
	if not t.ends_with("}"):
		return [text, null]
	var depth := 0
	for i in range(t.length() - 1, -1, -1):
		var ch := t[i]
		if ch == "}":
			depth += 1
		elif ch == "{":
			depth -= 1
			if depth == 0:
				var data = Py.find_json(t.substr(i))
				if data is Dictionary:
					for k in ["mood", "feel", "remember", "do", "intensity", "gesture"]:
						if data.has(k):
							return [t.substr(0, i), data]
				return [text, null]
	return [text, null]


static func whole_sentences(text: String) -> String:
	var t := Py.strip(text)
	var m := Py.re("^[\\s\\S]*[.!?\\x{2026}]" + CLOSERS + "*").search(t)
	return Py.strip(m.get_string(0)) if m != null else ""


static func words_re() -> RegEx:
	return Py.re("[" + W + "'\\x{2019}]+")


static func word_count(s: String) -> int:
	return words_re().search_all(s).size()


static func word_cut(sentence: String, chars: int) -> String:
	var n := sentence.length()
	var head_len := mini(n, maxi(1, chars - 1))
	var head := sentence.substr(0, head_len)
	if head.contains(" ") and n > head_len and not Py.is_space(sentence.unicode_at(head_len)):
		head = head.substr(0, head.rfind(" "))
	return Py.rstrip_chars(head, " ,;:-–—") + "…"


static func words_lower(s: String) -> Array:
	var out := []
	for m in Py.re("[" + W + "]+").search_all(Py.lower(s)):
		out.append(m.get_string(0))
	return out


static func ordered_set(items: Array) -> Array:
	var out := []
	for i in items:
		if not out.has(i):
			out.append(i)
	return out


static func same_action(a: String, b: String) -> bool:
	var drop := ["the", "a", "his", "her", "their", "le", "la", "sa", "son"]
	var x := []
	var y := []
	for w in words_lower(a):
		if not drop.has(w) and not x.has(w):
			x.append(w)
	for w in words_lower(b):
		if not drop.has(w) and not y.has(w):
			y.append(w)
	if x.is_empty() or y.is_empty():
		return false
	var both := 0
	for w in x:
		if y.has(w):
			both += 1
	return both >= 0.6 * maxi(x.size(), y.size())


## [what is said, the first narrated action or ""].
static func drop_narrated(said: String, gesture: String, habits: Array) -> Array:
	var all := [gesture]
	all.append_array(habits)
	var actions := []
	var firsts := {}
	for a in all:
		var w := ordered_set(words_lower(a))
		if w.size() >= 2:
			actions.append(w)
		var ws := words_lower(a)
		if not ws.is_empty():
			firsts[ws[0]] = true
	if actions.is_empty() or said == "":
		return [said, ""]
	var kept := ""
	var narrated := ""
	for m in Py.re("[^.!?]+[.!?]*" + Py.SPACE + "*").search_all(said):
		var sentence := m.get_string(0)
		var ordered := words_lower(sentence)
		var words := {}
		for w in ordered:
			words[w] = true
		var hit := false
		for a in actions:
			var n := 0
			for w in a:
				if words.has(w):
					n += 1
			if n >= 0.6 * a.size() and words.size() <= a.size() + 3:
				hit = true
				break
		if not ordered.is_empty() and firsts.has(ordered[0]) and hit:
			if narrated == "":
				narrated = Py.rstrip_chars(Py.strip(sentence), ".!?")
			continue
		kept += sentence
	return [Py.strip(kept), narrated]


static func key_line_re() -> RegEx:
	return Py.re("(?i)" + KEY_LINE)


## [inner Dictionary, the text left].
static func _inner_of(segment: String) -> Array:
	var at := segment.find("{")
	if at >= 0:
		var r := Py.decode(segment, at)
		if r[0] and r[1] is Dictionary:
			return [r[1], segment.substr(0, at) + segment.substr(r[2])]
		var data = Py.find_json(segment.substr(at))
		if data is Dictionary:
			return [data, segment.substr(0, at)]
	var found := {}
	for m in key_line_re().search_all(segment):
		var key := Py.lower(m.get_string(1))
		var value: Variant = Py.strip_chars(Py.strip(m.get_string(2)), "\",")
		if key == "do":
			var l := Py.loads(value)
			value = l[1] if l[0] else []
		found[key] = value
	return [found, segment if found.is_empty() else key_line_re().sub(segment, "", true)]


## [what is said out loud, the inner part ({} when none)].
static func split(text: String) -> Array:
	var at := text.find(MARK)
	if at >= 0:
		var said := text.substr(0, at)
		var rest := text.substr(at + MARK.length())
		if Py.strip(said) != "":
			return [Py.strip(said), _inner_of(rest)[0]]
		var inner := {}
		var speech := ""
		for segment in rest.split(MARK):
			var r := _inner_of(segment)
			inner.merge(r[0], true)
			if Py.strip(r[1]) != "":
				speech = Py.strip(r[1])
		return [speech, inner]
	var tj := _trailing_json(text)
	var said: String = tj[0]
	var data = tj[1]
	if data == null:
		var line := key_line_re().search(text)
		if line != null:
			data = _inner_of(text.substr(line.get_start(0)))[0]
			said = text.substr(0, line.get_start(0))
	return [Py.strip(said), data if data != null else {}]


static func inner_only(segment: String) -> bool:
	var t := Py.strip(segment)
	return t == "" or t.begins_with("{") or Py.re("(?i)^" + KEY_LINE).search("\n" + t) != null


static func key_start(text: String) -> bool:
	var compact := Py.re(Py.SPACE + "+").sub(text, "", true)
	for k in INNER_KEYS:
		if ("{\"" + k + "\"").begins_with(compact):
			return true
	return false


## What stays of a stage direction: a name in asterisks (*Bright Mercy*) as plain words; else null.
static func stage_keep(inner: String) -> Variant:
	var t := Py.strip(inner)
	var words := Py.split(t)
	if t == "" or words.size() > 3:
		return null
	for w in words:
		if not Py.is_upper(w[0]):
			return null
	return t


static func end_re() -> RegEx:
	return Py.re("[.!?\\x{2026}]+" + CLOSERS + "*" + Py.SPACE + "+")


static func norm_words(sentence: String) -> Array:
	var out := []
	for m in words_re().search_all(Py.lower(sentence)):
		out.append(m.get_string(0).replace("’", "'"))
	return out


## difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() on word lists.
static func seq_ratio(a: Array, b: Array) -> float:
	var total := a.size() + b.size()
	if total == 0:
		return 1.0
	var b2j := {}
	for j in b.size():
		if not b2j.has(b[j]):
			b2j[b[j]] = []
		b2j[b[j]].append(j)
	var matches := 0
	var queue := [[0, a.size(), 0, b.size()]]
	while not queue.is_empty():
		var q: Array = queue.pop_back()
		var alo: int = q[0]
		var ahi: int = q[1]
		var blo: int = q[2]
		var bhi: int = q[3]
		var besti := alo
		var bestj := blo
		var bestsize := 0
		var j2len := {}
		for i in range(alo, ahi):
			var next := {}
			for j in b2j.get(a[i], []):
				if j < blo:
					continue
				if j >= bhi:
					break
				var k: int = j2len.get(j - 1, 0) + 1
				next[j] = k
				if k > bestsize:
					besti = i - k + 1
					bestj = j - k + 1
					bestsize = k
			j2len = next
		while besti > alo and bestj > blo and a[besti - 1] == b[bestj - 1]:
			besti -= 1
			bestj -= 1
			bestsize += 1
		while besti + bestsize < ahi and bestj + bestsize < bhi and a[besti + bestsize] == b[bestj + bestsize]:
			bestsize += 1
		if bestsize > 0:
			matches += bestsize
			if alo < besti and blo < bestj:
				queue.append([alo, besti, blo, bestj])
			if besti + bestsize < ahi and bestj + bestsize < bhi:
				queue.append([besti + bestsize, ahi, bestj + bestsize, bhi])
	return 2.0 * matches / total


static func sentences(text: String) -> Array:
	var out := []
	for m in Py.re("[^.!?\\x{2026}]+[.!?\\x{2026}]*" + CLOSERS + "*").search_all(text):
		if Py.strip(m.get_string(0)) != "":
			out.append(m.get_string(0))
	return out


const _PLAIN := " the a an to of and or her his their she he they them it its in on for with that this was is be been from at by my i me you your not never has have had secretly once who what which when where why how so but as into "
const _IRREGULAR := {"sold": "sell", "paid": "pay", "stole": "steal", "stolen": "steal", "gave": "give", "given": "give", "told": "tell",
	"hid": "hide", "hidden": "hide", "bought": "buy", "lost": "lose", "killed": "kill", "slew": "kill", "slain": "kill",
	"betrayed": "betra", "owed": "owe", "owes": "owe", "owing": "owe"}


static func _stem(w: String) -> String:
	w = Py.lower(w.replace("’", "'"))
	if w.ends_with("'s"):
		w = w.substr(0, w.length() - 2)
	return str(_IRREGULAR.get(w, w)).substr(0, 5)


static func _raw_words(text: String) -> Array:
	var out := []
	for m in words_re().search_all(text):
		out.append(m.get_string(0))
	return out


static func _secret_marks(secret: String, pub: Array) -> Array:
	var own := []
	for w in _raw_words(secret):
		if not _PLAIN.contains(" " + Py.lower(w) + " ") and w.length() >= 3:
			var s := _stem(w)
			if not own.has(s):
				own.append(s)
	var known := {}
	for t in pub:
		for w in _raw_words(t):
			known[_stem(w)] = true
	var telling := []
	for w in own:
		if not known.has(w):
			telling.append(w)
	return telling if telling.size() >= 2 else own


## The secret a text gives away, or null.
static func leaks(text: String, secrets_in: Array, pub: Array, share: float, asked: String) -> Variant:
	var said := {}
	for w in _raw_words(text):
		said[_stem(w)] = true
	var sents := sentences(text)
	var first: String = sents[0] if not sents.is_empty() else ""
	var yes := asked != "" and _yes(first) and _raw_words(first).size() <= 8
	var both := said.duplicate()
	if yes:
		for w in _raw_words(asked):
			both[_stem(w)] = true
	for secret in secrets_in:
		var marks := _secret_marks(secret, pub)
		var in_said := 0
		var in_both := 0
		for m in marks:
			if said.has(m):
				in_said += 1
			if both.has(m):
				in_both += 1
		if marks.size() >= 2 and (in_said >= maxf(2.0, share * marks.size()) or (yes and in_both >= 2)):
			return secret
	return null


static func _yes(first: String) -> bool:
	return Py.re("^[^" + W + "]*(aye|yes|yeah|yep|yup|true|indeed|i did|so i did|that i did|it is|it was|guilty|oui|si|ja)(?![" + W + "])").search(Py.lower(first)) != null


static func keep_secrets(text: String, secrets_in: Array, pub: Array, asked: String) -> String:
	var kept := []
	for s in sentences(text):
		var trial := kept.duplicate()
		trial.append(s)
		if leaks(" ".join(trial), secrets_in, pub, 0.5, asked) == null:
			kept.append(s)
	var stripped := []
	for k in kept:
		stripped.append(Py.strip(k))
	return Py.strip(" ".join(stripped))


## [phrases, opener].
static func worn(replies: Array) -> Array:
	var said := []
	for r in replies:
		if r != "":
			said.append(r)
	said = said.slice(maxi(0, said.size() - 6))
	var words := []
	for r in said:
		var w := []
		for m in words_re().search_all(Py.lower(r)):
			w.append(m.get_string(0))
		words.append(w)
	var found := []
	for n in [8, 7, 6, 5, 4]:
		var seen := {}
		for i in words.size():
			var w: Array = words[i]
			for j in range(0, w.size() - n + 1):
				var g := " ".join(w.slice(j, j + n))
				if not seen.has(g):
					seen[g] = {}
				seen[g][i] = true
		for g in seen:
			if seen[g].size() < 2:
				continue
			var inside := false
			for f in found:
				if f.contains(g):
					inside = true
					break
			if not inside:
				found.append(g)
	var phrases := Py.stable_sort(found, func(x, y): return x.length() > y.length())
	phrases = phrases.slice(0, 4)
	var c := words.size()
	var opener := ""
	if c >= 2 and not words[c - 1].is_empty() and not words[c - 2].is_empty() and words[c - 1][0] == words[c - 2][0]:
		opener = words[c - 1][0]
	return [phrases, opener]


static func _soul_number(v: Variant) -> Variant:
	var f = null
	if typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT:
		f = float(v)
	elif typeof(v) == TYPE_STRING:
		f = Py.float_of(v)
	if f == null or is_nan(f) or is_inf(f):
		return null
	return f


## What changed inside, checked.
static func inner_of_reply(data: Variant) -> Dictionary:
	var d: Dictionary = data if data is Dictionary else {}
	var mood := Py.lower(soul_text(d.get("mood"), 20))
	var intensity = _soul_number(d.get("intensity"))
	var feel = _soul_number(d.get("feel"))
	var acts := []
	if d.get("do") is Array:
		for x in d["do"]:
			if x is Dictionary and acts.size() < 3:
				acts.append(x)
	return {"mood": mood if mood_ok(mood) else null, "intensity": 0.6 if intensity == null else clampf(intensity, 0.0, 1.0),
		"feel": null if feel == null else clampf(feel, -MAX_FEEL, MAX_FEEL), "remember": soul_text(d.get("remember"), MAX_ITEM),
		"self": soul_text(d.get("self"), MAX_ITEM), "gesture": soul_text(d.get("gesture"), 60), "do": acts}


## [word, level]. mood: {word, level, t} or null.
static func mood_now(mood: Variant, now: float, baseline: String) -> Array:
	var b := "calm" if baseline == "" else baseline
	if not (mood is Dictionary) or mood.is_empty():
		return [b, 0.0]
	var level := Py.num(mood.get("level")) * pow(0.5, maxf(0.0, now - Py.num(mood.get("t"))) / HALF_LIFE)
	if level < FADED:
		return [b, 0.0]
	return [mood.get("word"), Py.round_to(level, 4)]


static func strength(level: float) -> String:
	return "very" if level >= 0.7 else ("a little" if level < 0.35 else "quite")


static func ago(seconds: float) -> String:
	var s := maxf(0.0, seconds)
	for u in [["month", 30 * 86400.0], ["day", 86400.0], ["hour", 3600.0], ["minute", 60.0]]:
		if s >= u[1]:
			var n := int(floorf(s / u[1]))
			return "%d %s%s ago" % [n, u[0], "" if n == 1 else "s"]
	return "just now"
