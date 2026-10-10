extends RefCounted
## What characters remember: notes per session and scope, ranked by importance, recency and relevance, saved to a JSON
## file (user://...) a second after a change, so games never wait on disk (kinloom/memory.py).

const Py = preload("py.gd")


class Memory:
	const MAX_NOTES := 120
	const MAX_NOTE := 300
	const STOP := ["the", "and", "for", "with", "that", "this", "you", "your", "are", "was", "has", "have", "not", "but", "from", "they",
		"them", "its", "into", "who", "what", "just"]

	var path := ""
	var clock: Callable
	var notes_by := {}          # session -> {scope -> [note]}
	var extra := {}
	var dirty := false
	var waiting := false

	static func words(text: String) -> Dictionary:
		var out := {}
		for m in Py.re("[a-zA-Z0-9\\x{c0}-\\x{24f}]{3,}").search_all(text):
			var w := Py.lower(m.get_string(0))
			if not STOP.has(w):
				out[w] = true
		return out

	## What went wrong reading the file, if anything (the brain journals it).
	var problem := ""

	## A note recall() can rank: text, time and importance (a file edited by hand or a save from elsewhere).
	static func good_note(n) -> bool:
		return n is Dictionary and typeof(n.get("text")) == TYPE_STRING and Py.finite(n.get("t")) != null \
			and Py.finite(n.get("importance")) != null

	func _init(path_ := "", clock_: Callable = Callable()) -> void:
		path = path_
		clock = clock_ if clock_.is_valid() else func() -> float: return Time.get_unix_time_from_system()
		if path == "" or not FileAccess.file_exists(path):
			return
		var f := FileAccess.open(path, FileAccess.READ)
		if f == null:
			problem = "memory file unreadable (" + error_string(FileAccess.get_open_error()) + ")"
			return
		var r := Py.loads(f.get_as_text().trim_prefix(String.chr(0xFEFF)))
		f.close()
		if not r[0] or not (r[1] is Dictionary):
			# kept aside before anything overwrites it: memory.json.corrupt-<time>
			problem = "memory file unreadable (JSONDecodeError)" if not r[0] else "memory file is not a JSON object"
			var aside := path + ".corrupt-" + str(int(Time.get_unix_time_from_system()))
			if DirAccess.rename_absolute(path, aside) == OK:
				problem += "; kept as " + aside.get_file()
			return
		var data: Dictionary = r[1]
		if data.get("sessions") is Dictionary:
			for session in data["sessions"]:
				var scopes = data["sessions"][session]
				if not (scopes is Dictionary):
					continue
				for scope in scopes:
					var kept := []
					if scopes[scope] is Array:
						for n in scopes[scope]:
							if good_note(n):
								kept.append(n)
					if not kept.is_empty():
						_list(str(session), str(scope)).append_array(kept.slice(maxi(0, kept.size() - MAX_NOTES)))
		if data.get("extra") is Dictionary:
			for k in data["extra"]:
				if data["extra"][k] is Dictionary:
					extra[str(k)] = data["extra"][k]

	func _list(session: String, scope: String) -> Array:
		if not notes_by.has(session):
			notes_by[session] = {}
		if not notes_by[session].has(scope):
			notes_by[session][scope] = []
		return notes_by[session][scope]

	func _peek(session: String, scope: String) -> Array:
		return notes_by.get(session, {}).get(scope, [])

	## meta: small JSON values kept with the note (eid, tag, by, src, orig, impact).
	func add(session: String, scope: String, text: Variant, importance: Variant = 0.5, meta := {}) -> void:
		var t := Py.head(Py.squash(Py.text_of(text)), MAX_NOTE)
		if t == "":
			return
		var imp = Py.number_of(importance) if typeof(importance) != TYPE_BOOL else (1.0 if importance else 0.0)
		imp = 0.5 if imp == null or is_nan(imp) else clampf(imp, 0.0, 1.0)
		var note := {"t": clock.call(), "text": t, "importance": imp}
		for k in meta:
			var v = meta[k]
			if typeof(v) in [TYPE_STRING, TYPE_INT, TYPE_FLOAT, TYPE_BOOL]:
				note[k] = v
		var notes := _list(session, scope)
		notes.append(note)
		if notes.size() > MAX_NOTES:
			var by_worth := Py.stable_sort(notes, func(a, b): return a.importance < b.importance or (a.importance == b.importance and a.t < b.t))
			by_worth = by_worth.slice(by_worth.size() - MAX_NOTES)
			by_worth = Py.stable_sort(by_worth, func(a, b): return a.t < b.t)
			notes.clear()
			notes.append_array(by_worth)
		changed()

	## Removes the latest note with exactly this text (a reply the game refused is not remembered).
	func take_back(session: String, scope: String, text: Variant) -> void:
		var t := Py.head(Py.squash(Py.text_of(text)), MAX_NOTE)
		var notes := _peek(session, scope)
		for i in range(notes.size() - 1, -1, -1):
			if notes[i].text == t:
				notes.remove_at(i)
				changed()
				return

	## Copies of the notes of a scope, oldest first.
	func notes(session: String, scope: String) -> Array:
		var out := []
		for n in _peek(session, scope):
			out.append(n.duplicate())
		return out

	func annotate(session: String, scope: String, eid: Variant, meta: Dictionary) -> void:
		for n in _peek(session, scope):
			if n.has("eid") and Py.equal(n["eid"], eid):
				for k in meta:
					if typeof(meta[k]) in [TYPE_STRING, TYPE_INT, TYPE_FLOAT, TYPE_BOOL]:
						n[k] = meta[k]
				dirty = true
		changed()

	func get_value(section: String, key: String, default: Variant = null) -> Variant:
		return extra.get(section, {}).get(key, default)

	func put(section: String, key: String, value: Variant) -> void:
		if not extra.has(section):
			extra[section] = {}
		extra[section][key] = value
		changed()

	func remove(section: String, key: String) -> void:
		if extra.has(section) and extra[section].has(key):
			extra[section].erase(key)
			changed()

	## The keys of a section ("session/name" for learned minds).
	func keys(section: String) -> Array:
		return extra.get(section, {}).keys()

	## {scope: [notes]} of one session (copies): what a save slot keeps.
	func session_notes(session: String) -> Dictionary:
		var out := {}
		var scopes: Dictionary = notes_by.get(session, {})
		for scope in scopes:
			if not scopes[scope].is_empty():
				out[scope] = scopes[scope].duplicate(true)
		return out

	## The session's notes become these: a save slot loaded.
	func replace_session(session: String, given: Dictionary) -> void:
		notes_by.erase(session)
		for scope in given:
			var kept := []
			if given[scope] is Array:
				for n in given[scope]:
					if good_note(n):
						kept.append(n.duplicate(true))
			if not kept.is_empty():
				_list(session, str(scope)).append_array(kept.slice(maxi(0, kept.size() - MAX_NOTES)))
		changed()

	func all(session: String, scope: String) -> Array:
		var out := []
		for n in _peek(session, scope):
			out.append(n.text)
		return out

	## The k most useful notes: 0.45 importance + 0.35 recency + 0.2 overlap with the query.
	func recall(session: String, scopes: Array, query := "", k := 6, personal := true) -> Array:
		var q := words(query)
		var notes := []
		for s in scopes:
			for n in _peek(session, s):
				if personal or not Py.truthy(n.get("about")):
					notes.append(n)
		if notes.is_empty():
			return []
		var newest := -INF
		var oldest := INF
		for n in notes:
			newest = maxf(newest, Py.num(n.t))
			oldest = minf(oldest, Py.num(n.t))
		var span := maxf(1.0, newest - oldest)
		var scored := []
		for n in notes:
			var recency := (Py.num(n.t) - oldest) / span
			var overlap := 0.0
			if not q.is_empty():
				var both := 0
				for w in words(n.text):
					if q.has(w):
						both += 1
				overlap = float(both) / q.size()
			scored.append([0.45 * Py.num(n.importance) + 0.35 * recency + 0.2 * overlap, n, scored.size()])
		var best := Py.stable_sort(scored, func(a, b): return a[0] > b[0] or (a[0] == b[0] and a[2] > b[2])).slice(0, k)   # ties: the newest first
		best = Py.stable_sort(best, func(a, b): return Py.num(a[1].t) < Py.num(b[1].t) or (Py.num(a[1].t) == Py.num(b[1].t) and a[2] < b[2]))
		var out := []
		for x in best:
			out.append(x[1].text)
		return out

	func changed() -> void:
		dirty = true
		if path == "" or waiting:
			return
		var tree := Engine.get_main_loop() as SceneTree
		if tree == null:
			save()
			return
		waiting = true
		tree.create_timer(1.0, true, false, true).timeout.connect(save)

	func save() -> void:
		waiting = false
		if path == "" or not dirty:
			return
		var sessions := {}
		for session in notes_by:
			sessions[session] = notes_by[session]
		var text := Py.dumps({"version": 1, "sessions": sessions, "extra": extra})
		dirty = false
		var folder := path.get_base_dir()
		if folder != "" and not DirAccess.dir_exists_absolute(folder):
			DirAccess.make_dir_recursive_absolute(folder)
		# a unique name: two saves never share it; the rename leaves the old file or the new one, never half of one
		var tmp := path + "." + str(OS.get_process_id()) + "-" + str(randi()) + ".tmp"
		var f := FileAccess.open(tmp, FileAccess.WRITE)
		if f == null:
			dirty = true
			return
		f.store_string(text)
		f.close()
		if DirAccess.rename_absolute(tmp, path) != OK:
			DirAccess.remove_absolute(tmp)
			dirty = true
