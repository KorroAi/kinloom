class_name AICharacter
extends Node
## A character that talks, answers and steers your game: add the node, fill the inspector, done. No code.
##
## Talks:   pick the node it watches (its variables become the facts) and the signals that make it speak,
##          and the Label / RichTextLabel / Label3D it writes to.
## Answers: point "Chat Input" at a LineEdit; the player's text gets a reply in the output.
## Steers:  point "Control" at a node and list the properties it may set with their choices,
##          e.g. {"aggression": [0.0, 1.0], "mode": ["attack", "defend"]}.

signal said(text: String)

@export var character_name := "Guide"
@export_multiline var personality := "a friendly guide who speaks in short sentences"
## Give them a soul: the model turns the personality once into a full inner life (history, voice, fears, secrets,
## goals), saved in the memory file. Their mood and feelings for the player change as you talk.
@export var soul := false
## Lines used when no model is available. They may use {property} placeholders from the watched node.
@export var offline_lines: PackedStringArray = []

@export_group("Talks")
## The node whose variables are the facts (health, score, speed...).
@export var watch: NodePath
## Signals of the watched node that make the character speak (e.g. "died", "scored", "overtaken").
@export var react_to: PackedStringArray = []
## Seconds between spontaneous comments (0 = only on signals).
@export var talk_every := 0.0
## Label, RichTextLabel or Label3D that shows what it says.
@export var output: NodePath
## Seconds a line stays on screen (0 = forever).
@export var show_for := 4.0
@export var typewriter := true

@export_group("Answers")
## A LineEdit where the player types to this character.
@export var chat_input: NodePath

@export_group("Steers")
## The node whose properties it sets.
@export var control: NodePath
## Property -> choices: [min, max] for numbers, ["a", "b"] for one of, true/false, "#rrggbb" for colors.
@export var controls: Dictionary = {}
## Seconds between decisions (the latest one is applied instantly every time).
@export var decide_every := 8.0

var _talk_timer := 0.0
var _decide_timer := 0.0
var _shown_at := 0.0
var _last := ""


func _ready() -> void:
	var kl := _kinloom()
	if kl == null:
		push_error("[kinloom] AICharacter needs the Kinloom autoload (enable the Kinloom plugin).")
		return
	var events := {}
	for s in react_to:
		events[s] = []
	var options := {"lines": {"*": Array(offline_lines)}, "events": events if not events.is_empty() else ["idle"], "every": decide_every}
	if soul:
		options["soul"] = true
	kl.character(character_name, personality, options)
	var watched := get_node_or_null(watch)
	if watched != null:
		for s in react_to:
			if not watched.has_signal(s):
				push_warning("[kinloom] %s has no signal '%s'" % [watched.name, s])
				continue
			var argc := 0
			for info in watched.get_signal_list():
				if info.name == s:
					argc = info.args.size()
			watched.connect(s, _handler(s, argc))
	var input := get_node_or_null(chat_input)
	if input is LineEdit:
		input.text_submitted.connect(_on_chat)


func _process(delta: float) -> void:
	if talk_every > 0.0:
		_talk_timer += delta
		if _talk_timer >= talk_every:
			_talk_timer = 0.0
			speak("idle")
	if not controls.is_empty() and control != NodePath():
		_decide_timer += delta
		if _decide_timer >= 0.25:  # decide() is instant; the model refreshes every decide_every seconds
			_decide_timer = 0.0
			_steer()
	if show_for > 0.0 and _last != "" and Time.get_ticks_msec() / 1000.0 - _shown_at > show_for:
		_show("")


## Makes the character say something about an event now (facts: extra values next to the watched variables).
func speak(event: String, facts := {}) -> void:
	var kl := _kinloom()
	if kl == null:
		return
	var all := facts_now()
	all.merge(facts, true)
	var text: String = await kl.say(character_name, event, all)
	if text != "":
		_show(text)
		said.emit(text)


## The watched node's variables (numbers, text, true/false), which the character treats as facts.
func facts_now() -> Dictionary:
	var out := {}
	var watched := get_node_or_null(watch)
	if watched == null:
		return out
	for p in watched.get_property_list():
		if not (p.usage & PROPERTY_USAGE_SCRIPT_VARIABLE):
			continue
		var v = watched.get(p.name)
		if typeof(v) in [TYPE_INT, TYPE_FLOAT, TYPE_BOOL, TYPE_STRING, TYPE_STRING_NAME]:
			out[p.name] = v if typeof(v) != TYPE_STRING_NAME else str(v)
		if out.size() >= 24:
			break
	return out


func _handler(signal_name: String, argc: int) -> Callable:
	match argc:
		0: return func(): speak(signal_name)
		1: return func(a): speak(signal_name, _args([a]))
		2: return func(a, b): speak(signal_name, _args([a, b]))
		3: return func(a, b, c): speak(signal_name, _args([a, b, c]))
		_: return func(a, b, c, d): speak(signal_name, _args([a, b, c, d]))


func _args(values: Array) -> Dictionary:
	var out := {}
	for i in values.size():
		var v = values[i]
		if v is Node:
			v = v.name
		if typeof(v) in [TYPE_INT, TYPE_FLOAT, TYPE_BOOL, TYPE_STRING, TYPE_STRING_NAME]:
			out["arg%d" % i] = str(v) if typeof(v) == TYPE_STRING_NAME else v
	return out


func _on_chat(text: String) -> void:
	var input := get_node_or_null(chat_input)
	if input is LineEdit:
		input.clear()
	if text.strip_edges() == "":
		return
	var reply: String = await _kinloom().chat(character_name, text, facts_now())
	if reply != "":
		_show(reply)
		said.emit(reply)


func _steer() -> void:
	var target := get_node_or_null(control)
	if target == null:
		return
	var decision: Dictionary = _kinloom().decide(character_name, facts_now(), controls)
	for key in decision:
		var v = decision[key]
		if typeof(target.get(key)) == TYPE_COLOR and v is String:
			v = Color.html(v)
		target.set(key, v)


func _show(text: String) -> void:
	_last = text
	_shown_at = Time.get_ticks_msec() / 1000.0
	var label := get_node_or_null(output)
	if label == null:
		return
	label.text = text
	if typewriter and text != "" and (label is Label or label is RichTextLabel):
		label.visible_ratio = 0.0
		var tween := create_tween()
		tween.tween_property(label, "visible_ratio", 1.0, clampf(text.length() * 0.025, 0.2, 1.5))


func _kinloom() -> Node:
	return get_node_or_null("/root/Kinloom")
