language: GDScript (Godot 4, works in C# projects too)
Setup: `kinloom init` copied `addons/kinloom` and enabled it: the `Kinloom` autoload and the `AIDialogue`,
`AICharacter` and `AIMind` nodes exist (KINLOOM.md). While playing, `kinloom serve` runs (the addon
starts it in editor runs), or no server: `Kinloom.native({"provider": "auto"})` (the key from the environment).
Saves: `save_state()` / `load_state(text)`. Quitting in native mode: `await Kinloom.shutdown()`, then `get_tree().quit()`.
<!-- brief ends -->
The addon starts `kinloom serve` in editor/debug runs when `kinloom` is installed; with `kinloom bundle`, a
`kinloom-server/` folder next to the exported game or in the project is started in any build, so players need no Python.
Shipped game: set `Kinloom.token` (the relay's player token) and `Kinloom.session` per player; left at "default", each
install gets its own id (user://kinloom-session.txt). Web exports reach the relay over HTTP only (no TCP check).
No-code options: an `AIDialogue` node (a dialogue box with a character in it: name, one-sentence soul, tools;
`open()` shows it and the character speaks first; `acted(tool, args)` signal), an `AICharacter` node (name,
personality, watched node, signals, output label, controls), and an `AIMind` node under any unit (senses = its
properties, actions = its methods, rules; `reward_property` + `done_signal` to make it learn): it calls the chosen
method by itself.
GDScript keeps the names `save` and `load` for itself, hence `save_state()` / `load_state()`; `shutdown()` closes open
model requests first.
---
```gdscript
# Characters with a soul: one sentence, a person the player talks to (mood, feelings, memories, secrets, actions)
func _ready_souls() -> void:
	Kinloom.character("MIRA", "", {"soul": "a widowed blacksmith, gruff and proud, who secretly sold the king's sword",
		"offline": "Busy. Come back later.", "tools": {"give": {"item": "sword"}}})

func _on_talk(text: String) -> void:  # text "" = walks up: she speaks first
	$Dialogue.text = await Kinloom.chat("MIRA", text, {"gold": gold}, "Ana")  # ~1 s, the game keeps running
	for a in Kinloom.act("MIRA", {}, false):  # what she decided while talking
		if a.tool == "give":
			inventory.append(a.args.item)
	var soul = await Kinloom.soul("MIRA", "Ana")  # {card, mood, bonds, memories}
	$Mood.text = soul.mood.word if soul != null else ""

func _ready() -> void:
	Kinloom.character("VEGA", "over-excited race commentator, max 10 words", {
		"lines": {"overtake": ["{who} passes {whom}!"], "*": ["What a race!"]},  # offline lines
		"events": {"overtake": ["who", "whom", "gap"]},  # prepare these lines now
	})
	Kinloom.character("THEO", "calm race engineer", {"offline": "Copy that."})
	Kinloom.character("RAX", "brutal rival", {"tools": {"ram": {"force": [0.0, 1.0]}}})

func _on_overtake(who: String, whom: String, gap: float) -> void:
	$Label.text = await Kinloom.say("VEGA", "overtake", {"who": who, "whom": whom, "gap": gap})  # instant

func _on_radio_submitted(text: String) -> void:
	$Radio.text = await Kinloom.chat("THEO", text, {"gap_to_leader": 1.8, "lap": 3})  # ~1 s, the game keeps running

func _physics_process(delta: float) -> void:
	var plan := Kinloom.decide("RAX", {"gap": gap, "lap": lap},  # instant, refreshed in background
		{"strategy": ["attack", "block"], "aggression": [0.0, 1.0]})
	aggression = plan.aggression
	for a in Kinloom.act("RAX", {"gap": gap}):  # instant, validated tool calls
		if a.tool == "ram":
			ram(a.args.force)

func _start_race() -> void:
	var challenge = await Kinloom.create("a short race challenge", {"title": "Win clean", "laps": [2, 5], "sky": "#ff7a45"})
	var names = await Kinloom.create("rival driver names", "BLAZE", {}, 8)  # list of 8
	Kinloom.event("BLAZE crashed on lap 3", ["BLAZE", "VEGA"])  # they remember it
	Kinloom.state({"lap": 3, "leader": "NOVA"})  # facts every call sees

# Minds: utility AI for crowds, run locally every frame (never a model call); rules are the offline mind
func _ready_minds() -> void:
	Kinloom.mind("raider", "a cunning raider", {
		"senses": {"hp": [0.0, 1.0], "dist": [0.0, 40.0], "armed": true},
		"actions": {"charge": {"speed": [1.0, 3.0]}, "shoot": {}, "retreat": {}},
		"rules": {"retreat": ["hp low"], "shoot": ["armed", "dist below 20"], "charge": {"score": 0.5, "args": {"speed": "dist high"}}}})

func _enemy_tick(enemy: Node2D) -> void:  # every frame, every enemy
	var a := Kinloom.think("raider", {"hp": enemy.hp, "dist": enemy.dist, "armed": enemy.ammo > 0}, str(enemy.get_instance_id()))
	enemy.act(a.action, a.args)  # "charge", {"speed": 2.1}
	# later: Kinloom.reward(str(enemy.get_instance_id()), damage_dealt - damage_taken, enemy_died_or_won)

# World: who saw what, rumors, opinions
func _on_theft() -> void:
	Kinloom.event("the player stole bread", [], {"by": "PLAYER", "seen_by": ["BAKER"], "tag": "theft", "impact": -0.6})
	await Kinloom.meet("BAKER", "GUARD")  # when they are near each other
	if await Kinloom.knows("GUARD", "theft"):
		guard.alert()
```
