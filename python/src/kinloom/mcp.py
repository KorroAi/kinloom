"""`kinloom mcp`: an MCP server on stdio, so any MCP-capable coding agent (Claude Code, Codex, Cursor, Windsurf, Gemini
CLI, Zed, ...) can set up a game, read the instructions, hear a character and check its work.

    claude mcp add kinloom -- kinloom mcp          (other agents: command "kinloom", args ["mcp"])
"""
import contextlib
import io
import json
import os
import sys
import urllib.request

from . import __version__

PROTOCOL = "2025-06-18"

TOOLS = [
    {"name": "kinloom_recipe",
     "description": "Start here for ANY AI request in this game (\"a blacksmith players can talk to\", \"smarter enemies\", "
                    "\"a quest each morning\"...): returns the Kinloom call that does it, the closest ready pattern and the "
                    "code in this game's language. Short; offline; instant.",
     "inputSchema": {"type": "object", "required": ["request"], "properties": {
         "request": {"type": "string", "description": "the feature, in the developer's own words"},
         "engine": {"type": "string", "description": "default: detected"}}}},
    {"name": "kinloom_add",
     "description": "Add a character the player can talk to: writes it into kinloom.json (no declaration code in the game, "
                    "edits apply while it runs) and returns the lines to call it in this game's language. Also adds world "
                    "facts (lore).",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"},
         "soul": {"type": "string", "description": "who they are, in one sentence"},
         "tools": {"type": "string", "description": "what they can do in the game, e.g. \"give(item), follow, refuse_service\""},
         "trust": {"type": "object", "description": "tool -> feeling needed, e.g. {\"give\": 0.3}"},
         "offline": {"type": "string", "description": "what they say with no model"},
         "language": {"type": "string", "description": "the language they speak; \"auto\": the language of whoever talks to them"},
         "strict": {"type": "boolean", "description": "never make up names, places or events"},
         "voice": {"type": "string", "description": "how they sound when they speak, e.g. \"low, tired, warm\""},
         "max_chars": {"type": "integer", "description": "the characters their text box holds: replies never go past it"},
         "lore": {"type": "array", "items": {"type": "string"}, "description": "world facts every character treats as true"}}}},
    {"name": "kinloom_log",
     "description": "What the running Kinloom server did, as text: calls, replies, refusals, errors (after running the game).",
     "inputSchema": {"type": "object", "properties": {"n": {"type": "integer"}, "port": {"type": "integer"}}}},
    {"name": "kinloom_guide",
     "description": "The full Kinloom reference for this game's engine (every call, the rules). For one feature, "
                    "kinloom_recipe is shorter.",
     "inputSchema": {"type": "object", "properties": {
         "engine": {"type": "string", "description": "godot, unity, dotnet, web, python, love, unreal or other (default: detected)"}}}},
    {"name": "kinloom_init",
     "description": "Set up the game folder: installs the Kinloom client for its engine and writes the agent instructions.",
     "inputSchema": {"type": "object", "properties": {
         "engine": {"type": "string", "description": "force an engine (default: detected)"}}}},
    {"name": "kinloom_try",
     "description": "Hear a character before wiring it into the game: lines for an event, a chat reply, a decision, or "
                    "created content, using the developer's model (or offline answers without one).",
     "inputSchema": {"type": "object", "required": ["name"], "properties": {
         "name": {"type": "string"},
         "personality": {"type": "string"},
         "event": {"type": "string", "description": "an event to comment on, e.g. overtake"},
         "facts": {"type": "object", "description": "facts for the line or reply, e.g. {\"who\": \"BLAZE\"}"},
         "lines": {"type": "array", "items": {"type": "string"}, "description": "offline lines with {fact} placeholders"},
         "chat": {"type": "string", "description": "a message to answer (\"\": the character speaks first)"},
         "soul": {"type": "string", "description": "who they are in one sentence: the model writes their inner life (card) "
                                                   "and the reply shows it with their mood"},
         "speaker": {"type": "string", "description": "who talks to them (default player)"},
         "choices": {"type": "object", "description": "decide: choices by example, e.g. {\"strategy\": [\"attack\", \"block\"]}"},
         "create": {"type": "string", "description": "what to create, e.g. 'a dungeon room'"},
         "example": {"description": "the example answer for create (also the offline answer)"}}}},
    {"name": "kinloom_mind",
     "description": "Test a mind (utility AI) before wiring it: runs its rules on moments you give and returns the choice, "
                    "every action's score and each rule's value, plus any rule the mind cannot read. Offline, instant.",
     "inputSchema": {"type": "object", "required": ["senses", "actions", "moments"], "properties": {
         "senses": {"type": "object", "description": "by example: {\"hp\": [0, 1], \"armed\": true, \"mood\": [\"calm\", \"angry\"]}"},
         "actions": {"type": "object", "description": "{\"charge\": {\"speed\": [1.0, 3.0]}, \"retreat\": {}}"},
         "rules": {"type": "object", "description": "{\"retreat\": [\"hp low\"], \"charge\": {\"score\": 0.5, \"when\": [\"dist below 15\"]}}"},
         "moments": {"type": "array", "items": {"type": "object"}, "description": "senses to test, e.g. [{\"hp\": 0.2}]"}}}},
    {"name": "kinloom_check",
     "description": "Check the integration: client installed, characters declared, missing await, API keys in the source, "
                    "server running. Run it after adding AI.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "kinloom_ship",
     "description": "Before a release: model keys inside the game's files, how players reach a model, characters without "
                    "offline answers, spending caps and prices, the content rating; writes a draft of the store's AI "
                    "disclosure (kinloom-ai-disclosure.md) for the developer to review.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "kinloom_status",
     "description": "What the running `kinloom serve` is doing: model, characters, recent lines, decisions, actions, "
                    "refusals, calls and tokens.",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}}},
    {"name": "kinloom_test",
     "description": "Run the game's AI tests (kinloom.tests.json: steps calling say/chat/decide/act/create with checks such "
                    "as max_words, not, tools, different). Write the file first if there is none. replay runs on "
                    "recorded answers (no model, no cost); record keeps the model's answers for that.",
     "inputSchema": {"type": "object", "properties": {
         "file": {"type": "string", "description": "default: kinloom.tests.json"},
         "offline": {"type": "boolean"}, "record": {"type": "string"}, "replay": {"type": "string"}}}},
    {"name": "kinloom_probe",
     "description": "Play a character like a tester would (secrets, manipulation, prompt injection, numbers, repeats, "
                    "other languages) with the game's model and report problems. About 23 model calls.",
     "inputSchema": {"type": "object", "required": ["name"], "properties": {
         "name": {"type": "string"}, "soul": {"type": "string", "description": "for a character not in kinloom.json"}}}},
    {"name": "kinloom_use",
     "description": "Choose where answers come from: \"key\" (an API key from the environment) or the developer's coding "
                    "agent subscription: claude-code, codex, gemini-cli, opencode. Ask the developer first: it spends "
                    "their plan.",
     "inputSchema": {"type": "object", "required": ["what"], "properties": {
         "what": {"type": "string", "enum": ["key", "claude-code", "codex", "gemini-cli", "opencode"]},
         "model": {"type": "string", "description": "the agent's model, e.g. haiku for Claude Code (default: its own)"}}}},
]


def _text(s, error=False):
    return {"content": [{"type": "text", "text": s}], "isError": error}


def _get(url):
    with urllib.request.urlopen(url, timeout=2) as r:
        return json.loads(r.read().decode("utf-8"))


def call(folder, name, args):
    """Runs one tool; returns an MCP tool result. Never raises."""
    from . import init as _init
    try:
        if name == "kinloom_guide":
            engine = args.get("engine") or _init.detect(folder)
            return _text(_init.guide(engine, _client_path(folder, engine), folder) +
                         "\nPatterns: kinloom_recipe finds the ones for a request (all 34 are in KINLOOM.md).")
        if name == "kinloom_recipe":
            from .recipe import recipe
            return _text(recipe(str(args.get("request") or ""), args.get("engine") or _init.detect(folder)))
        if name == "kinloom_add":
            from .add import add
            trust = args.get("trust") if isinstance(args.get("trust"), dict) else {}
            lore = args.get("lore") if isinstance(args.get("lore"), list) else []
            return _text(add(folder, str(args.get("name") or ""), str(args.get("soul") or ""), str(args.get("tools") or ""),
                             ["%s=%s" % (k, v) for k, v in trust.items()], str(args.get("offline") or ""),
                             args.get("language"), bool(args.get("strict")), [str(x) for x in lore],
                             voice=str(args.get("voice") or ""), max_chars=args.get("max_chars")))
        if name == "kinloom_log":
            port = int(args.get("port") or 7717)
            from .cli import _server_get
            try:
                entries = _server_get(port, "/v1/journal?n=%d" % max(1, min(500, int(args.get("n") or 60))))
            except Exception:
                return _text("no Kinloom server on port %d: run the game with `kinloom run -- <command>`" % port, True)
            from .cli import _line
            return _text("\n".join(_line(e) for e in entries.get("entries", [])) or "(nothing yet)")
        if name == "kinloom_init":
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = _init.run(folder, args.get("engine"))
            return _text(buf.getvalue(), code != 0)
        if name == "kinloom_try":
            return _text(_try(folder, args))
        if name == "kinloom_mind":
            from . import minds
            decl = minds.Declaration("mind", "", args.get("senses"), args.get("actions"), args.get("rules"), 1)
            mind = minds.Mind(decl)
            out = {"rule_errors": decl.rule_errors, "moments": []}
            for moment in (args.get("moments") or [])[:50]:
                e = mind.explain(moment)
                out["moments"].append({"senses": moment, "choice": e["action"], "args": mind.think(moment)["args"],
                                       "scores": {a: {"score": v["score"], "rules": dict(zip(v["rules"], v["values"]))}
                                                  for a, v in e["scores"].items()}})
            return _text(json.dumps(out, indent=1), bool(decl.rule_errors))
        if name == "kinloom_check":
            from .check import check
            engine, results = check(folder)
            lines = ["Kinloom check (%s)" % engine] + ["%-5s %s" % (lvl.upper(), msg) for lvl, msg in results]
            return _text("\n".join(lines), any(lvl == "error" for lvl, _ in results))
        if name == "kinloom_ship":
            from . import ship
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = ship.run(folder)
            return _text(buf.getvalue()[-20000:], code != 0)
        if name in ("kinloom_test", "kinloom_probe", "kinloom_use"):
            buf = io.StringIO()                    # stdout is this server's channel: the tools' output is captured
            with contextlib.redirect_stdout(buf):
                if name == "kinloom_test":
                    from . import testing
                    code = testing.main(folder, args.get("file"), args.get("record"), args.get("replay"),
                                        bool(args.get("offline")), True)
                elif name == "kinloom_probe":
                    from . import probe
                    code = probe.main(folder, str(args.get("name") or ""), args.get("soul"), 1, True)
                else:
                    from .cli import main as cli_main
                    code = cli_main(["use", str(args.get("what") or "")] + (["--model", str(args["model"])] if args.get("model")
                                                                           else []) + ["--dir", folder])
            return _text(buf.getvalue()[-20000:], code != 0)
        if name == "kinloom_status":
            url = (args.get("url") or "http://127.0.0.1:7717").rstrip("/")
            try:
                status = _get(url + "/v1/status")
                journal = _get(url + "/v1/journal?n=40")
            except Exception:
                return _text("kinloom serve is not running at %s. Start it with `kinloom serve` in the game folder." % url, True)
            return _text(json.dumps({"status": status, "recent": journal}, indent=1)[:20000])
        return _text("unknown tool %s" % name, True)
    except Exception as e:  # a tool failure is reported to the agent, never crashes the server
        return _text("%s: %s" % (type(e).__name__, e), True)


def _client_path(folder, engine):
    for rel in ("src/kinloom/kinloom.ts", "kinloom/kinloom.ts", "src/kinloom/kinloom.js", "kinloom/kinloom.js", "Assets/Kinloom/Kinloom.cs", "Kinloom/Kinloom.cs", "addons/kinloom",
                "kinloom.lua", "kinloom/kinloom.lua", "src/kinloom.rs", "src/main/java/kinloom/Kinloom.java", "src/kinloom.hpp",
                "kinloom.hpp"):
        if os.path.exists(os.path.join(folder, rel)):
            return rel
    return None


def _try(folder, args):
    from .brain import Brain
    brain = Brain(memory_path=None, folder=folder)
    try:
        s = brain.status()
        out = ["model: %s" % ("%s (%s)" % (s["provider"], s["model"]) if s["mode"] == "online" else "none, offline answers")]
        name = str(args["name"])
        facts = args.get("facts") if isinstance(args.get("facts"), dict) else {}
        lines = args.get("lines") if isinstance(args.get("lines"), list) else None
        event = args.get("event")
        brain.character("try", name, args.get("personality") or "", lines=lines,
                        events={event: sorted(facts)} if event else None, soul=args.get("soul") or None)
        shown = False
        if args.get("soul"):
            brain.wait_idle(30)
            out.append("soul: %s" % json.dumps(brain.soul("try", name)["card"], ensure_ascii=False))
        if isinstance(args.get("chat"), str) and (args["chat"] or args.get("soul")):
            speaker = str(args.get("speaker") or "player")
            out.append("%s: %s" % (name, brain.chat("try", name, args["chat"], facts, speaker) or "(nothing)"))
            out.append("mood: %s, feeling toward %s: %+.2f" % (brain.soul("try", name)["mood"]["word"], speaker,
                                                              brain.opinion("try", name, speaker)))
            shown = True
        if isinstance(args.get("choices"), dict):
            brain.decide("try", name, facts, args["choices"])
            brain.wait_idle(20)
            out.append("decides: %s" % json.dumps(brain.decide("try", name, facts, args["choices"])))
            shown = True
        if args.get("create"):
            example = args.get("example", "a short text")
            out.append("created: %s" % json.dumps(brain.create("try", args["create"], example, facts), ensure_ascii=False))
            shown = True
        if event or not shown:
            event = event or "something happens"
            if not args.get("event"):
                brain._refill("try", brain._char("try", name), event, sorted(facts))
            brain.wait_idle(20)
            for _ in range(3):
                out.append("%s: %s" % (name, brain.say("try", name, event, facts) or "(nothing)"))
        st = brain.stats()
        out.append("%d call(s), %d tokens" % (st["calls"], st["input_tokens"] + st["output_tokens"]))
        return "\n".join(out)
    finally:
        brain.close()


def handle(folder, msg):
    """One JSON-RPC message in, one response out (None for notifications)."""
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        return None
    if method == "initialize":
        result = {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "kinloom", "version": __version__},
                  "instructions": "Kinloom adds AI to games in any engine. Call kinloom_guide before writing any AI "
                                  "feature, kinloom_init to set up the game, kinloom_check after."}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        result = call(folder, params.get("name"), params.get("arguments") or {})
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found: %s" % method}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(folder=".", stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    folder = os.path.abspath(folder)
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            with contextlib.redirect_stdout(sys.stderr):  # nothing but JSON-RPC may reach stdout
                reply = handle(folder, msg)
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
    return 0
