# Recipe: an analyst (understanding the player)

A role that studies how someone plays and writes its conclusions where other systems can read them: skill, style, frustration, preferences. Other roles, behaviors and your own code then adapt to it. It changes nothing in the game directly.

## Manifest

```json kinloom
{
  "types": {
    "PlayerStats": {
      "description": "Numbers the game collects about the player.",
      "properties": {
        "accuracy": { "type": "number", "min": 0, "max": 1 },
        "retries_last_10min": "integer",
        "avg_reaction_ms": "number",
        "time_in_menus_pct": { "type": "number", "min": 0, "max": 100 },
        "favorite_action": "string"
      }
    },
    "Profile": {
      "description": "What we believe about the player. Other systems read this.",
      "params": {
        "skill": { "type": "number", "min": 0, "max": 1, "default": 0.5 },
        "frustration": { "type": "number", "min": 0, "max": 1, "default": 0 },
        "style": { "type": "enum", "options": ["explorer", "competitor", "creator", "socializer", "unknown"], "default": "unknown" },
        "wants": { "type": "string", "max": 160, "default": "" }
      }
    }
  },
  "things": [
    { "id": "stats", "type": "PlayerStats" },
    { "id": "profile", "type": "Profile" }
  ],
  "events": { "gave_up": { "description": "The player quit an attempt early.", "importance": 0.7 } },
  "roles": [
    {
      "id": "analyst",
      "mission": "You study how this person plays. Every few minutes, update the profile: skill, frustration, style and one short sentence about what they seem to want. Change values gradually and only when the evidence supports it.",
      "sees": ["thing:stats", "thing:profile", "event:gave_up"],
      "can": ["set:profile.*", "remember"],
      "wake": [ { "every": 180 }, { "on": "event:gave_up" } ],
      "tier": "deep",
      "memory": { "scope": "role", "persist": true, "max": 80 },
      "budget": { "callsPerMinute": 2 }
    }
  ]
}
```

`persist: true` plus `SaveState()` in your save file lets the analysis carry over between sessions.

## Use the profile
- Other roles: add `"thing:profile"` to their `sees`.
- Behaviors: `"when": "profile.frustration > 0.7"` → lower a difficulty param, show a hint.
- Your code: read the confirmed params (Godot: the bound `profile` node receives `set`; C#: `Kinloom.Session.Things.Find("profile").Params`).

## Privacy
Only numbers you choose leave the game, and only to the provider configured in kinloom.json. Do not put personal data in properties.
