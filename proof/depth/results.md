## Learning without a key (`kinloom demo`, 8 seeds, 30 simulated minutes, 40 units)

| seed | won, minute 1 | won, minute 10 | won, minute 20 | won, last 5 minutes | generations | model calls |
|---|---|---|---|---|---|---|
| 0 | 9% | 6% | 12% | 64% | 90 | 0 |
| 1 | 12% | 66% | 64% | 64% | 99 | 0 |
| 2 | 13% | 15% | 65% | 67% | 110 | 0 |
| 3 | 8% | 51% | 52% | 55% | 104 | 0 |
| 4 | 7% | 21% | 63% | 71% | 87 | 0 |
| 5 | 12% | 42% | 53% | 61% | 110 | 0 |
| 6 | 12% | 12% | 19% | 49% | 81 | 0 |
| 7 | 19% | 22% | 43% | 56% | 65 | 0 |

Mean: 12% in the first minute, 61% in the last five (min 49%, max 71%); 64 s of computing for all runs.

- the naive rules, no learning: 12% won (3 seeds x 3 minutes)
- hand-written good rules, no learning: 87% won (3 seeds x 3 minutes)

## Speed of `think` (1,000 units, 5 senses, 4 actions, 3 variants)

- Python 3.12.10: 3.94 ms per 1,000 thinks
- JavaScript (Node v25.9.0): 0.60 ms per 1,000 thinks

The mind runs in the game process: no model call, no network, whatever the number of units.

## Rumors (a village of 40, one witness, `spread` rounds)

| rounds of talk | villagers who know | village's opinion of the player |
|---|---|---|
| 1 | 10 / 40 | -0.07 |
| 2 | 13 / 40 | -0.08 |
| 3 | 17 / 40 | -0.10 |
| 4 | 22 / 40 | -0.12 |
| 5 | 28 / 40 | -0.15 |
| 6 | 35 / 40 | -0.19 |

No model call: knowledge travels only through characters who meet, fainter with each hop and weighted by trust.

