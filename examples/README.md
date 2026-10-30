# Examples

Small, complete and runnable. Each one works with no key at all (the offline answers play), and with a model when one
is in your environment.

| Example | Engine | What it shows | Run it |
|---|---|---|---|
| [python/tavern.py](python/tavern.py) | Python (terminal) | a keeper with a secret (`chat`, `soul`), drinks she pours through a tool (`tools`, `reply.do`), the weather (`decide`), a rumor (`create`) | `python tavern.py` or `python tavern.py --offline` |
| [web/index.html](web/index.html) | Browser (JavaScript) | the ready dialogue box (`kinloom-talk.js`), a smith who sells or gives through validated tools, gold and an inventory | `python -m http.server 8000` at the repository root, then http://localhost:8000/examples/web/ |

For the model:

- **Python**: `pip install kinloom` and a key in your environment (`DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`, `OPENROUTER_API_KEY` with `KINLOOM_MODEL`...), or a local model with Ollama.
- **Browser**: run `kinloom serve` in another terminal with the key in its environment. The page talks to it, so the
  key never reaches the browser. With no server, the page answers offline.

What a model said, what was refused and why: `kinloom log` (with `kinloom serve`), or `kl.journal()` in Python.

Larger games built with Kinloom, with their measured results, are described in [`proof/`](../proof/README.md).
