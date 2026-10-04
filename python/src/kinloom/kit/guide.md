# Kinloom: AI in this game

This game uses Kinloom for anything a model does while it runs. Kinloom knows nothing about this game: pick the call
by what the game needs back. A choice or numbers every frame (`decide`); data, text or lists of any shape (`create`);
calls to the game's functions (`act`); a line when something happens (`say`); a free answer in a voice (`chat`, with a
**soul**: one sentence becomes someone with a mood, feelings per person and memories that last); who saw what
(`event`); units deciding every frame with no model call (`mind`/`think`). No prompts, no HTTP, no JSON parsing, no
retries to write. Every call has an offline answer that you give it (your lines, your example, your rules), so the
game still works with no key, no network or a slow model.

{setup}

## The calls ({language})

{code}

## Rules

- **A soul in one sentence**: `character(name, soul="who they are")` (inner life written once, saved). `chat(name, text,
  facts, speaker)` answers in their voice (~1 s, never per frame; stream: Python `stream=`, JS `onPiece`); `""`: they
  speak first. Always pass `speaker`. Size: `max_words` (25), `max_chars` (a text box: whole sentences, else cut with
  "…"; Python/HTTP also per call); `language="auto"`: replies in the speaker's language. `voice="low, warm"` + `speak(name, text)` -> WAV,
  `listen(recording)` -> text (`ELEVENLABS_API_KEY` / `OPENAI_API_KEY`, none: the system's voice).
- **Talk changes the game**: with `tools` (or the game's, declared once: `tools({...})`, then `tools=["open_door"]` or
  `"all"`), what they decide while talking comes with the reply (Python `reply.do`; others `act(name, {}, false)`), once. `trust={"give": 0.3}`: that tool only for people
  they like that much. `lore([...])`: facts never contradicted; `invent=false`: no made-up names; `soul(name, speaker)`:
  card, mood, bonds, memories, `gesture`. Boxes: Godot `AIDialogue`, Unity `KinloomDialogue`, web `talkBox(kl, name)`, Python `Talk`.
- **The game decides**: `steer(name, "admit you were in the office")`: their next reply does it, even a secret. Trust: `warmth` 0,
  `warm_up` 0.3 a talk, `secret_trust` 0.6. Source (Python `line.source`, others `source(name)`) "offline" with a model set up: late, show silence (`"reply_timeout"` 8 s).
- **Shapes by example**, and the example is the offline answer: `["a", "b"]` one of them; `[0.0, 1.0]` a number in that
  range; `[1, 10]` a whole number; `0.5`, `true`, `"A sample."` that type (shown offline); `[example]` a list; `{...}` an object. Answers are
  validated and clamped: use them as they are, no re-checks (the example is the fallback). `image=` (chat, create): it sees.
- **`say` is instant**: lines written ahead, filled with *your* facts (pass every value raw). Declare each character
  once with `lines` (offline `{fact}` lines per event or `"*"`; `{"dare": {"when": "what is happening", "lines": [...]}}`
  tells the model the moment) and `events` (fact names): lines ready (`prepare()` waits). `event`, `state`: facts.
- **No keyboard**: `suggest(name, [examples], speaker)` -> what the player can pick, one per example (offline: the
  examples). `converse(a, b, about)`: they talk together. `save()`/`load(text)`: the AI in your save file. `inspect()`.
- **`decide` and `act` are instant** every frame (refreshed in the background, `every` s); once, before a level: `create(...)`, ~1-2 s.
- The model, the developer's choice: a key in the environment for `kinloom serve` or the native SDK (`ANTHROPIC_API_KEY`,
  `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY` + `KINLOOM_MODEL`; never in the game) or their agent's plan (`kinloom use`).
  kinloom.json `"rating": "everyone"|"teen"|"mature"`, `"models": {"background": "a-cheaper-model"}`. Before a release:
  `kinloom ship`. Players: `kinloom deploy`, `kinloom bundle` (no Python). `kinloom recipe`, `kinloom add NAME "..."`, `kinloom run --
  <game>`, `kinloom test` (kinloom.tests.json), `kinloom probe NAME`. 34 patterns: `KINLOOM.md`.
- **Minds**: senses, actions, readable `rules` ("hp low"); `think(name, senses, who)` local and instant; `reward` makes
  them learn. **World**: `event(text, by=, seen_by=[...], tag=, impact=)`, `meet`, `knows`, `opinion`, `reputation`.
