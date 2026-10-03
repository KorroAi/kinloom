extends Node
## Conformance scenario for the Godot client (see ../README.md), then the no-code AICharacter node.

signal overtake

var who := "BLAZE"
var whom := "NOVA"
var aggression := 0.0
var strategy := "none"
# a unit for the no-code AIMind node: its properties are senses, its methods actions
var hp := 0.1
var dist := 30.0
var moves: Array = []


func retreat() -> void:
	moves.append("retreat")


func charge(speed: float) -> void:
	moves.append("charge %.1f" % speed)


func j(v) -> String:
	return JSON.stringify(v, "", true)


func out(line: String) -> void:
	print("T: " + line)


# Native mode (python conformance/native.py): the SDK calls the fake model itself, no kinloom serve; "offline" is then
# a brain with no model (the relay scenario points at a dead address instead).
var native := OS.get_environment("KINLOOM_NATIVE")
var host = null


func go_live(kl) -> void:
	if native != "":
		kl._brain = host
	else:
		kl.url = "http://127.0.0.1:%s" % OS.get_environment("KINLOOM_TEST_PORT")
		kl._down_until = 0.0


func go_dead(kl) -> void:
	if native != "":
		kl.offline({"memory": ""})
	else:
		kl.url = "http://127.0.0.1:9"


func _ready() -> void:
	get_tree().create_timer(180.0).timeout.connect(func(): print("KINLOOM_GD TIMEOUT"); get_tree().quit(1))
	await get_tree().process_frame
	var kl = get_node("/root/Kinloom")
	kl.url = "http://127.0.0.1:%s" % OS.get_environment("KINLOOM_TEST_PORT")
	kl.autostart = false
	if native != "":
		kl.native({"provider": {"url": native, "key": "fake-key", "model": "fake-model"}, "config": {"calls_per_minute": 600},
			"voice": {"url": native, "key": "fake-key", "speak_model": "fake-tts", "listen_model": "fake-stt", "name": "custom"},
			"memory": ""})
		host = kl._brain
	kl.character("VEGA", "commentator", {"lines": {"*": ["What a race, {who}!"]}, "events": {"overtake": ["who", "whom"]}})
	kl.character("THEO", "engineer", {"offline": "Copy."})
	kl.character("BLAZE", "rival", {"tools": {"boost": {"seconds": [0.5, 2.5]}}})
	var facts := {"who": "BLAZE", "whom": "NOVA"}
	var line := ""
	for i in 100:
		line = await kl.say("VEGA", "overtake", facts)
		if "passes" in line:
			break
		await get_tree().create_timer(0.05).timeout
	out("say: " + line)
	out("chat: " + await kl.chat("THEO", "gap?", {"position": 3}))
	var choices := {"strategy": ["attack", "block"], "aggression": [0.0, 1.0]}
	var first: Dictionary = kl.decide("BLAZE", {"lap": 1}, choices).duplicate()
	out("decide first: " + j(first))
	var later := first
	for i in 100:
		await get_tree().create_timer(0.05).timeout
		later = kl.decide("BLAZE", {"lap": 1}, choices).duplicate()
		if later != first:
			break
	out("decide later: " + j(later))
	for i in 100:
		var actions: Array = kl.act("BLAZE", {"lap": 1})
		if not actions.is_empty():
			for a in actions:
				out("act later: %s %s" % [a.tool, j(a.args)])
			break
		await get_tree().create_timer(0.05).timeout
	out("create: " + j(await kl.create("race", {"challenge": "Win clean", "sky": "#ff7a45"})))

	# The no-code node: talks on a signal of the watched node, steers its properties.
	var label := Label.new()
	add_child(label)
	var ai = load("res://addons/kinloom/ai_character.gd").new()
	ai.character_name = "VEGA"
	ai.personality = "commentator"
	ai.offline_lines = PackedStringArray(["What a race, {who}!"])
	ai.watch = NodePath("..")
	ai.react_to = PackedStringArray(["overtake"])
	ai.output = NodePath("../" + label.name)
	ai.typewriter = false
	ai.control = NodePath("..")
	ai.controls = {"strategy": ["attack", "block"], "aggression": [0.0, 1.0]}
	ai.decide_every = 0.5
	add_child(ai)
	await get_tree().create_timer(0.3).timeout
	overtake.emit()
	for i in 100:
		await get_tree().create_timer(0.05).timeout
		if label.text != "" and strategy == "block":
			break
	out("aichar talks: " + label.text)
	out("aichar steers: %s %.1f" % [strategy, aggression])

	# The no-code mind node: reads this node's properties, calls its methods.
	var mind = load("res://addons/kinloom/ai_mind.gd").new()
	mind.mind_name = "grunt"
	mind.unit = NodePath("..")
	mind.senses = {"hp": [0.0, 1.0], "dist": [0.0, 40.0]}
	mind.actions = {"retreat": {}, "charge": {"speed": [1.0, 3.0]}}
	mind.rules = {"retreat": ["hp low"], "charge": {"score": 0.5, "args": {"speed": "dist high"}}}
	mind.variants = 1
	mind.think_every = 0.0
	add_child(mind)
	for i in 30:
		await get_tree().physics_frame
	hp = 0.9
	for i in 30:
		await get_tree().physics_frame
	out("aimind moves: " + ", ".join(moves))

	# Offline: nothing listens at this address.
	go_dead(kl)
	out("offline say: " + await kl.say("VEGA", "overtake", facts))
	out("offline chat: " + await kl.chat("THEO", "gap?", {"position": 3}))
	kl._decisions.clear()
	out("offline decide: " + j(kl.decide("BLAZE", {"lap": 1}, choices)))
	out("offline create: " + j(await kl.create("race", {"challenge": "Win clean", "sky": "#ff7a45"})))
	# Minds and the world (the depth layer).
	go_live(kl)
	var raider := {"senses": {"hp": [0, 1], "dist": [0, 40], "armed": true, "enemy": ["idle", "alert"]},
		"actions": {"charge": {"speed": [0.5, 3.0]}, "shoot": {"burst": [1, 5]}, "retreat": {}},
		"rules": {"retreat": ["hp low"], "shoot": ["armed", "dist below 20"], "charge": {"score": 0.5, "args": {"speed": "dist high"}}},
		"variants": 1}
	kl.mind("raider", "a cunning raider", raider)
	kl.mind("scout", "a timid scout", {"senses": {"noise": [0, 1]}, "actions": {"run": {}, "hide": {}}, "variants": 2})
	for i in 100:
		if await kl.report("raider") != null:
			break
		await get_tree().create_timer(0.05).timeout
	out("think retreat: " + j(kl.think("raider", {"hp": 0.1, "dist": 30, "armed": true}, "u1")))
	out("think shoot: " + j(kl.think("raider", {"hp": 0.9, "dist": 8, "armed": true, "enemy": "alert"}, "u2")))
	out("think charge: " + j(kl.think("raider", {"hp": 0.9, "dist": 10, "armed": false}, "u3")))
	out("think sticky: " + str(kl.think("raider", {"hp": 0.52, "dist": 30, "armed": true}, "u1").action))
	out("think fresh: " + j(kl.think("raider", {"hp": 0.52, "dist": 30, "armed": true}, "u4")))
	var learned := ""
	for i in 100:
		learned = str(kl.think("scout", {"noise": 0.5}, "s1").action)
		if learned == "hide":
			break
		await get_tree().create_timer(0.1).timeout
	out("think learned: " + learned)
	kl.reward("u1", 1.0)
	kl.reward("u2", 0.5)
	kl.reward("u3", 0.0)
	await kl.flush()
	var report = await kl.report("raider")
	var total := 0
	for v in report.variants:
		total += int(v.rewards)
	out("rewards: %d" % total)
	kl.character("BAKER", "a warm baker", {"group": "village"})
	kl.character("GUARD", "a strict guard", {"group": "guards"})
	out("knows before: " + str(await kl.knows("GUARD", "theft")).to_lower())
	await kl.event("the player stole bread", [], {"by": "PLAYER", "seen_by": ["BAKER"], "tag": "theft", "impact": -0.8})
	var shared := []
	for i in 50:
		shared = await kl.meet("BAKER", "GUARD")
		if not shared.is_empty():
			break
		await get_tree().create_timer(0.1).timeout
	var pairs := []
	for x in shared:
		pairs.append("%s -> %s" % [x["from"], x["to"]])
	out("meet: " + ", ".join(pairs))
	out("knows after: " + str(await kl.knows("GUARD", "theft")).to_lower())
	out("opinion: " + str(await kl.opinion("GUARD", "PLAYER")))
	out("reputation: " + str(await kl.reputation("PLAYER", "village")))
	# The no-code dialogue box: a soul in one sentence, the player's name, a reply with a mood.
	var dialogue = load("res://addons/kinloom/ai_dialogue.gd").new()
	dialogue.character_name = "MIRA"
	dialogue.soul = '{"summary": "a gruff smith", "mood": "wary"}'
	dialogue.offline_line = "Hm."
	dialogue.speaker = "Ana"
	dialogue.tools = {"give": {"item": "wood"}}
	var did := []
	dialogue.acted.connect(func(tool, args): did.append("chat do: %s %s" % [tool, j(args)]))
	dialogue.typewriter = false
	dialogue.voice = true
	add_child(dialogue)
	await get_tree().create_timer(0.1).timeout
	out("soul chat: " + await dialogue.send("Nice toy hammer."))
	var mira_source: String = kl.source("MIRA")
	var soul = null
	for i in 50:
		soul = await kl.soul("MIRA", "Ana")
		if soul is Dictionary and soul.get("card") is Dictionary and soul["bonds"].has("Ana"):
			break
		await get_tree().create_timer(0.1).timeout
	out("lore: %d" % await kl.lore(["The village is Brookmere.", "The king died last winter."]))
	out("soul: %s %s %s" % [soul["mood"]["word"], "dislikes" if soul["bonds"]["Ana"]["feeling"] < 0 else "likes", soul["card"]["summary"]])
	var raw: PackedByteArray = await kl.speak_wav("GUARD", "Halt.")
	var stream = await kl.speak("GUARD", "Halt.")
	out("speak: " + ("wav" if raw.slice(0, 4).get_string_from_ascii() == "RIFF" and stream is AudioStreamWAV else "?"))
	out("listen: " + await kl.listen(raw))
	go_dead(kl)
	kl._minds.clear()
	kl.mind("raider", "a cunning raider", raider)
	out("offline think: " + j(kl.think("raider", {"hp": 0.1, "dist": 30, "armed": true}, "u1")))
	out("offline think charge: " + j(kl.think("raider", {"hp": 0.9, "dist": 10, "armed": false}, "u3")))
	out("offline knows: " + str(await kl.knows("GUARD", "theft")).to_lower())
	kl.character("MIRA", "", {"soul": {"summary": "a gruff smith"}, "offline": "Hm."})
	out("offline soul chat: " + await kl.chat("MIRA", "Nice toy hammer.", {}, "Ana"))
	out("offline speak: " + ("none" if (await kl.speak("GUARD", "Halt.")) == null else "audio"))
	var heard: String = await kl.listen(raw)
	out("offline listen: " + (heard if heard != "" else "-"))
	# What came back: where it came from, actions with the reply, events described in words.
	go_live(kl)
	var challenge := {"challenge": {"when": "challenging someone to a battle", "lines": ["{other}, fight!"]}}
	kl.character("ANA", "a trainer", {"lines": challenge})
	var said_line := ""
	for i in 50:
		said_line = await kl.say("ANA", "challenge", {"other": "BEN"})
		if said_line != "":
			break
		await get_tree().create_timer(0.1).timeout
	out("when say: " + said_line)
	await kl.say("VEGA", "overtake", facts)
	out("say source: " + kl.source("VEGA"))
	out("chat source: " + mira_source)
	for line_did in did:
		out(line_did)
	go_dead(kl)
	kl.character("ANA", "a trainer", {"lines": challenge})
	out("offline when say: " + await kl.say("ANA", "challenge", {"other": "BEN"}))
	out("offline source: " + kl.source("ANA"))
	# The game's tools, pictures, ready before play.
	var png := Marshalls.base64_to_raw("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGP4z8AARAwQCgAf7gP9i18U1AAAAABJRU5ErkJggg==")
	go_live(kl)
	out("tools: " + ", ".join(await kl.tools({"open_door": {"door": "north"}})))
	kl.character("KEEPER", "a gatekeeper", {"tools": ["open_door"]})
	await get_tree().create_timer(0.1).timeout
	for i in 100:
		var acts: Array = kl.act("KEEPER", {})
		if acts.size() > 0:
			for a in acts:
				out("tools act: %s %s" % [a["tool"], JSON.stringify(a["args"], "", true)])
			break
		await get_tree().create_timer(0.05).timeout
	kl.character("LOOK", "a painter", {"offline": "Blind."})
	await get_tree().create_timer(0.1).timeout
	out("chat image: " + await kl.chat("LOOK", "What is this?", {}, "player", png))
	var race := {"challenge": "Win clean", "sky": "#ff7a45"}
	out("create image: " + JSON.stringify(await kl.create("race", race, {}, 0, false, png), "", true))
	var ready: Dictionary = await kl.prepare(10.0)
	out("prepare: %s %s" % ["ready" if ready["ready"] else "waiting", "online" if ready["online"] else "offline"])
	go_dead(kl)
	kl._down_until = 0.0
	out("offline tools: " + ", ".join(await kl.tools({"open_door": {"door": "north"}})))
	kl.character("LOOK", "a painter", {"offline": "Blind."})
	out("offline chat image: " + await kl.chat("LOOK", "What is this?", {}, "player", png))
	out("offline create image: " + JSON.stringify(await kl.create("race", race, {}, 0, false, png), "", true))
	ready = await kl.prepare(1.0)
	out("offline prepare: %s %s" % ["ready" if ready["ready"] else "waiting", "online" if ready["online"] else "offline"])
	var t0 := Time.get_ticks_msec()
	kl._down_until = 0.0                        # like a fresh client: the server is checked again
	kl._failures = 0
	kl.character("THEO", "engineer", {"offline": "Copy."})
	var fast: bool = (await kl.chat("THEO", "gap?")) == "Copy." and (await kl.chat("THEO", "gap?")) == "Copy." \
		and (await kl.say("THEO", "x")) == ""
	var took := Time.get_ticks_msec() - t0
	out("offline fast: " + ("yes" if fast and took < 1500 else "no (%d ms)" % took))
	# v1: the player's choices, characters talking together, a snapshot, saves
	var reply_choices := ["Ask about the sword", "Buy something", "Leave"]
	go_live(kl)
	kl._failures = 0
	var suggested: Array = await kl.suggest("MIRA", reply_choices, "Ana")
	var talk := []
	for x in await kl.converse("MIRA", "BAKER", "the smoke", 4):
		talk.append("%s: %s" % [x["who"], x["text"]])
	var snap: Dictionary = await kl.inspect()
	var saved: String = await kl.save_state()
	kl.session = "slot2"
	await kl.load_state(saved)
	var feeling: float = await kl.opinion("MIRA", "Ana")
	kl.session = "default"
	go_dead(kl)
	out("suggest: " + " | ".join(suggested))
	out("offline suggest: " + " | ".join(await kl.suggest("MIRA", reply_choices, "Ana")))
	out("converse: " + " | ".join(talk))
	out("offline converse: %d" % (await kl.converse("MIRA", "BAKER", "", 4)).size())
	out("inspect: MIRA %s %s" % [snap["characters"]["MIRA"]["mood"]["word"], snap["characters"]["MIRA"]["last_words"]])
	out("load: MIRA %s Ana" % ("dislikes" if feeling < 0 else "likes"))
	if native != "":
		var vectors = load("res://addons/kinloom/native/vectors.gd")
		var v: Array = vectors.run_file(OS.get_environment("KINLOOM_VECTORS"))
		out("vectors: %d/%d" % [v[0], v[1]])
		for f in v[2].slice(0, 8):
			printerr("VECTOR %s %s\n  want: %s\n  got:  %s" % [f.fn, JSON.stringify(f.args).left(400), JSON.stringify(f.want).left(600),
				JSON.stringify(f.got).left(600)])
		host.close()
	print("KINLOOM_GD DONE")
	get_tree().quit()
