# Proof

What was run for real, how, what it cost, and what went wrong. Each folder has its method, its raw results and the
script that reproduces it. Real-model runs all use one model, OpenRouter's `deepseek/deepseek-v4.1-flash` (unless a
folder says otherwise), so results stay comparable; costs are read from the key's usage before and after.

| Folder | Question | Result |
|---|---|---|
| [souls](souls/README.md) | Do characters with a soul answer fast, and keep their secrets? | first word 1.06 s median, whole reply 1.61 s; 45 attacks in 10 families, read by hand |
| [speed](speed/README.md) | How fast with a hosted model, and with a local one? | `qwen3:8b` on Ollama: 10 of 12 replies offline before reasoning was turned off, 0 after |
| [replies](replies/README.md) | When a reply agrees to do something, does the action come with it? | 7 of 26 before, 14 of 26 after, no unwanted action |
| [rules](rules/README.md) | Do the game's own rules (`check=`) fix what the model makes? | plans that fit the game: 3 of 10 without, 10 of 10 with, in two runs |
| [triple](triple/README.md) | Items as they are written, passer-by lines, rules on what characters say | a forbidden name said in 4 of 6 replies without `check=`, 0 of 6 with |
| [universal](universal/README.md) | Does any request, in any words, become correct Kinloom code? | 8 % to 88 % of 30 requests, with the instructions `kinloom init` writes |
| [impact](impact/README.md) | Does a coding agent add AI faster with Kinloom than without? | 35-69 lines against 294-337, all safe; **no time gain shown** |
| [v1](v1/README.md) | The 1.0 features, end to end with real agents | aider and Claude Code each built a working dialogue in an existing game |
| [agents](agents/README.md) | A coding agent's subscription as the game's model | Claude Code (haiku): 16 calls, 0 failures, first word 0.8-1.7 s |
| [sdks](sdks/README.md) | Every SDK in native mode with a real model | 205 requests, 205 answered, $0.0094 in all |
| [engines](engines/README.md) | Real engines, outside the test hosts | Godot 4.7, LÖVE 11.5, Unity 6000.3 and 6000.6, an IL2CPP player |
| [depth](depth/README.md) | Do minds learn from play? | with a model 85 % of fights won, offline rules alone 65 % |
| [mod](mod/README.md) | A game with no source and no mod API | `kinloom hooks` found the 3 methods that make its lines; the Harmony mod ran offline and with a model |
| [voice](voice/README.md) | Characters that speak, players heard | the system voice in every SDK, 10/10; hosted voices tested against local copies of their APIs only |

Not measured yet: whether players find these characters more human than a plain prompt (the blind test,
[`souls/blind.html`](souls/blind.html), has not been judged), and Cursor, Codex or Gemini CLI as the developer's agent.
