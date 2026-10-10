# Kinloom

**Free, open-source AI for games. Any engine, any model, and it keeps working with no model at all.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Version 1.0.0](https://img.shields.io/badge/version-1.0.0-informational)
![SDKs](https://img.shields.io/badge/SDKs-C%23%20%7C%20GDScript%20%7C%20TS%2FJS%20%7C%20C%2B%2B%20%7C%20Rust%20%7C%20Java%20%7C%20Lua%20%7C%20Python-555)

Kinloom adds AI to your game: characters players can really talk to, decisions made every frame, content generated
in the shape you need, and actions taken through your game's own functions. You describe each answer **by giving an
example**. Kinloom asks the model, checks the answer against your example, and hands your game only what passes.
With no key, no network or a slow model, **your example is the answer**, so the game never stalls or breaks.

[Quick start](#quick-start) · [The calls](#what-your-game-can-ask-for) · [Engines](#every-engine-in-its-own-language) ·
[Models](#any-model) · [Shipping](#shipping-to-players) · [Measured](#measured-not-promised) · [Docs](#documentation)

## Why Kinloom

- **It never breaks your game.** Every call has an answer that needs no model: the example, the lines, the rules
  you wrote. A missing key, a dead network or a slow model changes the quality of the answers, never whether the game
  runs.
- **The model proposes, your game decides.** Answers are validated against your example's shape, numbers are kept in
  their ranges, unknown tools are refused, and your content rules apply before anything reaches the screen.
- **Native in your engine.** One file per language, no dependencies, the whole SDK inside your game's process:
  C#, GDScript, TypeScript/JavaScript, C++17, Rust, Java, Lua and Python, with the same calls and the same behavior.
- **Any model.** Claude, OpenAI, DeepSeek, OpenRouter, Groq, Gemini, Mistral, any OpenAI-compatible endpoint,
  or a model on your own machine (Ollama, LM Studio). During development, your coding agent's plan can answer instead
  of an API key.
- **Characters with a soul.** One sentence becomes someone with a mood, feelings for each person they meet, memories
  that last and secrets that are kept by code, not only by the prompt.
- **Ready to ship.** A relay keeps your key off players' machines, with player tokens, rate limits and spending caps.
  `kinloom ship` checks your build and drafts the store's AI disclosure.
- **Your coding agent does the wiring.** `kinloom init` installs the client and writes the instructions in `AGENTS.md`,
  plus the files of the coding agents it finds (Claude Code, Gemini CLI, Cursor, Copilot, Windsurf, opencode, aider).
  Then you ask in plain words.

## At a glance

TypeScript shown; every SDK has the same calls ([all languages](python/src/kinloom/kit/calls.md)).

```ts
import { Kinloom } from "./kinloom.js";

const kl = new Kinloom({ provider: { url, key, model } });   // or { offline: true }, or { url: "https://your-relay" }

// A value every frame: instant, refreshed in the background. The example is the shape and the offline answer.
const sky = kl.decide("WEATHER", { season: "winter", day: 12 }, { sky: ["sun", "snow"], wind: [0.0, 1.0] });

// Content of any shape, about 1-2 s.
const item = await kl.create("an item found in a cave", { name: "Glowcap", value: [1, 50], story: "Found under a cold stone." });

// A character to talk to, who can act through your game's functions.
kl.character("MIRA", "", {
  soul: "a widowed blacksmith, gruff and proud, who secretly sold the king's sword",
  offline: "Busy. Come back later.",
  tools: { give: { item: "sword" } },
});
const reply = await kl.chat("MIRA", playerText, { gold: 3 }, "Ana");   // in character, about 1 s, can stream
for (const a of kl.act("MIRA", {}, false)) run(a.tool, a.args);         // what she decided to do, validated
```

## What your game can ask for

Kinloom knows nothing about your game and imposes nothing: you pick the call by what the game needs back.

| Your game needs | Call | How it answers |
|---|---|---|
| A choice or numbers, every frame | `decide` | instantly, from a cached answer refreshed in the background |
| Data, text or lists of any shape | `create` | in about 1-2 s, or instantly from a pool written ahead |
| Items shown as they are written | `create(..., each=)` | each item of a list as soon as the model writes it |
| Your rules on what the model makes, says and does | `check=` on `create`, `chat`, `decide`, `act`, `suggest` | refused: fixed once with your reason, then your offline answer |
| A line from a passer-by, no character to declare | `remark` | one short line in that voice; offline, your lines in turn |
| The AI to use your game's functions | `tools`, `act` | validated calls only, with arguments of the declared shape |
| A line when something happens | `say` | instantly: lines written ahead, filled with your facts only |
| Free conversation with a character | `chat`, `speak`, `listen` | about 1 s, streamed; voice both ways, the system voice with no key |
| Reply choices for gamepads, mobile, VR | `suggest` | one reply per example; offline, the examples |
| Two characters talking together | `converse` | one model call; both remember it |
| Who saw what, rumors, opinions | `event`, `meet`, `knows`, `opinion`, `reputation` | locally: witnesses, trust and decay |
| Many units deciding every frame | `mind`, `think`, `reward` | rules run locally with no model call; the model rewrites them as they learn |
| Saves and debugging | `save` / `load`, `inspect` | the AI's whole state as one string; moods, feelings and memories at a glance |

## Every engine, in its own language

| Engine or runtime | Kinloom file | Ready-made dialogue |
|---|---|---|
| Unity, Godot C#, MonoGame, Stride, any .NET | `Kinloom.cs` (netstandard2.1) | `KinloomDialogue` component (Unity) |
| Godot 4 | addon (GDScript) | `AIDialogue`, `AICharacter`, `AIMind` nodes |
| Browsers, Node, Deno, Bun | `kinloom.ts` / `kinloom.js` | `kinloom-talk.js` dialogue box |
| Pygame, Arcade, Ren'Py, any Python | the `kinloom` package | `PygameTalkBox`, `Talk` |
| Bevy, macroquad, ggez | `kinloom.rs` | |
| libGDX, Android, any JVM 8+ | `Kinloom.java` | |
| raylib, SDL, SFML, Unreal through a wrapper, custom engines | `kinloom.hpp` (C++17, one header) | |
| LÖVE, Defold, Solar2D, LuaJIT, Lua 5.1-5.4 | `kinloom.lua` | |
| Anything that speaks HTTP | `kinloom serve` + [OpenAPI](python/src/kinloom/kit/openapi.json) | |

Each SDK runs in one of three modes, with the same calls:

| Mode | The model is called | Use it for |
|---|---|---|
| native | from the game, with a key | development, or games where each player brings a key |
| relay | by `kinloom serve` on your server | shipped games: the key never reaches players |
| offline | never | no network, tests, or a game that only uses your own lines |

Every SDK is checked against the Python reference: the same scenario gives the same transcript, the requests sent to
the model match word for word, and the shared test vectors (`python/conformance/vectors.json`) give the same results.

What each platform needs:

- **Browsers** (JavaScript, Godot web exports, Unity WebGL): only HTTP(S) to a relay, or to a model with the player's
  own key. Unity WebGL has no `HttpClient`: pass `KinloomOptions { Http = ... }` (a `UnityWebRequest` wrapper).
- **LÖVE 11** has no HTTPS: hosted models and an HTTPS relay need LuaSec or LÖVE 12; a plain-HTTP relay works.
  Other Lua engines pass their own `transport` (Defold's `http.request`, for example).
- **Rust and C++** reach HTTPS through WinHTTP on Windows and the `curl` command elsewhere. Consoles and mobile have
  neither: give native mode your own transport, or use a relay reached by your engine's HTTP.
- **Consoles** in general: no SDK here has been run on one; plan for your platform's own HTTP layer.

## Quick start

```bash
uv tool install "git+https://github.com/KorroAi/kinloom.git#subdirectory=python"   # Python 3.9+, no dependencies
cd your-game
kinloom init        # detects the engine, copies its client, writes your coding agent's instructions
```

`pipx install "git+https://github.com/KorroAi/kinloom.git#subdirectory=python"` works the same way. With plain `pip`,
if `kinloom` is not found afterwards (its folder is not on your PATH), run `python -m kinloom init` instead. Installing
from git needs read access to the repository (it works for everyone once the repository is public).

**No Python?** The clients are single files in [`python/src/kinloom/clients`](python/src/kinloom/clients): copy the one
for your engine (the Godot addon folder, `Kinloom.cs` and `Unity/` for Unity, or the one file for JavaScript/TypeScript,
C++, Rust, Java or Lua) into your project and call it; everything works offline, and a key or a relay brings the model.
Release zips (one per engine) are built by `python/release.py` and attached to a GitHub release when a `v*` tag is
pushed (`.github/workflows/release.yml`); none has been published yet.

Then ask your coding agent, or type `/kinloom <what you want>` in Claude Code, Cursor or Gemini CLI:
*"the weather follows how I play"*, *"generate each new level"*, *"a blacksmith I can talk to, who gives items to
people she likes"*. The agent uses three commands:

```bash
kinloom recipe "a blacksmith the player can talk to"     # the right call and code in your engine's language
kinloom add Mira "a widowed blacksmith who secretly sold the king's sword" --tools "give(item)" --trust give=0.3
kinloom run -- godot --path .                            # runs the game, then shows what the AI did
```

`kinloom add` writes the character into `kinloom.json` (no declaration code; edits apply while the game runs). The
clients also live in [`python/src/kinloom/clients`](python/src/kinloom/clients).

Not on PyPI, npm, NuGet, crates.io or LuaRocks yet: install from this repository.

## Any model

- **An API key** from the environment: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`
  and other hosted services, or `KINLOOM_BASE_URL` + `KINLOOM_MODEL` for any chat-completions endpoint.
- **A model on your machine**: Ollama or LM Studio.
- **Your coding agent's plan** during development: `kinloom use claude-code` (also codex, gemini-cli, opencode).
- **None**: everything still runs offline.

Keys are only read from environment variables, never written to files, logs or recordings. A cheaper model can serve
everything players do not wait for: `models: {"background": "..."}`. Details: [Models](python/README.md#models).

## Shipping to players

- `kinloom deploy` prepares a relay server with player tokens, rate limits and spending caps.
- One session per player: the relay keeps memory per session. Give each player's id (`session`), or let the clients
  pick one: with a relay token and no session, the browser client, the Godot addon and Unity's `KinloomDialogue` keep
  one id per install. Through a relay, every client asks `decide` and `act` far less often than once a frame (a
  quarter of the character's `every`) and waits out a rate limit (HTTP 429) instead of retrying.
- A server reachable from other machines always needs a token. A single-player game is the authority of its own
  session (it may set state, memories, feelings); a shared world run by your own game server keeps those for itself
  with `--player-can none`.
- `kinloom bundle` builds Kinloom as a program that needs no Python, shipped next to your game.
- `kinloom ship` checks a build before release: no key inside the game, how players reach a model, offline answers,
  caps, content rating. It drafts `kinloom-ai-disclosure.md` for the store page.
- `rating: "everyone" | "teen" | "mature"` adds a rule to every prompt, on top of the answer checks and your banned
  words.

## Measured, not promised

Real runs, with their method, cost and misses, are in [`proof/`](proof):

- **Conversation speed** (OpenRouter, `deepseek/deepseek-v4.1-flash`, 90 replies): first word 1.1 s median and 1.6 s
  at p95; whole reply 1.8 s median and 2.9 s at p95; about $0.0005 a reply. [proof/souls](proof/souls/README.md)
- **Secrets**: 24 manipulation attempts, no secret said, nothing given away. [proof/souls](proof/souls/README.md)
- **Coding agents**: across 30 requests, answers that run and use a right call went from 8 % to 88 % with Kinloom's
  instructions. [proof/universal](proof/universal/README.md)
- **Every SDK with a real model**: Python, JavaScript, TypeScript, C#, Java, Rust, C++, Lua and Godot each ran the
  conformance scenario natively against `deepseek/deepseek-v4.1-flash`: 205 requests, 205 answered, $0.0094 in all.
  [proof/sdks](proof/sdks/README.md)
- **Real engines**: Godot 4.7 (every conformance run), LÖVE 11.5 (offline, relay and native through its own
  `love.thread` transport) and the Unity 6000.3 and 6000.6 editors (the conformance scenario in relay and native mode,
  `KinloomDialogue` in play mode, a Windows IL2CPP player). Defold, Bevy and Unreal have not been run, nor Unity's
  mobile, console or WebGL builds.
  [proof/engines](proof/engines/README.md)
- **End to end**: aider (DeepSeek) and Claude Code (haiku) each built a working dialogue with reply choices in an
  existing game. [proof/v1](proof/v1/README.md)
- **Learning units**: with a real model, 85 % wins against 65 % for the offline rules alone (hand-written rules: 87 %).
  [proof/depth](proof/depth/README.md)

Not measured yet: whether players find these characters more human than a plain prompt (the blind test in
`proof/souls/blind.html` has not been judged), and how much time a coding agent saves overall.

Tests: the Python suite (run on 3.9 and 3.12 on Windows and Linux), the conformance scenario in every client
against a real server, every SDK's own brain against a fake model, and every language's calls from `calls.md` compiled
against its SDK (`python/conformance/calls.py`). CI is configured (`.github/workflows/ci.yml`) to run them on Linux,
macOS and Windows; it has not run on GitHub yet, as the repository has not been pushed with it. Its Windows and
Linux steps pass when run locally; macOS has not been run. Tests never call a real model.

## Documentation

| | |
|---|---|
| [python/README.md](python/README.md) | The full guide: every call, souls, voice, minds, the world, models, tools, safety |
| [calls.md](python/src/kinloom/kit/calls.md) | Every call in every language |
| [Engine guides](python/src/kinloom/kit/engines) | Setup notes per engine |
| [cookbook.md](python/src/kinloom/kit/cookbook.md) | 39 patterns, from free conversation to units that learn and the AI checked in CI |
| [CHANGELOG.md](CHANGELOG.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) | Releases, how to contribute, how to report a vulnerability |

## The legacy C# runtime

[`legacy/`](legacy) holds Kinloom's first design: a C# runtime where the game declares things, roles and instant
behaviors in JSON and an Arbiter validates every proposal, plus the earlier village-simulation demo *Asagiri Valley*
(Godot 4.7 .NET). It still builds and passes its tests from `legacy/` (`dotnet build`, `dotnet test`). A measured
comparison showed it saved coding agents no time, so the SDK above replaced it.

## License

[MIT](LICENSE). Third-party assets of the legacy demo keep their own licenses (`legacy/demo/valley/CREDITS.md`).
