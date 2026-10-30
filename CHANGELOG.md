# Changelog

## 1.0.0 (2026-10-30)

First public release: `pip install kinloom`, and one zip per engine on each GitHub release. What changed since
the 1.0 features were settled (2026-10-03, below):

Found by the launch review (2026-10-28):

- `kinloom init` wrote the description of the Claude Code skill, the Claude Code `/kinloom` command and the opencode
  command as unquoted YAML holding ": ", which is not valid YAML: depending on the agent, the description was lost or
  the file refused. Descriptions are now quoted; a test parses every header `init` writes (and the Gemini command as
  TOML).
- An action whose arguments left out an option or a range was run with the example's value: a reply that agreed to
  "a sale" without naming the item sold the first item of the list (found with `examples/web`). In Python and every
  SDK, a tool argument that is a choice (options or a range) must now be given; otherwise the action is refused and
  the journal says `sell: missing item`. Single example values still fill in. Shared vectors: `missing_choices`.
- Through a relay that cannot be reached, a character with several offline replies picked one at random, so the same
  line could come twice in a row (seen in `examples/web`). Relay clients (JavaScript/TypeScript, C#, Java, Rust, C++,
  Lua, Godot) now say them in turn, as native mode and the documentation do.
- A spoken reply whose call ended in error after it had already streamed words (the provider's own timeout
  falling with the reply's deadline, seen on a slow macOS CI runner) gave the offline line and lost what was said.
  In Python and every SDK with streaming (JavaScript/TypeScript, C#, Java, Rust, C++, Godot), the words said in
  time are now the reply, cut at a sentence, as for a stall.
- The Codex harness (`kinloom use codex`) now passes `-` so Codex reads the prompt from stdin, the form its
  documentation gives.
- CI runs Python 3.9, 3.12 and 3.14 on Linux, macOS and Windows, with current GitHub Actions; issue and pull request
  templates and a code of conduct.
- Legacy C# runtime: `KINLOOM_THINKING=off` turns a reasoning model's thinking off on a `custom` endpoint
  (OpenRouter takes `reasoning.enabled=false`, DeepSeek `thinking.type=disabled`); without it, a reasoning model on
  OpenRouter could spend the whole token budget thinking and answer nothing.

Mods of games with no source (2026-10-11):

- `kinloom hooks <game folder | .dll>`: where Kinloom plugs into a .NET game you do not have the source of (Unity
  Mono's `Assembly-CSharp.dll`, MonoGame, FNA, any .NET game). It reads the game's code with REA (Reverse Engineer
  Anything, optional, MIT: `rea` on PATH or `KINLOOM_REA`), never runs the game, and lists the methods that make a line,
  a reply, a choice or content, best first, with the call that fits (`say`, `chat`, `decide`, `create`) and a Harmony
  patch that keeps the game's own text when Kinloom has nothing (offline, no line ready); nested types are
  marked, methods of open generic types left out (Harmony patches concrete methods). `--json`; Unity IL2CPP and
  native games get what to do instead. `kinloom hooks --guide` (the new `kit/mod.md`): mod APIs, .NET, IL2CPP, native
  and web games. Also the MCP tool `kinloom_hooks`, a `mod` route in `kinloom recipe`, and a line in `kinloom doctor`.
  Kinloom needs REA for nothing else. Proof: `proof/mod` (a small .NET game, a Harmony mod built from the patches,
  offline, scripted and with a real model).

Found by that proof, in Python and every SDK:

- Through a relay, `character(...)` then `prepare()` could reach the server in the wrong order (a declaration is sent
  in the background): the server answered "ready" before it knew the characters, so nothing was written ahead and the
  first lines were the offline ones. Seen with a real model (only the reply came from it). `prepare`, `save` and
  `inspect`, which are about every character, now wait (5 s at most) for every declaration still on its way, as calls
  naming one character already waited for theirs (Python `Kinloom(url=)`, JavaScript/TypeScript, C#, Java, Rust, C++,
  Lua, Godot). C++ waited up to 5 s per declaration instead of 5 s in all. The relay conformance runs every client
  through `conformance/slowproxy.py`, which holds each declaration 0.3 s and fails a client whose `prepare`, `save`
  or `inspect` overtakes one: before the fix it failed JavaScript, TypeScript, C#, Java, Rust, C++ and Godot (Lua's
  test transport answers at once, so the order cannot change there; Python is checked by `tests/test_remote.py`).
- `kinloom serve` printed a `ConnectionResetError` traceback for each connection a game left open when it quit.
- The MCP `kinloom_guide` said there were 34 patterns (there are 39): the number is now counted.

Found by a release review (2026-10-13):

- On Windows, a command whose output was cut by its reader (`kinloom init | head`) ended with an
  `OSError: [Errno 22] Invalid argument` traceback: Windows reports the closed pipe as EINVAL, not as a broken pipe.
  It now ends quietly (exit 1), as on Linux and macOS.
- `kinloom think` with a mind file that does not exist ended with a traceback, and a moment that is not a JSON object
  (`[1, 2]`) was scored as if every sense were missing: both are now a clear error (exit 2).
- `--port` out of range (`kinloom serve --port 99999`) ended with a bind traceback: argparse now says it is not a port.
- On Windows, `kinloom init > NUL` started the questions of the wizard that nobody could see (Python calls the NUL
  device a terminal): the wizard now runs only in a real console.
- The package's README (its PyPI page) has absolute links. The Godot addon's install hints say the same. `pyproject.toml` and the clients'
  manifests (npm, UPM, NuGet, Cargo, LuaRocks) name the repository.

Found by a release review (2026-10-10):

- C#: an anonymous object as `Create`'s example or offline answer (`new { name = "Glowcap", value = new[] { 1, 50 } }`)
  threw "unsupported example", and with `count` it silently became its text (`["{ name = Glowcap, value =
  System.Int32[] }", ...]`). It is now the object it reads as, everywhere a value becomes JSON. A Unity IL2CPP build
  with managed stripping "High" removes what only reflection reads: there an anonymous object fails with a clear error
  (write a `Dictionary<string, object>`) instead of going out empty. The docs show dictionaries (`Obj`), which work
  in every build.
- C#, Java, TypeScript/JavaScript: `create` with `count` never checked its example, so an example with no shape (`{}`,
  `[]`, an object of an unsupported type) gave a list of copies of it instead of the error it gives without `count`
  (and in Python). It now fails at once in both cases.
- Rust: `set_say_wait_ms(ms)`, how long a relay `say()` waits for the server before answering from the game's own
  lines (30 ms by default), as C++ (`say_wait_ms`) and Java (`sayWaitMs`) already had. The conformance scenarios give
  it 2 s. The C++ relay run once failed on `say source` on a busy machine: a line fetched ahead in the background
  timed out (2 s), so the next `say` found nothing ready and answered offline after 30 ms. Reproduced with a proxy
  that holds that one answer 2.5 s and later ones 100 ms: `say source: offline` with 30 ms, the whole scenario passes
  with 2 s (CPU load alone did not trigger it in 8 runs).
- Lua relay clients wrote JSON without the SDK's markers: `Kinloom.null` was sent as `{}`, `Kinloom.ordered` lost its
  order (keys went alphabetical) and an empty list could not be sent at all. They now send `null`, keep the order, and
  `Kinloom.array()` (new) is a list even when empty, in both modes (native mode already honored the first two).
- C#: numbers past a double (`1e400`) are read as Python and .NET Core read them (an infinity, or zero when too
  small). Unity's Mono refused them: a model answer holding one was unreadable, and a mind rule with one gave another
  error than in every other SDK. Found by running the SDK in the Unity editor (`proof/engines/unity`); four new shared
  vectors (544) check it in every SDK.
- Unity: the C# SDK now runs in the Unity 6000.3 and 6000.6 editors in every check (`proof/engines/unity/run.py`):
  the conformance scenario through a relay and in native mode, `KinloomDialogue` in play mode, and a Windows player
  built with IL2CPP (managed stripping "Low" and "High") running the scenario in both modes.
- Memory recall, in Python and every SDK: among notes of equal score the newest are kept now, in the order they were
  written. Notes of the same instant are common (Python's clock on Windows before 3.13 ticks every 15.6 ms): a burst of
  eight lines recalled the oldest six and forgot the two latest. It was also the LuaJIT conformance run that failed
  about once in 30: which notes shared an instant changed from run to run, so the chat prompt's memory differed from
  Python's (caught by the failure log below). Three new shared vectors (547) check notes of one instant.
- `kinloom ship` failed on Windows when the game is on another drive than the current folder (`ValueError: path is
  on mount 'C:', start on mount 'D:'`): found by the first CI run, whose checkout is on D:. Paths are shown whole then.
- Conformance: a client that does not build is reported as a failure with the compiler's own message, and the other
  clients still run (the C++ build error was hidden).
- Conformance: every failure report of `run.py` and `native.py` is also appended to
  `<temp>/kinloom-conformance-failures.log`, so a flaky run leaves its reason even when the output was filtered.
- `kinloom ... | head` no longer ends in a `BrokenPipeError` traceback when the reader leaves early (exit 1, quietly).
- Every engine's brief (the instructions agents read each session) is now under 6250 characters, so `AGENTS.md` stays
  under 6300 in every engine (Unity's was 8198, Godot's 7572): C# examples use two aliases (`Obj` for
  `Dictionary<string, object>`, `Arr` for `List<object>`), comments are no longer aligned with spaces, and engine
  notes needed now and then (WebGL, bundles, node options) moved to `KINLOOM.md`. Every call is still shown once in
  every language.

Learned from the demo games (The Plot, the Isaac mod), in Python and every SDK:

- `create(..., check=, offline=)`: the game's rules in the loop. `check(answer)` returns nothing to accept the answer
  or why it breaks a rule (no room, too expensive, an unknown name); the model hears the reason once, then the game's
  own `offline` answer (checked against the example's shape) is used. With `count`/`instant`, refused items are
  replaced. With a real model, ten building requests on a crowded plot: 3/10 plans fit the rules without it, 10/10
  with it, all written by the model, 17 calls instead of 10 (`proof/rules`).
- `/v1/create` answers `"source": "model"|"offline"` and takes `"offline"` and `"refused": {"answer", "why"}`: relay
  clients run the check in the game. Game refusals show in the journal as `refused`.
- Cookbook: 35 (the game's rules decide what the model may make), 36 (challenges the game can check: the model picks
  the goal among the game's own); `kinloom recipe` routes such requests to them.

Then four more, in Python and every SDK (conformance native and relay, vectors 540):

- `create(..., each=fn)`: the items of a list answer reach the game as the model writes them (native SDKs and Python
  read the model's stream; `/v1/create` with `"stream": true` sends them as server-sent events `{"item"}` then
  `{"done", "value", "source"}`; relay clients hand them over when the answer is complete). With `check=`, refused
  items are left out; with `count`, the list is filled with the offline answer.
- `check=` on `chat`, `decide`, `act` and `suggest`. A refused reply is taken back (its words, the memory of it and the
  actions it decided), asked again once with the reason, then the offline reply is used (`/v1/chat` takes
  `"refused": {"answer", "why"}` and `"drop": true`). A refused decision is not used (the last accepted one is, else the
  default) and the next decisions see why; a refused action is not returned and the character remembers it; a refused
  suggestion is replaced by its example.
- `remark(about, who=, facts=, offline=, max_chars=)` (`/v1/remark`): one short line from someone in the crowd, no
  character to declare. Numbers only from the facts and what happened, the content filter, 20 words at most; offline, the game's lines in
  turn.
- Long `context`, `facts`, `situation` and `state` keep every key in its order: the last values are shortened first,
  then replaced by "(cut)" (before, the JSON was cut in the middle, losing whatever came last).
- Cookbook 37 (items as they are written), 38 (bystanders who react), 39 (the game's rules on what characters say,
  decide and do); `kinloom recipe` routes for them.
- Fixed (found with a real model, `proof/triple`): a list example without `count` often came back as the offline
  answer. In JSON mode the model wraps the list in an object (`{"list": [...]}`) or answers one item alone; both are
  now read as the list (two lists in one object stay an error). In the same runs, `chat(..., check=)` took a rule the model
  broke in 4 of 6 replies to 0 of 6, every reply still the model's.

Then an audit of the new calls (three reviews: the core and server, four SDKs, three SDKs and the docs), each bug
reproduced, fixed in Python and every SDK:

- A refused chat reply now also takes back what it changed inside: the feeling it moved (and the warm-up it used), its
  mood, its gesture and the memories it wrote (before, a refused "the password is swordfish" stayed in memory).
- Items stop when `create` returns: a call given up on (timed out) kept streaming into `each`, and the returned list
  kept growing. In C++ that stream also ran on a destroyed brain and the game's dangling references (use after free).
- A `check` that raises (or panics) now refuses the answer, on every call and path, and is journaled; an `each` or
  `on_piece` that raises is told and never breaks the call (it made `create` answer offline, or `act` drop actions).
- C#: `check`, `each` and `onPiece` run on the caller's context (Unity: the main thread), as the rest of the SDK.
- Long contexts are clipped in linear time (8000 keys: 74 s before, 0.3 s now; a 1 MB request could take minutes).
- A wrapped list is read as its first list, the same rule items stream by; a refused reply takes back only its own
  actions, never an equal one still waiting from an earlier reply (Godot, Rust, C++, Lua); a non-object situation keeps
  the refusal note (Lua crashed); decide-check, remark and take-back tables are bounded; relay `remark` names the
  speaker and sizes the box as the brain does; `/v1/remark` counts as model work for the rate limit; a refused reply
  that decided nothing no longer takes back an earlier reply's actions over a relay; an older server's whole answer is
  read when `create(each=)` asked for a stream.

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

### The 1.0 features (2026-10-03)

In Python and in every SDK (TypeScript/JavaScript, C#, Java, Rust, C++, GDScript, Lua).

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
