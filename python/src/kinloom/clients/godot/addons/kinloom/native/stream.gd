extends RefCounted
## Streamed replies: caps, the in-character guard, the spoken part, stage directions, echoes (kinloom/souls.py).

const Py = preload("py.gd")
const Souls = preload("souls.gd")

const CAP_END := "[.!?\\x{2026}]+" + Souls.CLOSERS + "*(?=" + Py.SPACE + ")"
const OPEN_MARKS := ["*", "(", "["]
const CLOSE_OF := {"*": "*", "(": ")", "[": "]"}
const LIMIT_OF := {"*": 200, "(": 200, "[": 60}


## The text up to the end of the sentence that reaches `words` words (chars: a text box's size, 0 for none).
static func cap(text: String, words: int, chars := 0) -> String:
	var c := Cap.new(words, chars)
	return Py.strip(c.feed(Py.strip(text)) + c.finish())


static func fit_chars(text: String, chars: int) -> String:
	return cap(Py.squash(text), 1000000, chars) if chars > 0 else text


## [what is left, stale].
static func drop_echoes(text: String, before: Array) -> Array:
	var e := Echo.new(before)
	var out := Py.strip(e.feed(text) + e.finish())
	return [out, e.stale()]


class Cap:
	var words := 0
	var chars := 0
	var shown := ""
	var done := false
	var text := ""
	var pos := 0

	func _init(words_: int, chars_ := 0) -> void:
		words = words_
		chars = chars_

	func feed(piece: String) -> String:
		if done or piece == "":
			return ""
		if chars > 0:
			text += piece
			var out := ""
			while not done:
				var m := Py.re(CAP_END).search(text, pos)
				if m == null:
					break
				out += _sentence(text.substr(pos, m.get_end(0) - pos))
				pos = m.get_end(0)
			return out
		var whole := shown + piece
		for m in Py.re(CAP_END).search_all(whole):
			if m.get_end(0) > shown.length() and Souls.word_count(whole.substr(0, m.get_end(0))) >= words:
				done = true
				piece = whole.substr(shown.length(), m.get_end(0) - shown.length())
				break
		shown += piece
		return piece

	func _sentence(sentence: String) -> String:
		sentence = Py.squash(sentence)
		if sentence == "":
			return ""
		var joined := Py.strip(shown + " " + sentence)
		if joined.length() > chars:
			done = true
			if shown != "":
				return ""
			sentence = Souls.word_cut(sentence, chars)
			joined = sentence
		var out := (" " if shown != "" else "") + sentence
		shown = joined
		if Souls.word_count(shown) >= words:
			done = true
		return out

	func finish() -> String:
		if chars <= 0 or done:
			return ""
		var rest := text.substr(pos)
		pos = text.length()
		var out := _sentence(rest)
		done = true
		return out


## Holds back the first words of a streamed reply until they are known to be in character; stops for good when not.
class Guard:
	var bad: RegEx
	var hold := 48
	var text := ""
	var shown := 0
	var blocked := false

	func _init(bad_: RegEx, hold_ := 48) -> void:
		bad = bad_
		hold = hold_

	func feed(piece: String) -> String:
		text += piece
		if blocked or bad.search(text) != null:
			blocked = true
			return ""
		if text.length() < hold:
			return ""
		var out := text.substr(shown)
		shown = text.length()
		return out

	func finish() -> String:
		if blocked or bad.search(text) != null:
			blocked = true
			return ""
		var out := text.substr(shown)
		shown = text.length()
		return out


## Streams only the spoken part of a reply.
class Splitter:
	var text := ""
	var start := 0
	var shown := 0
	var done := false
	var first := false

	func feed(piece: String) -> String:
		text += piece
		if done:
			return ""
		var mark: String = Souls.MARK
		var at := text.find(mark, start)
		if at >= 0 and start == 0 and Py.strip(text.substr(0, at)) == "":
			start = at + mark.length()
			shown = start
			first = true
			at = text.find(mark, start)
		while at >= 0 and first and Py.strip(text.substr(start, shown - start)) == "" and Souls.inner_only(text.substr(start, at - start)):
			start = at + mark.length()
			shown = start
			at = text.find(mark, start)
		if at >= 0:
			done = true
			var out := text.substr(shown, at - shown)
			shown = at
			return out
		var keep := 0
		for n in range(mini(mark.length() - 1, text.length() - start), 0, -1):
			if text.ends_with(mark.substr(0, n)):
				keep = n
				break
		var end := text.length() - keep
		var brace := text.substr(0, end).rfind("{")
		if brace < shown:
			brace = -1
		if brace >= 0 and Py.re("^\\{" + Py.SPACE + "*\"(mood|feel|remember|do|intensity|gesture)\"").search(text.substr(brace)) != null:
			end = brace
		elif brace >= 0 and Souls.key_start(text.substr(brace)):
			end = brace
		var line := Souls.key_line_re().search(text, shown)
		if line != null and line.get_start(0) < end:
			end = line.get_start(0)
			done = true
		else:
			var nl := text.substr(0, end).rfind("\n")
			if nl < shown:
				nl = -1
			var last := Py.lower(Py.strip(text.substr(nl + 1, end - nl - 1))) if nl >= 0 else ""
			if nl >= 0 and last != "" and last.length() < 12:
				for k in Souls.INNER_KEYS:
					if k.begins_with(last) or last.begins_with(k):
						end = nl
						break
		var out := text.substr(shown, end - shown) if end > shown else ""
		shown = maxi(shown, end)
		return out

	## [said, inner, the spoken text still to show].
	func finish() -> Array:
		var r := Souls.split(text)
		var said: String = r[0]
		if done:
			return [said, r[1], ""]
		var before := Py.strip(text.substr(start, shown - start))
		var tail := said.substr(before.length()) if said.begins_with(before) and said.length() > before.length() else ""
		return [said, r[1], tail]


## Drops stage directions (*smiles*, (sighs), [pause]) from a streamed reply.
class Unstage:
	var buf := ""
	var held := ""
	var pending := ""
	var skip := false
	var started := false

	func _emit(t: String) -> String:
		if t == "":
			return ""
		if skip:
			t = Py.lstrip(t)
			if t == "":
				return ""
			skip = false
			if started and not ".,!?".contains(t[0]):
				t = " " + t
		started = true
		return t

	func feed(piece: String, final := false) -> String:
		buf += piece
		var out := ""
		while buf != "":
			if held == "":
				var at := -1
				for o in OPEN_MARKS:
					var i := buf.find(o)
					if i >= 0 and (at < 0 or i < at):
						at = i
				if at < 0:
					out += _emit(buf)
					buf = ""
					break
				var kept := Py.rstrip(buf.substr(0, at))
				pending = buf.substr(kept.length(), at - kept.length())
				out += _emit(kept)
				held = buf[at]
				buf = buf.substr(at)
			var close: String = CLOSE_OF[held]
			var limit: int = LIMIT_OF[held]
			var end := buf.find(close, 1)
			var nl := buf.find("\n", 1)
			var inside := buf.substr(1, (end if end >= 0 else buf.length()) - 1)
			var bad := (nl >= 0 and (end < 0 or nl < end)) or inside.length() > limit or (held == "(" and inside.contains("("))
			if not bad and end < 0:
				if not final:
					break
				bad = true
			if not bad and end == 1:
				bad = true
			if not bad and held == "(":
				if end + 1 >= buf.length():
					if not final:
						break
				elif not (Py.is_space(buf.unicode_at(end + 1)) or ".,!?".contains(buf[end + 1])):
					bad = true
			if bad:
				out += _emit(pending + held)
				pending = ""
				buf = buf.substr(1)
				held = ""
				continue
			var keep = Souls.stage_keep(buf.substr(1, end - 1)) if held == "*" else null
			if keep != null:
				out += _emit(pending + keep)
			else:
				skip = true
			pending = ""
			buf = buf.substr(end + 1)
			held = ""
		return out

	func finish() -> String:
		return feed("", true)


## Drops what a character keeps saying, sentence by sentence, as the reply streams.
class Echo:
	var before: Array = []
	var seen := {}
	var buf := ""
	var kept := 0
	var dropped: Array = []
	var short := {}
	var fresh := 0
	var echoed := 0
	var early := 0

	func _init(before_replies: Array = []) -> void:
		for r in before_replies:
			if typeof(r) != TYPE_STRING or r == "":
				continue
			for s in Souls.sentences(r):
				var n := Souls.norm_words(s)
				seen[" ".join(n)] = true
				if n.size() >= 4:
					before.append(n)

	func _repeat(sentence: String) -> bool:
		var n := Souls.norm_words(sentence)
		if n.is_empty():
			return false
		if n.size() <= 3:
			var key := " ".join(n)
			if short.has(key):
				return true
			short[key] = n
			return false
		for b in before:
			if n == b or (mini(n.size(), b.size()) >= 4 and Souls.seq_ratio(n, b) >= 0.85):
				echoed += 1
				return true
		return false

	func _pass(sentence: String) -> String:
		if _repeat(sentence):
			dropped.append(sentence)
			return ""
		kept += 1
		var n := Souls.norm_words(sentence)
		if not seen.has(" ".join(n)):
			fresh += n.size()
		return sentence

	## Something said before was dropped and fewer than four new words are left.
	func stale() -> bool:
		return echoed > 0 and fresh < 4

	func _new_start(partial: String) -> bool:
		var words := Souls.norm_words(partial)
		var cut := Py.re("[" + Py.W + "'\\x{2019}]$").search(partial) == null
		var full: Array = words if cut else words.slice(0, words.size() - 1)
		var last = null if cut else (words[words.size() - 1] if not words.is_empty() else null)
		if full.is_empty():
			return false
		var all: Array = before.duplicate()
		all.append_array(short.values())
		for k in all:
			if k.slice(0, full.size()) == full and (last == null or (k.size() > full.size() and k[full.size()].begins_with(last))):
				return false
		return true

	func feed(piece: String) -> String:
		buf += piece
		var out := ""
		var end_re := Souls.end_re()
		while true:
			var m := end_re.search(buf)
			if m == null:
				break
			var sentence := buf.substr(0, m.get_end(0))
			buf = buf.substr(m.get_end(0))
			if early > 0:
				out += sentence.substr(early)
				_fresh_one(sentence)
				early = 0
			else:
				out += _pass(sentence)
		if buf != "" and early == 0 and _new_start(buf):
			early = buf.length()
			out += buf
		elif early > 0 and buf.length() > early:
			out += buf.substr(early)
			early = buf.length()
		return out

	func _fresh_one(sentence: String) -> void:
		kept += 1
		var n := Souls.norm_words(sentence)
		if n.size() <= 3:
			short[" ".join(n)] = n
		if not seen.has(" ".join(n)):
			fresh += n.size()

	func finish() -> String:
		var rest := buf
		buf = ""
		if early > 0:
			_fresh_one(rest)
			var out := rest.substr(early)
			early = 0
			return out
		return _pass(rest) if Py.strip(rest) != "" else rest
