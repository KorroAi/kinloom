"""`kinloom recipe "<any request>"`: what a coding agent needs for one feature, and only that. The request is matched to
the call that does it and the one or two closest patterns, with that call written in the game's language, instead of
reading every pattern. Offline, instant, no model."""
import os
import re

from .add import LANGUAGE, SNIPPETS

HERE = os.path.dirname(os.path.abspath(__file__))

# (what it is, the call, words that point to it, advice): the whole of Kinloom from the request side.
ROUTES = [
    ("talk", "chat + soul", "talk talks talking speak conversation converse dialogue dialog chat npc npcs villager villagers "
     "merchant shopkeeper shop vendor innkeeper companion friend ally character characters person human alive soul souls "
     "personality persuade convince bargain haggle bribe flirt romance interrogate ask answer question questions",
     "A character the player talks to freely: `kinloom add NAME \"who they are\" [--tools ... --trust ...]` writes it into "
     "kinloom.json; the game calls chat(name, text, facts, speaker) (\"\" = they speak first) and act(name, think=false)."),
    ("line", "say", "comment comments commentator commentary announcer narrator narrate narration bark barks react reaction "
     "reactions quip quips taunt taunts cheer caption subtitles radio callout callouts shout",
     "Instant lines on game events: declare lines and events once, then say(name, event, facts) returns at once, with "
     "your real facts filled in."),
    ("choice", "decide", "decide decision decisions choose choice strategy tactic tactics plan planning boss behavior behaviour "
     "difficulty director pacing adapt adaptive rival opponent opponents weather economy prices balance balancing",
     "A validated choice shaped by example: decide(name, situation, {\"strategy\": [\"attack\", \"block\"], \"aggression\": "
     "[0.0, 1.0]}) is instant every frame, refreshed in the background."),
    ("action", "act + tools", "command commands order orders obey instruction instructions tool tools action actions do control "
     "voice typed natural language agent follow execute function functions",
     "The character uses the game's functions: give tools (examples or functions), or declare the game's tools once with "
     "tools({...}) and name them per character (tools=[\"open_door\"] or \"all\"); act(name, situation) returns validated "
     "calls; while talking, act(name, think=false)."),
    ("sight", "create / chat + image=", "see sees seeing look looks looking screenshot screenshots screen picture pictures "
     "photo photos image images drawing drawings sketch camera vision visual recognize recognise",
     "The model looks at a picture: create(what, example, image=screenshot) answers in your example's shape; "
     "chat(name, text, image=...) talks about what it shows. Bytes, a file path, base64 or a data URI (PNG, JPEG, GIF, "
     "WebP). A model that cannot see answers from the text (told once in the journal)."),
    ("check", "kinloom test + kinloom probe", "test tests testing check checks verify regression regressions qa quality "
     "probe probing ci assert",
     "The AI checked like code: steps calling the verbs with checks in kinloom.tests.json, run by `kinloom test` "
     "(`--record` keeps the model's answers, `--replay` runs on them: no model, no cost); `kinloom probe NAME` plays a "
     "character like a tester (secrets, manipulation, injection, repeats)."),
    ("content", "create", "generate generated generator procedural content level levels map maps dungeon room rooms quest quests "
     "mission missions item items loot weapon weapons name names description descriptions story stories lore book books "
     "puzzle puzzles recipe dialogue-tree card cards recap summary summarize translate translation hint hints tutorial",
     "Content shaped like your example (the example is the offline answer): create(what, example, context, count=N); "
     "instant=True takes it from a ready pool."),
    ("crowd", "mind + think + reward", "enemy enemies crowd crowds swarm units unit soldiers monsters mobs ai-units every-frame "
     "frame pathfinding squad squads army armies learn learning improve evolve smarter reward rewards utility",
     "Many units deciding every frame: mind(name, senses, actions, rules) once; think(name, senses, who) is local and "
     "instant; reward(who, value, done) makes them learn."),
    ("world", "event + meet + opinion + reputation", "rumor rumors rumour gossip witness witnesses saw seen reputation faction "
     "factions opinion opinions relationship relationships trust grudge remember memory memories news spread",
     "Who saw what: event(text, by=, seen_by=[...], tag=, impact=); meet(a, b) spreads it; knows, opinion, "
     "reputation(target, group) for game logic. Conversations already remember each speaker."),
    ("voice", "speak + listen", "voice voices voiced speak speaks speaking spoken aloud read-aloud tts text-to-speech "
     "speech microphone mic audio narration narrated dub dubbing dubbed hear hears hearing listen listening push-to-talk "
     "accessibility",
     "Text said aloud and the player heard: character(name, voice=\"low, warm\"); speak(name, text) gives a WAV (the "
     "system's voice offline, cached per line); listen(recording) gives what was said; ready-made boxes take voice=true."),
    ("facts", "lore + invent=false", "lore world canon setting facts consistent consistency contradict hallucinate "
     "hallucination invent inventing made-up",
     "World facts every character treats as true: `kinloom add --lore \"...\"` or lore([...]); invent=false stops a "
     "character making up names or places."),
]
# the cookbook patterns that belong to each route (numbers in kit/cookbook.md), most general first
ROUTE_PATTERNS = {"talk": [1, 2, 3, 4, 7, 11, 18, 14, 28], "line": [6, 5, 8], "choice": [9, 10, 15, 16, 8, 19, 27],
                  "action": [20, 33, 2], "content": [17, 12, 13, 21, 22], "crowd": [23, 24, 9],
                  "world": [25, 26, 3], "facts": [1, 28], "voice": [29, 30], "sight": [32, 17], "check": [34]}
_STOP = {"a", "an", "the", "to", "of", "and", "with", "that", "for", "my", "in", "on", "as", "by", "go", "it", "is", "be",
         "make", "add", "want", "should", "can", "i", "we", "our", "their", "them", "they", "he", "she", "his", "her",
         "more", "some", "each", "every", "when", "so", "this", "from", "at", "into", "like", "game", "player", "players"}
# media Kinloom does not make (a picture to look at is covered: route "sight")
UNSUPPORTED = re.compile(r"\b(generate|generates|generated|generating|make|makes|create|creates|draw|draws|paint|render|"
                         r"compose|produce)\b.*\b(image|images|picture|pictures|sprite|sprites|texture|textures|portrait|"
                         r"portraits|art|artwork|3d|mesh|meshes|music|song|songs|video|videos|sound effects?|sfx)\b|"
                         r"\b(sprite|sprites|texture|textures|3d|mesh|meshes|sfx|sound effects?|music|song|songs|video|videos|"
                         r"animation clip)\b", re.I)


def _words(text):
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", (text or "").lower())


def _stem(w):
    for suffix in ("ing", "ers", "er", "es", "s", "ed"):
        if len(w) > 4 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


def patterns():
    """[(number, title, text)] from the cookbook."""
    with open(os.path.join(HERE, "kit", "cookbook.md"), encoding="utf-8") as f:
        text = f.read()
    parts = re.split(r"^## (\d+)\. (.+)$", text, flags=re.M)
    return [(int(parts[i]), parts[i + 1].strip(), parts[i + 2].strip()) for i in range(1, len(parts) - 2, 3)]


def route(request):
    """[(score, route)] best first."""
    ask = {_stem(w) for w in _words(request)}
    scored = []
    for r in ROUTES:
        keys = {_stem(w) for w in r[2].split()}
        score = len(ask & keys)
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return scored


def best_patterns(request, k=2, route_name=None):
    """The k closest patterns; with a route, only among that route's own patterns (the first one when nothing else
    matches better)."""
    ask = {_stem(w) for w in _words(request)} - {_stem(w) for w in _STOP}
    allowed = ROUTE_PATTERNS.get(route_name)
    out = []
    for n, title, text in patterns():
        if allowed is not None and n not in allowed:
            continue
        words = {_stem(w) for w in _words(title)}
        body = {_stem(w) for w in _words(text)}
        score = 3 * len(ask & words) + len(ask & body)
        if score or allowed is not None:
            rank = allowed.index(n) if allowed is not None else n
            out.append((score, rank, n, title, text))
    out.sort(key=lambda x: (-x[0], x[1]))
    return [(score, n, title, text) for score, _, n, title, text in out[:k]]


def recipe(request, engine="python"):
    """The text a coding agent needs for this request."""
    lang = LANGUAGE.get(engine, "http")
    lines = ["Request: %s" % request.strip(), ""]
    if UNSUPPORTED.search(request or ""):
        lines += ["Not covered yet: Kinloom does not generate images, video, music, sound effects or 3D. It can write "
                  "their text (descriptions, prompts) with create(), and look at a picture (image= on create and chat). "
                  "Voices are covered: speak / listen.", ""]
    routes = route(request)
    if not routes:
        from .init import calls
        lines += ["No word of this request points to one call, so pick by what the game needs back (Kinloom knows nothing "
                  "about this game; any call works for any game):"]
        lines += ["- %s: %s" % (r[1], r[3]) for r in ROUTES]
        lines += ["- anything else a model should write (data, text, lists of any shape): create, with your example.", "",
                  "Exactly these calls and arguments (%s):" % engine, calls(lang)]
        return "\n".join(lines)
    top = [r for s, r in routes if s >= routes[0][0] * 0.5][:2]
    for r in top:
        lines += ["Use %s (%s). %s" % (r[1], r[0], r[3])]
    if top[0][0] == "talk":
        lines += ["", "In this game (%s):" % engine, SNIPPETS[lang].format(name="NAME")]
    found = best_patterns(request, route_name=top[0][0])
    if found:
        lines += ["", "Closest patterns (Python; every client has the same calls%s):" % (
            "" if lang == "python" else ", see KINLOOM.md for the %s forms" % engine)]
        for _, n, title, text in found:
            lines += ["", "## %d. %s" % (n, title), text]
    lines += ["", "Rules: the example is the offline answer (no fallbacks to write); chat takes ~1 s (never per frame); "
              "say/decide/act/think are instant; keys stay in the environment of kinloom serve."]
    return "\n".join(lines)
