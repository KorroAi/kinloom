# Kinloom

*Your world notices.* Kinloom is the brain of a game world: NPCs that **plan their day, talk to each other, reflect, scheme, lie, remember and ask for help**, and a **story director** that turns the tensions of the world into events — driven by a language model, kept consistent and controllable by a rule-based simulation that holds the truth.

- **Layered cognition.** Rules run every tick (perception, reflexes, rumours, plans). The LLM runs only when something happens (a new day, a shock, a meeting, the player speaking), asynchronously: the game never waits for it.
- **The model proposes, the engine decides.** Every answer goes through the **Arbiter**: unknown people or places, items the NPC does not own, facts the NPC does not know, violence without a reason — refused and journaled. Knowledge is isolated: a prompt only contains what that NPC actually saw or heard.
- **Explainable.** Every thought, plan, rumour and change of heart is in the causal journal: `Journal.Why(id)` explains any decision, LLM ones included.
- **Bring your own key, any provider.** DeepSeek, OpenAI, Ollama/LM Studio (any OpenAI-compatible endpoint) or Claude. Without a key, rules keep the world alive.
- **Engine-agnostic.** Pure C# (.NET Standard 2.1): Unity, Godot, or anything that runs .NET. The engine owns the bodies, Kinloom owns the minds.

## Asagiri Valley (the demo game)

A Godot 4 action RPG in a misty feudal-Japan valley: 13 villagers with goals, secrets and grudges; a forest with beasts, a spirit grove and Crow's bandit camp; seven requests plus the main story (the Jade Fox Relic is stolen on the first night — investigate, accuse, fight, or bargain); arrests, fines and jail; reputation; companions; a story director; and an ending where the valley writes your legend from what each villager really thinks of you.

**Words are acts.** Write "here, 5 coins for you" and, if you have them, the gold changes hands; bluff with coins you don't have and the NPC calls it out. The same goes for handing over items, threatening, striking, insulting, accusing someone, or asking someone to come along.

Needs Godot 4.7 .NET (`winget install GodotEngine.GodotEngine.Mono`) and an API key in the environment (`DEEPSEEK_API_KEY`, or see "Configuration"). Then double-click `play-valley.cmd`.

| Key | Action |
|---|---|
| WASD / ZQSD / arrows | move · **Shift** dash |
| **E** | talk — type anything, or use the quick lines; accept requests, buy, give |
| **R** | take the item in front of you (witnesses will remember) |
| **Space** | strike (raiders and beasts are fair game; villagers are not). Enemies flash before they hit: step away or **Shift**-dash to dodge |
| **H** | heal (potions from beasts, herbs, food) · **F11** windowed / fullscreen |
| **Tab** / click | read a mind: intention, thoughts, what they know (and from whom), feelings, *why* |
| **Q** / **C** / **T** | requests · last chronicle · time speed · **F9** end the story now |

Languages: English or French (NPCs speak, think and narrate in the chosen language; the UI follows). French is picked when Windows is in French; **L** on the title screen switches; `KINLOOM_LANGUAGE` or `--fr` / `--en` force it. **R** also picks the pocket of the person next to you (stolen goods can be taken back), defeated raiders drop their loot, **F3** shows the Kinloom arbiter's refusals (developer view).

Cost: the HUD shows the running AI cost when `KINLOOM_PRICE_INPUT` / `KINLOOM_PRICE_CACHED` / `KINLOOM_PRICE_OUTPUT` are set (per million tokens; `play-valley.cmd` sets DeepSeek's published peak prices). Measured with `deepseek-flash` at peak prices: a scripted session covering ~16 game hours cost $0.12 (145 calls); a headless 6-hour run cost $0.043. Brains keep it down by writing out only the conversations the player can hear, capping spontaneous talks per game hour, and not repeating a fresh talk.

`--autoplay <dir>` plays a scripted session and saves screenshots; `--film` plays the directed demo (record with Godot's `--write-movie out/film.avi`).

## Use Kinloom in your game

```csharp
var sim = ScenarioLoader.Build(ScenarioLoader.LoadScenario("world.json"), ScenarioLoader.LoadPack("pack.json"));
sim.ExternalMovement = true;                           // your engine moves the bodies
var brain = new Brain(sim, LlmConfig.FromEnvironment(), new BrainOptions { WorldDescription = "..." });

// every frame
sim.Step();                                            // at your tick rate (1 tick = 5 game minutes)
brain.Update();                                        // never blocks: LLM jobs run in the background
foreach (var npc in sim.World.Agents)
    MoveBodyTowards(npc, sim.DestinationOf(npc));      // then write npc.Position back
foreach (var e in brain.DrainEvents()) Show(e);        // thoughts, lines, plans, quests, events, chronicle
int ticket = brain.Talk("mira", "Why do you look so worried?");   // reply arrives as a "reply" event
```

Configuration (environment): `KINLOOM_PROVIDER` = `deepseek` | `openai` | `anthropic` | `ollama` | `custom` (default: the first key found), `KINLOOM_API_KEY` (or `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`), `KINLOOM_MODEL` (required for openai, ollama, custom), `KINLOOM_BASE_URL`, `KINLOOM_CASSETTE` (record/replay LLM traffic to a file). Budget and pacing live in `BrainOptions` (`MaxConcurrent`, `TokensPerGameHour`, cooldowns, `Lockstep` for headless runs).

Headless story run: `dotnet run --project src/Kinloom.Sim -- --brain scenarios/asagiri.json packs/asagiri.pack.json 12 out/brain` prints the valley's life as it happens.

## Rule-only prototype (Phase 0)

### Play the village (real-time prototype)

Double-click `play.cmd`, or: `dotnet run -c Release --project src/Kinloom.Game`

| Key | Action |
|---|---|
| ZQSD (AZERTY) / WASD (QWERTY) / arrows | move (physical key positions) |
| E | steal the item next to you (bread at the bakery, sword at the forge, ale at the tavern, apples at the field) |
| F | draw your weapon |
| H / P | help / pay the nearest villager |
| B | buy from the nearest trader (price depends on what they think of you) |
| Left click / right click | inspect a villager (what they know about you, and why they act) / close |
| Space / Tab | pause / game speed x1, x3, x10 |

Standalone build (no .NET needed): `scripts/package-game.sh` → `dist/KinloomVillage/Kinloom.Game.exe` and `dist/KinloomVillage-win64.zip`.

Everything villagers do comes from the same core as the simulation: they see, react, report, gossip, remember, and change prices. `--autoplay <dir>` plays a fixed sequence and saves screenshots (used to check the rendering).

## Run the village demo

Requires the .NET 10 SDK.

```
dotnet run --project src/Kinloom.Sim -- scenarios/village.json packs/medieval.pack.json out/village
```

Outputs in `out/village/`:
- `report.txt` — opinions of the player, who knows what (and from whom), trades, consequences with their why-chains
- `journal.txt` — every entry with its cause (`because #id`)
- `replay.html` — open in a browser: play the 7 days, click any character to see the Thought Inspector ("Why?")
  - Deep links: `replay.html#t=138&select=guard` opens tick 138 with the guard selected; the URL follows the viewer, so any moment can be shared. Live: https://kinloom-lilac.vercel.app/demo.html#t=138&select=guard

Refresh the landing-page demo at the same time: add `--publish site` (copies `replay.html` to `site/demo.html`).

Performance probe: `dotnet run -c Release --project src/Kinloom.Sim -- --bench 200`

## Tests

```
dotnet test
python -m unittest discover -s docs/phase0b
```

## Layout

| Path | Content |
|---|---|
| `src/Kinloom.Core` | Engine-agnostic core (.NET Standard 2.1, no dependencies): world, minds, perception, reactions, rumors, commerce, plans, knowledge (tell/lie), combat, quests, world events, simulation, causal journal |
| `src/Kinloom.Brain` | LLM cognition (.NET Standard 2.1): day plans, reflection, conversations, dialogue, director, chronicle, epilogue; Arbiter, scheduler, providers, cassette |
| `src/Kinloom.Scenarios` | Scenario and pack loading and validation (.NET Standard 2.1) |
| `src/Kinloom.Sim` | Console runner: report, replay export, bench, `--brain` headless story run |
| `demo/valley` | Asagiri Valley, the Godot 4 demo (assets: Ninja Adventure, CC0; font: DotGothic16, OFL — see `demo/valley/CREDITS.md`) |
| `packs/` | Genre packs (deeds, barks) — `medieval.pack.json` |
| `scenarios/` | Scenarios (places, agents, schedules, player script) — `village.json` |
| `viewer/template.html` | Replay viewer (data injected at export) |
| `site/` | Landing page (`config.js`: waitlist URL, demo clip), `demo.html` (copy of the seed-42 replay) |
| `docs/phase0`, `docs/phase0b` | Verdict sheet, interview kit, thresholds, results |

## Writing a scenario

Unknown JSON keys are rejected (a typo such as `"shedule"` is an error, not a silent no-op). Unknown ids (places, agents, items, deeds) are reported with the script step or agent that uses them. Script actions: `goto` (place), `deed` (deed, optional target and item), `buy` (target trader, price > 0). One tick is 5 in-game minutes.

- A deed or purchase scheduled before the player reaches their last `goto` destination still happens where the player is, and the journal records a `warning`.
- `frameInterval` (default 1) keeps one replay frame every N ticks — use it for long scenarios to bound memory and replay size (short barks may be skipped between frames).

## Writing a genre pack

Each deed has `kind` (unique, non-empty), `valence` (−1 harmful … +1 kind), `threat` (0 … 1 danger to bystanders), `radius` (≥ 0, how far it can be witnessed), `isCrime`, `transfersItem`. Invalid values are rejected at load time with the deed named. Barks are lists of lines per reaction key: `flee`, `confront`, `report`, `scold`, `grateful`, `approve`, `recognize`, `refuse`, `overcharge`, `serve`.

Pricing: not decided. Trademark: a US conflict exists on KINLOOM — see `docs/naming/trademark-check-2026-09-26.md`.
