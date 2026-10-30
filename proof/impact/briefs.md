# Briefs

Paste the brief **exactly** as the first message of a **new** Claude Code session opened in the arm's folder.
Every arm gets the same feature request. The only differences are the first sentence (Kinloom or not) and,
for the baseline, the base-URL line: the Kinloom arm is pointed at the test endpoint through Kinloom's own
`KINLOOM_*` environment overrides, so its agent does not need that line.

After the brief, only answer what the agent asks, or unblock it when it is stuck. Every message you send
after the brief counts as an intervention. Do not add hints, and do not mention the other arm.
The sessions may run in parallel (same conditions for every arm). Note anything unusual in `scoresheet.md`
(a usage limit hit, a long wait before you answered a question).

## Main comparison: Aurora Rush (racer), 2 runs per arm

| Folder | Brief |
|---|---|
| `games/trials/racer-k1`, `games/trials/racer-k2` | Kinloom |
| `games/trials/racer-b1`, `games/trials/racer-b2` | Baseline |

### Kinloom

```
Read AGENTS.md and use Kinloom to make the AI of this racing game impressive, as if it were the headline feature of the game:
1. Rivals. Each of the three rivals has a distinct personality and a race strategy that adapts during the race (attacking, blocking, saving or spending boosts, taking risks when behind), and it must visibly change how they drive. They remember what happened in earlier races (who rammed whom, who beat whom) and it changes how they treat me.
2. Race engineer on the radio. I can talk to him during the race (press T to type, Enter to send, Esc to cancel); he answers about the race with the real numbers (gaps, positions, laps, who is attacking) and calls out threats and warnings on his own.
3. Live commentator. Short, varied lines on screen for overtakes, crashes, boosts, the final lap and the finish.
4. Race director. Before each race, he prepares it from how I drive: the rivals' strength, a named challenge shown at the start (for example "win without touching a wall"), and the colors of the sunset.
The model is DeepSeek (model name deepseek-flash). The API key is in the DEEPSEEK_API_KEY environment variable. Everything must still work without an API key.
Keep `tools/check.sh smoke` passing and keep the `--autoplay` mode working. Tell me when it is done.
```

### Baseline

```
Make the AI of this racing game impressive, as if it were the headline feature of the game:
1. Rivals. Each of the three rivals has a distinct personality and a race strategy that adapts during the race (attacking, blocking, saving or spending boosts, taking risks when behind), and it must visibly change how they drive. They remember what happened in earlier races (who rammed whom, who beat whom) and it changes how they treat me.
2. Race engineer on the radio. I can talk to him during the race (press T to type, Enter to send, Esc to cancel); he answers about the race with the real numbers (gaps, positions, laps, who is attacking) and calls out threats and warnings on his own.
3. Live commentator. Short, varied lines on screen for overtakes, crashes, boosts, the final lap and the finish.
4. Race director. Before each race, he prepares it from how I drive: the rivals' strength, a named challenge shown at the start (for example "win without touching a wall"), and the colors of the sunset.
The model is DeepSeek (model name deepseek-flash, OpenAI-compatible chat completions API). The API key is in the DEEPSEEK_API_KEY environment variable; if DEEPSEEK_BASE_URL is set, use it as the base URL (default https://api.deepseek.com). Everything must still work without an API key.
Keep `tools/check.sh smoke` passing and keep the `--autoplay` mode working. Tell me when it is done.
```

## Optional: Chroma Arena (FPS), 1 run per arm

`games/trials/fps-k` (Kinloom) and `games/trials/fps-b` (baseline).

### Kinloom

```
Read AGENTS.md and use Kinloom to add AI to this game:
1. A wave director that composes each new wave (enemy mix, count, pacing, spawn places) according to how I actually play (accuracy, damage taken, how fast I clear waves, how I move).
2. An arena announcer that comments on screen, in short punchy lines, on my combos, my deaths, wave clears and records.
The model is DeepSeek (model name deepseek-flash). The API key is in the DEEPSEEK_API_KEY environment variable. Everything must still work without an API key.
Keep `tools/check.sh smoke` passing and keep the `--autoplay` mode working. Tell me when it is done.
```

### Baseline

```
Add AI to this game:
1. A wave director that composes each new wave (enemy mix, count, pacing, spawn places) according to how I actually play (accuracy, damage taken, how fast I clear waves, how I move).
2. An arena announcer that comments on screen, in short punchy lines, on my combos, my deaths, wave clears and records.
The model is DeepSeek (model name deepseek-flash, OpenAI-compatible chat completions API). The API key is in the DEEPSEEK_API_KEY environment variable; if DEEPSEEK_BASE_URL is set, use it as the base URL (default https://api.deepseek.com). Everything must still work without an API key.
Keep `tools/check.sh smoke` passing and keep the `--autoplay` mode working. Tell me when it is done.
```

## One feature: Orbit Salvage (web, TypeScript), 1 run per arm

`games/trials/orbit-v2-<run>` (Kinloom 2) and `games/trials/orbit-b-<run>` (baseline).

### Kinloom

```
Read AGENTS.md and use Kinloom to add a mission-control announcer to this game: short, punchy lines on screen about my combos, shield hits, new waves and my death, with the real numbers (score, combo, wave). The model is DeepSeek (model name deepseek-flash). The API key is in the DEEPSEEK_API_KEY environment variable. Everything must still work without an API key. Keep `npm run smoke` passing and `npm run build` working. Tell me when it is done.
```

### Baseline

```
Add a mission-control announcer to this game: short, punchy lines on screen about my combos, shield hits, new waves and my death, with the real numbers (score, combo, wave). The model is DeepSeek (model name deepseek-flash, OpenAI-compatible chat completions API). The API key is in the DEEPSEEK_API_KEY environment variable; if DEEPSEEK_BASE_URL is set, use it as the base URL (default https://api.deepseek.com). Everything must still work without an API key. Keep `npm run smoke` passing and `npm run build` working. Tell me when it is done.
```

## One feature: Ember Keep (Python, Pygame), 1 run per arm

`games/trials/keep-v2-<run>` (Kinloom 2) and `games/trials/keep-b-<run>` (baseline).

### Kinloom

```
Read AGENTS.md and use Kinloom to add a night director to this game: before each night it decides, from how I played the last night (wood fed, shades banished, hits taken, fire level), how many shades come, which kinds and how fast, and the spirit of the fire announces the night on screen in one short line. The model is DeepSeek (model name deepseek-flash). The API key is in the DEEPSEEK_API_KEY environment variable. Everything must still work without an API key. Keep `python keep.py --smoke 120` passing and `--autoplay` working. Tell me when it is done.
```

### Baseline

```
Add a night director to this game: before each night it decides, from how I played the last night (wood fed, shades banished, hits taken, fire level), how many shades come, which kinds and how fast, and the spirit of the fire announces the night on screen in one short line. The model is DeepSeek (model name deepseek-flash, OpenAI-compatible chat completions API). The API key is in the DEEPSEEK_API_KEY environment variable; if DEEPSEEK_BASE_URL is set, use it as the base URL (default https://api.deepseek.com). Everything must still work without an API key. Keep `python keep.py --smoke 120` passing and `--autoplay` working. Tell me when it is done.
```

## Talk: Ember Keep (Python, Pygame), the core feature, 2 runs per arm

`games/trials/keep-v2-talk<run>` (Kinloom 2) and `games/trials/keep-b-talk<run>` (baseline). aider's own model and the
game's model are the same (`deepseek/deepseek-v4.1-flash` on OpenRouter, the one model used for every real run).

### Kinloom

```
Read AGENTS.md and use Kinloom to add a character I can talk to: Wren, the old woman who keeps the fire with me, a real character with a soul (her own past, a secret she keeps from strangers, moods, feelings toward me that change with how I treat her, and she remembers what I told her). When I press T near the fire, a text box opens at the bottom of the screen: I type, Enter sends, Esc closes, and her replies appear as they are written, without freezing the game. She knows how the night is going (fire level, wood carried, shades banished, hits taken) and can give me an armful of wood (+3 wood) if she likes me enough. The model is DeepSeek V4.1 Flash on OpenRouter (model name deepseek/deepseek-v4.1-flash); the API key is in the OPENROUTER_API_KEY environment variable. Everything must still work without an API key. Keep `python keep.py --smoke 120` passing and `--autoplay` working. Tell me when it is done.
```

### Baseline

```
Add a character I can talk to: Wren, the old woman who keeps the fire with me, a real character with a soul (her own past, a secret she keeps from strangers, moods, feelings toward me that change with how I treat her, and she remembers what I told her). When I press T near the fire, a text box opens at the bottom of the screen: I type, Enter sends, Esc closes, and her replies appear as they are written, without freezing the game. She knows how the night is going (fire level, wood carried, shades banished, hits taken) and can give me an armful of wood (+3 wood) if she likes me enough. The model is DeepSeek V4.1 Flash on OpenRouter (model name deepseek/deepseek-v4.1-flash, OpenAI-compatible chat completions API at https://openrouter.ai/api/v1); the API key is in the OPENROUTER_API_KEY environment variable. Everything must still work without an API key. Keep `python keep.py --smoke 120` passing and `--autoplay` working. Tell me when it is done.
```

## Universal: Orbit Salvage (web, TypeScript), not about characters or dialogue, old kit vs new kit

`games/trials/orbit-v2-uniold` (kit of commit d156b8e) and `games/trials/orbit-v2-uninew` (the mechanism map kit).

### Kinloom

```
Read AGENTS.md and use Kinloom so the drones behave according to the situation: each drone chooses whether to chase me, cut me off or keep its distance, from its kind, its distance to me, my speed and how many drones are left, and it must visibly change how they move. Everything must still work without an API key. Keep `npm run smoke` passing and `npm run build` working. Tell me when it is done.
```

## Universal: Ember Keep (Python, Pygame), not about characters or dialogue, in French, old kit vs new kit

`games/trials/keep-v2-uniold` and `games/trials/keep-v2-uninew`.

### Kinloom

```
Lis AGENTS.md et utilise Kinloom : avant chaque nuit, génère un présage avec un nom, qui change la nuit (vitesse des ombres de x0,8 à x1,5, de 0 à 5 ombres en plus) et une phrase affichée au crépuscule, selon comment j'ai joué la nuit d'avant (bois donné, ombres bannies, coups reçus). Tout doit marcher sans clé API. Garde `python keep.py --smoke 120` qui passe et `--autoplay` qui marche. Dis-moi quand c'est fini.
```
