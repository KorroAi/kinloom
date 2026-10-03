class_name AIMind
extends Node
## Utility AI for a unit, no code: add it under the unit, list what the unit senses (its properties) and what it can
## do (its methods), and it picks the best action and calls that method, every tick, without a model call. Units that
## share a Mind Name share one mind; each keeps its own temperament. Give it a score property and it learns.
##
## Senses:  {"hp": [0.0, 1.0], "dist": [0.0, 40.0], "armed": true, "mood": ["calm", "angry"]}  (the unit's properties)
## Actions: {"charge": {"speed": [1.0, 3.0]}, "retreat": {}}  (the unit's methods, called with these arguments in order)
## Rules:   {"retreat": ["hp low"], "charge": {"score": 0.5, "when": ["dist below 15"], "args": {"speed": "dist high"}}}

signal decided(action: String, args: Dictionary)

@export var mind_name := "unit"
@export_multiline var personality := "a clever unit that wants to win"
## The unit (default: the parent). Its properties are the senses; its methods are the actions.
@export var unit: NodePath = NodePath("..")
## Property -> what it can be: [min, max] for numbers, true for true/false, ["a", "b"] for one of.
@export var senses: Dictionary = {}
## Method -> its arguments by example ({} for none). The method is called with the chosen values, in this order.
@export var actions: Dictionary = {}
## The offline mind: action -> rules ("hp low", "dist below 12", "armed", "not armed", "mood is angry").
@export var rules: Dictionary = {}
## Temperaments in a crowd of units sharing this mind.
@export var variants := 3
## Seconds between decisions (0 = every physics frame).
@export var think_every := 0.2
## Call the action's method only when the choice changes (off: at every decision).
@export var call_on_change_only := true

@export_group("Learning")
## A number property of the unit that goes up when things go well (score, damage dealt, distance covered...). Its
## change between two decisions is the reward. Empty: no learning.
@export var reward_property := ""
## A signal of the unit that ends its round (died, won, reset...). Optional; rounds are then judged whole.
@export var done_signal := ""
## Seconds between learning steps.
@export var learn_every := 30.0

## The current action and its arguments.
var action := ""
var args := {}
var _timer := 0.0
var _last_score = null
var _who := ""


func _ready() -> void:
	var kl := _kinloom()
	if kl == null:
		push_error("[kinloom] AIMind needs the Kinloom autoload (enable the Kinloom plugin).")
		return
	_who = "%s-%d" % [mind_name, get_instance_id()]
	if not kl.has_mind(mind_name):
		kl.mind(mind_name, personality, {"senses": senses, "actions": actions, "rules": rules, "variants": variants,
			"learn": learn_every if reward_property != "" else 0})
	var u := get_node_or_null(unit)
	if u != null and done_signal != "":
		if not u.has_signal(done_signal):
			push_warning("[kinloom] %s has no signal '%s'" % [u.name, done_signal])
		else:
			var argc := 0
			for info in u.get_signal_list():
				if info.name == done_signal:
					argc = info.args.size()
			match argc:
				0: u.connect(done_signal, func(): _finish())
				1: u.connect(done_signal, func(_a): _finish())
				2: u.connect(done_signal, func(_a, _b): _finish())
				_: u.connect(done_signal, func(_a, _b, _c): _finish())


func _physics_process(delta: float) -> void:
	_timer += delta
	if _timer >= think_every:
		_timer = 0.0
		decide()


## Decides now: rewards the last choice (if learning), reads the senses, calls the chosen action's method.
func decide() -> void:
	var kl := _kinloom()
	var u := get_node_or_null(unit)
	if kl == null or u == null:
		return
	_reward(kl, u, false)
	var t: Dictionary = kl.think(mind_name, senses_now(), _who)
	if t.action == null:
		return
	var changed: bool = t.action != action
	action = t.action
	args = t.args
	if changed or not call_on_change_only:
		if u.has_method(action):
			u.callv(action, _ordered_args())
		decided.emit(action, args)


## The unit's current values of the declared senses.
func senses_now() -> Dictionary:
	var out := {}
	var u := get_node_or_null(unit)
	if u == null:
		return out
	for name in senses:
		var v = u.get(name)
		out[name] = str(v) if typeof(v) == TYPE_STRING_NAME else v
	return out


func _ordered_args() -> Array:
	var out := []
	var ex = actions.get(action, {})
	if ex is Dictionary:
		for k in ex:
			out.append(args.get(k))
	return out


func _reward(kl: Node, u: Node, done: bool) -> void:
	if reward_property == "":
		return
	var score = u.get(reward_property)
	if typeof(score) != TYPE_INT and typeof(score) != TYPE_FLOAT:
		return
	if _last_score != null:
		kl.reward(_who, float(score) - float(_last_score), done)
	_last_score = null if done else score


func _finish() -> void:
	var kl := _kinloom()
	var u := get_node_or_null(unit)
	if kl != null and u != null:
		_reward(kl, u, true)


func _kinloom() -> Node:
	return get_node_or_null("/root/Kinloom")
