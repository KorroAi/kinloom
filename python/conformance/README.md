# Client conformance

Every engine client must print exactly `expected.txt` when it runs this scenario against `kinloom serve` started with
`KINLOOM_SCRIPT=script.json` (a scripted model, no tokens), then against a dead address (offline answers):

1. `character("VEGA", "commentator", lines={"*": ["What a race, {who}!"]}, events={"overtake": ["who", "whom"]})`,
   `character("THEO", "engineer", offline="Copy.")`,
   `character("BLAZE", "rival", tools={"boost": {"seconds": [0.5, 2.5]}})`.
2. `say("VEGA", "overtake", {"who": "BLAZE", "whom": "NOVA"})` until it returns a prepared line → `say: ...`
3. `chat("THEO", "gap?", {"position": 3})` → `chat: ...`
4. `decide("BLAZE", {"lap": 1}, {"strategy": ["attack", "block"], "aggression": [0.0, 1.0]})` → `decide first: ...`,
   then again until it changes → `decide later: ...` (JSON with sorted keys, no spaces).
5. `act("BLAZE", {"lap": 1})` until it returns actions → `act later: <tool> <args JSON>` for each (unknown tools never appear).
6. `create("race", {"challenge": "Win clean", "sky": "#ff7a45"})` → `create: ...`
7. With the server unreachable: `say` (offline line), `chat` (offline reply), `decide` (defaults), `create` (the example).

Run everything: `python conformance/run.py`.

Godot played like a player (real key events into the addon's `AIDialogue`; quitting while a native model request is
open): `python conformance/godot_ui.py`. Both failed in a real game before they were fixed.
