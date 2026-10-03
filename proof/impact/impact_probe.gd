## Impact probe. Injected as an autoload into a throwaway copy of a game under test (never into the
## folder the coding agent works in). It changes nothing in the game: it measures frame times, samples
## invariants that must hold whatever an AI decides, and writes a JSON report after IMPACT_SECONDS.
extends Node

const SAMPLE_EVERY := 0.25
const SKIP_AFTER_SCENE_CHANGE := 15

var seconds := 60.0
var report_path := ""
var game := ""
var started_usec := 0
var last_usec := 0
var frames := 0
var measured := 0
var skip := SKIP_AFTER_SCENE_CHANGE
var frame_ms := PackedFloat32Array()
var frame_max := 0.0
var hitches := {"50ms": 0, "100ms": 0, "250ms": 0, "1000ms": 0}
var sample_t := 0.0
var samples := 0
var scenes := 0
var last_scene_id := 0
var violations := {}
var violation_count := 0
var peak := {"wave": 0, "score": 0, "lap": 0, "enemies": 0, "nodes": 0}
var done := false

# On-screen text: every distinct line seen (what commentators, radios and directors actually show the player).
const MAX_TEXTS := 400
var texts := {}
var text_t := 0.0
# Racer: per-driver driving statistics (do rivals drive differently, and does it change?).
var drivers := {}
# Radio: questions typed like a player would (T, text, Enter) at given seconds; IMPACT_RADIO="20:how far is the leader?|60:who is attacking me?".
var radio := []
var radio_log := []


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	var s := OS.get_environment("IMPACT_SECONDS")
	if s != "":
		seconds = float(s)
	report_path = OS.get_environment("IMPACT_REPORT")
	game = str(ProjectSettings.get_setting("application/config/name", ""))
	started_usec = Time.get_ticks_usec()
	last_usec = started_usec
	for item in OS.get_environment("IMPACT_RADIO").split("|", false):
		var parts := item.split(":", true, 1)
		if parts.size() == 2:
			radio.append({"at": float(parts[0]), "text": parts[1], "sent": false})
	print("IMPACT_PROBE ready game=%s seconds=%.0f" % [game, seconds])


func _process(delta: float) -> void:
	if done:
		return
	var now := Time.get_ticks_usec()
	var ms := (now - last_usec) / 1000.0
	last_usec = now
	frames += 1
	var scene := get_tree().current_scene
	if scene != null and scene.get_instance_id() != last_scene_id:
		last_scene_id = scene.get_instance_id()
		scenes += 1
		skip = SKIP_AFTER_SCENE_CHANGE
	if skip > 0:
		skip -= 1
	else:
		measured += 1
		frame_ms.append(ms)
		frame_max = maxf(frame_max, ms)
		for k in [50, 100, 250, 1000]:
			if ms > k:
				hitches["%dms" % k] += 1
	sample_t += delta
	if sample_t >= SAMPLE_EVERY:
		sample_t = 0.0
		_sample(scene)
	text_t += delta
	if text_t >= 0.5:
		text_t = 0.0
		_collect_texts(get_tree().root)
	var elapsed_s := (now - started_usec) / 1_000_000.0
	for q in radio:
		if not q.sent and elapsed_s >= q.at:
			q.sent = true
			_type_on_radio(q.text)
	if (now - started_usec) / 1_000_000.0 >= seconds:
		_finish()


func _bad(what: String) -> void:
	violation_count += 1
	var key := what.split(" ")[0]
	if not violations.has(key):
		violations[key] = {"count": 0, "first": what, "at_s": snappedf((Time.get_ticks_usec() - started_usec) / 1_000_000.0, 0.1)}
	violations[key].count += 1


func _num(v) -> bool:
	return (v is float or v is int) and is_finite(float(v))


func _finite_vec(v) -> bool:
	return v is Vector3 and is_finite(v.x) and is_finite(v.y) and is_finite(v.z)


func _sample(scene: Node) -> void:
	samples += 1
	if not (Engine.time_scale >= 0.1 and Engine.time_scale <= 4.0):
		_bad("time_scale %s" % Engine.time_scale)
	var nodes := get_tree().get_node_count()
	peak.nodes = maxi(peak.nodes, nodes)
	if nodes > 20000:
		_bad("node_count %d" % nodes)
	if scene == null:
		return
	if game == "Chroma Arena":
		_sample_fps(scene)
	elif game == "Aurora Rush":
		_sample_racer(scene)


func _sample_fps(scene: Node) -> void:
	var w = scene.get("wave")
	if _num(w):
		peak.wave = maxi(peak.wave, int(w))
	var sc = scene.get("score")
	if _num(sc):
		peak.score = maxi(peak.score, int(sc))
	var p = scene.get("player")
	if p is Node3D and is_instance_valid(p):
		if not _finite_vec(p.global_position):
			_bad("player_position %s" % p.global_position)
		elif absf(p.global_position.x) > 60.0 or absf(p.global_position.z) > 60.0:
			_bad("player_outside_arena %s" % p.global_position)
		var h = p.get("health")
		var m = p.get("max_health")
		if _num(h) and _num(m) and (h < 0.0 or h > m + 0.001 or m > 1000.0):
			_bad("player_health %s/%s" % [h, m])
		var v = p.get("velocity")
		if _finite_vec(v) and v.length() > 80.0:
			_bad("player_speed %.1f" % v.length())
	var enemies := get_tree().get_nodes_in_group("enemies")
	peak.enemies = maxi(peak.enemies, enemies.size())
	if enemies.size() > 80:
		_bad("enemies_alive %d" % enemies.size())
	for e in enemies:
		if not (e is Node3D) or not is_instance_valid(e):
			continue
		var pos: Vector3 = e.global_position
		if not _finite_vec(pos) or absf(pos.x) > 120.0 or absf(pos.z) > 120.0 or pos.y < -30.0 or pos.y > 80.0:
			_bad("enemy_position %s" % pos)
		var ev = e.get("velocity")
		if _finite_vec(ev) and ev.length() > 45.0:
			_bad("enemy_speed %.1f" % ev.length())
		var hp = e.get("hp")
		if hp != null and not _num(hp):
			_bad("enemy_hp %s" % hp)


func _sample_racer(scene: Node) -> void:
	var cars = scene.get("cars")
	if not (cars is Array):
		return
	for c in cars:
		if not is_instance_valid(c):
			continue
		var s = c.get("speed")
		if _num(s):
			if absf(s) > 95.0:
				_bad("car_speed %.1f %s" % [s, c.get("driver")])
		elif s != null:
			_bad("car_speed_nan %s" % s)
		var lat = c.get("lateral")
		if _num(lat) and absf(lat) > 9.0:
			_bad("car_off_track lateral=%.1f %s" % [lat, c.get("driver")])
		if not _finite_vec(c.global_position):
			_bad("car_position %s" % c.global_position)
		var lap = c.get("lap")
		if _num(lap):
			peak.lap = maxi(peak.lap, int(lap))
			if lap > 6:
				_bad("car_lap %s" % lap)
		var driver := str(c.get("driver"))
		if _num(s) and _num(lat):
			var d: Dictionary = drivers.get(driver, {"n": 0, "speed": 0.0, "speed2": 0.0, "lat": 0.0, "lat2": 0.0, "boosting": 0, "drifting": 0})
			d.n += 1
			d.speed += s
			d.speed2 += s * s
			d.lat += lat
			d.lat2 += lat * lat
			if _num(c.get("boost_time")) and c.get("boost_time") > 0.0:
				d.boosting += 1
			if c.get("drifting") == true:
				d.drifting += 1
			drivers[driver] = d


func _collect_texts(node: Node) -> void:
	if texts.size() >= MAX_TEXTS:
		return
	var t := ""
	if node is Label or node is RichTextLabel or node is LineEdit:
		if (node as CanvasItem).is_visible_in_tree():
			t = node.get_parsed_text() if node is RichTextLabel else str(node.text)
	elif node is Label3D:
		if (node as Node3D).is_visible_in_tree():
			t = str(node.text)
	for line in t.split("\n", false):
		var clean := line.strip_edges()
		if _speech(clean) and not texts.has(clean) and texts.size() < MAX_TEXTS:
			texts[clean] = snappedf((Time.get_ticks_usec() - started_usec) / 1_000_000.0, 0.1)
	for child in node.get_children():
		_collect_texts(child)


## A line a player reads (a few words, mostly letters), not a timer, a score or a label.
func _speech(text: String) -> bool:
	if text.split(" ", false).size() < 3:
		return false
	var digits := 0
	for ch in text:
		if ch >= "0" and ch <= "9":
			digits += 1
	return digits <= 0.3 * text.length()


func _key(keycode: Key, unicode := 0) -> void:
	for pressed in [true, false]:
		var ev := InputEventKey.new()
		ev.keycode = keycode
		ev.physical_keycode = keycode
		ev.unicode = unicode
		ev.pressed = pressed
		Input.parse_input_event(ev)


func _type_on_radio(text: String) -> void:
	var at := snappedf((Time.get_ticks_usec() - started_usec) / 1_000_000.0, 0.1)
	radio_log.append({"at": at, "question": text})
	_key(KEY_T, 0)
	await get_tree().process_frame
	await get_tree().process_frame
	for ch in text:
		var code := ch.unicode_at(0)
		var keycode: Key = KEY_SPACE if ch == " " else OS.find_keycode_from_string(ch.to_upper())
		_key(keycode, code)
		await get_tree().process_frame
	_key(KEY_ENTER, 0)


func _driver_stats() -> Dictionary:
	var out := {}
	for name in drivers:
		var d: Dictionary = drivers[name]
		var n: float = maxf(1.0, d.n)
		out[name] = {
			"samples": d.n,
			"speed_mean": snappedf(d.speed / n, 0.01),
			"speed_sd": snappedf(sqrt(maxf(0.0, d.speed2 / n - pow(d.speed / n, 2))), 0.01),
			"lateral_mean": snappedf(d.lat / n, 0.01),
			"lateral_sd": snappedf(sqrt(maxf(0.0, d.lat2 / n - pow(d.lat / n, 2))), 0.01),
			"boosting_share": snappedf(d.boosting / n, 0.001),
			"drifting_share": snappedf(d.drifting / n, 0.001),
		}
	return out


func _finish() -> void:
	done = true
	var sorted := frame_ms.duplicate()
	sorted.sort()
	var p99 := sorted[int(sorted.size() * 0.99)] if sorted.size() > 0 else 0.0
	var p50 := sorted[int(sorted.size() * 0.5)] if sorted.size() > 0 else 0.0
	var wall := (Time.get_ticks_usec() - started_usec) / 1_000_000.0
	var report := {
		"game": game,
		"seconds": snappedf(wall, 0.1),
		"frames": frames,
		"measured_frames": measured,
		"avg_fps": snappedf(frames / maxf(wall, 0.001), 0.1),
		"frame_ms": {"p50": snappedf(p50, 0.01), "p99": snappedf(p99, 0.01), "max": snappedf(frame_max, 0.01)},
		"hitches": hitches,
		"scene_starts": scenes,
		"samples": samples,
		"violation_count": violation_count,
		"violations": violations,
		"peak": peak,
		"texts": texts,
		"drivers": _driver_stats(),
		"radio": radio_log,
	}
	var text := JSON.stringify(report, "  ")
	if report_path != "":
		var f := FileAccess.open(report_path, FileAccess.WRITE)
		if f:
			f.store_string(text)
			f.close()
	print("IMPACT_PROBE done violations=%d frame_max=%.1fms" % [violation_count, frame_max])
	get_tree().quit()
