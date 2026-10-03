# Universal: any request, in any words, into correct Kinloom code

2026-09-29. Question: when a developer asks their
coding agent for **anything** (most requests here are not about characters or dialogue, a third are in French), does
the agent write correct Kinloom code from what `kinloom init` gave it?

## One-shot measure (`run.py`, 30 requests, 2 answers each)

The model (`deepseek/deepseek-v4.1-flash` on OpenRouter, the one allowed) reads what an agent reads in a Python game
(AGENTS.md written by `kinloom init`), with or without the output of `kinloom recipe "<request>"`, and writes the code.
The code is then run offline and against a hostile scripted model, in its own process, and checked: a call that can do
the request (lenient list per request, fixed before the runs), no hand-written HTTP/SDK/key, it runs. Prices from
`https://openrouter.ai/api/v1/models` read the same day: $0.30 / M input, $0.006 / M cached input, $1.20 / M output.

| Kit | What the agent reads | Pass | Right call | Runs | Cost of the run |
|---|---|---|---|---|---|
| before (commit `d156b8e`) | AGENTS.md only | **8 %** | 53 % | 18 % | $0.062 (both rows) |
| before | + `kinloom recipe` | 70 % | 92 % | 78 % | |
| after (mechanism map) | AGENTS.md only | **83 %** | 98 % | 85 % | $0.073 (both rows) |
| after | + `kinloom recipe` | 80 % | 90 % | 86 % | |
| after2 (+ mind example, `create([item], count)`) | AGENTS.md only | **88 %** | 100 % | 88 % | $0.066 (both rows) |
| after2 | + `kinloom recipe` | 89 % | 95 % | 93 % | |

60 answers per row, fewer where a call never came back (after: 59; after2: 59 and 56, 5 calls of the provider lost).
Total spent on the measure: about $0.21 (plus ~$0.01 for a first run stopped because a call hung). No answer wrote HTTP, an SDK or a key, before or after.

**Why the old kit failed**: the AGENTS.md of a Python game showed one code block, a Pygame dialogue box. For any other
request the agent guessed the arguments (`decide(..., options=)`, `context=`, `among=`, `kl.ask(...)`, `kl.rank(...)`)
and the code crashed. `kinloom recipe` fixed most of it, but only when the agent runs it.

**What changed**: the brief opens with "Kinloom knows nothing about this game", a table "the game needs back -> the
call", and every call once in the game's own language (`kit/calls.md`, 8 languages + HTTP), with neutral placeholders;
the dialogue box became one line. `kinloom recipe` shows the same map and exact calls when no word of the request points
to one call (a request in French, say). Cookbook titles lead with the mechanism ("Knobs refreshed in the background
(e.g. a director)"). READMEs, `kinloom init`, the Claude skill and Cursor rule no longer open on characters. Found by the
measure and fixed: `create([item], count=N)` returned N lists (now N items like `item`); `mind` was only named, not shown.

**What still fails (after)**, read by hand: mostly the model's own code (a stand-in function it forgot to define, an
indentation error, `input()`, its own data missing a key). Kinloom-side: a wrong `mind` shape (twice, fixed in after2),
a request answered with a call outside the fixed list (music intensity through `act` tools: arguably fine, counted as a
failure). After2: `knows`/`opinion` arguments guessed (their exact form is now in the Python map, not measured again),
and `character(..., facts=)`.

Limits: one model, a one-shot answer (a real agent can read files and retry), Python only for the run check, the
requests and the lists of right calls written by the same author as the kit.

## Real agent sessions (aider + the same model, 1 run each)

`proof/impact/run.py`, arms `{orbit,keep}-v2-uni{old,new}` (old: kit of `d156b8e`; new: mechanism map, before the
mind example). Briefs in `proof/impact/briefs.md` ("Universal"): Orbit (TypeScript) "drones choose to chase, cut off
or keep their distance", Ember Keep (Python) in French "an omen before each night".

| Arm | Minutes | Cost (upper bound) | Build / smoke with no key | Calls used | Lines changed (game) |
|---|---|---|---|---|---|
| orbit old | 5.2 | $0.103 | pass | `mind`, `think` | 101 |
| orbit new | 4.1 | $0.074 | pass | `mind`, `think` | 78 |
| keep old | 4.2 | $0.067 | pass | `create` (instant) | 45 |
| keep new | 3.5 | $0.045 | pass | `decide`, `say` | 47 |

All four work. A full agent reads files and retries, so the gap of the one-shot measure does not show here; one run per
arm is noise, not a result. Read by hand: keep old asked `create` for a name among one pre-written option (the model can
only pick what the code chose); keep new used `decide` for a once-a-night choice, whose answer is refreshed in the
background and so one night late. The brief now says it: a choice made once uses `create` with the same example.
