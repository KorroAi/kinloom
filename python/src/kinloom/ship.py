"""`kinloom ship`: what to fix before a game with Kinloom is released, and a draft of the store's AI disclosure.

    kinloom ship [folder] [--disclosure kinloom-ai-disclosure.md]

Reads the game's files (nothing is sent anywhere, no model is called): keys that would ship inside the game, how the
game reaches a model once players have it, characters without offline answers, spending caps and prices, the content
rating; then writes a draft disclosure of the AI the game uses, for the developer to review.
"""
import hashlib
import os
import re

from . import check as _check
from . import config as _config
from .harness import KINDS as _AGENTS

# keys by their published formats (OpenAI, Anthropic, OpenRouter, Groq, xAI, Google), whatever file they hide in
_KEY = re.compile(r"(?<![A-Za-z0-9_\-])(sk-ant-[A-Za-z0-9_\-]{16,}|sk-or-v1-[A-Za-z0-9]{32,}|sk-proj-[A-Za-z0-9_\-]{20,}|"
                  r"sk-[A-Za-z0-9]{24,}|gsk_[A-Za-z0-9]{24,}|xai-[A-Za-z0-9]{24,}|AIza[0-9A-Za-z_\-]{35})")
# the variables Kinloom reads keys from: a game that reads them runs the model on the player's machine
_ENV_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
             "MISTRAL_API_KEY", "TOGETHER_API_KEY", "XAI_API_KEY", "FIREWORKS_API_KEY", "CEREBRAS_API_KEY", "KINLOOM_API_KEY")
_ENV_READ = re.compile(r"\b(%s)\b" % "|".join(_ENV_KEYS))
_KINLOOM_NEW = re.compile(r"(?<![\w.])Kinloom\(")
_LOCAL = re.compile(r"(127\.0\.0\.1|localhost):7717")
_RELAY = re.compile(r"[\"'](https://[^\"'\s]+)[\"']")
_SKIP = {".git", "node_modules", ".godot", "Library", "Temp", ".venv", "venv", "__pycache__", ".kinloom", ".claude", ".cursor"}
_TEXT_LIMIT = 2_000_000
# the admin token of an online server (the player token is meant to ship; this one never)
_SERVER_TOKEN = re.compile(r"KINLOOM_SERVER_TOKEN[\"']?\s*[=:]\s*[\"']?([A-Za-z0-9_\-]{16,})")
_MARK = re.compile(r"^<!-- kinloom ship: sha256 ([0-9a-f]{64})[^\n]*-->\n")

# what the code calls -> what players get, for the disclosure (any engine: method names are the same everywhere)
_FEATURES = [
    (re.compile(r"\b(chat|Chat|chat_as|chatStream|ChatAsync|talkBox|AIDialogue|KinloomDialogue|PygameTalkBox)\b"),
     "Characters answer what players type or say, written by a language model during play."),
    (re.compile(r"\b(say|Say|SayAsync)\("), "Characters' lines for game events, written by a language model (ahead of time or during play)."),
    (re.compile(r"\b(suggest|Suggest|SuggestAsync)\("), "Replies offered to the player to choose from, written for the moment by a language model."),
    (re.compile(r"\b(converse|Converse|ConverseAsync)\("), "Characters talking with each other, written by a language model."),
    (re.compile(r"\b(decide|act|think|mind|Decide|Act|Think|Mind)\("), "Characters' choices and actions, chosen by a language model or by rules it wrote."),
    (re.compile(r"\b(create|Create|CreateAsync)\("), "Game content (shaped like the developer's examples) generated during play."),
    (re.compile(r"\b(speak|Speak|speak_aloud|SpeakAsync)\("), "Synthetic voices read characters' lines aloud."),
    (re.compile(r"\b(listen|Listen|hear|ListenAsync)\("), "Players' voice recordings are turned into text by a speech service."),
    (re.compile(r"\bimage\s*[=:]|\bimage\)|, *png\)"), "Pictures from the game can be sent to the model."),
]


def _files(folder):
    """(relative path, text) for every text file a release could contain."""
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in _SKIP]
        for f in files:
            path = os.path.join(root, f)
            try:
                if os.path.getsize(path) > _TEXT_LIMIT:
                    continue
                with open(path, "rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            if b"\0" in data[:4096]:
                continue
            yield os.path.relpath(path, folder).replace(os.sep, "/"), data.decode("utf-8", errors="replace")


def _bundled(folder):
    """True when a `kinloom bundle` folder sits in the game."""
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in _SKIP]
        if "README.txt" in files:
            try:
                with open(os.path.join(root, "README.txt"), encoding="utf-8", errors="replace") as f:
                    if f.read(40).startswith("Kinloom for this game"):
                        return True
            except OSError:
                pass
    return False


def _line(text, at):
    return text.count("\n", 0, at) + 1


def review(folder="."):
    """(engine, [(level, message)], facts for the disclosure); level is "ok", "warn" or "error"."""
    folder = os.path.abspath(folder)
    engine, found = _check.check(folder, url="http://127.0.0.1:1")      # the integration, without asking a server
    out = [(level, m) for level, m in found if "kinloom serve is not running" not in m and not m.startswith("kinloom serve is running")]
    try:
        cfg = _config.load(folder)
    except _config.ConfigError:
        cfg = {}
    facts = {"engine": engine, "features": [], "provider": str(cfg.get("provider") or ""), "rating": cfg.get("rating"),
             "banned": len([w for w in cfg.get("banned_words") or [] if isinstance(w, str) and w.strip()]),
             "caps": [k for k in ("max_cost_per_hour", "max_cost_per_day") if cfg.get(k) is not None], "relay": None,
             "native": [], "local": False}
    sources = {rel: text for rel, text in _check._sources(folder)}

    # 1. keys inside anything that could ship
    keys = 0
    for rel, text in _files(folder):
        for m in _KEY.finditer(text):
            keys += 1
            where = "%s:%d" % (rel, _line(text, m.start()))
            if os.path.basename(rel).startswith(".env"):
                out.append(("warn", "%s holds a model key: keep this file out of the release (players could read it)" % where))
            elif rel in sources:
                pass            # kinloom check already says it, as an error
            else:
                out.append(("error", "%s looks like a model key: anything inside a game can be read by players; keys belong "
                                     "on your relay (kinloom deploy) or in the player's own environment" % where))
    if not keys:
        out.append(("ok", "no model key found in the game's files"))
    deploys = set()
    for rel, text in _files(folder):
        for m in _SERVER_TOKEN.finditer(text):
            out.append(("error", "%s:%d holds the server's admin token (KINLOOM_SERVER_TOKEN): it opens the journal and "
                                 "everything; keep it on the host only" % (rel, _line(text, m.start()))))
        if os.path.basename(rel) == "DEPLOY.md" and text.startswith("# Kinloom online server"):
            deploys.add(os.path.dirname(rel) or ".")
    for d in sorted(deploys):
        out.append(("warn", "%s/ is an online server's folder (kinloom deploy): keep it out of the game you ship" % d))

    # 2. how the game reaches a model once players have it
    kind = facts["provider"].lower()
    if kind in _AGENTS:
        out.append(("error", "kinloom.json: provider %r is your coding agent's subscription: players do not have it. Ship "
                             "with an API key on a relay (kinloom deploy), or let players bring their own key" % kind))
    for rel, text in sources.items():
        for m in _ENV_READ.finditer(text):
            facts["native"].append(m.group(1))
        if _LOCAL.search(text):
            facts["local"] = True
        for m in _RELAY.finditer(text):
            if "kinloom" in text.lower() and not any(h in m.group(1) for h in ("anthropic.com", "openai.com", "openrouter.ai", "github.com")):
                facts["relay"] = facts["relay"] or m.group(1)
    if engine == "python":                         # Kinloom() in the game finds a key in the player's environment
        for rel, text in sources.items():
            for m in _KINLOOM_NEW.finditer(text):
                args = _check._args(text, m.end())
                if "url" not in args and "provider" not in args and "brain" not in args:
                    facts["native"].append("a model key (Kinloom() looks in the environment)")
    if facts["native"]:
        out.append(("warn", "the game reads %s on the player's machine: players without that key get the offline answers. To "
                            "pay for your players' AI, run a relay (kinloom deploy) with a token and spending caps"
                    % ", ".join(sorted(set(facts["native"])))))
    if facts["local"] and engine != "python" and not facts["relay"]:
        if _bundled(folder):
            out.append(("ok", "the game talks to the bundled kinloom server (kinloom bundle) on the player's machine"))
        else:
            out.append(("warn", "the game talks to kinloom serve on 127.0.0.1:7717: players do not run one. Ship `kinloom "
                                "bundle` next to the game, or point it at your relay (kinloom deploy); until then players "
                                "get the offline answers"))
    elif facts["relay"]:
        out.append(("ok", "the game talks to a relay: %s (give it a player token: kinloom serve --token)" % facts["relay"]))

    # 3. offline answers: what players see when no model answers
    chars = cfg.get("characters")
    chars = chars if isinstance(chars, dict) else {}
    bare = sorted(n for n, s in chars.items() if isinstance(s, dict) and not s.get("offline") and not s.get("lines"))
    for rel, text in sources.items():
        for m in _check._DECLARE.finditer(text):
            args = _check._args(text, m.start() + text[m.start():].index("(") + 1)
            if "offline" not in args and "lines" not in args and "Offline" not in args and "Lines" not in args:
                bare.append("%s (%s:%d)" % (m.group(1), rel, _line(text, m.start())))
    if bare:
        out.append(("warn", "no offline answer for %s: without a model (no key, no network, over budget) they say nothing; "
                            "give \"offline\" or \"lines\"" % ", ".join(sorted(set(bare)))))
    elif chars or any(_check._DECLARE.search(t) for t in sources.values()):
        out.append(("ok", "every character has offline answers"))

    # 4. money
    if not facts["caps"]:
        out.append(("warn", "no spending cap: set \"max_cost_per_hour\" and/or \"max_cost_per_day\" in kinloom.json (with "
                            "\"prices\": caps need them)"))
    if not isinstance(cfg.get("prices"), dict):
        out.append(("warn", "no \"prices\" in kinloom.json: costs are not counted. Copy your model's prices from the provider's "
                            "price page: {\"input\": ..., \"output\": ..., \"cached_input\": ..., \"source\": \"<the page>\"} "
                            "($ per million tokens)"))
    elif facts["caps"]:
        out.append(("ok", "prices declared and spending capped (%s)" % ", ".join(facts["caps"])))

    # 5. audience
    rating = cfg.get("rating")
    if rating in (None, ""):
        out.append(("warn", "no content rating: set \"rating\": \"everyone\", \"teen\" or \"mature\" in kinloom.json (a rule "
                            "in every prompt, on top of the checks)"))
    elif str(rating).strip().lower() not in ("everyone", "teen", "mature"):
        out.append(("error", "kinloom.json: rating %r: use \"everyone\", \"teen\" or \"mature\"" % (rating,)))
    else:
        out.append(("ok", "content rating: %s" % str(rating).strip().lower()))

    # what the game uses, for the disclosure
    code = "\n".join(sources.values())
    for pattern, sentence in _FEATURES:
        if pattern.search(code) and sentence not in facts["features"]:
            facts["features"].append(sentence)
    if chars and _FEATURES[0][1] not in facts["features"]:
        facts["features"].insert(0, _FEATURES[0][1])
    return engine, out, facts


def disclosure(facts):
    """A draft of the store's AI disclosure, from what the game uses. The developer reviews and adapts it."""
    provider = facts["provider"]
    who = ("the model service set in kinloom.json (%s)" % provider) if provider and provider not in ("offline",) else \
          "the model service you configure"
    lines = ["# AI disclosure (draft)", "",
             "Drafted by `kinloom ship` from the game's files. Review every line, remove what your release does not do, and",
             "follow your store's current rules and form (stores ask, for example, what is generated during play and which",
             "guardrails stop illegal or harmful content).", "",
             "## Content generated during play", ""]
    if facts["features"]:
        lines.append("This game uses generative AI while it runs (through Kinloom, with %s):" % who)
        lines += ["- " + f for f in facts["features"]]
    else:
        lines.append("No Kinloom call was found in the game's code: check this section by hand.")
    lines += ["", "## Guardrails", "",
              "- Every model answer is checked before the game uses it: its shape, characters staying in character, numbers",
              "  taken only from the game's data, secrets kept, and a content filter.",
              "- Content rating: %s." % (("\"%s\", given to the model as a rule for every answer" % facts["rating"])
                                         if facts["rating"] else "none set (set one before release)"),
              "- Banned words: %s." % ("%d, blocked in every answer" % facts["banned"] if facts["banned"] else "none set"),
              "- Spending: %s." % ("capped (%s)" % ", ".join(facts["caps"]) if facts["caps"] else "no cap set"),
              "- Without a model (no key, no network, over budget) the game still works with its own prepared lines.",
              "", "## Data", "",
              "- What players type%s is sent to %s to write the answers." % (
                  " or say" if any("voice recordings" in f for f in facts["features"]) else "", who),
              "- Characters' memories are kept by Kinloom %s." % (
                  "on the relay server" if facts["relay"] else "on the player's machine (the game's memory file)"),
              "", "## Content made with AI tools before release", "",
              "Not detected by this tool: list here any art, text, voice or music you made with AI tools.", ""]
    return "\n".join(lines)


def _write_draft(target, text):
    """Writes the draft with a mark of what was written; a file edited since then (or not Kinloom's) is kept and the
    draft goes to target.new. Returns the path written."""
    def digest(body):
        return hashlib.sha256(body.encode("utf-8")).hexdigest()
    marked = "<!-- kinloom ship: sha256 %s (edit freely: an edited draft is never overwritten) -->\n%s" % (digest(text), text)
    if os.path.exists(target):
        with open(target, encoding="utf-8", newline="") as f:
            old = f.read()
        m = _MARK.match(old)
        if not (m and digest(old[m.end():]) == m.group(1)):
            target = target + ".new"
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(marked)
    return target


def run(folder=".", path="kinloom-ai-disclosure.md"):
    engine, results, facts = review(folder)
    print("Kinloom ship (%s): before you release" % engine)
    for level, message in results:
        print("  %-5s %s" % (level.upper(), message))
    errors = sum(1 for level, _ in results if level == "error")
    warns = sum(1 for level, _ in results if level == "warn")
    if path:
        target = path if os.path.isabs(path) else os.path.join(folder, path)
        written = _write_draft(target, disclosure(facts))
        if written == target:
            print("\nAI disclosure draft: %s (review it before you use it)" % os.path.relpath(target))
        else:
            print("\nAI disclosure: %s was edited since Kinloom wrote it, so it was kept; the new draft is %s (compare "
                  "them)" % (os.path.relpath(target), os.path.relpath(written)))
    print("\n%s" % ("Fix the errors before you ship." if errors else
                    "%d thing(s) to look at before you ship." % warns if warns else "Ready to ship."))
    return 1 if errors else 0
