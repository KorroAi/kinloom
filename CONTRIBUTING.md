# Contributing

## Rules

- Everything must work with no API key: the example, the lines or the offline reply answer.
- The model proposes, validation decides: model output reaches a game only after the shape check and the content
  filter.
- The Python package needs Python 3.9 or later and the standard library only. Each client is one file with no
  dependencies, the same calls and the same offline behavior as Python.
- Tests never call a real model: they use scripted models (`KINLOOM_SCRIPT`). Real-model runs live in `proof/` and
  report what they cost.
- API keys come from environment variables only, never from files, logs or recordings.
- Product code, docs and messages are in English.

## Checks

```bash
cd python && python -m pytest                       # the package
python python/conformance/run.py                    # every client against a real `kinloom serve`
python python/conformance/native.py                 # every SDK's own brain against a fake model
```

C++ needs a compiler in `CXX` (for example `CXX="uvx --from ziglang python -m ziglang c++"`); Lua needs a Python
with `lupa` in `LUA_PYTHON`. A change to one SDK goes into every SDK, with a vector or a conformance line that proves
they agree.

The legacy C# runtime builds from `legacy/`: `dotnet build -warnaserror --no-incremental` and `dotnet test`.

## Releasing

Push a tag such as `v1.0.0`: `.github/workflows/release.yml` builds the wheel and one zip per engine
(`python/release.py`) and attaches them to a GitHub release. PyPI publishing runs too once a trusted publisher is set
up on pypi.org and the repository variable `PUBLISH_PYPI` is `true`.
