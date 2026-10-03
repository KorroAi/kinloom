# Speed with real models

`python proof/speed/bench.py ollama <model>` (local, free) or `python proof/speed/bench.py openrouter` (the one
OpenRouter model allowed, `deepseek/deepseek-v4.1-flash`, cents). One character with a soul, the player walks up,
then 11 more lines; each reply streamed. Measured: time to the first word shown, the whole reply, tokens sent and
cached. `KINLOOM_SRC=<folder>` runs the same on another copy of Kinloom (before/after). 2026-09-29, RTX 4060 laptop
GPU for the local models.

## Local models (Ollama)

| Model | Before (committed code) | After |
|---|---|---|
| `qwen3:8b` (a reasoning model) | **10 of 12 replies offline**: the hidden reasoning used the token budget (empty answers) or the 8 s limit; the one real reply's first word at 7.2 s; card 30 s | **0 offline**; first word 0.52 s median, 2.34 s p95; whole reply 2.27 s / 3.77 s; 66 % of the tokens sent reused from Ollama's cache; card 10.5 s |
| `llama3.2:1b` | not measured before | 1 offline of 12; first word 0.17 s / 0.88 s; whole 0.91 s / 1.86 s. Fast, but the replies of a 1B model stay weak (it copies bits of the prompt, answers a question with a question); Kinloom now asks again when it copies prompt labels |

What made the difference: reasoning turned off (`reasoning_effort: "none"`; 4.9 s → 0.4 s for the same line on
qwen3:8b), no second request when a local model is slow (it only slowed both), the model loaded when Kinloom starts,
more time for the inner part and the reply on a local model, the conversation placed before the parts that change
every reply (so the cached start grows), and small models' formats read (`~~~` first, `mood: calm` lines).

## Hosted model (OpenRouter, `deepseek/deepseek-v4.1-flash`)

Four runs of 12 replies each side (the committed code and the final code), the same day:

| | First word, median | First word, p95 | Whole reply, median | Cost of the 12 replies |
|---|---|---|---|---|
| Before | 0.66 / 1.19 / 1.16 s | 4.61 / 2.86 / 1.22 s | 1.11 / 1.73 / 1.53 s | $0.0065 / $0.0069 / $0.0073 |
| After | 1.26 / 1.25 / 1.11 / 1.20 s | 7.47 / 3.33 / 1.31 / 6.24 s | 1.69 / 1.91 / 1.30 / 1.55 s | $0.0053 / $0.0054 / $0.0059 / $0.0072 |

No speed difference can be claimed on the hosted model: the provider sets it, and the tail moves from run to run on
both sides. Cost: 0 to 20 % less (cached tokens are now counted when streaming, and the prompt order lets the
provider reuse more; how much it reuses varies). The first two "after" runs predate the change that lets a new
sentence stream before it ends (the no-repeat filter held each sentence until its end).
