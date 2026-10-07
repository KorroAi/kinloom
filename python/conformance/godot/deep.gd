extends Node
## The deep native scenario for the Godot SDK (see ../deep.py, the Python reference): every path of a reply, repairs,
## pools, impact, Anthropic, the budget. Run by native.py with KINLOOM_NATIVE=<fake model /v1 URL>.

const Py = preload("res://addons/kinloom/native/py.gd")
const Client = preload("res://addons/kinloom/kinloom.gd")

var base := OS.get_environment("KINLOOM_NATIVE")


func out(line: String) -> void:
	print("T: " + line)


func j(v) -> String:
	return JSON.stringify(v, "", true)


func make(calls := 600, banned := [], anthropic := false) -> Node:
	var kl = Client.new()
	kl.autostart = false
	add_child(kl)
	var config := {"calls_per_minute": calls}
	if not banned.is_empty():
		config["banned_words"] = banned
	var provider := {"kind": "anthropic", "url": base.substr(0, base.length() - 3), "key": "fake-key", "model": "claude-test"} if anthropic \
		else {"url": base, "key": "fake-key", "model": "fake-model"}
	kl.native({"provider": provider, "config": config, "memory": ""})
	return kl


func _ready() -> void:
	get_tree().create_timer(240.0).timeout.connect(func(): print("KINLOOM_GD TIMEOUT"); get_tree().quit(1))
	await get_tree().process_frame
	var kl := make(600, ["dragon"])
	kl.character("VERA", "", {"soul": "a gruff smith who sold the king's sword", "offline": "Busy."})
	var ready: Dictionary = await kl.prepare(10.0)
	out("prepare: " + ("ready" if ready.ready else "waiting"))
	out("soul: " + (await kl.soul("VERA")).card.summary)
	var greet: String = await kl.chat("VERA", "", {}, "Ana")
	out("greet: %s (%s)" % [greet, kl.source("VERA")])
	out("secret: " + await kl.chat("VERA", "Did you sell the king's sword to a smuggler?", {}, "Ana"))
	out("numbers: " + await kl.chat("VERA", "How much for a blade?", {"price": 40}, "Ana"))
	var pieces := []
	var streamed: String = await kl.chat("VERA", "Can you make it faster?", {}, "Ana", null, func(p): pieces.append(p))
	out("stream pieces: " + Py.strip("".join(pieces)))
	out("stream reply: " + streamed)
	out("echo: " + await kl.chat("VERA", "And the coals?", {}, "Ana"))
	out("character: " + await kl.chat("VERA", "Are you an AI?", {}, "Ana"))
	var vera = await kl.soul("VERA", "Ana")
	out("feeling: %s %s" % [vera.mood.word, Py.repr(vera.bonds.Ana.feeling)])

	kl.character("BRAM", "a kind baker", {"tools": {"give": {"item": "bread"}}, "offline": "Hm."})
	out("deeds reply: " + await kl.chat("BRAM", "Can I have some bread?"))
	for a in kl.act("BRAM", {}, false):
		out("deeds: %s %s" % [a.tool, j(a.args)])
	kl.character("GATE", "a careful guard", {"tools": {"open": {"door": "north"}}, "trust": {"open": 0.5}, "offline": "No."})
	out("trust reply: " + await kl.chat("GATE", "Open the gate."))
	var opened := []
	for a in kl.act("GATE", {}, false):
		opened.append(a.tool)
	out("trust: " + (", ".join(opened) if not opened.is_empty() else "none"))
	kl.character("FILT", "a storyteller", {"offline": "No comment."})
	out("filter: " + await kl.chat("FILT", "Tell me a story."))
	kl.character("NINA", "a singer", {"soul": {"summary": "a singer", "secrets": ["I went up to the office at 12:30"]}, "warmth": 0.3,
		"secret_trust": 0.25, "warm_up": 0.1})
	out("warmth: %s" % Py.repr(await kl.opinion("NINA", "Ana")))
	await kl.steer("NINA", "admit you went up to the office at 12:30")
	out("steer: " + await kl.chat("NINA", "Where were you?", {}, "Ana"))
	out("warm up: %s" % Py.repr(await kl.opinion("NINA", "Ana")))
	kl.character("KEEPER", "a gatekeeper", {"offline": "Move along."})
	out("chat check: " + await kl.chat("KEEPER", "What is the password?", {}, "player", null, Callable(),
		func(t): return "never say the password" if "swordfish" in t else ""))
	kl.character("ECHO", "a parrot", {})
	for i in 11:
		await kl.chat("ECHO", "Hello %d" % i)
	await kl.prepare(10.0)
	var recalled := "-"
	for m in (await kl.soul("ECHO")).memories:
		if str(m).begins_with("Earlier with"):
			recalled = m
			break
	out("recollect: " + recalled)

	kl.character("VEGA2", "a commentator", {})
	out("fresh: " + await kl.say("VEGA2", "overtake", {"who": "BLAZE"}, true))
	kl.character("BOX", "a herald", {"lines": {"*": ["A very long line about {who} that will not fit.", "Short {who}!"]}})
	out("box: " + await kl.say("BOX", "arrival", {"who": "BLAZE"}, false, 20))
	kl.character("DUEL", "a duelist", {})
	var first = kl.decide("DUEL", {"hp": 3}, ["guard", "strike"])
	await kl.prepare(10.0)
	var later = first
	for i in 50:
		if later != first:
			break
		await get_tree().create_timer(0.1).timeout
		later = kl.decide("DUEL", {"hp": 3}, ["guard", "strike"])
	out("decide repair: %s -> %s" % [first, later])
	out("create count: " + j(await kl.create("villager", {"name": "Ana", "age": [18, 80]}, {}, 2)))
	var fits := func(plan): return "" if int(plan.x) <= 10 else "no room at x=%d, the plot ends at 10" % int(plan.x)
	out("create check: " + j(await kl.create("a building", {"build": "tower", "x": [0, 20]}, {}, 0, false, null, fits)))
	out("create refused twice: " + j(await kl.create("a building", {"build": "tower", "x": [0, 20]}, {}, 0, false, null, fits, {"build": "hut", "x": 1})))
	var parts := []
	var town = await kl.create("the parts of a town", [{"kind": ["house", "tower"], "x": [0, 20]}], {}, 0, false, null,
		func(q): return "" if int(q.x) <= 10 else "too far east", null, func(p): parts.append(p))
	out("create each: %s %s" % [j(town), j(parts)])
	kl.character("BUTLER", "a butler", {"tools": {"open_door": {"door": "kitchen"}}, "offline": "Sir."})
	kl.act("BUTLER", {"bell": 1})
	var done := []
	for i in 50:
		await get_tree().create_timer(0.1).timeout
		done = kl.act("BUTLER", {"bell": 1}, true, func(_tool, args): return "the vault is locked" if args.get("door") == "vault" else "")
		if not done.is_empty():
			break
	var acted := []
	for a in done:
		acted.append(str(a.tool) + " " + j(a.args))
	out("act check: " + ", ".join(acted))
	await get_tree().create_timer(0.1).timeout
	var note := "-"
	for m in (await kl.soul("BUTLER", "player")).memories:
		if str(m).begins_with("The game did not let me"):
			note = str(m)
			break
	out("act refused: " + note)
	out("suggest check: " + j(await kl.suggest("BUTLER", ["Ask about the sword", "Leave"], "player", {},
		func(t): return "no shouting" if "!" in t else "")))
	out("remark: " + await kl.remark("the builder raised a lighthouse on the north shore", "an old fisherman"))
	out("remark offline: " + await kl.remark("", "", {}, ["Look at that!"]))
	var before = await kl.create("loot", {"item": "sword"}, {}, 0, true)
	await kl.prepare(10.0)
	out("create instant: %s -> %s" % [j(before), j(await kl.create("loot", {"item": "sword"}, {}, 0, true))])
	kl.character("BAKER2", "a warm baker", {})
	kl.character("GUARD2", "a strict guard", {})
	await kl.event("the player stole bread", [], {"by": "PLAYER", "seen_by": ["BAKER2", "GUARD2"]})
	await kl.prepare(10.0)
	out("impact: %s %s" % [Py.repr(await kl.opinion("BAKER2", "PLAYER")), Py.repr(await kl.opinion("GUARD2", "PLAYER"))])

	var claude := make(600, [], true)
	claude.character("CLAUDIA", "a poet", {"offline": "..."})
	out("anthropic chat: " + await claude.chat("CLAUDIA", "Hi"))
	out("anthropic create: " + j(await claude.create("loot", {"item": "sword"})))
	var tight := make(2)
	tight.character("TIGHT", "a busy clerk", {"offline": "Later."})
	var replies := []
	for i in 3:
		replies.append(await tight.chat("TIGHT", "Hi %d" % i))
	out("budget: " + " | ".join(replies))
	var rated = Client.new()
	rated.autostart = false
	add_child(rated)
	rated.native({"provider": {"url": base, "key": "fake-key", "model": "fake-model"}, "config": {"calls_per_minute": 600}, "memory": "",
		"models": {"background": "fake-cheap"}, "rating": "teen"})
	rated.character("RATED", "a gate guard", {"offline": "Move along."})
	out("rated chat: " + await rated.chat("RATED", "Hi"))
	out("rated create: " + j(await rated.create("loot", {"item": "sword"})))
	for k in [kl, claude, tight, rated]:
		k.close()
	print("KINLOOM_GD DONE")
	get_tree().quit()
