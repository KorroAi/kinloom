# Kinloom protocol

The same contract serves every engine and language. A C# game can host the runtime in-process (`KinloomSession`); anything else connects to `kinloom serve` over a local WebSocket and speaks JSON-RPC 2.0. This page is enough to write a client in any language.

## Connection

- Start the service: `kinloom serve` (default port 7717, `--port` to change). It listens on `localhost` only.
- Browsers: only pages served from this machine (`localhost`, `127.0.0.1`) may open the WebSockets; other web origins get HTTP 403, so a web page you visit cannot use your key. Native clients send no `Origin` and are accepted.
- A message larger than 16 MB closes the connection.
- Ready-made clients: `clients/javascript/kinloom.js` (browser, Node 22+, Deno, Bun) and `clients/python/kinloom_client.py` (standard library only); `kinloom init` copies the right one into JavaScript/TypeScript and Python projects.
- Game connection: `ws://localhost:7717/ws`. Each connection gets its own session (its own world, roles, memory).
- Inspector: `http://localhost:7717/` in a browser. Tools (MCP `attach`, the inspector) use `ws://localhost:7717/debug`.
- Messages are UTF-8 JSON text frames, one JSON-RPC message per frame.

JSON-RPC in short: a **request** has `id`, `method`, `params` and gets exactly one response with the same `id` (`result` or `error`). A **notification** has no `id` and gets no response. Kinloom pushes notifications of its own (`effects`, and `journal` on debug connections).

## The loop

1. `declare` your manifest (types, things, events, roles, behaviors, generators). Fix any returned errors.
2. Every frame (or 10–30 times per second): send `update` for things whose properties changed, `event` for what happened, then `tick` with the game time.
3. Apply every effect you receive (from `tick` responses and `effects` notifications), then send `resolve` with the outcome.
4. When the player talks to a character, or you need content, send `ask` or `generate` and wait for the response while you keep ticking.

Game time is yours: seconds since whatever start you like, never decreasing.

## Methods (client → Kinloom)

| Method | Params | Result |
|---|---|---|
| `declare` | `manifest`: object or JSON string; `source`?: name for error messages | `{ errors: [{path, message}] }` — nothing is applied when errors is not empty |
| `update` | `thing`: id, `props`: object of property/param values | none |
| `event` | `type`, `data`?: object, `perceivedBy`?: [thing ids] (omit = public), `time`?, `importance`? (0–1) | none |
| `tick` | `time`: game seconds | as a request: `{ effects: [Effect] }`; as a notification: effects are pushed with an `effects` notification |
| `resolve` | `id`: effect id, `status`: `ok` \| `failed` \| `refused`, `reason`?, `value`? | none |
| `ask` | `role`, `input`: text (player speech, a question...), `from`?: who speaks | `{ reply, usedFallback, error, effects: [Effect] }` |
| `generate` | `generator`, `context`?: object | `{ ok, value, usedFallback, errors: [string] }` |
| `media` | `kind`, `prompt`, `spec`?: object (`format`, size...) | `{ ok, path, format, error, cached }` |
| `bind` / `unbind` | `thing` | none — only needed when the session requires binding |
| `remove` | `thing` | `{ removed }` — the game destroyed a thing |
| `save` | — | `{ state }`: an opaque string to store with the player's save |
| `load` | `state` | none |
| `stats` | — | counters: calls, failures, repairs, fallbacks, refusals, effects, tokens, `cost` (null without declared prices) |
| `snapshot` | — | things, roles, behaviors, generators, media kinds, stats, last 300 journal entries |
| `setMission` | `role`, `mission` | none — live edit (inspector) |

Errors: `-32700` parse error, `-32600` invalid request, `-32601` unknown method, `-32602` invalid params (the message names the param), `-32603` internal error.

## Notifications (Kinloom → client)

- `effects` — `{ items: [Effect] }`. Sent when model work finishes between ticks, and after `tick` notifications.
- `journal` — one journal entry (debug connections only).

## Effect

```json
{ "id": 12, "kind": "set", "thing": "truck_2", "member": "aggression", "args": { "value": 0.9 },
  "source": "role:rex", "text": null, "time": 41.5 }
```

| kind | Apply it by | `member` | `args` |
|---|---|---|---|
| `set` | writing the param on the thing | param | `{ value }` |
| `invoke` | calling the function | function | named arguments, already validated, defaults filled |
| `create` | spawning a thing of that type; use `thing` as its id | type | `{ args: {...}, name? }` |
| `destroy` | removing the thing | — | — |
| `say` | showing/speaking `text` for the thing (subtitles, bubble, TTS) | — | `{ to? }` |
| `media` | loading the file at `args.path` | media kind | `{ path, format, prompt }` |
| `validate` | checking `args.value` with your own rules (generators with `gameValidate`) | generator id | `{ value }` |

Content a role asked a generator for arrives as `invoke` on the built-in thing `world`, member `generated`, args `{ generator, value, source }`.

Always `resolve` each effect: `ok` when applied, `refused` with a reason when your own rules said no (the AI learns from the reason), `failed` when something broke. Unresolved effects expire after 10 game seconds.

## Minimal client (Python, for illustration)

```python
import json, itertools, websocket  # pip install websocket-client

ws = websocket.create_connection("ws://localhost:7717/ws")
ids = itertools.count(1)

def request(method, **params):
    i = next(ids)
    ws.send(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == i:
            return msg.get("result")
        handle_notification(msg)  # effects pushed meanwhile

def handle_notification(msg):
    if msg.get("method") == "effects":
        for effect in msg["params"]["items"]:
            apply_and_resolve(effect)

def apply_and_resolve(effect):
    ok = game_apply(effect)  # your code
    ws.send(json.dumps({"jsonrpc": "2.0", "method": "resolve",
                        "params": {"id": effect["id"], "status": "ok" if ok else "refused"}}))

print(request("declare", manifest=open("kinloom/game.json").read()))
for effect in request("tick", time=0.0)["effects"]:
    apply_and_resolve(effect)
```

A production client keeps one reader thread that routes responses by `id` and handles `effects` notifications, like `RemoteSession` in `src/Kinloom.Runtime/Protocol/RemoteSession.cs`.
