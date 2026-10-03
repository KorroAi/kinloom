class_name AIDialogue
extends PanelContainer
## A dialogue box with a real character in it: add the node, write who they are in one sentence, done. No code.
##
## The player types (or you call send()); the character answers in its own voice, with a mood, feelings for the
## player and memories that last. What it decides to do while talking comes out as the `acted` signal (validated
## against the tools you list). Without a model it answers with its offline line and the game keeps working.
## voice: replies are said aloud (the voice of `kinloom serve`, else the system's voice) and a microphone button
## (hold to talk) sends what the player says. The microphone needs Project Settings > Audio > Driver > Enable Input.

signal replied(text: String)
signal acted(tool: String, args: Dictionary)
## The visible thing the character does while speaking ("points at the door"): play an animation.
signal gestured(gesture: String)
signal closed

@export var character_name := "Mira"
## Who they are, in one sentence. The model turns it once into a full inner life (saved in the memory file).
## A whole card written by you also works, as JSON: {"summary": "...", "voice": "...", "secrets": ["..."], "mood": "wary"}.
@export_multiline var soul := "a widowed blacksmith, gruff and proud, who secretly sold the king's sword"
## What they say when no model is available.
@export var offline_line := "..."
## Language of what they say (empty: the server's language).
@export var language := ""
## The player's name: the character remembers each person it talks to.
@export var speaker := "player"
## Tools they may use while talking, e.g. {"give": {"item": "sword"}, "follow": {}}. They arrive as `acted`.
@export var tools: Dictionary = {}
## The character speaks first when the box opens.
@export var speak_first := true
## Open as soon as the scene starts (else call open()).
@export var open_on_ready := false
## The node whose variables are facts the character can use (health, gold, quest...).
@export var watch: NodePath
@export var typewriter := true
## Say replies aloud, and show a microphone button (hold to talk).
@export var voice := false
## How they sound ("low, tired, warm"); their soul and mood are added.
@export var voice_description := ""
## An input action that records while held (push to talk), besides the button. Empty: the button only.
@export var talk_action := ""

var _log: RichTextLabel
var _input: LineEdit
var _mood: Label
var _busy := false
var _mic: Button
var _record: AudioEffectRecord
var _mic_player: AudioStreamPlayer
var _recording := false


func _ready() -> void:
	_build()
	var kl := _kinloom()
	if kl == null:
		push_error("[kinloom] AIDialogue needs the Kinloom autoload (enable the Kinloom plugin).")
		return
	var card = JSON.parse_string(soul) if soul.strip_edges().begins_with("{") else null
	var options := {"soul": card if card is Dictionary else (soul if soul.strip_edges() != "" else true), "offline": offline_line}
	if language != "":
		options["language"] = language
	if not tools.is_empty():
		options["tools"] = tools
	if voice_description != "":
		options["voice"] = voice_description
	kl.character(character_name, "", options)
	visible = false
	if open_on_ready:
		open()


## Shows the box; the character speaks first when speak_first is on.
func open() -> void:
	visible = true
	_input.grab_focus()
	if speak_first:
		send("")


func close() -> void:
	visible = false
	_stop_recording(false)
	var kl := _kinloom()
	if kl != null and voice:
		kl.stop_speaking()
	closed.emit()


## Says something to the character ("" lets it speak first). Returns its reply.
func send(text: String) -> String:
	if _busy:
		return ""
	_busy = true
	_input.editable = false
	if text != "":
		_log.append_text("[right][color=#9fb4ff]%s[/color][/right]\n" % _escape(text))
	var kl := _kinloom()
	var reply: String = await kl.chat(character_name, text, _facts(), speaker)
	if voice and reply != "":
		kl.speak_aloud(character_name, reply)
	_log.append_text("[b]%s[/b]  %s\n" % [_escape(character_name), _escape(reply)])
	if typewriter and reply != "":
		var start := _log.get_total_character_count() - reply.length() - 1
		_log.visible_characters = maxi(start, 0)
		var tween := create_tween()
		tween.tween_property(_log, "visible_characters", _log.get_total_character_count(), clampf(reply.length() * 0.02, 0.2, 2.0))
		tween.tween_callback(func(): _log.visible_characters = -1)
	for action in kl.act(character_name, {}, false):
		acted.emit(str(action.get("tool", "")), action.get("args", {}))
	var s = await kl.soul(character_name, speaker)
	if s is Dictionary and s.get("mood") is Dictionary:
		_mood.text = str(s["mood"].get("word", ""))
	if s is Dictionary and str(s.get("gesture", "")) != "":
		_log.append_text("[i]- %s[/i]\n" % _escape(str(s["gesture"])))
		gestured.emit(str(s["gesture"]))
	_busy = false
	_input.editable = true
	_input.grab_focus()
	replied.emit(reply)
	return reply


func _facts() -> Dictionary:
	var out := {}
	var watched := get_node_or_null(watch)
	if watched == null:
		return out
	for p in watched.get_property_list():
		if p.usage & PROPERTY_USAGE_SCRIPT_VARIABLE:
			var v = watched.get(p.name)
			if typeof(v) in [TYPE_INT, TYPE_FLOAT, TYPE_BOOL, TYPE_STRING]:
				out[p.name] = v
	return out


func _build() -> void:
	if custom_minimum_size == Vector2.ZERO:
		custom_minimum_size = Vector2(520, 260)
	var box := VBoxContainer.new()
	add_child(box)
	var head := HBoxContainer.new()
	box.add_child(head)
	var title := Label.new()
	title.text = character_name
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(title)
	_mood = Label.new()
	_mood.modulate = Color(1, 1, 1, 0.6)
	head.add_child(_mood)
	var x := Button.new()
	x.text = "x"
	x.flat = true
	x.pressed.connect(close)
	head.add_child(x)
	_log = RichTextLabel.new()
	_log.bbcode_enabled = true
	_log.scroll_following = true
	_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	box.add_child(_log)
	var row := HBoxContainer.new()
	box.add_child(row)
	_input = LineEdit.new()
	_input.placeholder_text = "Say something..."
	_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_input.text_submitted.connect(func(t: String):
		_input.clear()
		if t.strip_edges() != "":
			send(t.strip_edges()))
	row.add_child(_input)
	if voice:
		_mic = Button.new()
		_mic.text = "Mic"
		_mic.tooltip_text = "Hold to talk"
		_mic.button_down.connect(_start_recording)
		_mic.button_up.connect(func(): _stop_recording(true))
		row.add_child(_mic)
		if not ProjectSettings.get_setting("audio/driver/enable_input", false):
			_mic.disabled = true
			_mic.tooltip_text = "Turn on Project Settings > Audio > Driver > Enable Input to talk"


## Starts recording the microphone (push to talk; the button and talk_action call it).
func _start_recording() -> void:
	if _recording or _busy or not ProjectSettings.get_setting("audio/driver/enable_input", false):
		return
	if _record == null:
		var bus := AudioServer.bus_count
		AudioServer.add_bus(bus)
		AudioServer.set_bus_name(bus, "KinloomMic")
		AudioServer.set_bus_mute(bus, true)              # recorded, never played back
		_record = AudioEffectRecord.new()
		AudioServer.add_bus_effect(bus, _record)
		_mic_player = AudioStreamPlayer.new()
		_mic_player.stream = AudioStreamMicrophone.new()
		_mic_player.bus = "KinloomMic"
		add_child(_mic_player)
	var kl := _kinloom()
	if kl != null:
		kl.stop_speaking()
	_mic_player.play()
	_record.set_recording_active(true)
	_recording = true
	_input.placeholder_text = "Listening..."


## Stops recording; with send, what was said is understood and sent.
func _stop_recording(send_it: bool) -> void:
	if not _recording:
		return
	_recording = false
	_record.set_recording_active(false)
	_mic_player.stop()
	_input.placeholder_text = "Say something..."
	var clip := _record.get_recording()
	if not send_it or clip == null:
		return
	var path := "user://kinloom_heard.wav"
	clip.save_to_wav(path)
	var wav := FileAccess.get_file_as_bytes(path)
	var kl := _kinloom()
	if kl == null or wav.size() < 1000:
		return
	_input.placeholder_text = "..."
	var heard: String = await kl.listen(wav, language)
	_input.placeholder_text = "Say something..."
	if heard != "":
		send(heard)


func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("ui_cancel"):
		close()
	elif visible and voice and talk_action != "" and InputMap.has_action(talk_action):
		if event.is_action_pressed(talk_action):
			_start_recording()
		elif event.is_action_released(talk_action):
			_stop_recording(true)


func _escape(text: String) -> String:
	return text.replace("[", "[lb]")


func _kinloom() -> Node:
	return get_node_or_null("/root/Kinloom")
