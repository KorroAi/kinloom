# Kinloom reference

Kinloom connects language models to a game without knowing anything about the game. The game declares **things** (anything: a door, a road, a monster, the camera, the music, the UI, a rule), what can be read and changed on them, and **roles** (AIs with a mission). Kinloom wakes roles, lets them act only through the levers they were given, validates every proposal (the **Arbiter**), and hands the game **effects** to apply. The game stays the owner of its truth.

Everything below is enforced by the runtime. When in doubt, run `kinloom validate`, `kinloom test` or the MCP tools.

## 1. Concepts

| Word | Meaning |
|---|---|
| thing | Any game element exposed to Kinloom: `id`, `type`, optional `name`, `tags`. The built-in thing `world` holds global facts. |
| property | State of a thing the game pushes (`update`); AIs read it. |
| param | State of a thing AIs may change (`set`), within a declared range. The game applies it. |
| function | Something a thing can do (`invoke`), with typed arguments and an optional cooldown. |
| creatable | A type Kinloom may ask the game to spawn (`create`), with a live-instance limit. |
| event | Something that happened (`overtake`, `door_opened`, `combo_broken`...), optionally perceived only by some things. |
| role | An AI with a mission, what it sees, what it can do, when it wakes, its memory and budget. May inhabit one thing (`self`). |
| behavior | Instant rules (`when` → `set`/`invoke`/`emit`/`wake`) evaluated locally every pump, no model call. Roles can write them. |
| generator | Structured content on demand, validated against a schema, constraints and optionally the game. |
| media | An asset (image, sound, voice, 3D...) made by the developer's own tools; Kinloom routes, checks and caches. |
| effect | What Kinloom asks the game to do. The game applies it and resolves it (`ok`, `refused` + reason, `failed`). |
| journal | Every event, proposal, effect, refusal, fallback: the answer to "why did it do that?". |

Three speeds: **instant** (behaviors, every frame, local), **fast** (small model, ~1 s), **deep** (large model, seconds, async). A model cannot aim or steer frame by frame; it decides intentions and writes behaviors that run every frame.

## 2. kinloom.json (project root)

```json
{
  "manifest": "kinloom",
  "provider": { "kind": "deepseek", "keyEnv": "DEEPSEEK_API_KEY", "baseUrl": null, "fast": "model-name", "deep": "model-name" },
  "prices": { "input": null, "cachedInput": null, "output": null, "source": "" },
  "language": "English",
  "budget": { "maxCallsPerMinute": 30, "maxCostPerHour": null },
  "media": { "image": { "command": "python tools/make_image.py --prompt {prompt} --out {out}", "format": "png" },
             "voice": { "http": "http://localhost:5002/tts", "format": "wav" } },
  "requireBind": false,
  "servePort": 7717,
  "debugPort": 7718
}
```

- `provider.kind`: `deepseek`, `openai`, `anthropic`, `ollama`, `custom` (any OpenAI-compatible endpoint, needs `baseUrl`), `scripted` (with `script`: a file of canned answers, kept in a sub-folder such as `kinloom/tests/`, for headless checks).
- The key is read from the environment variable named by `keyEnv` (defaults: `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `KINLOOM_API_KEY` for custom). It is never written in files, logs or journals. Without it, the game runs on rules and fallbacks.
- `fast` / `deep`: model names from the provider. Kinloom does not guess them.
- `prices`: per million tokens, copied from the provider's pricing page, with `source` saying where and when. All three numbers or no cost is computed. Never invent them.
- `media`: `command` (run without a shell; placeholders `{prompt}`, `{out}`, `{spec}`) or `http` (POST `{kind, prompt, spec}`, answer = file bytes, or JSON `{path}` / `{base64}`).
- Environment overrides for headless checks: `KINLOOM_PROVIDER=scripted` + `KINLOOM_SCRIPT=path`, `KINLOOM_CASSETTE=path` (record/replay real calls).

## 3. Manifest files (`kinloom/*.json`)

All `*.json` files directly in the manifest folder are merged; sub-folders are ignored, so keep other JSON (tests, scripted answers, data) in sub-folders such as `kinloom/tests/`. Duplicate ids across files are errors. Comments and trailing commas are allowed.

```json kinloom
{
  "types": {
    "Gate": {
      "description": "A gate on the path.",
      "properties": { "position": "vec3", "locked": "boolean" },
      "params": { "open_speed": { "type": "number", "min": 0.1, "max": 5, "default": 1, "unit": "m/s" } },
      "functions": { "open": { "description": "Open it.", "cooldown": 3 }, "shake": { "args": { "strength": { "type": "number", "min": 0, "max": 1 } } } },
      "creatable": { "args": { "position": "vec3" }, "max": 4 },
      "engine": { "godot": { "scene": "res://props/gate.tscn", "parent": "/root/Main/Props" } }
    }
  },
  "things": [ { "id": "gate_a", "type": "Gate", "name": "North gate", "tags": ["entrance"] } ],
  "events": { "gate_hit": { "description": "Something hit a gate.", "importance": 0.4 } },
  "roles": [
    { "id": "gatekeeper", "mission": "You keep the north gate. Open it for friends, shake it at strangers.",
      "inhabits": "gate_a", "sees": ["thing:self", "event:gate_hit"], "can": ["invoke:self.open", "invoke:self.shake"],
      "wake": [ { "on": "event:gate_hit" } ] }
  ]
}
```

### Field specs

A spec is a type name (`"number"`) or an object:

| Key | Meaning |
|---|---|
| `type` | `number`, `integer`, `boolean`, `string`, `enum`, `vec2`, `vec3`, `color`, `ref` (thing id), `list`, `object`, `any` |
| `min` / `max` | numbers: value range; strings and lists: length range |
| `options` | enum values (required for `enum`) |
| `items` | spec of list items |
| `fields` / `required` | object fields and the required ones |
| `default` | used for params at start and for missing function arguments |
| `unit`, `description` | shown to models |

Vectors are `[x, y]` / `[x, y, z]` or `{x, y(, z)}`; colors are `"#rrggbb"` or `[r, g, b(, a)]`.

### types
`description`, `properties`, `params`, `functions` (`description`, `args`, `cooldown` seconds), `creatable` (`true` or `{args, max}`), `engine` (hints for adapters, ignored by the runtime). A name cannot be both a property and a param.

### things
`id` (letters, digits, `_`, `-`; `world`, `self` and `event` are reserved), `type`, `name`, `description`, `tags`. Things can also be added at run time (declare again, or the engine adapter's spawn call) and removed.

### events
`"type": "description"` or `{description, importance 0..1}`. Undeclared event types can still be emitted (importance 0.5).

### roles

| Field | Meaning |
|---|---|
| `id`, `mission` | required. The mission is the role's whole personality and goal. |
| `inhabits` | a thing id: that thing is `self`; the role only knows events that thing perceived (or public ones). |
| `sees` | views: `thing:self`, `thing:<id>`, `type:<Type>`, `tag:<tag>`, `event:<type>`, `event:*`, `world`, `*`. Nothing else reaches the prompt. |
| `can` | permissions (section 4). Only matching tools are offered to the model. |
| `wake` | list of `{"on": "event:<type>"}` (+ optional `"where": "<expr>"` with `event` in scope), `{"every": seconds}`, `{"when": "<expr>"}` (fires on the rising edge), `{"on": "ask"}`. `ask` always works. |
| `tier` | `fast` (default) or `deep`. |
| `memory` | `{scope: role\|thing\|shared\|none, persist: true, max: 50}` |
| `budget` | `{callsPerMinute: n}` |
| `fallback` | `{behavior: "<behavior id>", say: ["line", ...]}` used without a model, over budget, or when a call fails. A behavior named here does not run from the start: it is installed at the first fallback and removed when the model answers again. |
| `minInterval` | minimum game seconds between two calls (asks bypass it). |

### behaviors
`{id, owner, rules: [{when, do: [...], cooldown}]}`. `owner` is the thing `self` refers to. Actions: `{"set": "<thing>.<param>", "to": "<expr>"}`, `{"invoke": "<thing>.<function>", "args": {"<arg>": "<expr>"}}`, `{"emit": "<event>", "data": {"<key>": "<expr>"}}`, `{"wake": "<role id>"}`. Expressions may be strings or plain JSON numbers/booleans.

### generators
`{id, description, schema, constraints: ["<expr over value and context>"], repair: 1, gameValidate: false, tier: "deep", fallback: <value>}`.

## 4. Permissions (`can`)

| Entry | Allows |
|---|---|
| `set:<target>.<param>` | changing a param (value checked against its spec) |
| `invoke:<target>.<function>` | calling a function (arguments checked, cooldown enforced) |
| `create:<Type>` / `create:*` | asking the game to spawn a creatable type (within `max`) |
| `destroy:own` / `destroy:<target>` | removing things this role created / matching things |
| `behavior:<target>` | installing behaviors owned by matching things (their levers must also be allowed) |
| `generate:<id>` / `generate:*` | running generators (the game receives the result) |
| `media:<kind>` / `media:*` | requesting assets from the media tools |
| `say` | speaking (effect `say`, max 600 characters; control characters are removed) |
| `remember` | keeping notes in memory (max 500 characters each) |

`<target>` is `self`, a thing id, a type name, `tag:<tag>` or `*`; members may be `*`. Player text never changes permissions.

Safe limits apply even where the manifest declares none, so a broken or hostile model answer cannot reach the game:
integers must fit a 32-bit int unless you declare wider bounds, strings are at most 20,000 characters and lists 2,000 items
unless you declare a `max`, `min`/`max` on `vec2`/`vec3` apply to every component, and an `object` with declared `fields`
refuses unknown fields. Declare tight ranges anyway: they are what the model sees and what keeps the game sane.

## 5. Expressions

Paths: `self.<member>`, `<thing id>.<member>`, `world.<fact>`, `event.<field>` (`event.type`, `event.time`, data fields directly or via `event.data`), nested fields, list indexes `a[0]`, vector components `.x .y .z`. Ids with dashes: `` `truck-2`.speed ``.
Operators: `+ - * / %`, `< <= > >= == !=`, `&& || !`, `c ? a : b`; `+` joins strings; vectors add and scale.
Functions: `min max clamp lerp abs sign floor ceil round sqrt pow sin cos tan atan2 pi dist len rand now since contains exists` (`dist(a, b)` for two points or numbers, `dist(x1, y1, x2, y2)` for coordinates).
Evaluation never throws: unknown paths are null, arithmetic with null is null, comparisons with null are false, division by zero gives 0.
An expression is at most 2,000 characters and 40 levels deep; evaluation allocates no memory, so behaviors can run every frame.

## 6. Behavior semantics

- `set` applies continuously while its rule holds; an unchanged value, a value already on its way, or a change under 0.1 % of the param's range sends nothing.
- `invoke`, `emit`, `wake` fire when the rule becomes true, then again every `cooldown` seconds while it stays true.
- Game-declared behaviors are trusted; role-installed ones are checked against the role's permissions and may not replace a game behavior.
- A role-installed rule fires its `invoke`/`emit`/`wake` actions at most 5 times per second, however fast its condition flips.
- Two rules setting the same param to different values fight every frame: give each param one owner.
- Removing a thing removes the behaviors it owns.

## 7. Effects

| kind | the game should | `member` | `args` |
|---|---|---|---|
| `set` | write the param | param | `{value}` |
| `invoke` | call the function | function | named args, validated, defaults filled |
| `create` | spawn the type, using the effect's `thing` as the new id | type | `{args, name?}` |
| `destroy` | remove the thing | — | — |
| `say` | show or speak `text` for the thing | — | `{to?}` |
| `media` | load `args.path` | media kind | `{path, format, prompt}` |
| `validate` | judge a generated value | generator id | `{value}` |

Generated content a role asked for arrives as `invoke` on `world`, member `generated`, args `{generator, value, source}`.
Always resolve: `ok`, `refused` with a reason (the role remembers it and sees it next time), or `failed`. Unresolved effects expire after 10 game seconds. Effects for removed (or unbound, with `requireBind`) things are dropped and journaled.

## 8. Memory, persistence, budget

- Memories: what woke a role, what was said to it, what it said, refusals, and notes from `remember`. Recall ranks importance, recency (10-minute half-life) and keyword overlap; 7 are shown.
- `Save()` returns a string with memories, role-installed behaviors, things Kinloom created and role state; `Load()` restores it (ages are kept relative to the new clock). Store it with the player's save.
- Budget: `budget.maxCallsPerMinute` (global), role `budget.callsPerMinute`, `budget.maxCostPerHour` (needs prices). Over budget → the role's fallback.
- Time limits: a fast-tier call is abandoned after 20 s, a deep one after 60 s (`SessionOptions.FastTimeout`/`DeepTimeout`), and the fallback answers. A rate-limit or server error is retried once. At most 4 questions wait for a role that is already thinking; more get the fallback at once.
- A saved behavior gets its role's permissions as declared when the save is loaded, never the ones stored in the save.

## 9. Using it from a game

### Godot (C# or GDScript)
`kinloom init` installs `addons/kinloom/` and the autoload `Kinloom`. At startup it reads `kinloom.json` and the manifest folder.

| Call | Does |
|---|---|
| `Kinloom.Bind(id, node)` | links a declared thing to a node: properties are read from the node (`node.get(name)`, or a `_kinloom_state()` method returning a Dictionary), params written with `node.set`, functions called with `node.callv` (arguments in declared order). |
| `Kinloom.Unbind(id)` | stops reading/steering it. A freed node is unbound automatically; a thing from the manifest stays declared, so a new node can be bound later. |
| `Kinloom.Spawned(id, type, node)` | declares and binds a thing the game created itself. `Kinloom.Despawned(id)` removes it. |
| `Kinloom.EmitEvent(type, data)` / `Kinloom.EmitEventSeenBy(type, data, [ids])` | reports what happened. |
| `Kinloom.SetFact(key, value)` | writes a global fact on `world`. |
| `Kinloom.Ask(role, text, from)` | talks to a role; the answer comes with the `Replied(role, text)` signal. |
| `Kinloom.Generate(generator, context)` | the result comes with `Generated(generator, json)`. |
| `Kinloom.Wake(role)` | makes a role think now. |
| `Kinloom.SaveState()` / `Kinloom.LoadState(state)` | persistence. |
| `Kinloom.ResolveValidation(id, ok, reason)` | answers `ValidateRequested(id, generator, json)`. |
| `Kinloom.StatsJson()` / `Kinloom.DescribeThing(id)` / `Kinloom.JournalText(n)` | calls, tokens and cost so far / a thing's state as Kinloom sees it / the last journal lines. |

Signals: `Said(role, thing, text, to)`, `Replied(role, text)`, `Generated(generator, json)`, `MediaReady(kind, path, prompt, thing)`, `CreateRequested(type, id, args)` (when the type has no `engine.godot.scene`), `ValidateRequested(id, generator, json)`.
Creation: with `engine.godot.scene` (and optional `parent`), the addon instantiates the scene, sets the creation args as properties, adds it and binds it. Destroy frees nodes Kinloom created.
In debug builds the addon serves the inspector on `debugPort` (open with `kinloom inspect`). C# code can use `Kinloom.Session` (a `KinloomSession`) directly.

### JavaScript / TypeScript (Phaser, Three.js, Babylon, PixiJS, Node, Deno, Bun)
`kinloom init` copies `kinloom/client/kinloom.js` (+ `kinloom.d.ts`), no dependencies. Run `kinloom serve`, then:
```js
import { Kinloom } from "./kinloom/client/kinloom.js";
const kl = await Kinloom.connect();                        // ws://localhost:7717/ws
kl.handle("say", e => showLine(e.thing, e.text));           // return nothing = ok, a string = refused (with that reason)
kl.handle("set", e => { things[e.thing][e.member] = e.args.value; });
await kl.declare(manifest);
// each frame: kl.update(id, props); kl.event(type, data); kl.frame(timeSeconds);
const { reply } = await kl.ask("guide", playerText, "player");
```
The page must be served from `localhost` (Kinloom refuses WebSocket connections from other web origins).

### Python (Pygame, Ren'Py, Panda3D, Arcade, Blender...)
`kinloom init` copies `kinloom/client/kinloom_client.py` (standard library only). Effects are applied on your thread inside `frame()`/`tick()`/`poll()`:
```python
from kinloom_client import Kinloom
kl = Kinloom.connect()
kl.handle("say", lambda e: show_line(e["thing"], e["text"]))
kl.declare(manifest)
# each frame: kl.update(id, props); kl.event(type, data); kl.frame(t)
future = kl.ask_async("guide", player_text, "player")      # keep playing; future.result() when done()
```

### Any other engine or language
Run `kinloom serve` and speak JSON-RPC over `ws://localhost:7717/ws`: see `protocol.md` (the two clients above are short references to port). A C# game can also host `KinloomSession` in-process: `Declare`, `Update`, `Emit`, `Pump(time)` → apply effects → `Resolve`, `Ask`, `Generate`, `RequestMedia`, `Save`/`Load`. Things appearing at run time (declaring only `things`) are checked on their own, so spawning thousands stays fast.

## 10. Tests (`kinloom/tests/*.test.json`)

```json
{
  "description": "What this proves.",
  "script": { "role:gatekeeper": ["{\"actions\":[{\"tool\":\"invoke\",\"args\":{\"thing\":\"self\",\"function\":\"open\",\"args\":{}}}]}"] },
  "resolve": "ok",
  "steps": [
    { "time": 1, "update": { "thing": "gate_a", "props": { "locked": false } } },
    { "time": 2, "event": { "type": "gate_hit", "data": { "by": "friend" } } },
    { "time": 3, "ask": { "role": "gatekeeper", "input": "Let me in!", "from": "player" } },
    { "wait": 30 },
    { "generate": { "generator": "some_generator", "context": {} } }
  ],
  "expect": [
    { "effect": { "kind": "invoke", "thing": "gate_a", "member": "open" } },
    { "noEffect": { "kind": "destroy" } },
    { "refused": "part of a refusal reason" },
    { "reply": "part of a reply" },
    { "journal": "part of any journal line" },
    { "generated": "some_generator" },
    { "fallback": false }
  ]
}
```

`script` keys are call names: `role:<id>`, `generator:<id>`, or `*`. Answers are consumed in order (a repair call takes the next one). Answers use the JSON form of tool calls: `{"thought": "...", "actions": [{"tool": "<tool>", "args": {...}}]}`. Tools: `set_param{thing,param,value}`, `invoke{thing,function,args}`, `create{type,args,name}`, `destroy{thing}`, `say{text,to}`, `set_behavior{id,owner,rules}`, `remove_behavior{id}`, `remember{text,importance}`, `generate{generator,brief}`, `request_media{kind,prompt,spec}`.

## 11. CLI and MCP

`kinloom init | doctor [--ping] | validate | test | serve [--port] [--no-manifest] | inspect [--port] | mcp`.
MCP tools (`kinloom mcp`): `scan_project`, `validate`, `simulate_role` (prompt preview, or `live` with the real model), `attack_guardrails` (worst-case model + injections; `escapes` must be 0), `attach` (running game), `estimate_cost` (declared prices only), `run_tests`.
