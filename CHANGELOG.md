# Changelog

## Unreleased

Found by an audit (2026-10-07) of the core, the server and every SDK, each bug reproduced first:

- Safety: a streamed reply reached the player before the content filter ran (the final reply was filtered, the
  words already shown were not). Every piece is now checked before it is shown, in Python and every SDK.
- Crashes from model output or stored data: a tool name given as a list or object, bonds with bad numbers in a
  loaded save or memory file, notes without a time. One bad note in memory.json no longer costs every learned mind,
  opinion and bond; a file that cannot be read is kept as `memory.json.corrupt-<time>` and told in the journal.
- `say(fresh=True)` could show "None" or raw JSON as a line; it now falls back to the game's lines.
- An object answer with none of the declared fields came back as the example, counted as a model answer. Keys in
  another case and one wrapper object (`{"item": {...}}`) are read; trailing commas are read (the inner object was
  taken before); otherwise the model is asked again.
- `chat()` for characters with tools took up to 10 s past `reply_timeout` (the call that reads what a reply agreed
  to): it now fits in the reply's time.
- Cost caps ignored calls that timed out (their tokens were billed all the same): they now count.
- Unbounded growth on long-running servers: decision, line, pool caches and characters are capped (300 characters
  per session; a full table lets go of characters the game never declared, then of the idlest session). A dropped
  `Kinloom()` (never closed) no longer keeps its threads alive; `with Kinloom() as kl:` closes it.
- Windows: kinloom.json with a byte order mark (PowerShell writes one) stopped the game; the same line spoken from
  two threads raised; the CLI crashed printing non-ASCII names when piped (coding agents pipe it); the MCP server read
  "René" as "RenÃ©". Bad `prices` in kinloom.json are refused in the journal instead of raising later.
- Anthropic streaming lost the HTTP status, so a dead key never switched to the next provider during chats; an
  error event mid-stream counted as an answer. `models: {"background": ...}` now follows a provider switch.
- Server: slow clients could hold every thread (socket timeout, `--max-connections`); the rate-limit table grew
  forever; behind a proxy every player shared one address (`--trust-proxy`); any bind beyond this machine and
  `--allow-origin null` now need a token; a chunked body desynced the connection (411); the admin token is no longer
  accepted in URLs; `GET /healthz`; errors carry a `code`; a refused character says `"stored": false`. A player token
  may no longer read other speakers' conversations through `soul`, create characters with it, or redeclare
  kinloom.json characters; `--player-can none` keeps state, memories, feelings and steering for a shared world's own
  game server. Polling decide/act has its own, larger rate bucket: per-frame polling no longer starves chat.
- `kinloom deploy` writes to its own folder (`kinloom-deploy/`), refuses a bundle or a non-empty folder and never
  writes the admin token to disk; `kinloom ship` flags tokens in files and never overwrites a disclosure you edited.
- Clients through a relay: polling is far less frequent, HTTP 429 is waited out instead of retried every frame, a
  streamed reply waits for its character's declaration, timeouts no longer mark the relay down, the dialogue
  components use one session per install. C#: streamed pieces come back on the calling thread (Unity), a stalled
  stream honors `ChatTimeout`, typed dictionaries (`Dictionary<string,int>`) are sent as objects. Godot web and Unity
  WebGL relays no longer go offline (no raw TCP there). Rust/C++ relay URLs with a path work. Java/Rust/C++ relay
  `say()` no longer blocks the game for a round trip. The web Talk box no longer leaves the microphone on.
- Docs: four `calls.md` snippets did not compile (redeclared names); `python conformance/calls.py` now builds every
  language's section. README counts and claims corrected. Packaging: SPDX license, releases run the tests first.

Found by building and playtesting a Godot demo game (real keyboard and mouse events, real model):

- Godot native: quitting while a model request was open crashed Godot on exit (an HTTP connection freed during
  shutdown). New `await Kinloom.shutdown()` closes open requests, waits for them and saves memory: call it, then
  `get_tree().quit()`.
- Godot `AIDialogue`: after the first message the line kept the focus but left edit mode (Godot 4.4+), so typing
  went nowhere until the player clicked it again. It now stays in edit mode.
- `steer(name, text)`, in Python, every SDK and over HTTP: the game decides what happens in a character's next reply
  ("admit you were in the office at 12:30") and the model says it in their voice, even a secret of their card (used
  once). Written rules in a soul ("break when shown the proof") were followed about half the time; game state is not.
- `warmth` (the feeling for anyone before any talk, default 0), `warm_up` (the most one conversation can win, 0.3) and
  `secret_trust` (the feeling above which a secret may be shared, 0.6), per character and in kinloom.json. With the
  old fixed values a secret could not come out in one conversation.
- `"reply_timeout"` in kinloom.json: how long a spoken reply may take on a hosted model (8 s, was fixed).
- The second look at a reply (what it commits the character to do) is asked again once when the call fails: under a
  slow model an admission was lost.
- Prompts: gestures are written about the character ("taps the table", never "my"), habits show in the gesture and
  are never spoken, and a tool is not used for what a reply only hints at or denies.
- `python conformance/godot_ui.py` (and CI): the Godot addon played with real key events.

Found by a type-to-build demo (long `create` answers) and a ScriptHook game mod (C++ relay), in Python and every SDK:

- An answer cut by the token limit came back as the example with no word: the first complete object inside the cut
  JSON was taken for the answer and every missing field filled from the example. JSON that stops before its end is
  now recognised: the model is asked again with twice the room (at most 4000 tokens), then the example is used and
  counted as an offline answer. `create` gets 1500 tokens (was 800).
- What the model reads was cut with no word: facts, situation, context and state at 1500 characters, `create`'s
  `what` at 200. They are now 4000 and 500, and a cut is written once in the journal (`clipped`, with the size).
- Relay clients sent `character` on its own and the next call could reach the server first: the first reply came
  without the character's soul and tools (no deeds), fixed only on the call after. Calls naming a character now wait
  for its declaration (5 s at most), as the Python remote client already did.

## 1.0.0 (2026-10-03)

First release, in Python and in every SDK (TypeScript/JavaScript, C#, Java, Rust, C++, GDScript, Lua).

- `save()` / `load(text)` (Godot: `save_state()` / `load_state()`): everything Kinloom knows about a player in one
  string for the game's own save slot. Saves loaded with a player token are signed: only an unchanged save from the
  same server loads.
- `suggest(name, examples, speaker)`: reply choices for gamepads, mobile and VR; offline, the examples.
- `converse(a, b, about)`: two characters talk together in one model call; both remember it (offline: no lines).
- `models: {"chat": ..., "background": ...}`: a cheaper model for what players do not wait for.
- `rating: "everyone" | "teen" | "mature"`: a rule line in every prompt.
- `inspect()`: moods, feelings, memories, waiting actions and minds in one call.
- Unity: the `KinloomDialogue` component (`kinloom init` copies it for Unity projects).
- `kinloom ship`: checks a game before release (keys in files, how players reach a model, offline answers, caps,
  rating) and drafts `kinloom-ai-disclosure.md`.
- `python -m kinloom`.
- `kinloom init` writes `AGENTS.md` plus the files of the coding agents found here (installed, or already used by the
  project) instead of every agent's format; `--agents all` writes them all.
- One zip per engine for each GitHub release (`python/release.py`), and CI on Linux, macOS and Windows (Python 3.9
  and 3.12, every SDK's conformance).
- Fixes found by real-model and agent runs: replies follow each example's language; a conversation no longer leaks
  what only one character knew; `Line.text`; `kinloom check` warns about placeholder `"text"` lines.
- Fixes found by differential fuzzing of every SDK against Python: C# `load` of non-JSON, `character` with
  `every: null`, unbounded spoken-line history after `load`, bad `models` / `rating` in `kinloom.json`.

## Before 1.0 (2026-09-27 to 2026-10-03, unreleased)

- Native SDK in every language: each client runs the whole of Kinloom in the game's process (native, relay or
  offline), checked against Python by one scenario, shared vectors and differential fuzzing.
- Ship anywhere: an API key or the coding agent's plan as the model, images, the game's tools, `prepare()`,
  `kinloom test` / `probe`, OpenAPI, `kinloom bundle`.
- Voice both ways (`speak`, `listen`, the system voice with no key), souls (mood, feelings, memories, secrets kept by
  code), minds that learn, a world where rumors spread, the agent-first kit (`kinloom init`, `recipe`, `add`, `run`).
- The legacy C# runtime (Kinloom 1) moved to `legacy/`.
