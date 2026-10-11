# A mod of a game with no source

Question: can Kinloom go into a game whose source you do not have, with no mod API, and keep the game working with
no model?

- `game/`: **Lantern Row**, a tiny .NET 10 console game (a shopkeeper who greets and answers, a guard on his round),
  no AI and no mod API. The proof only uses its built `.dll`: nothing in the mod refers to its source.
- `kinloom hooks` reads that `.dll` with REA (static: the game is not run) and proposes where to plug in.
- `mod/`: the mod, Kinloom's C# client (one file) + Harmony 2.4.2, with the three patches `hooks` proposed filled in.
  It loads the game, patches it, and starts the game's own `Main`.
- `run.py` builds both, runs the game alone, then the mod offline, then with `kinloom serve` and a scripted model, and
  checks every step. `run.py live` uses the model from the environment instead (billed).

Needs the .NET SDK 8+, REA (`npm install --global rea-agents`, or `KINLOOM_REA` = the command that runs it) and the
network once for the Harmony package.

## Results (2026-10-11, Windows 11, .NET 10, REA 6.3.0)

`python proof/mod/run.py`: ALL PASS.

| Step | Result |
|---|---|
| `kinloom hooks` on the built game | 3 methods proposed in 3.6 s, exactly the ones that make the game's lines: `Guard.Shout(string)` (say, before the text is shown), `Shopkeeper.Answer(Player, string) -> string` (chat), `Shopkeeper.Greet(Player) -> string` (say). Not proposed: `Player`, `Guard.Patrol(int)`, `Main`. |
| Mod, no server | the transcript is the game's own, line for line; every patch ran (`source` offline) |
| Mod, `kinloom serve` + scripted model | every line and the reply come from the model (`source` prepared), the game runs to its end in 0.4 s |
| `kinloom serve` when the game quits | no traceback (before the fix: one `ConnectionResetError` per open connection) |

`python proof/mod/run.py live` (`deepseek/deepseek-v4.1-flash`): before the fix below, three runs: the game always ran
to its end with no empty line and Marlo's reply came from the model, but the lines written ahead did not: in two runs
the game's own lines were said instead. The journal showed why, and it was a Kinloom bug: `Character()` then
`Prepare()` reached the server in the wrong order, so the server answered "ready" knowing no character. Fixed in every
SDK (see CHANGELOG). In one of those runs the provider was slow (two calls over 12 s) and the guard's curfew had no
model line ready: the game's own was said, the intended behaviour.

After the fix, four runs: 4/4 ALL PASS, every time 5 of 5 lines and the reply written by the model (`source` prepared),
e.g. "Nine o'clock, folks. Lantern Row's closed for the night." for the curfew. 6 model calls a run, about 3,000 tokens
in and 1,000 out; the game ran to its end in 6.5 to 12.1 s, most of it the loading-screen `Prepare`. The cost was not
measured (the OpenRouter key's usage counter did not move, so the calls probably went through the DeepSeek key, whose
price is not declared here).

Lesson kept in the generated patches: an earlier version passed the game's line to `say` as a fact (`{line}`) to make
it the offline line. A real model then wrote lines around it ("Who goes there at this hour, Move along..") and facts
are cut at 80 characters. The patches now leave the game's text alone when `say` returns nothing.

## Limits

- One small game, written for the proof: method names were honest. Obfuscated or terse names give `hooks` nothing to
  rank (it says so); a real game needs each candidate checked in play.
- Harmony on .NET 10 here; Unity Mono loads the same patches through BepInEx or MelonLoader, which this proof did not
  run. IL2CPP and native games are covered by the guide only (`kinloom hooks --guide`).
- Very small methods can be inlined by the JIT, and a patch on them never runs: the guide says to patch the caller.
