"""`kinloom add NAME "who they are"`: a character the player can talk to, in one command. Writes it into kinloom.json
(no declaration code in the game, any engine) and prints the lines to call it in the game's own language."""
import json
import os
import re

from . import config as _config

SNIPPETS = {
    "gdscript": '''# The player talks to {name} (text from a LineEdit; "" when they walk up: {name} speaks first). ~1 s, the game runs on.
var reply: String = await Kinloom.chat("{name}", text, {{"gold": gold}}, player_name)
for a in Kinloom.act("{name}", {{}}, false):          # what {name} decided while talking, validated
	if a.tool == "give": give_item(a.args.item)
var soul = await Kinloom.soul("{name}", player_name)     # soul.mood.word, soul.gesture: animations
# No code at all: an AIDialogue node with character_name = "{name}", then call open().''',
    "csharp": '''// The player talks to {name} ("" when they walk up: {name} speaks first). ~1 s: awaited, the game runs on.
string reply = await kl.Chat("{name}", text, new Dictionary<string, object> {{ ["gold"] = gold }}, playerName);
foreach (var a in kl.Act("{name}", null, false)) if (a.Tool == "give") GiveItem((string)a.Args["item"]);
var soul = await kl.Soul("{name}", playerName);      // soul["mood"], soul["gesture"]: animations''',
    "js": '''// The player talks to {name} ("" when they walk up: {name} speaks first). Streamed as it is written.
const reply = await kl.chat("{name}", text, {{ gold }}, playerName, (piece) => (bubble.textContent += piece));
for (const a of kl.act("{name}", {{}}, false)) if (a.tool === "give") giveItem(a.args.item);   // decided while talking
const soul = await kl.soul("{name}", playerName);     // soul.mood.word, soul.gesture: animations
// Ready UI: import {{ talkBox }} from "./kinloom/kinloom-talk.js"; talkBox(kl, "{name}", {{ speaker: playerName }}).open();''',
    "python": '''# Pygame / pygame-ce: a ready dialogue box (typing, Enter sends, Esc closes, replies stream in, never blocks).
from kinloom.talk import PygameTalkBox
box = PygameTalkBox(kl, "{name}", speaker=player_name, facts=lambda: {{"gold": gold}},
                    on_action=lambda tool, args: give_item(args["item"]))   # what {name} decides while talking
# events:  if e.type == pygame.KEYDOWN and e.key == pygame.K_t and not box.is_open: box.open()   ({name} speaks first)
#          if box.handle(e): continue          # the box used the key: not for the game
# frame:   box.update(); box.draw(screen)      # box.mood, box.gesture: animations
# Other Python engines: kinloom.talk.Talk (same, without drawing: talk.send(text), talk.update(), talk.lines).''',
    "lua": '''-- The player talks to {name} ("" when they walk up: {name} speaks first); the reply arrives in the callback.
kl:chat("{name}", text, {{ gold = gold }}, function(reply) dialogue = reply end, player_name)
for _, a in ipairs(kl:act("{name}", {{}}, false)) do if a.tool == "give" then give_item(a.args.item) end end
kl:soul("{name}", player_name, function(soul) mood = soul and soul.mood.word end)''',
    "rust": '''// The player talks to {name} ("" when they walk up: {name} speaks first). Blocking ~1 s: run it on a thread.
let reply = kl.chat_as("{name}", &text, obj! {{ "gold" => gold }}, &player_name);
for a in kl.act_with("{name}", obj! {{}}, false) {{ if a.tool == "give" {{ give_item(a.args.get("item").as_str()); }} }}
let soul = kl.soul("{name}", &player_name);          // Option<Json>: mood, gesture''',
    "java": '''// The player talks to {name} ("" when they walk up: {name} speaks first). ~1 s: off the game thread.
String reply = kl.chat("{name}", text, map("gold", gold), playerName);
for (Kinloom.Action a : kl.act("{name}", map(), false)) if (a.tool.equals("give")) giveItem((String) a.args.get("item"));
Map<String, Object> soul = kl.soul("{name}", playerName);   // mood, gesture''',
    "cpp": '''// The player talks to {name} ("" when they walk up: {name} speaks first). ~1 s: off the game loop.
std::string reply = kl.chat("{name}", text, obj({{{{"gold", gold}}}}), player_name);
for (auto& a : kl.act("{name}", obj({{}}), false)) if (a.tool == "give") give_item(a.args["item"].str());
kinloom::Json soul = kl.soul("{name}", player_name);   // soul["mood"]["word"], soul["gesture"]''',
    "http": '''POST /v1/chat {{"name": "{name}", "message": "<what the player said, or \\"\\">", "speaker": "<player name>", "facts": {{}}}}
     -> {{"text", "mood", "feeling", "gesture"}}      (add "stream": true for server-sent events)
POST /v1/act  {{"name": "{name}", "think": false}}  -> {{"actions": [{{"tool", "args"}}]}}  (decided while talking)''',
}
LANGUAGE = {"godot": "gdscript", "unity": "csharp", "dotnet": "csharp", "web": "js", "python": "python", "love": "lua",
            "defold": "lua", "rust": "rust", "java": "java", "cpp": "cpp", "unreal": "cpp", "other": "http"}


def parse_tools(text):
    """"give(item), follow, sell(item, price)" -> {"give": {"item": "text"}, "follow": {}, "sell": {...}}."""
    tools = {}
    for m in re.finditer(r"([A-Za-z_]\w*)\s*(?:\(([^)]*)\))?", text or ""):
        args = {}
        for a in (x.strip() for x in (m.group(2) or "").split(",")):
            if re.match(r"^[A-Za-z_]\w*$", a):
                args[a] = [0, 100] if a in ("price", "amount", "count", "gold", "quantity") else "text"
        tools[m.group(1)] = args
    return tools


def parse_trust(items):
    """["give=0.3"] -> {"give": 0.3}"""
    out = {}
    for item in items or []:
        name, _, value = str(item).partition("=")
        try:
            out[name.strip()] = max(-1.0, min(1.0, float(value)))
        except ValueError:
            raise ValueError("--trust takes tool=feeling, e.g. give=0.3 (got %r)" % item)
    return out


def update_config(folder, name, entry, lore=()):
    """Adds or replaces one character (and appends lore) in kinloom.json, keeping everything else. Returns the path."""
    path = os.path.join(folder, _config.FILE)
    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise _config.ConfigError("%s is not valid JSON (%s): fix it first, nothing was changed" % (path, e))
        if not isinstance(data, dict):
            raise _config.ConfigError("%s must be a JSON object: nothing was changed" % path)
    chars = data.get("characters") if isinstance(data.get("characters"), dict) else {}
    if name:
        chars[name] = entry
        data["characters"] = chars
    if lore:
        facts = data.get("lore") if isinstance(data.get("lore"), list) else []
        data["lore"] = facts + [x for x in lore if x not in facts]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    return path


def add(folder, name, soul="", tools="", trust=(), offline="", language=None, strict=False, lore=(), engine=None, voice="",
        max_chars=None):
    """Writes the character into kinloom.json and returns the text to show: what was written and the code to call it."""
    from . import init as _init
    name = (name or "").strip()
    if not name and not lore:
        raise ValueError("a name is needed (or --lore facts)")
    entry = {}
    if name:
        entry["soul"] = soul.strip() if soul and soul.strip() else True
        entry["offline"] = offline or "..."
        t = parse_tools(tools)
        if t:
            entry["tools"] = t
        tr = parse_trust(trust)
        unknown = [k for k in tr if k not in t]
        if unknown:
            raise ValueError("--trust names tools that are not in --tools: %s" % ", ".join(unknown))
        if tr:
            entry["trust"] = tr
        if language:
            entry["language"] = language
        if strict:
            entry["invent"] = False
        if voice and voice.strip():
            entry["voice"] = voice.strip()
        if max_chars:
            n = int(max_chars)
            if n < 10:
                raise ValueError("--max-chars must be at least 10 (the characters a text box holds)")
            entry["max_chars"] = n
    path = update_config(folder, name, entry, [x.strip() for x in lore if x and x.strip()])
    engine = engine or _init.detect(folder)
    lang = LANGUAGE.get(engine, "http")
    out = ["kinloom.json: %s%s" % (("character %s " % name) if name else "", "and %d world fact(s)" % len(lore) if lore else "written"),
           "(%s)" % os.path.abspath(path)]
    if name:
        out += ["", "No declaration code needed: every engine and session gets %s from kinloom.json (edits apply while the game runs)." % name,
                "Call it from the game (%s):" % engine, "", SNIPPETS[lang].format(name=name)]
        if entry.get("tools") and not entry.get("trust"):
            out += ["", "Tip: players will try to talk %s into using its tools; bound them with --trust %s=0.3." % (name, next(iter(entry["tools"])))]
    return "\n".join(out)
