# Changelog

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
