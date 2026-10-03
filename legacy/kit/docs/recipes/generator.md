# Recipe: a generator

Content made on demand and guaranteed to fit: a level chunk, a track section, a puzzle, an item with stats, a quest, a dialogue tree, a shop inventory, a name, a UI layout. The schema, the constraints and (optionally) the game itself must accept it; otherwise Kinloom asks the model to repair, then falls back to a declared value.

## Manifest

```json kinloom
{
  "types": {
    "LevelBuilder": {
      "description": "Builds the next chunk of the level from a plan.",
      "functions": { "build": { "args": { "plan": { "type": "object" } } } }
    }
  },
  "things": [ { "id": "builder", "type": "LevelBuilder" } ],
  "events": { "chunk_needed": { "description": "The player is close to the end of the current chunk.", "importance": 0.3 } },
  "generators": [
    {
      "id": "chunk",
      "description": "The next chunk of the level: a sequence of pieces that is fun for the player described in the context.",
      "schema": {
        "type": "object",
        "fields": {
          "pieces": { "type": "list", "min": 4, "max": 16, "items": { "type": "enum", "options": ["flat", "gap", "ramp", "wall", "moving", "enemy", "reward"] } },
          "theme": { "type": "string", "max": 40 }
        },
        "required": ["pieces"]
      },
      "constraints": [
        "len(value.pieces) >= 4",
        "value.pieces[0] == 'flat'",
        "!contains(value.pieces, 'gap') || contains(value.pieces, 'reward') || context.skill > 0.7"
      ],
      "repair": 1,
      "gameValidate": true,
      "fallback": { "pieces": ["flat", "ramp", "flat", "gap", "flat", "reward"], "theme": "default" }
    }
  ],
  "roles": [
    {
      "id": "architect",
      "mission": "You design the next chunk for this player. Ask the chunk generator with a one-sentence brief that reflects how they have been playing.",
      "sees": ["event:chunk_needed", "world"],
      "can": ["generate:chunk"],
      "wake": [ { "on": "event:chunk_needed" } ],
      "tier": "fast"
    }
  ]
}
```

Two ways to use it:
- **The game calls it directly**: Godot `Kinloom.Generate("chunk", {"skill": 0.4, "deaths": 3})` → `Generated("chunk", json)`; protocol `generate`.
- **A role calls it** (like `architect` above): the validated value arrives as an `invoke` on `world`, member `generated`, args `{generator, value, source}`.

`gameValidate: true` sends a `validate` effect first (Godot: `ValidateRequested(id, generator, json)` → your checks → `Kinloom.ResolveValidation(id, ok, reason)`). Refusal reasons go back to the model for its repair.

## Tips
- Put every hard rule in the schema or a constraint; put taste in the description.
- Constraints see `value` and `context` (what you passed to `generate`).
- Always declare a `fallback` for content the game cannot run without.
- New media (textures, sounds) for generated content: add a `media` tool in kinloom.json and a role with `media:<kind>`.
