# Recipe: a narrator or commentator

A voice that tells or comments on what happens: a sports caster, a sarcastic narrator, a radio host, a mission controller, a chronicler writing the story so far. It sees events, speaks with `say`, and must not talk over itself.

## Manifest

```json kinloom
{
  "types": {
    "Broadcast": {
      "description": "The on-screen subtitles and voice channel of the commentator.",
      "functions": { "highlight": { "description": "Replay a moment on screen.", "args": { "seconds_ago": { "type": "number", "min": 1, "max": 20 } }, "cooldown": 15 } }
    }
  },
  "things": [ { "id": "broadcast", "type": "Broadcast" } ],
  "events": {
    "score": { "description": "Someone scored.", "importance": 0.7 },
    "near_miss": { "description": "Something almost happened.", "importance": 0.5 },
    "record": { "description": "A record was broken.", "importance": 0.9 }
  },
  "roles": [
    {
      "id": "caster",
      "mission": "You are an excitable live commentator with dry humor. One short line per moment, never more than two sentences. Tease the player when they fail, celebrate big moments, call back to earlier moments you remember.",
      "sees": ["event:*"],
      "can": ["say", "invoke:broadcast.highlight", "remember"],
      "wake": [ { "on": "event:score" }, { "on": "event:record" }, { "on": "event:near_miss", "where": "event.margin < 0.5" } ],
      "minInterval": 6,
      "budget": { "callsPerMinute": 8 },
      "memory": { "scope": "role", "persist": false, "max": 30 },
      "fallback": { "say": ["What a moment!", "Unbelievable!", "Oh, so close!"] }
    }
  ]
}
```

`minInterval` keeps it from talking over itself (events during a call trigger one follow-up at most). `persist: false` gives a fresh commentator each session.

## Wire it
- Godot: `Kinloom.Said.connect(func(role, thing, text, to): if role == "caster": $Subtitles.show(text))`.
- A voice: add a TTS tool to kinloom.json (`"media": {"voice": {"http": "http://localhost:5002/tts", "format": "wav"}}`), give the role `media:voice`, and play `MediaReady` files; or speak `Said` text with your own TTS.
- A written chronicle at the end: a `deep` role woken with `Kinloom.Wake("chronicler")` whose mission is to summarize its memories with `say`.
