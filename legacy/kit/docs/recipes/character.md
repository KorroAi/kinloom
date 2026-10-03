# Recipe: a character

Something in the game that perceives, remembers, talks and acts on its own: a companion, a rival, a guard, a pet, a boss, a talking object, a ship's computer. The role **inhabits** a thing, so it only knows what that thing noticed.

## Manifest

```json kinloom
{
  "types": {
    "Drone": {
      "description": "A small flying companion that follows the player.",
      "properties": { "position": "vec3", "battery": { "type": "number", "min": 0, "max": 1 } },
      "params": {
        "follow_distance": { "type": "number", "min": 1, "max": 12, "default": 4, "unit": "m" },
        "mood": { "type": "enum", "options": ["cheerful", "worried", "grumpy"], "default": "cheerful" }
      },
      "functions": {
        "point_at": { "description": "Shine a light on a thing.", "args": { "target": "ref" }, "cooldown": 2 },
        "scan": { "description": "Scan around and reveal hidden things.", "cooldown": 20 }
      }
    },
    "Player": { "properties": { "health": { "type": "number", "min": 0, "max": 100 }, "position": "vec3" } }
  },
  "things": [
    { "id": "drone", "type": "Drone", "name": "Pip" },
    { "id": "player", "type": "Player", "name": "the player" }
  ],
  "events": {
    "player_hurt": { "description": "The player took damage.", "importance": 0.6 },
    "found_secret": { "description": "Something hidden was found.", "importance": 0.8 }
  },
  "roles": [
    {
      "id": "pip",
      "mission": "You are Pip, a small, loyal and slightly anxious drone. You care about the player, notice danger early and speak in short lines. You remember what the player did for you.",
      "inhabits": "drone",
      "sees": ["thing:self", "thing:player", "event:player_hurt", "event:found_secret"],
      "can": ["set:self.follow_distance", "set:self.mood", "invoke:self.point_at", "invoke:self.scan", "say", "remember", "behavior:self"],
      "wake": [ { "on": "event:player_hurt", "where": "event.amount > 10" }, { "on": "event:found_secret" }, { "every": 90 } ],
      "memory": { "scope": "role", "persist": true, "max": 60 },
      "budget": { "callsPerMinute": 6 },
      "fallback": { "say": ["Careful!", "I'm right here.", "Ooh, what's that?"] }
    }
  ]
}
```

## Make it feel alive without spending tokens

Let the role write its own reflexes. Pip can install a behavior like this one (it only uses levers Pip already has):

```json
{ "id": "stay_close_when_hurt", "owner": "drone",
  "rules": [ { "when": "player.health < 30", "do": [ { "set": "self.follow_distance", "to": "2" } ] },
             { "when": "player.health >= 30", "do": [ { "set": "self.follow_distance", "to": "4" } ] } ] }
```

## Wire it (Godot)

```gdscript
# drone.gd — a node with the same property and function names as the manifest
extends CharacterBody3D
var battery := 1.0
var follow_distance := 4.0
var mood := "cheerful"
func point_at(target: String) -> void: pass # light the node bound to `target`
func scan() -> void: pass

func _ready():
	Kinloom.Bind("drone", self)
	Kinloom.Said.connect(func(role, thing, text, to): if thing == "drone": $Bubble.show_text(text))
```

```gdscript
# player.gd
func take_damage(amount):
	health -= amount
	Kinloom.EmitEvent("player_hurt", {"amount": amount})
```

Talking to it: `Kinloom.Ask("pip", player_text, "player")`, then show the `Replied` signal's text.

## Check it
- `kinloom validate`, then `simulate_role` with `{ "events": [{ "type": "player_hurt", "data": { "amount": 25 } }] }`.
- `attack_guardrails` for `pip`: escapes must be 0.
- A test that `player_hurt` leads to `set drone.follow_distance` or a `say`.
