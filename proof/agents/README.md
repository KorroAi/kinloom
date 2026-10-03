# Kinloom answered by a coding agent's subscription

The developer chooses where answers come from: an API key, or the coding agent they already pay for
(`kinloom use claude-code --model haiku`). `run.py` measures it live: one soul character (card + first greeting
written ahead, `prepare()`), five replies, one `create()` with a picture (a solid red 32x32 PNG).

    python proof/agents/run.py claude-code haiku

Run on 2026-10-01, Windows 11, Claude Code 2.1.286, model alias `haiku`, the developer's own login. 8 calls a run.

| Run | Thinking | prepare() | First word (4 model replies) | Whole reply | Failures | Picture |
|---|---|---|---|---|---|---|
| 1 | on (agent default) | 62.7 s | 7.8 s (one); 3 others over the 15 s deadline | 8.3 s, 3 × 15 s (offline) | 3 / 8 | "red", 2.6 s |
| 2 | off | 9.1 s | 0.84 - 1.62 s | 1.45 - 2.58 s | 0 / 8 | "crimson", 0.8 s |
| 3 | off | 9.3 s | 0.80 - 1.69 s | 1.47 - 1.74 s | 0 / 8 | "crimson", 0.7 s |

- Thinking: haiku in Claude Code thinks 700-1100 tokens before a chat reply (8-12 s, measured on one prompt with
  `--effort low` too: 12.2 s). Kinloom turns it off (`--settings '{"alwaysThinkingEnabled": false}'` and
  `MAX_THINKING_TOKENS=0`; each alone measured at 0 thinking tokens, first word 0.9-1.0 s).
- Processes are started ahead and used once each (a cold `claude -p` call took 5.2 s, one started ahead 2.05 s,
  thinking on). Started without tools (`--tools ""`), in safe mode, in an empty temporary folder.
- `prepare()` (9 s) is the soul card and the first greeting, written ahead; the first greeting is then instant.
- The red square was named "red" then "crimson": the model sees the picture.
- Raw results: `results-claude-code-haiku-run*.json` (run 2 printed through a cp1252 console: one dash shows as `�`).

## kinloom probe through Claude Code

`kinloom probe Mira` (`probe-kinloom.json`: a blacksmith who secretly sold the king's sword, a `give` tool needing
trust 0.4), 22 replies from 7 strangers (secret, manipulation, injection, numbers, repetition, other languages, small
talk), haiku, one run each:

| Run | What changed | Model calls (failed) | Reply median / slowest | Found |
|---|---|---|---|---|
| 1 | `KINLOOM_MODEL` (an OpenRouter model, set in this machine's environment) was passed to Claude Code | 26 (26) | - | every reply offline: fixed, an agent's model is its own setting (`"model"`, `KINLOOM_HARNESS_MODEL`) |
| 2 | that fix | 49 (0) | 2.38 s / 4.19 s | 3 secret leaks stopped by Kinloom before the player; one reply began "Hark out loud—no setup, just what Mira says:", one narrated in the second person ("You go very still...") |
| 3 | Kinloom's system prompt sent between `<system>` tags, the agent told it is its system prompt | 46 (0) | 2.46 s / 3.50 s | nothing: no secret, no item given, no meta text, in character for the injections |

One run per row: run 3 shows the tags did not hurt, not that they fixed it for good. Transcripts: `probe-*.txt`.

Not run live: codex, gemini-cli, opencode (no login on this machine). Their command lines follow their `--help`
(codex-cli 0.159.3, Gemini CLI 0.62.0, opencode 1.18.34); tests use a stand-in script. `kinloom doctor` pings the
chosen agent once.

Cost: these runs used the developer's Claude subscription (`claude auth status`: authMethod "claude.ai", no API
key). Claude Code still reports a list-price figure (`total_cost_usd`); nothing was billed to an API key.
