# Recipe: a director

A system that watches the whole session and adjusts it: pacing, difficulty, spawns, weather, music, lighting, events, rewards. It does not inhabit anything; it **governs** things through params, functions and creations, and it can leave instant behaviors running between its decisions.

## Manifest

```json kinloom
{
  "types": {
    "Spawner": {
      "description": "Brings opponents or obstacles into play.",
      "properties": { "active_count": "integer" },
      "params": {
        "rate": { "type": "number", "min": 0, "max": 5, "default": 1, "unit": "per minute" },
        "difficulty": { "type": "number", "min": 0, "max": 1, "default": 0.5 }
      }
    },
    "Atmosphere": {
      "description": "Weather, light and music of the current area.",
      "params": {
        "weather": { "type": "enum", "options": ["clear", "fog", "rain", "storm"], "default": "clear" },
        "music_intensity": { "type": "number", "min": 0, "max": 1, "default": 0.3 }
      }
    },
    "Hazard": {
      "description": "A temporary obstacle the director can place.",
      "creatable": { "args": { "position": "vec3", "kind": { "type": "enum", "options": ["rocks", "fire", "ice"] } }, "max": 3 }
    },
    "Session": { "properties": { "deaths_last_5min": "integer", "minutes_played": "number", "score": "number" } }
  },
  "things": [
    { "id": "spawner", "type": "Spawner" },
    { "id": "atmosphere", "type": "Atmosphere" },
    { "id": "session", "type": "Session" }
  ],
  "events": {
    "player_died": { "description": "The player lost a life.", "importance": 0.7 },
    "milestone": { "description": "The player reached a milestone.", "importance": 0.6 }
  },
  "roles": [
    {
      "id": "director",
      "mission": "You direct the pacing. Keep the player in the zone: challenged, never crushed, never bored. Build tension, then give breathing room. Change one or two things at a time and explain your intent in a thought.",
      "sees": ["thing:spawner", "thing:atmosphere", "thing:session", "event:*"],
      "can": ["set:spawner.*", "set:atmosphere.*", "create:Hazard", "destroy:own", "behavior:spawner", "behavior:atmosphere"],
      "wake": [ { "every": 45 }, { "on": "event:player_died" }, { "on": "event:milestone" } ],
      "tier": "deep",
      "budget": { "callsPerMinute": 3 },
      "fallback": { "behavior": "ease_on_deaths" }
    }
  ],
  "behaviors": [
    {
      "id": "ease_on_deaths", "owner": "spawner",
      "rules": [ { "when": "session.deaths_last_5min >= 3", "do": [ { "set": "self.difficulty", "to": "clamp(self.difficulty - 0.1, 0.1, 1)" } ], "cooldown": 30 } ]
    }
  ]
}
```

`ease_on_deaths` is declared by the game, so it works without a model; the director can install more (for example music rising with the number of active opponents).

## Wire it

- Push `session` numbers with updates (Godot: bind a node exposing `deaths_last_5min`, `minutes_played`, `score`, or implement `_kinloom_state()`).
- Apply `set` on `spawner` / `atmosphere` in your systems (Godot: bound nodes receive `node.set`).
- `Hazard` creation: give the type `"engine": {"godot": {"scene": "res://hazards/hazard.tscn", "parent": "/root/Main/Level"}}` or handle `CreateRequested(type, id, args)`.

## Check it
- `estimate_cost` (after declaring prices) shows the cost of `every: 45` on the deep tier.
- A test with three `player_died` events and `"script": {"role:director": [...]}` expecting `set spawner.difficulty`.
- A test with no script at all expecting `{ "fallback": true }` once the rule threshold is met.
