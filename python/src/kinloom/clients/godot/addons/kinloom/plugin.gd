@tool
extends EditorPlugin
## Adds the Kinloom autoload, the AICharacter, AIDialogue and AIMind nodes and a small dock (server status, dashboard, try a character).

const AUTOLOAD := "Kinloom"
var _dock: Control


func _enter_tree() -> void:
	if not ProjectSettings.has_setting("autoload/" + AUTOLOAD):
		add_autoload_singleton(AUTOLOAD, "res://addons/kinloom/kinloom.gd")
	add_custom_type("AICharacter", "Node", preload("res://addons/kinloom/ai_character.gd"), null)
	add_custom_type("AIDialogue", "PanelContainer", preload("res://addons/kinloom/ai_dialogue.gd"), null)
	add_custom_type("AIMind", "Node", preload("res://addons/kinloom/ai_mind.gd"), null)
	_dock = _build_dock()
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)


func _exit_tree() -> void:
	remove_custom_type("AICharacter")
	remove_custom_type("AIDialogue")
	remove_custom_type("AIMind")
	if _dock:
		remove_control_from_docks(_dock)
		_dock.queue_free()


func _build_dock() -> Control:
	var box := VBoxContainer.new()
	box.name = "Kinloom"
	var status := Label.new()
	status.name = "Status"
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.text = "Kinloom: checking the server…"
	box.add_child(status)
	var row := HBoxContainer.new()
	var start := Button.new()
	start.text = "Start server"
	start.tooltip_text = "Runs `kinloom serve` (install once with: pip install kinloom)"
	start.pressed.connect(func():
		var pid := OS.create_process("kinloom", ["serve"], true)
		status.text = "Started kinloom serve." if pid > 0 else "Could not start `kinloom`. Install it: pip install kinloom")
	row.add_child(start)
	var dash := Button.new()
	dash.text = "Dashboard"
	dash.pressed.connect(func(): OS.shell_open(_url() + "/"))
	row.add_child(dash)
	var talk := Button.new()
	talk.text = "Talk"
	talk.tooltip_text = "Talk to a character in the browser: one sentence, a real conversation"
	talk.pressed.connect(func(): OS.shell_open(_url() + "/talk"))
	row.add_child(talk)
	var refresh := Button.new()
	refresh.text = "Refresh"
	refresh.pressed.connect(func(): _check(status))
	row.add_child(refresh)
	box.add_child(row)

	var name_edit := LineEdit.new()
	name_edit.placeholder_text = "Character name (e.g. VEGA)"
	box.add_child(name_edit)
	var who := LineEdit.new()
	who.placeholder_text = "Who they are (e.g. an over-excited commentator)"
	box.add_child(who)
	var ev := LineEdit.new()
	ev.placeholder_text = "Something that happens (e.g. the player scores)"
	box.add_child(ev)
	var try_button := Button.new()
	try_button.text = "Hear a line"
	box.add_child(try_button)
	var out := Label.new()
	out.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(out)
	try_button.pressed.connect(func(): _try(name_edit.text, who.text, ev.text, out))
	_check.call_deferred(status)
	return box


func _url() -> String:
	return str(ProjectSettings.get_setting("kinloom/url", "http://127.0.0.1:7717"))


func _request(path: String, body: Variant) -> Variant:
	var req := HTTPRequest.new()
	req.timeout = 15.0
	_dock.add_child(req)
	var method := HTTPClient.METHOD_GET if body == null else HTTPClient.METHOD_POST
	var err := req.request(_url() + path, PackedStringArray(["Content-Type: application/json", "X-Kinloom-Session: editor"]),
		method, "" if body == null else JSON.stringify(body))
	if err != OK:
		req.queue_free()
		return null
	var res: Array = await req.request_completed
	req.queue_free()
	if res[0] != HTTPRequest.RESULT_SUCCESS or res[1] != 200:
		return null
	return JSON.parse_string(res[3].get_string_from_utf8())


func _check(status: Label) -> void:
	var s = await _request("/v1/status", null)
	if s == null:
		status.text = "Kinloom: no server at %s. The game still works offline. Press Start server for AI." % _url()
	elif s.get("mode") == "online":
		var cost = s.stats.get("cost")
		status.text = "Kinloom: online with %s (%s). %d calls%s." % [s.provider, s.model, s.stats.calls,
			"" if cost == null else ", $%.4f" % cost]
	else:
		status.text = "Kinloom: server running, no model found (set ANTHROPIC_API_KEY or DEEPSEEK_API_KEY, or OPENAI_API_KEY / OPENROUTER_API_KEY with KINLOOM_MODEL, or run Ollama)."


func _try(character_name: String, personality: String, what: String, out: Label) -> void:
	if character_name.strip_edges() == "":
		character_name = "Guide"
	out.text = "…"
	await _request("/v1/character", {"name": character_name, "personality": personality})
	var r = await _request("/v1/say", {"name": character_name, "event": what if what != "" else "hello", "fresh": true})
	out.text = "(no server)" if r == null else (r.get("text", "") if r.get("text", "") != "" else "(no model: offline)")
