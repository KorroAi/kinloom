## What this changes

<!-- What and why, in a few lines. Link the issue if there is one. -->

## Checklist

- [ ] Works with no API key: the example, the lines or the offline reply still answer.
- [ ] Tests use scripted models only (`KINLOOM_SCRIPT`), never a real one.
- [ ] A change to one SDK is made in every SDK, with a vector or a conformance line proving they agree.
- [ ] `cd python && python -m pytest` passes; for SDK changes, `python python/conformance/run.py` and `native.py` too.
- [ ] No key, token or personal data in code, logs or recordings.
- [ ] `CHANGELOG.md` says what changed for users.
