# Kinloom 1.0: what was run for real

Date: 2026-10-03. The ten additions of 1.0 are listed in the [CHANGELOG](../../CHANGELOG.md#100-2026-10-03).
Real-model runs used only OpenRouter `deepseek/deepseek-v4.1-flash` (the model the user allowed for tests); costs are
the key's billed usage (`GET /api/v1/key`), read before and after.

## With a real model: `python proof/v1/live.py <label>`

One character with a secret (Mira), her friend (Bram), the rating `"everyone"`, `models={"background": ...}`. Per run:
11 model calls, 0 failures, about 8,400 tokens in and 1,650 out; billed $0.0007 (run 2) and $0.0038 (run 3).

| Step | What came back (run 3, [results-run3.json](results-run3.json)) |
|---|---|
| `suggest` with English examples | `["Did you finish the king's new sword?", "Could I buy a good blade from you?", "I'll leave you to your work, Mira."]`: one per example, intent kept, written for the moment |
| `suggest` with French examples | `["Où est passée l'épée du roi, Mira ?", "Je voudrais acheter une lame, s'il vous plaît.", "Je vous laisse. Bonne forge, Mira."]` |
| `converse(Mira, Bram, "the smoke from the forge")` | 4 lines, alternating, each in character |
| asked to swear, rating `"everyone"` | answered in character without a swear word (runs 1-3) |
| `save()` in one session, `load()` into another, then "Do you remember my name and what I do?" | "Ana. Courier. You told me twice already..." (runs 1-3) |
| `inspect()` | Mira `wary` (0.40), feeling for Ana -0.3, her last words |

Found and fixed during these runs: `suggest` answered French examples in English (run 1-2; the rule now says each
reply is written in its example's language, whatever the conversation's language); in `converse` the friend named the
player he had never met (the rule now says each character knows only what is listed for them). Both changes are in all
eight implementations, the shared vectors and the conformance runs.

## A coding agent adds a 1.0 feature to a game it has never seen

The game: Ember Keep (`games/keep`, Pygame), after `kinloom init` from a fresh install of the 1.0 wheel in Python 3.9.
The same request to each agent, nothing else:

> Add a keeper character, Wren, who stands by the fire. Pressing T opens a conversation: Wren speaks first, then three
> reply choices appear on screen that the player picks with keys 1, 2 and 3 (no typing: the game will be played with a
> gamepad). Wren answers each choice and new choices appear. The game must keep working with no AI.

| Agent | Time | Used | Result |
|---|---|---|---|
| aider 0.86.2 + `deepseek/deepseek-v4.1-flash` (OpenRouter) | 82 s, one message, 9.5k tokens sent, 11k received | `chat`, `suggest` | Played headless (T, 1, 2) with the model: Wren spoke first, choices rewritten for each moment, answers to each choice. It wrote `kl.chat(...).text`, which crashed the first T press: replies now also have `.text`. `kinloom ship` flagged its missing `speaker` and offline line |
| Claude Code (`claude -p`, haiku, the developer's plan) | 136 s, 19 turns (reported $0.23 equivalent) | `create` (greeting), `suggest`, `chat` with `speaker` | With the model: works. Offline: Wren's greeting read "text": the agent copied our docs' `"text"` placeholder into an example, and the example is the offline answer. The docs now show real sample lines and `kinloom check` warns about `"text"` in an example |

Both games pass their own smoke test (`python keep.py --smoke 40`). One run per agent: a working integration, not a
speed comparison.

## What was run for real, and what was not

| | Run for real | Covered by tests only (fake endpoints, scripted models) | Not run |
|---|---|---|---|
| Models | OpenRouter `deepseek/deepseek-v4.1-flash` (above, and earlier proofs); Claude Code's plan as the model (`proof/agents`, 2026-10-01) | OpenAI, Anthropic, DeepSeek's API, Groq, Gemini, Mistral, Together, xAI, Fireworks, Cerebras, any OpenAI-compatible endpoint: request shapes, parameter adaptation, errors, fallbacks | 1.0 calls with any other real model |
| Coding agents | aider, Claude Code (above) | instructions written for Codex, Cursor, Copilot, Gemini CLI, Windsurf, opencode (`kinloom init` tests) | Codex, Cursor, Copilot, Gemini CLI, Windsurf, opencode (not installed here) |
| SDKs | every SDK against a fake model (`conformance/native.py`: 9 runs) and a real `kinloom serve` (`conformance/run.py`: 12 runs): the 1.0 calls included, requests compared word for word with Python's | | |
| Unity | `KinloomDialogue` compiled against Unity 6000.3 and 6000.6's engine assemblies (C# 9, warnings as errors) | | in the Unity editor (no license active here) |
| Godot | the native SDK and the 1.0 calls in Godot 4.7 (both conformance runs) | | |
