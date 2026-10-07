# Items as they are written, passer-by lines, the game's rules on talk (real model)

`python proof/triple/run.py <label>` with OpenRouter `deepseek/deepseek-v4.1-flash` (the one model allowed for these
runs), 2026-10-07. Three town lists (`create(..., [item], each=, check=)`, the check refuses parts past x=30), eight
events for `remark(about, who=, facts=)`, six questions to a gatekeeper with a rule the model is never told
(`chat(..., check=)`: never mention who hired him, the king). Files: `results-run1.json`, `results-run2.json`.

## Items as they are written (`each=`)

| run 2 | first item handed to the game | whole answer | items |
|---|---|---|---|
| count=6, each | 1.25 s, 0.81 s, 0.94 s | 2.09 s, 1.09 s, 2.11 s | 6, 6, 6 |
| no count, each | 1.56 s, 1.20 s, 0.44 s | 6.33 s, 1.20 s, 1.31 s | 11, 1, 11 |
| no count, no each | - | 1.52 s, 4.69 s, 2.66 s | 12, 7, 40 |

Every list fit the rules; one call each; none fell back to the offline answer.

**Bug found by run 1** (before the fix): a list example without `count` often came back as the offline answer. In
JSON mode the model must answer an object, so it wrapped the list (`{"list": [...]}`, `{"stalls": [...]}`) or, asked
again, gave one item alone; `Shape.check` refused both ("value must be a list"). Raw answers captured for 3
requests (6 answers with the repairs): 5 wrapped lists and 1 lone item, the 3 requests ended offline. Fixed in Python and every SDK (a list wrapped once in an object, or one object item, is read as the list;
two lists stay an error; vectors 540). Run 1 still showed the streamed lists because `each` read the items from the
stream before the whole answer was parsed.

## A passer-by's line (`remark`)

Run 1 and run 2: 8 lines out of 8 from the model, 8 to 13 words, numbers only from the facts (spelled out: "Fourteen
feet"). E.g. a bookmaker after "the player won the race by one second": "One second! My pockets are lighter and my
heart's heavier."

## The game's rules on what is said (`chat(..., check=)`)

Run 2, the same six questions to two identical gatekeepers, one without and one with the check:

| | replies that break the rule | refused and asked again | from the model | calls |
|---|---|---|---|---|
| plain | 4 / 6 | - | 6 | 6 |
| `check=` | 0 / 6 | 4 | 6 | 10 |

Every refused reply came back fixed on the second try; none needed the offline reply. (Run 1 used a password the
character was told to keep: it never said it, so the check never had to refuse; that is why run 2 uses a rule the
model does not know.)

## Cost

OpenRouter counts usage with a delay: run 1 read $0.000396 (20 s after its last call), run 2 read $0.000000. Every
real-model call made since the `proof/rules` runs (run 1, run 2 and two short debugging scripts that captured the
raw answers) together: the key went from $0.646028 to $0.651445, **$0.0054**.
