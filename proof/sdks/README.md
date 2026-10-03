# Every SDK with a real model

Date: 2026-10-03. `live.py` runs the conformance scenario (`python/conformance`) in every SDK's native mode: the SDK's
own brain builds the prompts, calls the model, checks the answers and keeps the state. The model is OpenRouter's
`deepseek/deepseek-v4.1-flash`, reached through a small local proxy that adds the key, the model name and
`reasoning: {"enabled": false}` (what the SDKs send themselves when their URL is OpenRouter's). Voice requests go to the
conformance fake (no voice key). Python is run the same way through `kinloom serve`.

## Result ([results-2026-10-03.json](results-2026-10-03.json))

| SDK | Scenario | Model requests answered | Median latency | Tokens in / out | Time |
|---|---|---|---|---|---|
| Python (`kinloom serve`) | finished | 16 / 16 | 1.59 s | 5,028 / 940 | 40 s |
| JavaScript | finished | 17 / 17 | 1.58 s | 5,153 / 1,034 | 41 s |
| TypeScript | finished | 17 / 17 | 1.38 s | 5,182 / 962 | 38 s |
| C# | finished | 16 / 16 | 2.09 s | 5,011 / 862 | 45 s |
| Java | finished | 16 / 16 | 1.78 s | 5,004 / 942 | 41 s |
| Rust | finished | 16 / 16 | 1.61 s | 5,025 / 852 | 41 s |
| C++ | finished | 17 / 17 | 1.75 s | 5,444 / 1,108 | 39 s |
| Lua (LuaJIT 2.1) | finished | 31 / 31 | 2.61 s | 7,511 / 2,829 | 161 s |
| Lua (5.4) | finished | 29 / 29 | 3.97 s | 7,163 / 2,799 | 128 s |
| Godot 4.7 | finished | 30 / 30 | 1.36 s | 7,612 / 1,254 | 40 s |

**205 requests, 205 answered, 0 errors; billed $0.0094** (the key's usage read before and after).

Every transcript has the scripted run's structure (52 to 57 lines against 55) with the model's own words: lines,
replies in character, decisions and created content in the declared shapes, reply choices, two characters talking,
and the same offline answers as the scripted run. Differences from the scripted transcript are the model's choices, for
example no `give` in the reply where the script forces one.

Read by hand, three things that are not SDK bugs:

- **Lua makes more line requests.** Its scenario calls `say` up to 100 times until a line contains "passes" (the
  fake model's word), so with a real model it uses up and refills the line bank about 11 times. Replaying the same
  model answers in Lua gives 4 requests for 24 lines, as in the other SDKs. Lua's time is longer because the test host
  carries each request synchronously.
- **Godot makes more requests**: its AI nodes keep deciding while the scenario runs (as in the scripted run).
- **Images are not evaluated here**: the scenario's picture is 2 x 2 pixels. One SDK's character called it "a blank
  canvas", another invented a banner.

## Found on the way (test harness only)

- The Python scenario's own HTTP client waited 5 s per request (made for the fake): a soul's first reply took longer.
  `KINLOOM_SCENARIO_TIMEOUT` sets it (30 s here).
- The C# scenario needs `KINLOOM_VECTORS` (the shared vectors' path); without it, it stopped with an exception at
  its last line.

Run it: `OPENROUTER_API_KEY=... python proof/sdks/live.py [sdk ...]` (`LUA_PYTHON` and `CXX` as for
`python/conformance`).
