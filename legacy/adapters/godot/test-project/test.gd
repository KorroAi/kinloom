extends Node2D
# Headless check of the Kinloom Godot addon, driven by a scripted model (no tokens).
var said := []
var replied := ""
var generated := ""
var frames := 0
var captured := {}

func _ready():
	Kinloom.Said.connect(func(role, thing, text, to): said.append(text))
	Kinloom.Replied.connect(func(role, text): replied = text)
	Kinloom.Generated.connect(func(generator, json): generated = json)
	Kinloom.Bind("crate", $Crate)
	Kinloom.EmitEvent("start", {"by": "test"})

func _process(_delta):
	frames += 1
	if frames == 30:
		Kinloom.Ask("mover", "Say hello.", "player")
		Kinloom.Generate("label", {"for": "crate"})
	if frames == 190:
		captured = {"color": $Crate.color_name, "pushed": $Crate.pushed_with}
		$Crate.free() # the game frees a bound node (a level unloads)...
	if frames == 200:
		var again = Node2D.new()
		again.set_script(load("res://crate.gd"))
		again.name = "Crate"
		add_child(again)
		Kinloom.Bind("crate", again) # ...and binds a new one later: the declared thing must still exist
	if frames == 240:
		finish()

func finish():
	var problems := []
	if captured.get("color") != "blue": problems.append("color_name was %s" % captured.get("color"))
	if captured.get("pushed") != 3.0: problems.append("pushed_with was %s" % captured.get("pushed"))
	if not said.has("Pushed!"): problems.append("said: %s" % [said])
	if replied != "Hello there.": problems.append("replied is '%s'" % replied)
	if not generated.contains("Heavy"): problems.append("generated is '%s'" % generated)
	var box = null
	for child in get_children():
		if child.name.begins_with("box_"): box = child
	if box == null: problems.append("no box was created")
	var described: String = Kinloom.DescribeThing("crate")
	if not described.contains("weight=2.5"): problems.append("crate state not read: %s" % described)
	var state: String = Kinloom.SaveState()
	if not state.contains("\"version\":1"): problems.append("save state missing")
	if problems.is_empty():
		print("KINLOOM_TEST PASS")
		get_tree().quit(0)
	else:
		print("KINLOOM_TEST FAIL: ", problems)
		get_tree().quit(1)
