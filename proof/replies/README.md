# Replies: words and deeds

Question: when a player's message calls for something a character can do (a battle, a sale, leaving), does the
character's reply carry that action (`reply.do`)? Found while building FireRed with Kinloom: trainers said "yes,
let's battle" and no battle started, so the game fell back on reading the player's own words.

`tools.py`: 20 messages (13 that call for a tool, 7 that call for none), each from a new speaker, twice (40 replies),
two characters with three tools each. Model: `deepseek/deepseek-v4.1-flash` on OpenRouter, the one model used for every real run here.
Cost at $0.30 per million input tokens and $1.20 per million output tokens: what most of the providers OpenRouter
routes this model to charge (https://openrouter.ai/api/v1/models/deepseek/deepseek-v4.1-flash/endpoints, read on
2026-10-01: $0.0243-$0.60 in, $0.40-$2.40 out). The cheaper price `/models` shows is the cheapest provider's: the
key's billed usage did not follow it (every live run of 2026-10-01 together: $0.187 billed).

| Run | Tool used when called for | Unwanted action (none called for) | Wrong tool | Calls | Cost |
|---|---|---|---|---|---|
| `before` (Kinloom as it was) | 7/26 | 0/14 | 0 | 30 (+10 offline: budget) | about $0.010 |
| `after` (stronger wording in the prompt) | 5/26 | 0/14 | 0 | 41 | about $0.013 |
| `deeds` (a second look, kept) | **14/26** | **0/14** | 0 | 73 | about $0.016 |

- `before`: 10 of the 40 replies were the offline line, because the default budget (30 calls per minute) was reached.
  That is the budget working as designed; the script now raises it (`calls_per_minute=600`) to measure the model.
- Prompt wording alone did not help (`after`: 5/26). Two more prompt layouts, tried on 20 replies each, made the model
  drop the `~~~` inner part more often (from 1/20 to 6/20 and 11/20) and were reverted.
- Kept (`deeds`): when a reply from the model names no tool and the character has tools, one small JSON call reads
  the exchange and says what the reply commits the character to (validated and trust-gated like the reply). Only for
  characters with tools; about 0.5 s more before `chat` returns (the streamed text is not delayed).
- The 12 misses left, read by hand: almost all are replies that do not commit in words (the character haggles, asks
  "which sword?", or tells the player to leave without leaving itself). One clear miss: "Then you won't mind walking
  out empty-handed. Door's where you left it." with no `refuse_service`.
- One run each: noise is large at this size.

Results: `tools-before.json`, `tools-after.json`, `tools-deeds.json` (every reply, to read by hand).
