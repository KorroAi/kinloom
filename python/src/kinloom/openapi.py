"""The HTTP API of `kinloom serve` as an OpenAPI 3.1 description: served at GET /v1/openapi.json and shipped as
kit/openapi.json, so a coding agent can write a client for an engine Kinloom has none for (or check one).
tests/test_kit.py keeps it in step with server.VERBS.

    python -m kinloom.openapi > src/kinloom/kit/openapi.json      (after changing the API)
"""
import json

from . import __version__

S, N, I, B, O, A = ({"type": "string"}, {"type": "number"}, {"type": "integer"}, {"type": "boolean"}, {"type": "object"},
                    {"type": "array"})
ANY = {}
NAMES = {"type": "array", "items": {"type": "string"}}
ACTIONS = {"type": "array", "items": {"type": "object", "properties": {"tool": S, "args": O}}}
SHARED = {"type": "array", "items": {"type": "object", "properties": {"from": S, "to": S, "text": S, "tag": S}}}
PICTURE = {"type": "string", "description": "a picture the model looks at: base64 or a data URI (PNG, JPEG, GIF, WebP; 8 MB)"}


def _one(*types):
    return {"anyOf": list(types)}


# verb -> (summary, {field: schema}, required fields, {answer field: schema})
POSTS = {
    "character": ("Declare a character (characters in kinloom.json need no call).",
                  {"name": S, "personality": S, "lines": _one(O, NAMES), "offline": _one(S, NAMES),
                   "events": _one(NAMES, O), "tools": _one(O, A, S), "max_words": I, "max_chars": I, "every": N,
                   "language": S, "group": S, "soul": _one(S, B, O), "trust": O, "invent": B, "voice": _one(S, O)},
                  ["name"], {"ok": B}),
    "say": ("An instant line for an event, the facts filled in.", {"name": S, "event": S, "facts": O, "fresh": B, "max_chars": I},
            ["name", "event"], {"text": S, "source": S, "declared": B}),
    "chat": ("A reply in character (stream: true answers with server-sent events {piece} then {done, ...}).",
             {"name": S, "message": S, "facts": O, "speaker": S, "stream": B, "do": B, "max_chars": I, "image": PICTURE},
             ["name", "message"], {"text": S, "source": S, "declared": B, "mood": S, "feeling": N, "gesture": S, "do": ACTIONS}),
    "lore": ("World facts every character takes as true ({} reads them).", {"lines": _one(NAMES, S), "text": S}, [],
             {"lines": I, "lore": NAMES}),
    "soul": ("What a character is and feels: card, mood, bonds, memories, conversation.", {"name": S, "speaker": S},
             ["name"], {"card": O, "ready": B, "mood": O, "bonds": O, "memories": A, "tools": NAMES, "conversation": A}),
    "decide": ("An instant decision shaped like the choices, refreshed in the background.",
               {"name": S, "situation": O, "choices": O, "every": N}, ["name", "choices"], {"decision": O, "declared": B}),
    "act": ("Tool calls the character chose (handed out once).", {"name": S, "situation": ANY, "think": B}, ["name"],
            {"actions": ACTIONS, "declared": B}),
    "create": ("Content shaped like the example (the example is the offline answer).",
               {"what": S, "example": ANY, "context": ANY, "count": I, "instant": B, "image": PICTURE}, ["what", "example"],
               {"value": ANY}),
    "event": ("Something happened; witnesses remember it.",
              {"text": S, "about": _one(NAMES, S), "importance": N, "by": S, "seen_by": NAMES, "tag": S, "impact": N},
              ["text"], {"ok": B}),
    "remember": ("A memory for one character.", {"name": S, "note": S, "importance": N}, ["name", "note"], {"ok": B}),
    "state": ("A live snapshot every call can see.", {"state": O}, ["state"], {"ok": B}),
    "tools": ("The game's tools, declared once; characters use them by name ({} reads the names).", {"tools": O}, [],
              {"tools": NAMES}),
    "prepare": ("For a loading screen: waits until what Kinloom writes ahead is ready.", {"timeout": N}, [],
                {"ready": B, "waiting": I, "online": B}),
    "mind": ("Declare a mind (utility AI the client runs locally); answers its compiled form.",
             {"name": S, "personality": S, "senses": O, "actions": O, "rules": O, "variants": I, "learn": N, "order": NAMES},
             ["name", "senses", "actions"], {"mind": O}),
    "report": ("A mind and how it is doing.", {"name": S}, ["name"], {"mind": O, "report": O, "missing": B}),
    "think": ("Run a mind on one moment.", {"name": S, "senses": O, "who": S}, ["name"], {"action": S, "args": O, "variant": I}),
    "explain": ("Every action's score for one moment.", {"name": S, "senses": O, "who": S}, ["name"],
                {"action": S, "variant": I, "scores": O}),
    "reward": ("How well units' last choices went (minds learn).", {"rewards": {"type": "array", "items": {
        "type": "object", "properties": {"who": S, "mind": S, "variant": I, "id": ANY, "action": S, "reward": N,
                                         "senses": O, "done": B}}}}, ["rewards"], {"versions": O}),
    "meet": ("Two characters share what they know.", {"a": S, "b": S, "k": I}, ["a", "b"], {"shared": SHARED}),
    "spread": ("Rounds of talk in a group.", {"group": S, "rounds": I}, [], {"shared": SHARED}),
    "knows": ("Whether a character knows about a tagged event.", {"name": S, "tag": S}, ["name", "tag"],
              {"knows": B, "notes": A}),
    "opinion": ("What a thinks of b (-1..1).", {"a": S, "b": S}, ["a", "b"], {"opinion": N}),
    "opinions": ("Everything a thinks of others.", {"name": S}, ["name"], {"opinions": O}),
    "feel": ("Move a's opinion of b.", {"a": S, "b": S, "change": N}, ["a", "b"], {"opinion": N}),
    "reputation": ("A group's average opinion of target.", {"target": S, "group": S}, ["target", "group"], {"reputation": N}),
    "speak": ("A line said aloud (WAV, base64); audio \"\" when no voice can speak.", {"name": S, "text": S}, ["text"],
              {"audio": S, "format": S, "seconds": N, "text": S}),
    "listen": ("What was said in a recording (base64; 12 MB).", {"audio": S, "language": S}, ["audio"], {"text": S}),
    "suggest": ("What the player could say now: one reply per example, in its order (the examples are the offline answer).",
                {"name": S, "examples": NAMES, "speaker": S, "facts": O}, ["name", "examples"], {"replies": NAMES}),
    "converse": ("A short exchange between two characters, remembered by both ([] offline).",
                 {"a": S, "b": S, "about": S, "turns": I}, ["a", "b"],
                 {"lines": {"type": "array", "items": {"type": "object", "properties": {"who": S, "text": S}}}}),
    "inspect": ("A snapshot for a debug overlay: characters, minds, calls (admin token).", {}, [],
                {"online": B, "characters": O, "minds": O, "calls": I, "failures": I, "cost": N}),
    "save": ("Everything Kinloom knows about this session, as one text for the game's save slot.", {}, [], {"data": S}),
    "steer": ("What the game decides happens in the character's next reply (the model words it; a secret may come out); "
              "\"\" takes it back.", {"name": S, "text": S}, ["name", "text"], {"ok": B}),
    "load": ("Puts back what save gave (this session's state is replaced; 12 MB).", {"data": S}, ["data"], {"ok": B}),
}

GETS = {
    "/v1/status": ("Mode, model, stats, characters and minds (a player token sees only the mode).", []),
    "/v1/journal": ("What Kinloom did lately (admin token).", [("n", I)]),
    "/v1/stream": ("The journal live, as server-sent events (admin token).", []),
    "/v1/mind": ("A mind and its report (404 when unknown).", [("name", S)]),
    "/v1/soul": ("Like POST /v1/soul.", [("name", S), ("speaker", S)]),
    "/v1/openapi.json": ("This description.", []),
}


def spec():
    session = {"name": "X-Kinloom-Session", "in": "header", "required": False, "schema": S,
               "description": "one per player, match or save (default \"default\"); also \"session\" in the body"}
    paths = {}
    for verb in sorted(POSTS):
        summary, fields, required, answer = POSTS[verb]
        body = {"type": "object", "properties": dict(fields, session=S)}
        if required:
            body["required"] = required
        paths["/v1/" + verb] = {"post": {
            "operationId": verb, "summary": summary, "parameters": [session],
            "requestBody": {"required": True, "content": {"application/json": {"schema": body}}},
            "responses": {
                "200": {"description": "the answer", "content": {"application/json": {"schema": {
                    "type": "object", "properties": answer}}}},
                "400": {"description": "a missing or wrong field: {error}"},
                "401": {"description": "this server needs its token"},
                "429": {"description": "a player over its limits: answer offline"}}}}
    for path in sorted(GETS):
        summary, query = GETS[path]
        paths[path] = {"get": {
            "operationId": "get_" + path.strip("/").replace("/v1/", "").replace(".", "_"), "summary": summary,
            "parameters": [session] + [{"name": n, "in": "query", "required": False, "schema": t} for n, t in query],
            "responses": {"200": {"description": "JSON (text/event-stream for /v1/stream)"}}}}
    return {
        "openapi": "3.1.0",
        "info": {"title": "Kinloom", "version": __version__,
                 "description": "The API of `kinloom serve`: every engine's client speaks it. Local by default (only "
                                "pages from this machine); `--public --token` for an online server. A client answers "
                                "offline itself when the server cannot be reached: the game's lines, offline replies "
                                "and examples."},
        "servers": [{"url": "http://127.0.0.1:7717"}],
        "components": {"securitySchemes": {"token": {"type": "http", "scheme": "bearer",
                                                     "description": "--token (admin) or --player-token (a shipped game)"}}},
        "security": [{}, {"token": []}],
        "paths": paths,
    }


def text():
    return json.dumps(spec(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    import sys
    sys.stdout.write(text())
