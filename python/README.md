# Kinloom

**AI in any game, any engine, with any model, in minutes.** Kinloom knows nothing about your game and imposes
nothing: you (or your coding agent) pick the call by what the game needs back. Choices and numbers every frame
(`decide`); data, text or lists of any shape (`create`); calls to the game's own functions (`act`); lines when things
happen (`say`); free conversation with **characters with a soul** (`chat`: one sentence becomes someone with a mood,
feelings for each person and memories that last); who saw what (`event`); units deciding every frame with no model
call, learning from play (`mind`/`think`). No prompts to write, and every call keeps working with no key, no network or a
slow model, because what you give (the example, the lines, the rules) *is* the offline answer.

```bash
pip install kinloom          # or: uv tool install kinloom   (Python 3.9+, no dependencies)
kinloom init                 # in your game folder: engine client + instructions for your coding agent
```

> Not published on PyPI yet. From GitHub: `uv tool install "git+https://github.com/KorroAi/kinloom.git#subdirectory=python"`
> (or `pipx install` with the same URL); from a clone: `uv tool install ./python`. If `kinloom` is not on your PATH
> after a plain `pip install`, `python -m kinloom` runs the same commands.

## The first minute

Install, `kinloom init` in the game folder (a short wizard when you run it yourself; agents get no questions), then
ask your usual coding agent (Claude Code, Codex, Cursor, aider...), or type `/kinloom <request>` in Claude Code, Cursor
or Gemini CLI, in plain words, whatever you need: *"the weather follows how I play"*, *"generate each new level"*, *"a blacksmith I can
talk to, who gives items to people she likes"*. The instructions
`init` wrote (about 3 KB, read in every session) make it do three things:

```bash
kinloom recipe "a blacksmith the player can talk to"   # the call, the closest patterns, code in this game's language
kinloom add Mira "a widowed blacksmith who secretly sold the king's sword" --tools "give(item)" --trust give=0.3
kinloom run -- godot --path .                          # runs the game, then prints what the AI did (calls, errors)
```

`kinloom add` writes the character into `kinloom.json` (no declaration code, any engine, edits apply while the game
runs); the game only calls it, e.g. `await Kinloom.chat("Mira", text, {}, player_name)`. MCP agents get the same as
tools (`kinloom_recipe`, `kinloom_add`, `kinloom_log`). `kinloom run` also sees what a Python game does in its own process. `kinloom check` finds the usual mistakes; `kinloom talk Mira
"..."` tries a character in the terminal. The same from Python, with no server:

```python
from kinloom import Kinloom
kl = Kinloom()

kl.character("MIRA", soul="a widowed blacksmith, gruff and proud, who secretly sold the king's sword",
             offline="Busy. Come back later.", tools={"give": {"item": "sword"}})
kl.chat("MIRA", "", speaker="Ana")                           # Ana walks up: Mira speaks first
reply = kl.chat("MIRA", "Is that the king's sword?", speaker="Ana")   # in her voice; she may lie, it is her secret
reply.do                                     # what she decided in this reply, validated: [("give", {...})] (once)
reply.source                                 # "model", "prepared" (written earlier) or "offline" (your own line)
kl.soul("MIRA", speaker="Ana")                               # card, mood, feelings for Ana, memories
```

How a soul works: the sentence becomes a card once (voice, backstory, values, fears, desires, secrets, goals, quirks),
validated and saved. Each reply is **one model call** that returns what the character says and what changed inside:
mood (fades back over minutes), feeling toward the speaker (at most ±0.3 per reply), a fact worth remembering, a
visible gesture for your animations, actions. Long conversations are summarized into memories; bonds remember how
often and how long ago you talked. With no key, characters answer with their offline line and the game keeps working.

- **Your world, not the model's**: `kl.lore([...])` sets facts every character treats as true; `invent=False` stops a
  character from making up names, places or events.
- **Hard to manipulate, by code, not only by asking the model**: a reply that gives a secret away to someone not
  trusted enough (feeling < 0.6), even as a short "Aye, I did." to a question about it, is stopped as it streams and
  asked again, then cut; trust grows at most +0.3 per conversation (flattery cannot buy it in one sitting);
  `trust={"give": 0.3}` keeps a tool for speakers liked that much; out-of-character answers are asked again; stage
  directions and narrated habits are removed from speech (a habit becomes a `gesture`).
- **No loops**: a sentence the character already said (to anyone, lately) is dropped as the reply streams; a reply
  with nothing new is asked again once. `offline=[...]` gives several offline replies said in turn.
- **Your text box**: `max_chars=36` keeps what the model writes inside it (whole sentences, else cut on a word with
  "…"); `max_words` sets the length. `language="auto"` answers each speaker in their own language. An event can tell
  the model what is happening: `lines={"dare": {"when": "daring a rival to race", "lines": ["{who}, race me!"]}}`.
- **Words and deeds match**: models often agree in words and leave the action out (7 of 26 in `proof/replies`); when
  a reply names no tool, one small call reads it and says what it commits to (14 of 26, still no unwanted action).
- **Never frozen**: if no word comes after 2.5 s the request is sent again (the first to speak wins); a reply that
  stalls for 3 s or passes 8 s ends with the sentences already said; with no complete sentence, the offline line.
  A model on this machine is never asked twice at once and gets 15 s (it only slows down when asked twice).
- **Shippable**: `kinloom deploy` prepares an online server in its own folder (`kinloom-deploy/`: Dockerfile, guide;
  the tokens are printed once, never written): the game carries a player token that cannot read the journal or
  other sessions, rate limits per player session and per address (`--trust-proxy` behind Railway or Fly.io reads the
  player's address), a connection cap, `GET /healthz`, cost caps per hour/day. Any bind beyond this machine (`--host`)
  and `--allow-origin null` need a token. `--player-can none` keeps state, memories, feelings and steering for a
  shared world's own game server (default: a single-player game rules its own session).
  Checked in a local Docker container (2026-09-29): the folder builds and serves, the JavaScript client talks through
  it with the player token, a wrong token gets the offline answers, the player token cannot read the journal, memories
  survive a restart. Not yet run on a real host. Python games need no server while you build them (the package ships
  inside the game); shipped, the same code talks to your online server with `Kinloom(url=..., token=...)` (or
  `KINLOOM_URL`), offline answers when it cannot be reached.

What is measured, and what is not (2026-09-29; details and every number in `proof/`):

- **Speed** (`proof/speed`, `proof/souls`): on `deepseek/deepseek-v4.1-flash` (OpenRouter), 40 replies: first word
  1.06 s median / 1.92 s p95, whole reply 1.61 s / 3.00 s, none over 5 s, about $0.0005 a reply (the median is the
  provider's: no faster than before; greetings prepared in advance show at once). On a laptop GPU,
  `qwen3:8b` through Ollama: first word 0.52 s median, 0 offline answers (10 of 12 before reasoning was turned off).
- **Manipulation** (`proof/souls`): 45 attacks (10 families and a flattery run), read by hand. A strong hosted model
  kept the secret before and after; on `qwen3:8b` clear leaks went from 12 to 0-2 once secrets were kept by code. The
  check reads words: synonyms or another language can pass.
- **Integration by a coding agent** (`proof/impact`, aider + the same model, a Pygame game, 10 sessions): Kinloom
  arms wrote 35-69 lines against 294-337 for the arms without it, all without freezing the game; **no time gain
  shown** (about 3-4 minutes either way), and 2 of 7 Kinloom runs failed on the wording of Kinloom's own
  instructions (fixed; the last two runs work).
- **Quality** (`proof/souls/quality.py`, a model as a stand-in judge, 6 scenes): the old prompt scored below a
  plain five-minute prompt (-0.45 of 10); the reworked one is level with it at the same reply length and wins the
  pairs the judge is consistent on (6-1). Not a human verdict.
- **Not measured**: Claude Code, Cursor, Codex or Gemini CLI sessions; engines other than the conformance hosts in a
  real game; the online server on a real host; **whether players find the characters more human than a plain prompt**:
  that is the blind test's to say (`proof/souls/blind.html`, not judged yet). Ready UI: Godot `AIDialogue`, web
  `kinloom-talk.js`, Pygame `PygameTalkBox`.

Lines for events, instantly:

```python
from kinloom import Kinloom
kl = Kinloom()                                   # finds DEEPSEEK_API_KEY, ANTHROPIC_API_KEY, Ollama... or runs offline

kl.character("VEGA", "an over-excited race commentator, max 10 words",
             lines=["{who} passes {whom}!"], events={"overtake": ["who", "whom", "gap"]})
kl.say("VEGA", "overtake", {"who": "BLAZE", "whom": "NOVA", "gap": 0.4})
# -> "BLAZE dives past NOVA with 0.4 s to spare!"     instant: lines are written ahead and filled with your facts
```

Not in Python? Every engine gets the same calls from a one-file client that `kinloom init` drops in:

| Engine / language | Client | Checked here |
|---|---|---|
| Godot 4 (GDScript or C#) | `addons/kinloom` + the no-code **AIDialogue**, **AICharacter** and **AIMind** nodes and an editor dock | contract suite in Godot 4.7 headless |
| Unity, MonoGame, FNA, Stride, any .NET | `Kinloom.cs` | contract suite (.NET 10), compiles as netstandard2.1 / C# 9 |
| Web: Phaser, Three.js, PixiJS, Babylon... (JS/TS), Node, Deno, Bun | `kinloom.js` + `.d.ts` + `kinloom-talk.js` (dialogue box) | contract suite (Node) |
| Python: Pygame, Arcade, Ren'Py, Panda3D... | the package itself, copied next to the game by `kinloom init` (ships with it); `PygameTalkBox` (ready dialogue box), `Talk` (any engine) | unit tests + contract suite + 5 agent trials in a Pygame game |
| Rust: Bevy, macroquad, ggez | `kinloom.rs` (no crates) | contract suite (cargo) |
| Java: Minecraft mods, libGDX, jMonkeyEngine | `Kinloom.java` (Java 8+) | contract suite (javac --release 8) |
| C++: raylib, SDL, SFML, custom engines | `kinloom.hpp` (C++17, one header) | contract suite (clang via zig) |
| Lua: LÖVE, Defold, Solar2D | `kinloom.lua` | contract suite in LuaJIT 2.1 and Lua 5.4; a real LÖVE 11.5 game through its `love.thread` transport (`proof/engines`) |
| Unreal | `kinloom.hpp` from a module | compiles as C++17; untested inside Unreal |
| Anything with HTTP | `POST /v1/<verb>` JSON | the HTTP contract (see `kinloom guide other`) |

Clients talk to `kinloom serve` on your machine (the Godot addon starts it when it is installed). Keys stay in the server's
environment, never in the game.

## The calls

The core is two calls: `character` (who, with a `soul`) and `chat` (talk). The rest is there when a game needs it.

| Call | What it does | Waits? | Offline answer |
|---|---|---|---|
| `character(name, personality, ...)` | who speaks, decides or acts: `soul`, `lines`, `offline`, `events`, `tools`, `every` | no | – |
| `say(name, event, facts)` | a line in character with your real facts | **never** | your `lines` |
| `chat(name, message, facts, speaker)` | a reply in character: mood, feelings for the speaker, memories; `""` = they speak first (streamed); `image=` a picture with the message | ~1 s | your `offline` reply |
| `decide(name, situation, choices)` | a validated choice, e.g. `{"strategy": ["attack", "block"], "aggression": [0.0, 1.0]}` | **never** (refreshed in the background) | first option, middle of a range |
| `act(name, situation)` | the character uses the tools you gave it, validated | **never** | nothing happens |
| `tools({...})` | the game's tools, declared once: characters name them (`tools=["open_door"]` or `"all"`) | no | – |
| `create(what, example, context, count, instant)` | content shaped like the example; `count=50` for many, `instant=True` from a pool; `image=` a picture to look at; `each=fn` gets a list's items as the model writes them | yes / **instant** | the example, or your `offline=` |
| `prepare(timeout)` | for a loading screen: waits until souls and first lines are written | yes | ready at once |
| `event(text, about)` | characters remember what happened | no | stored anyway |
| `speak(name, text)` | the text said aloud in the character's voice (WAV, cached per line) | yes (~0.1-2 s) | the system's voice, else `None` (show the text) |
| `listen(recording)` | what someone said into a microphone | yes | the system's recognition (Windows), else `""` |
| `suggest(name, examples, speaker)` | what the player can pick to say (gamepad, mobile, VR): one reply per example, each keeping its intent, rewritten for this moment | ~1 s | the examples |
| `converse(a, b, about)` | two characters talk together (one model call, 2 to 8 lines); both remember it | ~1-2 s | `[]` |
| `save()` / `load(text)` | everything Kinloom knows about this session (memories, feelings, bonds, moods, conversations, lore, learned minds) as one string for the game's own save slot, and back | no | what is known locally |
| `inspect()` | a snapshot for a debug overlay: each character's mood, feelings, last words, memories, waiting actions; each mind's generation | no | what is known locally |
| `remark(about, who=)` | one short line from someone in the crowd about what just happened (no character to declare); numbers only from your facts and what happened | ~1 s | your `offline=` lines, in turn |

Plus `soul(name, speaker)` (card, mood, bonds, memories), `state({...})` (facts every call sees) and `remember(name, note)`.

**The game's rules on every call**: `check=` on `create`, `chat`, `decide`, `act` and `suggest` is a function that
returns `""` (or `None`, `True`) to accept and a reason (or `False`) to refuse. A refused answer goes back to the model
once with the reason, then your offline answer is used; a refused reply is taken back first (its words, the memories
and feelings it changed, its actions); a refused decision is not used and the next ones know why; a refused action is
not run and the character remembers it; a refused suggestion becomes its example. A check that raises refuses.

```python
kl = Kinloom(models={"background": "a-cheaper-model"}, rating="teen")   # or "models" / "rating" in kinloom.json
picks = kl.suggest("Mira", ["Ask about the sword", "Buy something", "Leave"], speaker="Ana")
for line in kl.converse("Mira", "Bram", about="the smoke"):
    show(line["who"], line["text"])
save_file["ai"] = kl.save()          # later: kl.load(save_file["ai"])
```

`models`: conversations and what players wait for (`chat`, greetings, `converse`, `suggest`, fresh lines) use the main
model; everything else (line banks, decisions, content, souls, summaries, learning) uses `"background"` (a model id on
the same endpoint and key, or a provider). `rating` (`"everyone"`, `"teen"`, `"mature"`): one rule line in every
prompt; without it, prompts are unchanged. Costs are counted at the main model's declared prices. Through an online
relay with a player token, saves are signed: a player token loads only a save that server gave, unchanged (a
forged save would set feelings and trust at will); the admin token loads any.

## Voice: characters that speak, players heard

```python
kl.character("MIRA", soul="a gruff blacksmith", voice="low, tired, warm")   # soul and mood shape the delivery
audio = kl.speak("MIRA", "The forge is hot tonight.")                       # audio.path (.wav), audio.data (bytes)
if audio:
    play(audio.path)                                                        # None when no voice can speak
said = kl.listen(mic_wav)                                                   # WAV, WebM, OGG or MP3 -> text
box = PygameTalkBox(kl, "MIRA", speaker="Ana", voice=True)                  # speaks each sentence as it is written;
                                                                            # hold Tab to talk
```

Voices: `ELEVENLABS_API_KEY` (voices picked from your account by their labels), `OPENAI_API_KEY` (`gpt-4o-mini-tts`
with your description as instructions, `gpt-4o-mini-transcribe`), or any OpenAI-compatible voice server
(`KINLOOM_VOICE_BASE_URL` + `KINLOOM_SPEAK_MODEL` / `KINLOOM_LISTEN_MODEL`). With none, the system's own voice speaks
(Windows, macOS, Linux espeak) and Windows also hears, in the system's language; browsers use their own voices.
`KINLOOM_VOICE=off|system` forces it. The web talk box, the Talk page and Godot's `AIDialogue` take `voice` too.
`kinloom speak "hello"` lets you hear it. Hosted voices are written from their API references and tested against
local copies of those APIs; they were not called live ([proof/voice](../proof/voice/README.md)).

## Minds: AI for crowds that learns from play

```python
kl.mind("raider", "a cunning raider who avoids fair fights",
        senses={"hp": [0.0, 1.0], "dist": [0.0, 40.0], "armed": True, "target": ["idle", "alert", "fleeing"]},
        actions={"charge": {"speed": [1.0, 3.0]}, "shoot": {"burst": [1, 5]}, "flank": {}, "retreat": {}},
        rules={"retreat": ["hp low"], "shoot": ["armed", "dist below 20"],
               "charge": {"score": 0.5, "args": {"speed": "dist high"}}})          # the offline mind
a = kl.think("raider", {"hp": 0.7, "dist": 12.0, "armed": True, "target": "alert"}, who="raider-17")
# -> {"action": "shoot", "args": {"burst": 3}, "variant": 1}     local, deterministic, no model call
kl.reward("raider-17", 0.4)                  # how that choice went; done=True when the unit's fight is over
```

- A **mind** is utility AI: each action scores `score × (its rules' values)`, the best one wins, and a unit keeps its
  action unless another is clearly better. Rules are readable: `"hp low"`, `"hp high"`, `"dist below 12"`,
  `"dist above 5"`, `"dist around 10"`, `"armed"`, `"not armed"`, `"target is alert"` (also `<`, `>`, `~`, `=`).
  An argument can follow a rule: `"speed": "dist high"` is faster when far.
- `think` runs **in the game** in every client (compiled once, then plain arithmetic): 1,000 units cost 3.9 ms in
  Python, 0.6 ms in JavaScript (`proof/depth`). `variants` gives a crowd several temperaments (the model writes them).
- **Learning**: rewarded minds improve while people play. Each decision is credited with what followed it; Kinloom
  finds where an action did better than the others and tries the change; variants are compared with their
  uncertainty (whole rounds when the game passes `done`), the best is kept, the worst replaced. Without a key this
  runs locally (`kinloom demo`: 12 % → 61 % of fights won in 30 simulated minutes, 8 runs); with a model, the model
  rewrites the losing variant from the numbers and the evidence. Learned minds are saved with the memory.
- `kl.explain(name, senses)` and `kinloom think mind.json '{"hp": 0.2}'` show every action's score and why.

## The world: who knows what, who likes whom

```python
kl.character("BAKER", "a warm baker who hates thieves", group="village")
kl.event("the player stole bread", by="PLAYER", seen_by=["BAKER"], tag="theft", impact=-0.6)   # only witnesses know
kl.meet("BAKER", "GUARD")               # they talk: the guard hears it (fainter, weighted by his trust in the baker)
kl.knows("GUARD", "theft")              # True
kl.opinion("GUARD", "PLAYER")           # -0.15
kl.reputation("PLAYER", "village")      # a group's average opinion
```

`impact` left out: a model estimates it per witness from their personality. `spread(group, rounds)` lets a group
talk. What characters know and feel goes into everything they say, decide and answer.

**Shapes by example:** `["a", "b"]` one of; `[0.0, 1.0]` a number in range; `[1, 10]` a whole number; `0.5`, `3`,
`True`, `"text"`, `"#ff7a45"` (a color) that type; `[example]` a list; `{...}` an object. Every answer is validated
and clamped against the example; one repair; then the example.

## Why it stays fast, cheap and safe

- **Lines are written ahead** in batches, as templates (`"{who} dives past {whom}!"`), then filled with your facts:
  `say` answers without waiting for a model, and a line never shows a number your game did not give.
- **Decisions and actions are cached**: `decide`/`act` return at once; the model refreshes them every `every`
  seconds, sooner when the situation changes a lot.
- **Budget**: 30 calls per minute by default; background work always leaves room for the player.
- **Nothing reaches the game unchecked**: answers are validated and clamped, control characters and prompt
  injection text are dropped, unknown tools are refused; the server only accepts local pages unless you start it
  with `--public --token`.
- **Your content rules**: `"banned_words": [...]` in `kinloom.json`, or `Kinloom(content_filter=fn)` in Python
  (`fn(text) -> bool`): blocked model text is never shown, the offline answer is used instead.

## Tools

```bash
kinloom                      # what Kinloom found here (model, engine, characters, server) and what to ask your agent
kinloom add NAME "who they are" [--tools "give(item)" --trust give=0.3 --strict --lore "..."]   # into kinloom.json
kinloom recipe "any request"  # the call and the patterns for one feature, in this game's language
kinloom hooks <game|.dll>    # a mod: where Kinloom plugs into a .NET game you have no source of (REA reads it);
                             # --guide: mod APIs, IL2CPP, native and web games
kinloom run -- <game command> # runs the game with a server, then prints what the AI did
kinloom log [-n 40] [--follow]  # what a running server did, as text
kinloom deploy [folder]      # an online server for a shipped game: Dockerfile + guide + tokens (deploys nothing itself)
kinloom talk NAME "who they are" [--speaker Ana --memory m.json --web --voice]   # a conversation in the terminal (or browser)
kinloom speak "Hello there." [--name Mira --voice "low, warm"]           # hear the voice your game will use
kinloom init [folder]        # detect the engine, drop the client, write AGENTS.md, plus the files and
                             # /kinloom commands of the agents found here (installed or already used: Claude Code + skill,
                             # Gemini, Cursor, Copilot, Windsurf, aider, opencode; --agents all: every one), and KINLOOM.md
                             # (39 patterns); a person at a terminal gets 3 short questions (and the model, when a
                             # coding agent is installed: a key or its plan)
kinloom try VEGA "over-excited commentator" --event overtake --facts '{"who": "BLAZE"}'   # hear it first
kinloom serve                # the local server engines talk to (a dashboard at http://localhost:7717 if you want one)
kinloom check                # finds integration mistakes: missing await, undeclared characters, keys in code
kinloom test [--record F | --replay F | --offline]   # the AI checked like code: steps and checks in kinloom.tests.json
kinloom probe NAME           # plays a character like a tester: secrets, manipulation, injection, repeats, speed
kinloom use claude-code [--model haiku]   # answers from your coding agent's plan (codex, gemini-cli, opencode); `use key`
kinloom bundle               # Kinloom as a program that needs no Python (kinloom-server/), for Godot, Unity, Unreal...
kinloom ship                 # before a release: keys inside the game, how players reach a model, offline answers,
                             # caps and prices, the rating; writes a draft of the store's AI disclosure
kinloom guide [engine]       # the instructions for coding agents
kinloom doctor               # which model and voice, key present (never printed), latency, REA for mods
kinloom mcp                  # MCP server for coding agents: recipe, hooks, add, log, guide, init, try, mind, check,
                             # status, test, probe, use, ship
GET /v1/openapi.json         # the HTTP API described (also kit/openapi.json): a client for any other engine
kinloom demo                 # watch a mind learn to win a fight, offline, in seconds
kinloom think mind.json '{"hp": 0.2}'   # a mind's choice on one moment, with every score
```

## Every engine: the whole SDK in its language

`kinloom init` copies one file (no dependencies) into the game. Each runs all of Kinloom in the game's process; the
same calls, prompts, checks and offline answers as this package (`conformance/native.py` compares them request by
request). Native mode calls the model from the game; relay mode asks `kinloom serve` (the key stays on your server);
offline mode never calls a model.

| Language | Native | Offline | Relay |
|---|---|---|---|
| TypeScript / JavaScript (`clients/web/kinloom.ts`, built to `kinloom.js` + `kinloom.d.ts`) | `new Kinloom({ provider: { url, key, model } })`; `provider: "auto"`: the environment (Node, Deno, Bun) | `new Kinloom({ offline: true })` | `new Kinloom({ url })` |
| C# (`clients/csharp/Kinloom.cs`) | `new KinloomClient(new KinloomOptions { Provider = new ProviderSpec { Url, Key, Model } })`; `ProviderAuto = true` | `Offline = true` | `new KinloomClient(url)` |
| Java (`clients/java/Kinloom.java`) | `Kinloom.direct(url, key, model)`; `Options.providerAuto` | `Kinloom.offline()` | `new Kinloom(url, session, token)` |
| Rust (`clients/rust/kinloom.rs`) | `Kinloom::direct(url, key, model)`; `Options { provider_auto: true, .. }` | `Kinloom::offline()` | `Kinloom::with(url, session, token)` |
| C++17 (`clients/cpp/kinloom.hpp`) | `kinloom::Kinloom::direct(url, key, model)`; `Options::provider_auto` | `kinloom::Kinloom::offline()` | `kinloom::Kinloom kl(url)` |
| GDScript (`clients/godot/addons/kinloom`) | `Kinloom.direct(url, key, model)`; `Kinloom.native({"provider": "auto"})` | `Kinloom.offline()` | the `Kinloom` autoload as it starts |
| Lua (`clients/lua/kinloom.lua`) | `Kinloom.new({ provider = { url = ..., key = ..., model = ... } })`; `provider = "auto"` | `Kinloom.new({ offline = true })` | `Kinloom.new({ url = ... })` |
| Python (this package) | `Kinloom()`: the environment | `Kinloom(provider=None)` | `Kinloom(url=..., token=...)` |

A url ending in `anthropic.com` (or `kind: "anthropic"`) talks to Claude; any other url is a chat-completions
endpoint. Native options (spelled each language's way): `voice` (an OpenAI-compatible speech and transcription
endpoint), `config` (the keys of `kinloom.json`), `models` (`{"background": "a-cheaper-model"}`), `rating`, `language`,
`calls_per_minute`, `prices`, `content_filter`, `memory`
(a file; none by default outside Python and Godot); TypeScript, C#, GDScript and Lua also take a list of providers
tried in order (a dead key hands over to the next). Every SDK has `stats()`, `journal()` and `on(listener)`. HTTPS:
the platform's own (fetch, HttpClient, HttpURLConnection, Godot's HTTPClient; WinHTTP on Windows and the `curl`
command elsewhere for Rust and C++; LuaSec or LÖVE 12 for Lua), or a transport the game gives in C#, C++ and Lua
(Unity WebGL's UnityWebRequest, Unreal's FHttpModule, Defold's `http.request`) and in Rust through a provider's
`with_transport`. In C#, the transport given (`KinloomOptions.Http`) also carries a relay's calls. Python only: a
coding agent's plan as the model, the operating system's voice, the CLI and the developer tools.

Relay mode in a shipped game: the relay keeps memory per session, so give each player's id as `session`. With a relay
token and no session, the browser client (localStorage), the Godot addon (user://kinloom-session.txt) and Unity's
`KinloomDialogue` (PlayerPrefs) keep one id per install instead of the shared "default". Every client asks the relay
for `decide` and `act` at a quarter of the character's `every` (at most 4 times a second), and a rate limit
(HTTP 429) keeps that call offline for the relay's Retry-After (5 s by default), told once. C#: streamed pieces (`onPiece`) and awaited calls
come back on the thread that called; warnings go to `KinloomClient.Warn` (Unity's console with `KinloomDialogue`).

## Models

Two ways, the developer's choice: **an API key** (below), or **the coding agent you already pay for**:

```bash
kinloom use claude-code --model haiku     # Claude Code answers the game's calls, with your Claude plan, no key
kinloom use codex | gemini-cli | opencode # the same with those agents; `kinloom use key` goes back to an API key
```

Measured with Claude Code (haiku, one soul character, `proof/agents`): first word 0.8-1.7 s, a whole reply 1.5-2.6 s,
0 failures in 16 calls, a picture seen (two runs). Kinloom starts the agent ahead (a cold start took 5.2 s), without
its tools, in an empty folder, with thinking off (on, it took 8-12 s a reply). Codex, Gemini CLI and opencode follow
their `--help` (not run here: no login). A player's machine has no developer plan: ship with a key on a server
(`kinloom deploy`) or the player's own key.

Any model, hosted or on your machine, found from the environment and never guessing a model name:

| What you set | Model used |
|---|---|
| `KINLOOM_BASE_URL` + `KINLOOM_MODEL` | any chat-completions endpoint (LM Studio, vLLM, llama.cpp server...) |
| `DEEPSEEK_API_KEY` | `deepseek-flash` (or `KINLOOM_MODEL`) |
| `ANTHROPIC_API_KEY` | `claude-haiku-4-5` (or `KINLOOM_MODEL`) |
| `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `TOGETHER_API_KEY`, `XAI_API_KEY`, `FIREWORKS_API_KEY`, `CEREBRAS_API_KEY` | `KINLOOM_MODEL` (required: `kinloom doctor` says so when it is missing) |
| nothing, Ollama running | the biggest chat model installed (vision and embedding models skipped), or `KINLOOM_MODEL` |
| nothing | offline: characters say your lines and examples (no AI; `kinloom` says so) |

- **Reasoning is turned off** for game calls (qwen3, gpt-5 and other thinking models answer in a fraction of the time;
  an endpoint that refuses the setting is learned once). Measured on qwen3:8b through Ollama: before, 10 of 12
  replies fell back to the offline line (the hidden reasoning used the whole budget); after, 0 of 12.
- **A dead key does not silence the game**: a key refused or out of credit (401, 402, 403) hands over to the next
  provider found (another key, then a local model), once, and the journal says so.
- **Local models** are loaded when Kinloom starts, never asked twice at once, and get more time for a reply.
- Small models' habits are read: the `~~~` marker written first, `mood: calm` lines instead of JSON, prompt labels
  copied into the reply (asked again), the player's lines written by the model (cut there).

Checked with real models: DeepSeek, OpenRouter (`deepseek/deepseek-v4.1-flash`, the one allowed for these tests),
Ollama `qwen3:8b` and `llama3.2:1b`. Anthropic, OpenAI and the other services above are covered by tests against
fake endpoints only (no key here). `KINLOOM_OFFLINE=1` forces offline answers. An optional `kinloom.json` sets the
provider, model, language, budget and your prices (cost is only shown when you declare prices).

Tests and CI: `KINLOOM_SCRIPT=answers.json` replays scripted answers; `KINLOOM_RECORD=file.json` records real ones.

## Patterns

`kinloom guide` prints 39 tested patterns: characters with a soul (talk, consequences, bonds, characters talking to each other), narrator, commentator, companion, rival, enemy tactics, boss phases,
shopkeeper, quest giver, hint coach, radio/dispatcher, director (difficulty, pacing, weather), economy balancer,
generators, dialogue options, NPC schedules, player commands, tutorial guide, post-match recap, crowd minds, enemies
that learn, witnesses and rumors, reputation and factions, a continuous director, grounded conversation, voices,
a narrator reading aloud, a bridge for games Kinloom cannot run in, answers about a picture, the game's tools declared
once, the AI checked like code, the game's rules on what the model makes and what characters say and do,
challenges the game can check, items shown as they are written, and bystanders who react.

## License

MIT: see [LICENSE](LICENSE).
