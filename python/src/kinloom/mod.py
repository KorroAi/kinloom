"""`kinloom hooks <game>`: where Kinloom plugs into a game whose source you do not have (a mod). For .NET games (Unity
Mono's `Assembly-CSharp.dll`, MonoGame, FNA, XNA, any .NET game) it reads the game's own code with REA (Reverse Engineer
Anything, an optional tool: https://github.com/morluto/rea) and lists the methods where the game makes a line, a reply,
a choice or content, with the Kinloom call for each and a Harmony patch to start from. Static: the game is never run.
Kinloom never needs REA for anything else; without it this command says how to get it."""
import json
import os
import re
import shlex
import shutil
import struct
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
GUIDE = os.path.join(HERE, "kit", "mod.md")
REA_URL = "https://github.com/morluto/rea"
INSTALL = ("REA (Reverse Engineer Anything, MIT, Node.js 22.19+ / 24.11+) reads the game's code: `npm install --global "
           "rea-agents` gives the `rea` command, or set KINLOOM_REA to the command that runs it (e.g. "
           "`node C:/tools/rea/node_modules/rea-agents/scripts/rea.mjs`). Coding agents can also use it as an MCP "
           "server: `npx rea-agents setup`. " + REA_URL)

# Assemblies every .NET game ships that are not the game's own code.
_FRAMEWORK = re.compile(r"^(system|microsoft|mscorlib|netstandard|mono|unity|unityengine|0harmony|harmony|monomod|"
                        r"newtonsoft|steamworks|fna|monogame|xna|sharpdx|nvorbis|galaxy|discord|bepinex|melonloader|"
                        r"il2cpp|assembly-csharp-firstpass|dotween|rewired|fmod|com\.unity|cinemachine|textmeshpro|"
                        r"windowsbase|presentation|accessibility)", re.I)

# Words in a method's or type's name, by what Kinloom would do there.
LINE = set("say says said greet greeting greetings bark barks line lines talk talks speak speaks speech dialog dialogs "
           "dialogue dialogues chat chats reply replies answer answers respond response message messages subtitle "
           "subtitles conversation converse quote quotes comment comments taunt taunts shout hello farewell goodbye "
           "introduce intro text texts phrase phrases rumor rumour gossip ask asks".split())
CHOICE = set("decide decides decision choose chooses choice think thinks pick picks select selects plan plans strategy "
             "behaviour behavior tactic tactics target next act ai brain".split())
CONTENT = set("generate generates create creates spawn spawns build builds roll rolls random level levels room rooms map "
              "maps quest quests item items loot name names describe description title titles story stories riddle "
              "riddles book books recipe recipes".split())
PEOPLE = set("npc npcs character characters villager villagers merchant merchants shop shopkeeper vendor trader guard "
             "guards companion companions ally allies enemy enemies boss bosses dialogue dialog conversation speaker "
             "person people citizen citizens innkeeper actor actors creature creatures mob mobs ai brain narrator "
             "announcer commentator king queen priest bartender".split())
REPLY = set("answer answers reply replies respond ask asks chat chats converse conversation".split())
# Calls that put text on screen: a method calling them shows what it makes.
SHOWS = re.compile(r"^(set_text|settext|set_message|writeline|write|print|show\w*|display\w*|say|speak|log)$", re.I)


class HookError(Exception):
    pass


def rea_command(env=None):
    """The command that runs REA: KINLOOM_REA, else `rea` on PATH, else None."""
    env = os.environ if env is None else env
    own = (env.get("KINLOOM_REA") or "").strip()
    if own:
        return [p.strip('"\'') for p in shlex.split(own, posix=os.name != "nt")]
    found = shutil.which("rea")
    return [found] if found else None


def is_managed(path):
    """True for a .NET assembly (a PE file with a CLI header), False for native code, None if not a PE file."""
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return None
    if len(head) < 0x40 or head[:2] != b"MZ":
        return None
    pe = struct.unpack_from("<I", head, 0x3C)[0]
    if pe + 24 > len(head) or head[pe:pe + 4] != b"PE\0\0":
        return None
    opt = pe + 24
    magic = struct.unpack_from("<H", head, opt)[0]
    dirs = opt + (96 if magic == 0x10B else 112 if magic == 0x20B else -1)
    if dirs < opt or dirs + 15 * 8 > len(head):
        return None
    rva, size = struct.unpack_from("<II", head, dirs + 14 * 8)
    return bool(rva and size)


def find_code(path):
    """The game's own .NET assembly in a file or a game folder."""
    path = os.path.abspath(path)
    if os.path.isfile(path):
        kind = is_managed(path)
        if kind is None:
            raise HookError("%s is not a program or library file (.dll / .exe)." % path)
        if not kind:
            raise HookError(_native(path))
        return path
    if not os.path.isdir(path):
        raise HookError("no such file or folder: %s" % path)
    for name in sorted(os.listdir(path)):
        managed = os.path.join(path, name, "Managed")
        if name.endswith("_Data") and os.path.isdir(managed):
            unity = os.path.join(managed, "Assembly-CSharp.dll")
            if os.path.isfile(unity):
                return unity
    if os.path.isfile(os.path.join(path, "GameAssembly.dll")):
        raise HookError("This is a Unity IL2CPP build: its C# was compiled to native code (GameAssembly.dll), so there "
                        "is no .NET code to read. Il2CppDumper or Cpp2IL recover the class and method names; then "
                        "BepInEx 6 (IL2CPP) or MelonLoader patch them. See `kinloom hooks --guide`.")
    found = []
    for root, dirs, files in os.walk(path):
        if root[len(path):].count(os.sep) >= 2:
            dirs[:] = []
        for f in files:
            if f.lower().endswith((".dll", ".exe")) and not _FRAMEWORK.match(f):
                full = os.path.join(root, f)
                if is_managed(full):
                    found.append((os.path.getsize(full), full))
    if not found:
        raise HookError("No .NET game code in %s. A native game (C++, Unreal, a custom engine) has no methods to read "
                        "here: use its mod tools (Lua, scripts, a script hook) or REA's native analysis (Ghidra, IDA or "
                        "Hopper). See `kinloom hooks --guide`." % path)
    found.sort(reverse=True)
    return found[0][1]


def _native(path):
    return ("%s is native code, not .NET: there are no methods to read here. Use the game's mod tools (Lua, scripts, a "
            "script hook) or REA's native analysis (Ghidra, IDA or Hopper). See `kinloom hooks --guide`." % path)


def scan(path, rea=None, timeout=600):
    """REA's reading of a .NET assembly: types, methods with signatures, and who calls what."""
    rea = rea or rea_command()
    if not rea:
        raise HookError("REA is not installed. " + INSTALL)
    try:
        r = subprocess.run(rea + ["inspect-managed-members", path, "--json"], capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise HookError("REA did not start (%s). %s" % (" ".join(rea), INSTALL))
    except subprocess.TimeoutExpired:
        raise HookError("REA took more than %d s on %s." % (timeout, path))
    out = r.stdout.decode("utf-8", "replace")
    if r.returncode != 0:
        err = (r.stderr.decode("utf-8", "replace") or out).strip()
        raise HookError("REA failed on %s (exit %d): %s" % (path, r.returncode, err[-1500:]))
    try:
        data = json.loads(out)
    except ValueError:
        raise HookError("REA's answer is not JSON: %s" % out[:300])
    found = data.get("normalized_result", data) if isinstance(data, dict) else None
    if not isinstance(found, dict) or not isinstance(found.get("methods"), list):
        raise HookError("REA's answer has no methods (REA %s?)" % (data.get("provider", {}).get("version", "?")
                                                                   if isinstance(data, dict) else "?"))
    return found


def words(name):
    return [w.lower() for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name or "")]


def candidates(found, top=8):
    """The methods where Kinloom fits, best first: [{type, method, params, returns, call, score, why}]."""
    shows = {}
    for e in found.get("call_edges") or []:
        caller, target = e.get("caller") or "", e.get("target_name") or ""
        if SHOWS.match(target):
            shows.setdefault(caller, set()).add(target)
    rows = {}           # TypeDef row -> name, to read "class:8" (a coded index: row 2 of TypeDef) as "LanternRow.Player"
    nested = set()      # types declared inside another (REA gives their short name; Harmony finds them by it)
    for t in found.get("types") or []:
        if isinstance(t.get("flags"), int) and t["flags"] & 7 >= 2:
            nested.add(t.get("full_name") or t.get("name"))
        try:
            rows[int(str(t.get("token")), 16) & 0xFFFFFF] = t.get("full_name") or t.get("name")
        except ValueError:
            pass

    def named(p):
        m = re.match(r"^(class|valuetype):(\d+)$", p)
        if not m:
            return p
        n = int(m.group(2))
        return rows.get(n >> 2, m.group(1)) if n & 3 == 0 else m.group(1)

    out = []
    for m in found["methods"]:
        name, owner = m.get("name") or "", m.get("declaring_type") or ""
        if not name or "<" in name or "<" in owner or name in (".ctor", ".cctor") or name.startswith(("add_", "remove_")):
            continue
        sig = m.get("signature") or {}
        params = [named(str(p)) for p in sig.get("parameter_types") or []]
        returns = named(str(sig.get("return_type") or "void"))
        if "`" in owner or sig.get("generic_parameter_count") or any(t.startswith(("var:", "mvar:")) for t in params + [returns]):
            continue    # generic: Harmony patches concrete methods, not an open generic one
        own = words(name[4:] if name.startswith(("get_", "set_")) else name)
        kind = words(owner.split(".")[-1])
        why, score = [], 0
        line, choice, content = LINE.intersection(own), CHOICE.intersection(own), CONTENT.intersection(own)
        people = PEOPLE.intersection(kind)
        if line:
            score += 3
            why.append("name: %s" % ", ".join(sorted(line)))
        if choice:
            score += 2
            why.append("name: %s" % ", ".join(sorted(choice)))
        if content:
            score += 2
            why.append("name: %s" % ", ".join(sorted(content)))
        if not score:
            continue
        if people:
            score += 2
            why.append("type: %s" % ", ".join(sorted(people)))
        text_out = returns == "string"
        text_in = "string" in params
        if line and text_out:
            score += 2
            why.append("returns text")
        elif line and text_in and returns == "void":
            score += 1
            why.append("takes the text")
        elif (choice or content) and returns != "void":
            score += 1
        caller = "%s.%s" % (owner, name)
        if caller in shows:
            score += 2
            why.append("shows it: %s" % ", ".join(sorted(shows[caller])))
        if name.startswith(("get_", "set_")):
            score -= 1
        if line and (REPLY & set(own)) and text_in and text_out:
            call = "chat"
        elif line and (text_out or text_in):
            call = "say"
        elif choice and returns != "void":
            call = "decide"
        elif content and returns != "void":
            call = "create"
        elif line:
            call = "say"
        else:
            continue
        out.append({"type": owner, "method": name, "params": params, "returns": returns, "call": call,
                    "static": bool((m.get("flags") or 0) & 0x10), "nested": owner in nested, "score": score, "why": why})
    out.sort(key=lambda c: (-c["score"], c["type"], c["method"]))
    return out[:top]


def patch(c, character="NAME"):
    """A Harmony patch for one candidate, using Kinloom's C# client: the game's own value is the offline answer."""
    target = "%s:%s" % (c["type"], c["method"])
    cls = re.sub(r"\W", "_", "%s_%s" % (c["type"].split(".")[-1], c["method"]))
    event = (words(c["method"]) or ["line"])[-1]
    if c["call"] in ("say", "chat") and c["returns"] == "string":
        if c["call"] == "chat":
            asked = c["params"].index("string")
            head = "static void Postfix(object[] __args, ref string __result)"
            body = ("    // ~1 s: the game waits here. Async games: show __result now, then the reply when it comes.\n"
                    "    var reply = Mod.Kl.Chat(\"%s\", (string)__args[%d], new Obj { [\"usual\"] = __result }).GetAwaiter().GetResult();\n"
                    "    if (reply.Length > 0) __result = reply;      // nothing (offline): the game's own reply stays"
                    % (character, asked))
        else:
            head = "static void Postfix(ref string __result)"
            body = (_declare(character, event) +
                    "    var said = Mod.Kl.Say(\"%s\", \"%s\", new Obj { /* the game's values now: __instance's fields, __args */ }).GetAwaiter().GetResult();\n"
                    "    if (said.Length > 0) __result = said;      // nothing (offline, no line yet): the game's own line stays"
                    % (character, event))
    elif c["call"] == "say":
        at = c["params"].index("string") if "string" in c["params"] else 0
        head = "static void Prefix(object[] __args)"
        body = (_declare(character, event) +
                "    var said = Mod.Kl.Say(\"%s\", \"%s\", new Obj { /* the game's values now: __instance's fields, __args */ }).GetAwaiter().GetResult();\n"
                "    if (said.Length > 0) __args[%d] = said;    // nothing (offline, no line yet): the game's own text stays"
                % (character, event, at))
    elif c["call"] == "decide":
        head = "static void Postfix(ref %s __result)" % _cs(c["returns"])
        body = ("    // decide is instant: give its shape by example, the game's own choice as the offline answer\n"
                "    // var d = Mod.Kl.Decide(\"%s\", situation, new Obj { [\"choice\"] = new Arr { ... } });" % character)
    else:
        head = "static void Postfix(ref %s __result)" % _cs(c["returns"])
        body = ("    // once, before it is needed (~1-2 s): create(what, example) answers in the example's shape\n"
                "    // __result = ... Mod.Kl.Create(\"%s\", example, context) ..." % c["method"])
    return ("[HarmonyPatch]\nstatic class %s\n{\n    static MethodBase TargetMethod() => AccessTools.Method(\"%s\");\n"
            "    %s\n    {\n%s\n    }\n}" % (cls, target, head, "\n".join("    " + l for l in body.split("\n"))))


def _declare(character, event):
    return ("    // once, at load: Mod.Kl.Character(\"%s\", \"who they are\", new Obj {\n"
            "    //     [\"lines\"] = new Obj { [\"%s\"] = new Obj { [\"when\"] = \"what is happening then\", [\"lines\"] = new Arr() } },\n"
            "    //     [\"events\"] = new Obj { [\"%s\"] = new Arr { /* the names of the values below */ } } });\n"
            % (character, event, event))


def _cs(t):
    return {"string": "string", "bool": "bool", "i4": "int", "r4": "float", "r8": "double", "i8": "long"}.get(t, "object")


def report(path, top=8, rea=None):
    """Everything `kinloom hooks` prints, as data."""
    code = find_code(path)
    found = scan(code, rea)
    found_types = [t for t in found.get("types") or [] if "<" not in (t.get("name") or "")]
    best = candidates(found, top)
    return {"game": os.path.abspath(path), "code": code, "types": len(found_types), "methods": len(found["methods"]),
            "candidates": best, "patch": patch(best[0]) if best else ""}


def text(r):
    lines = ["Game code: %s (.NET: %d types, %d methods; read by REA, nothing was run)" % (r["code"], r["types"], r["methods"])]
    if not r["candidates"]:
        lines += ["", "No method name points to a line, a reply, a choice or content (obfuscated names?). Read the types "
                  "yourself (REA's inspect-managed-members, or ILSpy / dnSpyEx), then patch as in `kinloom hooks --guide`."]
        return "\n".join(lines)
    lines += ["", "Where Kinloom fits (best first):"]
    for i, c in enumerate(r["candidates"], 1):
        lines.append("%d. %s.%s(%s) -> %s   [%s]%s" % (i, c["type"], c["method"], ", ".join(c["params"]), c["returns"],
                                                     c["call"], "  static" if c["static"] else ""))
        if c.get("nested"):
            lines.append("   nested: Harmony finds it by its short name (two types of that name: the first one)")
        lines.append("   why: %s" % "; ".join(c["why"]))
    lines += ["", "A Harmony patch for #1 (BepInEx and MelonLoader load Harmony patches; a loader of your own can too). "
              "`Mod.Kl` is your one KinloomClient; `Obj` and `Arr` are the shorthands from KINLOOM.md (with `using HarmonyLib;` "
              "and `using System.Reflection;`):", "", r["patch"], "",
              "Then: `kinloom add NAME \"who they are\"` for the character, `kinloom serve` while playing. Check each "
              "candidate in the game before relying on it (names can mislead). Steps, loaders, IL2CPP and native games: "
              "`kinloom hooks --guide`."]
    return "\n".join(lines)


def guide():
    with open(GUIDE, encoding="utf-8") as f:
        return f.read()


def run(path, as_json=False, top=8):
    """The `kinloom hooks` command."""
    try:
        r = report(path, top)
    except HookError as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            print("kinloom hooks: %s" % e)
        return 1
    print(json.dumps(r, indent=2) if as_json else text(r))
    return 0
