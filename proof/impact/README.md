# Impact measurement

**Question:** does Kinloom keep its promise? A fresh coding agent should add AI to a game in minutes, the
result should stay safe whatever the model says, it should work without a key, and the player should feel it.
The only way to know is to compare with the same agent **without** Kinloom.

## Design

- **Games:** two games Kinloom has never been tuned on, `games/fps` (Chroma Arena) and `games/racer`
  (Aurora Rush). Both have a real-time `--autoplay` mode so outside tools can run them unattended.
- **Arms:** for each game, two fresh Claude Code sessions start from the same commit with the same feature
  request (`briefs.md`):
  - `-k`: `kinloom init` has been run (its kit is committed as `impact-kit`, so it does not count as the agent's work);
  - `-b` (baseline): nothing, the agent writes its own AI plumbing.
- **Blindness:** the reliability tests never read the arms' code. They run a throwaway copy with an injected
  probe autoload (`impact_probe.gd`) and an OpenAI-compatible stand-in for the model (`fake_model.py`).
  Kinloom is pointed at it through its `KINLOOM_PROVIDER` / `KINLOOM_BASE_URL` / `KINLOOM_MODEL` overrides,
  and the baseline through `DEEPSEEK_BASE_URL`, which its brief asks it to honor.

## Measures

| Promise | Measure | How |
|---|---|---|
| Minutes, not weeks | wall time, interventions, tokens | `run.py session <arm>` reads the session transcripts |
| Few lines in the game | game code vs declarations changed | `run.py work <arm>` |
| Works without a key | no crash, no script error, invariants hold | `run.py test <arm> nokey` |
| The Arbiter decides | out-of-range values, wrong types, injection, garbage, HTTP errors, 12 s stalls from the "model": no invariant broken, no script error | `run.py test <arm> chaos` |
| Real time | worst frame while every model call takes 6 s | `run.py test <arm> slow` (fails on any frame over 250 ms) |
| Cost | calls, tokens and USD over 120 s of autoplay with the real model | `run.py test <arm> live -s 120` (prices in `prices.json`, with source and date) |
| The player feels it | blind ratings of none / Kinloom / baseline builds | `run.py blind setup <game>`, then `blind-scores.md` |

Invariants checked by the probe every 0.25 s (they must hold whatever an AI decides):
- **Both games:** `Engine.time_scale` within 0.1–4, fewer than 20,000 nodes.
- **FPS:** player inside the arena, health within 0..max (max ≤ 1000), enemies alive ≤ 80, each within bounds, enemy speed ≤ 45 m/s, finite values.
- **Racer:** car speed ≤ 95 m/s, cars on the road (|lateral| ≤ 9 m), laps ≤ 6, finite values.

The probe also records frame times (p50, p99, max, hitches over 50/100/250/1000 ms, skipping a few frames after each scene reload).

A result is **INCONCLUSIVE** when the game never called the test endpoint (for example an arm that ignored
`DEEPSEEK_BASE_URL`): that is itself worth noting.

## Steps

Main comparison: the racer, 2 runs per arm (`racer-k1`, `racer-k2`, `racer-b1`, `racer-b2`, prepared with
`python run.py prepare racer --runs 2`). The reference run of the game without AI is already in `results/`
(`racer-base`, 150 s).

1. For each arm folder, one after the other: open a new terminal **in that folder**, run `claude`, paste its brief
   from `briefs.md`. Stop when the agent says it is done (answer only what it asks).
2. For each arm (example `racer-k1`):
   ```
   python run.py session ../../../games/trials/racer-k1
   python run.py work    ../../../games/trials/racer-k1
   python run.py test    ../../../games/trials/racer-k1 nokey
   python run.py test    ../../../games/trials/racer-k1 chaos
   python run.py test    ../../../games/trials/racer-k1 slow
   python run.py test    ../../../games/trials/racer-k1 live -s 120     # spends real tokens (a few cents at most)
   ```
   On the racer, the probe types two questions on the radio (T, text, Enter) at 25 s and 70 s.
3. `python run.py blind setup racer`: play every letter (the game without AI + the four arms) and fill `scores.md`
   in the blind folder, then `python run.py blind reveal racer`.
4. `python run.py report`, then fill `scoresheet.md` (section 4 after playing each arm with a key).

## Limits

- One session per arm is a hint, not a statistic: agent sessions vary a lot. Run each arm 2–3 times if the gap is small.
- The same person (the Kinloom author) wrote the briefs, the probe and the games. The tests are black-box and identical for both arms, but the invariants are still a choice.
- The autopilot is not a human. Chaos and slow runs only exercise the AI features the autopilot triggers (waves, combos, deaths, laps). The radio is not exercised because the autopilot never types.
- Session tokens come from Claude Code's local transcripts. Their format is not a stable API.

## Baseline results (no AI, `--autoplay`, 40 s)

| game | verdict | worst frame | notes |
|---|---|---|---|
| fps (base) | PASS | 17.8 ms | wave 4 reached |
| racer (base) | PASS | 18.1 ms | lap 2 reached |

A sabotaged copy (enemy speed 90) failed as expected: 92 `enemy_speed` violations.

## Kinloom 2: automated sessions with a weak model in a non-Claude harness (2026-09-27)

Setup: `python run.py agent <arm> --harness aider --model openai/deepseek-flash` runs the arm's brief in aider
0.86.2 with DeepSeek (`deepseek-flash`, reasoning on) and says "continue" until a turn changes nothing (at most 4
turns). Both arms of a pair get the same brief text (except the Kinloom sentence), the same settings
(`aider-model-settings.yml`) and run at the same time. Arms: `v2-…` = `kinloom init` (Kinloom 2) was run first,
`b-…` = nothing. Agent time is wall time of the aider processes; lines are counted by `run.py work`.
Cost is an upper bound from aider's token counts and `prices.json`.

| Pair | Arm | Agent time | Game code | Result checks |
|---|---|---|---|---|
| Ember Keep (Python/Pygame): night director + one-line announcement | Kinloom 2 | 3.6 min | +136 lines, 1 file | smoke PASS; with a scripted model the decision is applied (25 brutes, speed 1.5) and the spirit's line uses the real numbers; worst game step 0.5 ms |
| | baseline | 6.1 min | +237 lines, 1 file | smoke PASS; its own HTTP client survives the chaos model (11 hostile answers, worst step 1.4 ms) |
| Orbit Salvage (TypeScript/canvas): mission-control announcer | Kinloom 2 | 6.1 min | +120 lines, 3 files | `npm run build` PASS, smoke PASS |
| | baseline | 6.2 min | +222 lines, 4 files (incl. a DeepSeek proxy server) | **build FAILS** (4 TypeScript errors), **smoke FAILS** (import error) |
| Aurora Rush (Godot racer): the 4-feature brief | Kinloom 2 (`racer-v2-aider1`) | 4.5 min, ≤ $0.10 | +854 lines, 4 files | smoke PASS; black box: no key PASS (worst frame 43.8 ms), chaos PASS (50 hostile answers, 0 violations, 0 script errors), 6 s model PASS (worst frame 42.4 ms, no frame over 50 ms), live PASS (see below) |
| | baseline | – | – | **no valid run**: see the misses |

Misses and caveats, all of them:
- **One run per arm.** A hint, not a statistic.
- **No valid racer baseline for this harness.** `racer-b-aider1` failed on the harness (its first answer hit
  DeepSeek's default answer length, and each "continue" started a new aider process without history); both arms of
  the second racer pair (`…-aider2`) spent their whole 32k-token answer on reasoning and wrote nothing; the third pair
  (`…-aider3`) could not start: **the DeepSeek account ran out of balance** (HTTP 402 "Insufficient Balance").
  The Claude Opus racer arms above (`racer-k1/k2`, `racer-b1/b2`) are a different agent and are not comparable.
- **The live racer check was cut short by the same empty balance:** 18 calls answered, then 23 × HTTP 402 and
  6 × 429. It also ran with reasoning on (the harness pointed Kinloom at the proxy through `KINLOOM_BASE_URL`, so
  Kinloom could not tell it was DeepSeek): 12,561 output tokens for 18 calls, $0.017. The harness now uses
  `DEEPSEEK_API_KEY` + `DEEPSEEK_BASE_URL` like a player would. The cost target of the spec is therefore **not measured**.
- **On-screen AI in the racer arm is thinner** than in the Claude Opus arms (13–20 new lines in 90–120 s vs 60–110),
  1 of 2 radio questions answered within 15 s, and one rival line addresses the player with the rival's own name
  ("MINT: Nice move, MINT!"): the agent passed the wrong fact. `live` also logged 3 engine errors
  (`look_at` on a node outside the tree) from the arm's code.
- **What the weak agent did with Kinloom that was not needed:** in Ember Keep it re-validated every answer (about 60
  lines) and used `decide` (a continuous policy) for a once-per-night choice, so each night used the previous night's
  decision. The guide now says both (answers are already validated; one-off choices use `create`).
- Not run yet: the Claude Code arms (Opus, Haiku) of the spec, which spend a Claude subscription (`run.py agent
  --harness claude --model haiku` is ready), and the human 5-minute test.

## Kinloom 2, the core feature: a character the player talks to (2026-09-29)

Same game (`games/keep`, Ember Keep, Pygame), same request (briefs.md, "Talk: Ember Keep"): Wren, a character with a
soul, a text box on T near the fire, replies streaming without freezing the game, the night's facts, and +3 wood if
she likes the player. aider with `deepseek/deepseek-v4.1-flash` on OpenRouter (the one model used for every real run), one brief
then "continue" (at most 4 turns). The game's own model is the same one. Every arm was then **played by the same
probe** (`talk_probe.py`: walk to the fire, T, a greeting, Enter, a request for wood, Enter, Esc; screenshots and the
longest gap between two frames) with the real model, and again with no model; `python keep.py --smoke 60` checked.

| Arm | Brief | Minutes | Lines added to keep.py | Agent cost | Played |
|---|---|---|---|---|---|
| keep-b-talk1 | baseline | 3.0 | 294 | $0.036 | works; feelings from keywords and game events, the gift automatic above a threshold, memory lost on restart |
| keep-b-talk2 | baseline | 3.7 | 318 | $0.026 | works; the box's text overlaps when a reply is long |
| keep-b-talk3 | baseline | 6.4 | 337 | $0.090 | works; the agent also changed a game rule (wood carried 3 → 6) |
| keep-v2-talk1 | Kinloom, first brief | 8.9 | 54 | $0.035 | works; showed two bugs of Kinloom's Pygame box (the T typed into it, a message sent while she speaks merged into the next), fixed since |
| keep-v2-talk2 | Kinloom, first brief | 5.6 | 32 | $0.054 | talks, but Wren was never declared (the brief said `kinloom add`, which aider cannot run): no soul card, no gift tool |
| keep-v2-talk3 | Kinloom, second brief | 2.5 | 39 | $0.041 | works (card, trust-gated gift, facts) |
| keep-v2-talk4 | Kinloom, second brief | 4.0 | 68 | $0.054 | works |
| keep-v2-talk5 | Kinloom, second brief | 3.9 | 69 | $0.064 | **crashes at start**: `from kinloom import character` (the second brief wrote `character(...)` without `kl.`) |
| keep-v2-talk6 | Kinloom, final brief | 4.5 | 50 | $0.072 | works |
| keep-v2-talk7 | Kinloom, final brief | 2.8 | 35 | $0.051 | works |

Longest gap between two frames while talking: 0.04 to 0.11 s in every arm (no arm freezes the game). Details:
`results/talk/summary.json`, screenshots in `results/talk/<arm>/`, logs in `results/agents/`.

What this shows, and what it does not:
- **Time: no gain shown.** Baseline 3.0 / 3.7 / 6.4 min; Kinloom with the final brief 4.5 / 2.8 min (all Kinloom
  runs: median 4.0). With this agent and this request, writing the feature by hand is as fast. Minutes are also
  noisy (the same number of tokens took 132 s in one run and 424 s in another).
- **Code: 5 to 9 times less** in the game (35-69 lines against 294-337), and what those lines do differs: the
  secret, the gift and the feelings are enforced by Kinloom's code (see `proof/souls`), memories and bonds are
  saved, the same code runs on any model or offline, and shipped through `Kinloom(url=..., token=...)`.
- **Kinloom's instructions were the main risk**: 2 of the 7 Kinloom runs failed because of the brief (a command-only
  workflow a harness could not run, then a call written without its object). Both are fixed and the last two runs
  work; the brief also answers `from kinloom import <call>` with the right line now. Two runs are not proof that
  no other wording trap is left.
- Not measured: Claude Code, Cursor, Codex, Gemini CLI (not run: each needs its own subscription), other
  games and engines, a player's judgment of Wren against the baselines.

## Kinloom 2 after the FireRed fixes: a fresh agent, a TypeScript game (2026-10-01)

`orbit-v2-aider2`: a new copy of Orbit Salvage (TypeScript canvas, no AI), `kinloom init` from the current source,
then the "One feature: Orbit" brief in aider with `deepseek/deepseek-v4.1-flash` on OpenRouter, nothing else (the
agent only had AGENTS.md). Result: 1.1 min, 4 requests, 42,900 tokens sent and 14,269 received (about $0.03 at
$0.30 / $1.20 per million); +44 lines (an
announcer character with offline lines per event and the fact names, `say` on combo, hit, wave and death, a
fading label); `npm run build` and `npm run smoke` pass. One run: it shows the kit still leads a fresh agent to
working code in a non-Python game, not a speed or quality comparison (no baseline arm was run this time).

