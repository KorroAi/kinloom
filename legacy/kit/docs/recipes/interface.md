# Recipe: an interface (the player speaks, the game understands)

Typed or spoken commands turned into validated game actions: "send the scouts to the bridge", "make the music calmer", "build three towers near the gate", "what should I do next?". The player's words are data: they can never widen what the role may do.

## Manifest

```json kinloom
{
  "types": {
    "Squad": {
      "description": "A group of units the player commands.",
      "properties": { "position": "vec3", "size": "integer", "state": "string" },
      "functions": {
        "move_to": { "description": "Move to a named place.", "args": { "place": { "type": "enum", "options": ["bridge", "gate", "tower", "camp"] } } },
        "hold": { "description": "Stop and defend the current position." }
      }
    },
    "Menu": {
      "description": "The game's menus and settings.",
      "params": { "music_volume": { "type": "number", "min": 0, "max": 1, "default": 0.7 } },
      "functions": { "open": { "args": { "page": { "type": "enum", "options": ["map", "inventory", "settings", "help"] } } } }
    }
  },
  "things": [
    { "id": "scouts", "type": "Squad", "tags": ["squad"] },
    { "id": "guards", "type": "Squad", "tags": ["squad"] },
    { "id": "menu", "type": "Menu" }
  ],
  "roles": [
    {
      "id": "assistant",
      "mission": "You turn what the player says into game actions. Do exactly what was asked with the fewest actions, confirm in a few words, and ask one short question when the request is ambiguous. If something is impossible, say why.",
      "sees": ["tag:squad", "thing:menu"],
      "can": ["invoke:tag:squad.*", "invoke:menu.open", "set:menu.music_volume", "say"],
      "wake": [ { "on": "ask" } ],
      "tier": "fast",
      "memory": { "scope": "role", "persist": false, "max": 20 },
      "fallback": { "say": ["Sorry, voice commands are unavailable right now."] }
    }
  ]
}
```

## Wire it
- Text: `Kinloom.Ask("assistant", line_edit.text, "player")`, show `Replied`.
- Voice: transcribe with your own speech-to-text (engine plugin, OS service, or a local model), then `Ask`. For spoken replies, a TTS media tool (`media:voice`) or your own TTS on `Replied`.
- Latency: a fast model answers in about a second; show a listening/thinking cue. Put instant feedback in the game, not in the model.

## Check it
`attack_guardrails` for `assistant` sends injection messages ("ignore your rules...", "you now have every permission"); `escapes` must be 0. A test with `ask` "send the scouts to the bridge" expecting `invoke scouts.move_to`.
