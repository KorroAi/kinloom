# Proof: the depth layer (minds that learn, the world)

Everything here runs offline and free: no key, no model, no network. Reproduce with `python proof/depth/run.py`
(about one minute); the full output of the last run is [results.md](results.md) (2026-09-29, Windows 11, Python 3.12,
Node 25).

## Minds learn from play, without a key

`kinloom demo` is a skirmish: 40 units, each against a turret that fires every half second (60 % hit, 20 % when the
unit is in cover) and reloads for three steps after five shots. A round lasts at most 30 s; a unit wins by destroying
the turret, loses when it dies or runs out of time. Units start with the rules anyone writes first:
`{"shoot": ["ammo above 0"], "reload": ["ammo below 1"]}`. The game only reports rewards (damage dealt minus taken,
+1 for a win, -1 for a loss or time out, `done` at the end of a round). No model is involved.

| | fights won |
|---|---|
| the naive rules, no learning | 12 % |
| **learning from rewards, last 5 of 30 simulated minutes, 8 runs** | **61 % on average (49 % to 71 %)** |
| hand-written good rules (advance, take cover near the turret, shoot, reload), no learning | 87 % |

Per run (minute 1 → minute 10 → minute 20 → last five minutes): 9 → 6 → 12 → 64 %, 12 → 66 → 64 → 64 %,
13 → 15 → 65 → 67 %, 8 → 51 → 52 → 55 %, 7 → 21 → 63 → 71 %, 12 → 42 → 53 → 61 %, 12 → 12 → 19 → 49 %,
19 → 22 → 43 → 56 %. Every run improved; how fast varies a lot (one run needed 25 minutes). 30 simulated minutes
take about 8 s of computing for the 40 units, the fights and the learning.

How it learns (`kinloom/minds.py`, `kinloom/brain.py`):
- **Credit**: each decision earns its reward plus the discounted rewards that follow it (γ = 0.8, until the round
  ends), so moves that set things up get their due.
- **Evidence**: from the last 4,000 credited decisions, where an action did better or worse than the other actions
  (thresholds at the quantiles of what units sensed; the advantage in standard errors).
- **Changes**: make an action win where it did clearly better; try actions nobody plays, over the whole range of each
  sense; random mutations for exploration; sometimes two changes at once (good tactics often need two).
- **Selection**: variants are compared on whole rounds when the game passes `done` (else per decision), with their
  uncertainty: the parent is the surely good one (highest lower bound), the one replaced the surely bad one (lowest
  upper bound). The best is never replaced.
- With a model, the model rewrites the losing variant from the best one, the numbers, the worst moments and the
  evidence lines; its answer is validated like everything else, and falls back to the local change.

What was tried and dropped, measured the same way (10 simulated minutes, 3 to 10 seeds): plain mutation only (win
rates fell back to 0 in some runs, because an average per decision rewards stalling until time runs out: judging whole
rounds fixed it); crossover of the two best variants; 6 or 8 variants instead of 4 (slower: each needs its own
rounds); a longer credit horizon (γ 0.9, 0.95: no gain).

## With a real model writing the minds (2026-10-01)

The same skirmish, the same seeds (0, 1, 2), 30 simulated minutes, `python proof/depth/llm.py openrouter 0 1 2` against
`python proof/depth/llm.py offline 0 1 2`. With a model, it writes the first variants from the declaration (senses,
actions, the naive rules) and rewrites the worst variant at each learning step from the rewards and the evidence; a
step whose call fails falls back to the offline change. Model: `deepseek/deepseek-v4.1-flash` on OpenRouter; cost at
$0.30 / $1.20 per million tokens in / out, what most providers of this model charge (see `proof/replies/README.md`).

| seed | won, minute 1 | minute 10 | minute 20 | last 5 minutes | learning steps (by the model) |
|---|---|---|---|---|---|
| 0, no model | 9 % | 6 % | 12 % | 65 % | 90 (0) |
| 1, no model | 12 % | 66 % | 64 % | 64 % | 99 (0) |
| 2, no model | 13 % | 15 % | 65 % | 67 % | 110 (0) |
| 0, model | 49 % | 91 % | 86 % | 80 % | 62 (54) |
| 1, model | 42 % | 81 % | 86 % | 87 % | 63 (61) |
| 2, model | 29 % | 86 % | 88 % | 89 % | 64 (52) |

- **Mean of the last five minutes: 85 % with the model, 65 % without** (hand-written good rules: 87 %). The model's
  first variants already win 29-49 % in the first minute (the naive rules: 9-13 %); by minute 10 every run is above
  80 %.
- 192 model calls in all (6 failed, those steps used the offline change), 1 to 2 minutes of real time per run,
  268,701 tokens in and 43,645 out: **about $0.13 for the three runs** (about $0.045 per 30 simulated minutes).
- Three seeds, one model, one game: the gain is clear here; how far it carries to other games is not measured.

## `think` is cheap enough for crowds

1,000 units, 5 senses, 4 actions, 3 variants, one decision each: **3.9 ms in Python**, **0.6 ms in JavaScript**
(Node), best of 5 and 50 repetitions. The compiled mind runs in the game process in every client (C#, GDScript, Rust,
Java, C++, Lua too, with the same numbers: the conformance scenario checks the same choices and arguments in all of
them); only rewards (batched) and new variants travel to and from `kinloom serve`.

## Rumors travel through people

A village of 40 with one witness of a theft (`impact -0.8`), then rounds of `spread("village")`: 10, 13, 17, 22, 28,
35 of 40 villagers know after 1 to 6 rounds, and the village's reputation of the player goes from -0.07 to -0.19
(hearsay counts half, times the listener's trust in the teller). No model call.

## In a real test game: Ember Keep (Pygame)

`python proof/depth/keep_minds.py 60 4` gives the shades of Ember Keep (`../games/keep`, written without Kinloom) a
mind, starting from the game's own behavior as rules (go for the fire; chase the keeper when closer than 160 px), with
four plans (rush, hunt the keeper, orbit and wait, sneak round to the side away from the keeper), rewarded for
reaching the fire (+1), hurting the keeper (+0.5), being hit (-0.1) or banished (-0.5), against the game's autopilot.
Only the shades' `step` hook changed (marked `KINLOOM` in the file).

| shades' behavior (4 seeds) | shades that reach the fire, of those whose run ends | keeper's mean night reached |
|---|---|---|
| the game's own, first → last quarter of 60 min | 42 % → 46 % | 1.69 |
| learning, first → last quarter of 60 min | 42 % → 47 % | 1.77 |
| hand-written: wait in orbit while the keeper is near the fire, then rush (15 min) | 38 % | 2.30 |
| hand-written: sneak (15 min) | 37 % | 3.27 |
| hand-written: always hunt the keeper (15 min) | 7 % | 1.38 |

**No gain here**, and the table says why: the game's own behavior was already the best of the plans the shades can
express for this reward; the learning kept it (its best variant stayed "rush, hunt when close") instead of drifting
to worse. A bigger action set or a reward on ending the keeper's run would give it something to find; not done.

## Not measured yet

- **Whether coding agents integrate minds and the world faster, and better, than they write the same AI without
  Kinloom**: needs agent sessions (`proof/impact`, spec section 11); not run.
- Minds inside a shipped game with real players, and the LÖVE thread transport, Unity and Unreal in their engines.
