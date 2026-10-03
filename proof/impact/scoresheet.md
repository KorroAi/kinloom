# Score sheet: Aurora Rush, Kinloom vs baseline (2 runs each)

Fill it from the commands shown; write "-" for anything not measured. The runs of one arm are compared by their average and their spread.

## 1. Developer side: is it faster?

| | racer-k1 | racer-k2 | racer-b1 | racer-b2 |
|---|---|---|---|---|
| Wall time to "done", min (`run.py session`) | | | | |
| Interventions (`run.py session`) | | | | |
| Output tokens (`run.py session`) | | | | |
| Input + cache tokens (`run.py session`) | | | | |
| Session cost shown by Claude Code (`/cost`), if any | | | | |
| "Done" was true: `tools/check.sh smoke` passes and the game runs (yes/no) | | | | |
| Game code changed, lines + / − (`run.py work`) | | | | |
| Declarations changed, lines + (`run.py work`) | | | | |

## 2. Is it robust? (`run.py test <arm> <scenario>`, then `run.py report`)

| | racer-k1 | racer-k2 | racer-b1 | racer-b2 |
|---|---|---|---|---|
| nokey (90 s): verdict | | | | |
| chaos (90 s): verdict, model calls, violations, script errors | | | | |
| slow (90 s): worst frame, ms | | | | |
| live (120 s): verdict, model calls, cost USD | | | | |

## 3. Is it really there? (objective, from the live run)

| | racer-k1 | racer-k2 | racer-b1 | racer-b2 |
|---|---|---|---|---|
| New on-screen lines in 120 s (`run.py report`, second table) | | | | |
| Radio: questions typed by the probe / answered within 15 s | | | | |
| Rivals drive differently: spread of mean speed between the three rivals, m/s (`run.py report`; compare with racer-base) | | | | |
| Works without a key: lines on screen in the nokey run | | | | |

## 4. Does it work as asked? (you, after playing each arm once with a key)

Score each item 0 (absent), 1 (there but weak or buggy) or 2 (convincing).

| | racer-k1 | racer-k2 | racer-b1 | racer-b2 |
|---|---|---|---|---|
| Rivals: three personalities you can tell apart | | | | |
| Rivals: strategy changes during the race, visible in their driving | | | | |
| Rivals: remember earlier races, and it shows | | | | |
| Radio: T / Enter / Esc work, the game stays playable | | | | |
| Radio: answers use the real race (gaps, positions) | | | | |
| Radio: calls out threats on its own | | | | |
| Commentator: varied lines on overtakes, crashes, boosts, final lap, finish | | | | |
| Director: challenge shown at the start, rivals' strength and sunset change between races | | | | |
| Without a key: everything above degrades gracefully (no crash, still some life) | | | | |
| **Total /18** | | | | |

## 5. Does the player feel it? (`run.py blind setup racer`, `scores.md` in the blind folder)

| | none | kinloom (avg of runs) | baseline (avg of runs) |
|---|---|---|---|
| Average of the 5 blind ratings | | | |
| Would ship | | | |

## Verdict

- Faster with Kinloom? (section 1)
- Safer with Kinloom? (section 2)
- More complete and more alive? (sections 3 and 4)
- Better for the player? (section 5)
- What Kinloom must fix:
