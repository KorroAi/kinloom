---
name: kinloom-integrate
description: Use when adding, changing or debugging AI-driven features in this game with Kinloom (characters, directors, generated content, narrators, player analysis, voice or text commands, anything an AI should read, steer or create).
---

# Integrate an AI feature with Kinloom

Kinloom is already installed in this project (`kinloom.json`, `kinloom/`). Your job: turn the developer's request into declarations, engine wiring and tests, then prove it works.

## 1. Understand the request
- Restate it as: which **things** the AI must see, which it may **change** (params), which **actions** it may take (functions, creations), **when** it should think (events, intervals, conditions, when asked), and what must happen **without** a model (fallback).
- Pick the closest recipe in `kinloom/docs/recipes/`. Recipes are starting points; combine or ignore them.

## 2. Look at the game
- MCP `scan_project` (or read the code): find the classes/scripts/nodes involved and their state and methods.
- Reuse existing names: a Kinloom property/param/function name should match the node member it maps to (Godot reads/writes/calls members by name).

## 3. Declare (kinloom/*.json)
- Types: properties the AI reads, params it may change (always with `min`/`max` or `options`), functions with typed args and cooldowns, `creatable` with `max`.
- Events with `importance`, and `perceivedBy` at emit time when only some things should know.
- Roles: a vivid `mission`, the narrowest `sees` and `can`, a `wake` list, a `budget`, a `fallback`. Use `inhabits` for a character.
- Behaviors for anything that must react every frame; generators for content.
- Run MCP `validate` until it reports OK.

## 4. Wire the engine
- Godot: `Kinloom.Bind("id", self)` in `_ready`, `Kinloom.EmitEvent(...)` where things happen, connect `Said` / `Replied` / `Generated` / `MediaReady` / `CreateRequested` / `ValidateRequested` as needed, `Kinloom.Ask(role, text, "player")` for conversation, `Kinloom.SaveState()` in the save file.
- JavaScript/TypeScript or Python games: `kinloom serve` + the ready client in `kinloom/client/` (see reference §9).
- Other engines: `kinloom serve` + a small client following `kinloom/docs/protocol.md`.

## 5. Prove it
- Write `kinloom/tests/<feature>.test.json` (scripted answers, expected effects, a no-key fallback case) and run `kinloom test` (or MCP `run_tests`).
- MCP `simulate_role` to read the exact prompt; `live: true` once with the real model if a key is configured, and report calls and cost from its stats.
- MCP `attack_guardrails` for every role: `escapes: 0`.
- Run the game; MCP `attach` (debug port 7718) or `kinloom inspect` to watch decisions and refusals.

## 6. Report honestly
Say what works, what you verified and how, what you could not verify (no key, no display), and the measured cost if you ran it live. Never invent prices, model names or results.
