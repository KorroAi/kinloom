# Kinloom: AI in this game

This game uses **Kinloom** for anything a model does while it runs. Kinloom knows nothing about this game: you decide
what to build, and pick the call by what the game needs back. Never write prompts, HTTP calls, JSON parsing, threads
or retries for AI: the calls do it all, validated, each with an offline answer (the game works with no key).

| The game needs back | Call |
|---|---|
| a choice or numbers from the situation, every frame | `decide` (instant, refreshed in the background) |
| a choice made once (before a level or a round): the same example | `create` (~1-2 s, a fresh answer) |
| anything else a model can write: data of any shape, text, lists | `create` (~1-2 s, or `instant` from a pool) |
| calls to the game's own functions | `act` + `tools` |
| an answer about a picture or the screen | `create` / `chat` + `image=` |
| a line when something happens, filled with your facts | `say` (instant) |
| a free answer to what someone typed or said, in a voice | `chat` (~1 s, never per frame) |
| text said aloud, or what a microphone heard | `speak` / `listen` (WAV; system voice offline) |
| who saw what, and what they now think | `event`, `meet`, `knows`, `opinion`, `reputation` |
| many units deciding every frame, no model call | `mind`, `think`, `reward` |
| choices for the player to say (no keyboard) | `suggest` |
| characters talking to each other | `converse` |
| the AI in the game's save file; a debug view | `save`/`load`; `inspect` |

Exactly these calls and arguments ({language}):
```{fence}
{snippet}
```
Shapes by example: `["a", "b"]` one of them, `[0.0, 1.0]` a number in that range, `[1, 10]` a whole number, `"A real line."`
any text (shown offline), `{...}` an object, `[example]` a list. Answers come in that shape: use them as they are.
More (streaming, memories, secrets, lore, this engine): `KINLOOM.md` or `kinloom recipe "<the request>"`.
`kinloom run -- <game command>` shows what the AI did; `kinloom test` and `kinloom probe NAME` check it.

{setup}

Rules:
- The example / offline line is the fallback: no try/except, no fallbacks, no re-checks around Kinloom calls.
- Declare a named character once, in code (`character(name, soul="who they are", ...)`) or with `kinloom add NAME
  "who they are"` (kinloom.json), not both. Kinloom saves memories, feelings and bonds.
- Keys live in the environment, never in the game or its files. Shipping: `kinloom deploy`, then `kinloom ship`
  before a release.
- The model (an API key, or the developer's agent plan: `kinloom use`) is the developer's choice: ask, never switch it.
