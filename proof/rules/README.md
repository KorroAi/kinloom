# The game's rules in the loop (`create(..., check=, offline=)`)

Learned from the demos: The Plot (type-to-build: a plan must fit the free tiles and name structures that exist), the
Isaac mod (a carved room must fit the game's room), the wishes (an item must be one the game can give). Each game wrote
its own validation around `create` and compared Kinloom's stats to know whether the model had answered. Now:

- `check(answer)`: the game's own rules. `""`/`None`/`true` accept the answer; a reason (or `false`) refuses it. The
  model gets the reason and the refused answer once ("The game refused your last answer: ..."), then the game's
  offline answer is used. With `count`/`instant`, refused items are replaced by the offline answer.
- `offline`: the game's own offline answer (a keyword planner's, a template's), checked against the example's shape.
- Over HTTP the check runs in the game: `/v1/create` answers `{"value", "source": "model"|"offline"}` and takes
  `"offline"` and `"refused": {"answer", "why"}` (what the relay clients send for their check).

Built in Python and the 7 SDKs (TS/JS, C#, Java, Rust, C++, GDScript, Lua); proven by `conformance/native.py` (the deep
scenario: the same requests as Python, the refusal included) and `conformance/run.py` (every client through a server).

## With a real model

`python proof/rules/run.py <label>`: ten building requests on a plot with 16 free tiles and three structures, first
plain, then with the rules as `check=`. OpenRouter `deepseek/deepseek-v4.1-flash`, 2026-10-07:

| | plans that fit the rules | from the model | offline | calls |
|---|---|---|---|---|
| run1, plain | 3 / 10 | 3 | 0 | 10 |
| run1, `check=` | 10 / 10 | 10 | 0 | 17 |
| run2, plain | 3 / 10 | 3 | 0 | 10 |
| run2, `check=` | 10 / 10 | 10 | 0 | 17 |

The rules were also in the context ("the building must fit in the free tiles"): the model still broke them 7 times out
of 10 (a 12 x 12 statue, a 96-tile cathedral). With the reason told once, every refused plan came back fitting; none
needed the offline answer. Cost: OpenRouter counts usage with a delay, so the per-run figures in the JSON files are not
reliable (run1 showed $0.000000); for both runs together (54 calls) the key went from $0.638979 to $0.646028:
$0.0070, read 20 s after the second run.

Files: `results-run1.json`, `results-run2.json` (every plan, its calls and why it broke a rule).
