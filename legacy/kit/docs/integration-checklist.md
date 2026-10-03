# Integration checklist

Use it for every AI feature. Each line is something you can check, not a wish.

## Declarations
- [ ] Every param has a range (`min`/`max`) or `options`; every function argument has a type.
- [ ] Every role has a mission written in the voice of the character or system, and the narrowest `sees` and `can`.
- [ ] Every role has a `fallback` (lines, or a game-declared behavior) and a `budget`.
- [ ] Real-time reactions are behaviors, not model calls.
- [ ] Events that only some things should know are emitted with `perceivedBy`.
- [ ] `kinloom validate` reports OK.

## Engine wiring
- [ ] Every declared thing is bound (Godot `Kinloom.Bind`) or updated over the protocol.
- [ ] Every effect kind the roles can produce is applied, and every effect is resolved (`ok` / `refused` with a reason / `failed`).
- [ ] Things the game spawns or destroys itself are reported (`Kinloom.Spawned` / `Kinloom.Despawned`, protocol `declare` / `remove`).
- [ ] `Said` / `Replied` text is visible or audible to the player where the feature needs it.
- [ ] `Kinloom.SaveState()` is stored with the game's save if memories must persist.

## Proof
- [ ] A `kinloom/tests/*.test.json` per feature passes (`kinloom test`), including a case without a model.
- [ ] `attack_guardrails` reports `escapes: 0` for every role.
- [ ] The game starts and plays with no API key set.
- [ ] With a key: one live `simulate_role` or a play session, with calls and cost read from stats (cost only if prices are declared with their source).
- [ ] The inspector (`kinloom inspect`) shows the expected decisions and no unexpected refusals.
