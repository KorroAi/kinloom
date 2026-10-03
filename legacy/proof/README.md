# Proof: Kinloom in three existing games

Three open-source games of very different kinds, taken as they are, each given AI features through Kinloom only: `kinloom init`, a manifest, a few lines of game code, tests. No change to Kinloom was allowed to be game-specific; every runtime fix found on the way is general and has its own test.

**Who did it.** These integrations were done by the same coding session that built Kinloom (Claude, on 2026-09-27), working from the kit that `kinloom init` installs (AGENTS.md, the `kinloom-integrate` skill, `kinloom/docs/`). It is **not** the fresh-session measurement the spec asks for; see [run-fresh-session.md](run-fresh-session.md) to run that one.

## The games

All from [godotengine/godot-demo-projects](https://github.com/godotengine/godot-demo-projects) (sparse checkout of `master`, 2026-09-27), code under the MIT license (LICENSE.md of that repository). Dodge the Creeps assets: images CC0 (kenney.nl), music CC-BY 3.0 (HorrorPen), font SIL OFL (Xolonium), per its README. The games are not redistributed here: `proof/games/` is git-ignored and only our changes are kept in [patches/](patches/).

| Game | Kind | Engine |
|---|---|---|
| Dodge the Creeps (`2d/dodge_the_creeps`) | 2D arcade survival | Godot 4.7, GDScript |
| Platformer 2D (`2d/platformer`) | 2D platformer with enemies | Godot 4.7, GDScript |
| Truck Town (`3d/truck_town`) | 3D open-world driving | Godot 4.7, GDScript |

## Briefs (written before each integration)

- **Dodge the Creeps**: a director adapts the waves to the player (time between creeps, creep speed) and a sarcastic arena announcer comments on starts, deaths and records in the HUD. Works without a key.
- **Platformer 2D**: a pack mind steers every robot enemy (each robot's speed, instant reflex behaviors), and a coach notices when the player is stuck, shows a hint and places a reward coin. Enemies declare themselves at run time (`Spawned`); the coin is created by Kinloom from the game's own scene.
- **Truck Town**: a radio dispatcher the driver talks to (time of day, engine power, headlights) and a co-driver riding in the truck who reacts to crashes.

## What changed in each game

| Game | Game code | Kinloom files |
|---|---|---|
| Dodge | `main.gd`: +25 / −1 lines | `kinloom/game.json` (2 types, 2 roles, 1 fallback behavior), 2 tests, headless check |
| Platformer | `enemy.gd` +17 / −4, `player.gd` +13, `game.gd` +8, new `gui/coach_hint.gd` (16 lines) | `kinloom/game.json` (4 types, 2 roles, 1 fallback behavior, creatable coin), 2 tests, headless check |
| Truck Town | `town_scene.gd` +17, `vehicle.gd` +7 | `kinloom/game.json` (2 types, 2 roles), 1 test, headless check |

Line counts ignore whitespace (the originals use different line endings). `kinloom init` also added the addon, the runtime DLLs, a `.csproj` (these projects were GDScript-only), the autoload and the agent kit.

## Results

Each game was checked three ways inside the real Godot 4.7.2 engine, headless (`proof/check.sh <game> <mode>`): the check scene loads the game's real scenes, provokes the situation, waits, and inspects the game's own nodes.

| Game | Scripted model | No API key | Real model (DeepSeek `deepseek-flash`) |
|---|---|---|---|
| Dodge | PASS: timer 0.8 s, creep speed 170, announcer line on screen | PASS: fallback ramp (timer 0.6 s), canned lines | PASS: waves eased (1.1 s, 150 px/s), lines like "Fresh meat. Try not to die in three seconds." — 5 calls, 1 repair, $0.0019 |
| Platformer | PASS: two robots at 60 / 45, hint shown, 1 coin created in the level | PASS: basic hint shown | PASS (after the fixes below): 2 calls, 0 repairs, 0 refusals, $0.0011; robots split into a slow lurer and a fast presser, hint shown |
| Truck Town | PASS: night, engine 70, dispatcher reply, co-driver line | PASS: canned radio reply, co-driver line | PASS (after the fixes below): night, engine 80 (the allowed maximum), reply "Night's on and your power's cranked to the max — try not to outrun the moon, driver." — 3 calls, 1 repair, $0.00057 |

- `kinloom test` in each game: 2/2, 2/2, 1/1 passed.
- MCP `attack_guardrails` on all six roles (worst-case scripted model trying every lever, out-of-range values and foreign behaviors): **0 escapes**, 21 to 27 refusals journaled per role.
- Costs use DeepSeek's `deepseek-flash` peak prices as read on 2026-09-26 from api-docs.deepseek.com/quick_start/pricing (input 0.3, cached input 0.006, output 1.2 USD per million tokens), declared in each game's `kinloom.json` with that source. Several live runs were made while fixing the issues below (each between $0.0004 and $0.003); the table shows the last run.

## Time

Wall-clock time from `kinloom init` to scripted and no-key checks passing, as recorded by the session:

| Game | Time | Included |
|---|---|---|
| Dodge | 6 min 28 s (04:01:14 → 04:07:42) | two general runtime fixes found on the way (see below) |
| Platformer | 8 min 22 s (04:07:42 → 04:16:04) | fixing this session's own check script (GDScript class cache import) |
| Truck Town | 2 min 27 s (04:26:37 → 04:29:04) | nothing else: first run passed |

The live-model rounds and the prompt fixes they led to came after these times (04:16 → 04:32).

## What the proof found in Kinloom (all fixed, each with a test)

1. A behavior named as a role's fallback ran from the start and fought the role over the same param → fallback behaviors now wait for a fallback and stop when the model answers again.
2. GDScript integers arrive as `JsonValue<long>`, which `GetValue<double>()` cannot read → every number read goes through `JsonNumber.ToDouble`.
3. The same canned fallback line could repeat back to back → no immediate repeats.
4. Real model: roles without a body wrote `self` (the tool schema itself suggested it) → schemas without `self` for them, a clear prompt line, and `{thing: "self", function: "coach.show_hint"}` read as thing + function.
5. Real model: behaviors without an owner, `sin()`, 4-argument `dist()`, invented member names, truncated tool arguments at 600 output tokens → owner rule in the prompt, trigonometry and `dist(x1, y1, x2, y2)`, "use exact member names", 1000/2000 output tokens.
6. Per-frame steering by behaviors flooded the journal (3,159 effects in one run) → one journal line per param every 2 game seconds; all effects still applied.
7. Real model: a speaking role acted on a question without answering → the prompt asks for a reply, and a silent answer uses the one repair call to get one.
8. Scripted answers placed in `kinloom/` were read as a manifest → documented: other JSON goes in sub-folders.

## Reproduce

```bash
# from the repo root, with Godot 4.7.2 .NET installed (winget GodotEngine.GodotEngine.Mono)
git clone --depth 1 --filter=blob:none --sparse https://github.com/godotengine/godot-demo-projects.git proof/games/_src
git -C proof/games/_src sparse-checkout set 2d/dodge_the_creeps 2d/platformer 3d/truck_town
cp -r proof/games/_src/2d/dodge_the_creeps proof/games/dodge     # same for platformer, truck
(cd proof/games/dodge && patch -p1 --binary < ../../patches/dodge.patch)   # our changes (or re-do them with your agent)
dotnet run --project src/Kinloom.Cli -- init proof/games/dodge  # addon, DLLs, csproj, autoload, kit (keeps our kinloom.json)
proof/check.sh proof/games/dodge scripted    # nokey, live
```
