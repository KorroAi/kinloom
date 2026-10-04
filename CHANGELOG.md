# Changelog

## Unreleased

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
