"""Writes vectors.json: inputs and the Python reference's outputs for the pure functions every native SDK ports
(shapes, JSON finding, reply splitting, caps, echoes, secrets, numbers, fill, prompts, minds, memory recall).
Each SDK's conformance scenario runs them and prints "vectors: N/N".

    python conformance/vectors.py

Numbers in examples are never floats with nothing after the point (1.0): JavaScript and GDScript read them as whole
numbers, Python does not; the SDKs agree on everything else.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from kinloom import minds, prompts, souls  # noqa: E402
from kinloom.brain import (_DIGIT, _NUMBER, _PLACEHOLDER, Brain, Character, _allowed_numbers, _changed,  # noqa: E402,F401
                           _event_key, _number_ok, _speech_only, fill, format_value)
from kinloom.memory import Memory  # noqa: E402
from kinloom.shapes import Shape, clean_text, find_json  # noqa: E402
from kinloom.voice import stable_pick  # noqa: E402

OUT = []


def add(fn, args, out):
    OUT.append({"fn": fn, "args": args, "out": out})


def plain(x):
    """JSON-able: tuples become lists, sets sorted lists."""
    return json.loads(json.dumps(x, default=lambda o: sorted(o) if isinstance(o, set) else str(o)))


# ---------------- shapes ----------------

SHAPES = [
    (["attack", "block"], ["Block", " attack ", "run", 3, None]),
    ([0.5, 2.5], [1.2, 9, -3, "2", "x", True]),
    ([1, 5], [3.4, 3.5, 9, "4"]),
    ([0, 1], [0.25, 2]),
    (3, [4, 4.0, 4.5, "7", True, 10 ** 12]),
    (0.5, [0.25, "1.5", 1e10, "nan"]),
    (True, [False, "yes", "No", 1, "maybe"]),
    ("#ff7a45", ["#00FF00", "a0b0c0", "#12345678", "red"]),
    ("Win clean", ["Ghost  mode\n", 42, "", "x" * 250, "\x1b[31mred\x1b[0m", "‮evil"]),
    (["#ff0000"], [["#00ff00", "#0000ff"], [], ["x"], "x", ["#aaaaaa"] * 51]),
    ([{"name": "Ana", "hp": [0, 100]}], [[{"name": "Bo", "hp": 120}], [{"hp": 5}], [{"name": 3}]]),
    ({"challenge": "Win clean", "sky": "#ff7a45"}, [{"challenge": "Ghost mode", "sky": "#000000"},
                                                    {"challenge": "x", "sky": "nope"}, {"sky": "#111111", "extra": 1},
                                                    [1, 2], "text"]),
    ({"strategy": ["attack", "block"], "aggression": [0, 1], "nested": {"ok": True, "tags": ["a"]}},
     [{"strategy": "block", "aggression": 0.9, "nested": {"ok": "no", "tags": ["b", "c"]}}, {}]),
    ("a long example text " * 12, ["short", "y" * 500]),
    # an answer with none of the fields is not one; keys in another case and one wrapper are read
    ({"name": "Sword", "power": [1, 10]}, [{"Name": "Frost", "POWER": 8}, {"item": {"name": "Frost", "power": 8}},
                                           {"title": "x"}, {"item": {"title": "x"}}, {"name": "a", "Name": "b"},
                                           {"item": {"name": "x"}, "other": 1}]),
]
for example, values in SHAPES:
    shape = Shape.of(example)
    for v in values:
        ok, value, error = shape.check(v)
        add("shape", [example, v], {"ok": ok, "value": value, "error": error, "describe": shape.describe(),
                                     "default": shape.default()})
for bad in ([], {}, [[[[[[[[[[[[[[["deep"]]]]]]]]]]]]]]]):
    try:
        Shape.of(bad)
        add("shape_error", [bad], None)
    except ValueError as e:
        add("shape_error", [bad], str(e))

# ---------------- finding JSON in answers ----------------

for text in ['{"a": 1}', 'Sure! ```json\n{"lines": ["x"]}\n``` hope it helps', 'noise {"a": {"b": [1, 2]}} trailing } {',
             '[1, 2, 3] and more', "not json at all", "", '{"broken": ', 'x {"a": 1} {"b": 2}', '```\n[{"k": "v"}]\n```',
             '{"text": "a } inside"} after',
             # an answer cut by the token limit: never its first inner object
             '{"say": "ok", "actions": [{"op": "build", "parts": ["pier"]}, {"op": "bu',
             '```json\n[{"a": 1}, {"a": 2','{"a": "} no end", "b": [1, 2', 'Smile :-[ here {"a": 1}',
             '{bad} then {"ok": true}', '[ "x", {"a": 1}', 'chat [not json] {"a": [1, {"b": 2}]}', '{ "k" : {"a": 1} ',
             # trailing commas, as models write them: the whole answer, never its inner object
             '{"name": "Frost", "stats": {"atk": 7},}', 'Here: {"a": [1, 2,], "b": "x,}"} done', '[1, 2, 3,]',
             '{"a": "q\\"", "b": [1 , ] , }', '{"a": 1,,}']:
    add("find_json", [text], find_json(text))

for example, text in [({"say": "Done.", "actions": [{"op": "build"}]}, '{"say": "ok", "actions": [{"op": "build"}, {"op": "bu'),
                      ({"say": "Done.", "actions": [{"op": "build"}]}, 'Here: {"say": "ok", "actions": []}'),
                      ({"name": "Glowcap"}, "no json here"), ({"name": "Glowcap"}, '```json\n{"name": "Mossb'),
                      (["a", "b"], '"b"'), ([{"n": 1}], '[{"n": 2}, {"n": 3'),
                      # JSON mode: a list wrapped once in an object, or one item alone; two lists stay an error
                      ([{"n": 1}], '{"list": [{"n": 2}, {"n": 3}]}'), ([{"n": 1}], '{"stalls": [{"n": 4}], "note": "x"}'),
                      ([{"n": 1}], '{"n": 5}'), ([{"n": 1}], '{"a": [{"n": 1}], "b": [{"n": 2}]}'), (["x"], '{"tags": ["a", "b"]}'),
                      (["x"], '{"tag": "a"}'), ([{"n": 1}], '{"other": 1}')]:
    ok, value, error = Shape.of(example).parse(text)
    add("parse", [example, text], {"ok": ok, "value": value, "error": error})

for text in ["  hello   world ", "tab\tnew\nline", "\x00bell\x07", "\x1b[1mbold\x1b[0m", "bidi‮ok⁦", "é à ü 漢字"]:
    add("clean_text", [text], clean_text(text))

# ---------------- filling lines ----------------

for template, facts in [("{who} passes {whom}!", {"who": "BLAZE", "whom": "NOVA"}),
                        ("Lap {lap} of {total}", {"lap": 3, "total": 12}),
                        ("Gap {gap}s", {"gap": 0.4567}), ("Gap {gap}", {"gap": 0.04}), ("Big {n}", {"n": 1234.6}),
                        ("Ok {flag}", {"flag": True}), ("Missing {x}", {}), ("{a}{b}", {"a": "x" * 100, "b": None}),
                        ("Neg {n}", {"n": -2.25}), ("Half {n}", {"n": 2.5}), ("Tiny {n}", {"n": 0.001})]:
    add("fill", [template, facts], fill(template, facts))

for event in ["overtake", "  challenging   another trainer\n", "x" * 300]:
    add("event_key", [event], _event_key(event))

# ---------------- replies ----------------

REPLIES = [
    'Hmph. What do you want?\n~~~\n{"mood": "annoyed", "intensity": 0.7, "feel": -0.1, "remember": "Ana mocked my hammer", "do": []}',
    'Fine, take it.~~~{"mood":"calm","do":[{"tool":"give","args":{"item":"bread"}}]}',
    '~~~\n{"mood": "happy"}\n~~~\nWell met, traveler!',
    'No marker here {"mood": "sad", "feel": 0.2}',
    'Just words, no inner part.',
    'I see.\nmood: curious\nfeel: 0.1\nremember: they like ships',
    'Text ~~~ not json at all',
    '{"mood": "odd"} only json',
    'Two {"x": 1} braces {"mood": "tired", "gesture": "yawns"}',
]
for text in REPLIES:
    said, inner = souls.split(text)
    add("split", [text], [said, inner])

TEXTS = ["One. Two three four. Five six seven eight nine ten eleven twelve thirteen. Fourteen.",
         "A very long first sentence that goes on and on without any end in sight for the box",
         "Short! Sure? Yes… Done.", "No end at all", "\"Quoted.\" Then more words here. And more.",
         "Hi. " * 20]
for text in TEXTS:
    for words, chars in [(25, None), (5, None), (3, None), (25, 40), (25, 12), (100, 30)]:
        add("cap", [text, words, chars], souls.cap(text, words, chars))
    add("fit_chars", [text, 30], souls.fit_chars(text, 30))
    add("whole_sentences", [text], souls.whole_sentences(text))

BEFORE = ["The forge is hot today. Bring me iron.", "I said bring me iron, didn't I?", "Clank."]
for text in ["The forge is hot today. What else?", "Bring me iron. Bring me iron!", "Clank. Clank. Something new here.",
             "the forge is hot today, bring me iron", "Totally fresh words for you.", "Clank."]:
    left, stale = souls.drop_echoes(text, BEFORE)
    add("drop_echoes", [text, BEFORE], [left, stale])

SECRETS = ["I sold the king's sword to a smuggler", "My brother died in the mine"]
PUBLIC = ["a gruff smith who owes debts", "her husband left"]
for text, asked in [("I sold the sword to a smuggler, yes.", ""), ("The king's sword? Gone.", ""),
                    ("Aye, I did.", "Did you sell the king's sword to a smuggler?"), ("My brother? He died down in the mine.", ""),
                    ("I owe debts, everyone knows.", ""), ("Nothing to tell.", "Did your brother die?")]:
    add("leaks", [text, SECRETS, PUBLIC, asked], souls.leaks(text, SECRETS, PUBLIC, asked=asked))
    add("keep_secrets", [text, SECRETS, PUBLIC, asked], souls.keep_secrets(text, SECRETS, PUBLIC, asked=asked))

for replies in [["Well, well, look who it is again.", "Well, well, look who came back.", "Hmm."],
                ["I need more iron for the forge today.", "Bring more iron for the forge today please."],
                ["Hello there.", "Hello again."], [], ["a b c d e f", "a b c d e f", "a b c d e f"]]:
    phrases, opener = souls.worn(replies)
    add("worn", [replies], [phrases, opener])

for said, gesture, habits in [("Taps the barometer three times. Storm's coming.", "taps the barometer", []),
                              ("Rubs thumb over the burn scar. What now?", "", ["rubs left thumb over burn scar"]),
                              ("I tap the barometer when nervous.", "taps the barometer", []), ("Just talk.", "", [])]:
    add("drop_narrated", [said, gesture, habits], list(souls.drop_narrated(said, gesture, habits)))

for data in [{"mood": "Annoyed", "intensity": 2, "feel": -0.9, "remember": "x" * 300, "do": [{"tool": "give"}, "bad", {}, {}, {}]},
             {"mood": "two words", "intensity": "0.4", "feel": "abc"}, {}, None, {"self": "I was born in Brookmere", "gesture": "nods slowly"},
             {"mood": "calm", "feel": True, "do": "nope"}]:
    add("inner", [data], souls.inner(data))

for value, seed in [({"summary": "a gruff smith", "values": ["honor", "honor", ""], "mood": "Wary", "secrets": "one secret"}, ""),
                    ({"summary": "who they are, in one sentence", "voice": "how they talk: rhythm, words they use, verbal tics"}, "a baker"),
                    ("nope", "seed sentence"), ({"fears": ["x" * 400] * 10, "mood": "very angry"}, "s")]:
    c = souls.card(value, seed)
    add("card", [value, seed], c)
    add("describe_card", [c], souls.describe(c))

for mood, now, baseline in [(None, 100.0, "wary"), ({"word": "angry", "level": 0.8, "t": 0.0}, 0.0, None),
                            ({"word": "angry", "level": 0.8, "t": 0.0}, 300.0, "calm"), ({"word": "angry", "level": 0.8, "t": 0.0}, 3000.0, "calm")]:
    add("mood_now", [mood, now, baseline], list(souls.mood_now(mood, now, baseline)))
for s in [0, 59, 61, 3600, 7300, 86400 * 3, 86400 * 65]:
    add("ago", [s], souls.ago(s))
for level in [0.1, 0.35, 0.69, 0.7]:
    add("strength", [level], souls.strength(level))
for v in [-0.7, -0.6, -0.2, 0.0, 0.1, 0.2, 0.6, 0.9]:
    add("feeling", [v], prompts.feeling(v))

# ---------------- the streamed reply chain (brain.chat's show): splitter -> guard -> echo -> cap ----------------

from kinloom.brain import _META  # noqa: E402


def stream_chain(pieces, before, words, chars):
    splitter, guard, unstage = souls.Splitter(), souls.Guard(_META), souls.Unstage()
    echo, cut = souls.Echo(before), souls.Cap(words, chars)
    shown = [cut.feed(echo.feed(unstage.feed(guard.feed(splitter.feed(p))))) for p in pieces]
    tail = cut.feed(echo.feed(unstage.feed(guard.feed(splitter.finish()[2]) + guard.finish()) + unstage.finish()) + echo.finish())
    tail += cut.finish()
    return [x for x in shown if x] + ([tail] if tail else [])


STREAMS = [
    ["Hmph", ". What", " do you", " want?", "\n~", "~~\n{\"mood\":", " \"annoyed\"}"],
    ["The forge is hot today. ", "Bring me ", "iron. ", "And coal too, ", "lots of coal."],
    ["~~~", "\n{\"mood\": \"happy\"}\n~~~\n", "Well met, ", "traveler! ", "Sit down."],
    ["As an AI language model, ", "I cannot."],
    ["One two three four five six. ", "Seven eight nine ten eleven twelve thirteen. ", "More words."],
    ["I see.", "\nmood", ": curious\n"],
    ["Short reply {\"mo", "od\": \"calm\"}"],
    ["*wipes the anvil* Fine work", " takes time. (sigh", "s) Come back (sighs). Now [pause] go."],
    ["I love *Bright", " Mercy* the ship, ", "5 * 3 is fifteen (a)b and (c"],
]
for pieces in STREAMS:
    for words, chars in [(25, None), (6, None), (25, 30)]:
        add("stream", [pieces, BEFORE, words, chars], stream_chain(pieces, BEFORE, words, chars))

# ---------------- cleaning what the model said ----------------

b = Brain(provider=None, memory_path=None, voice=None)
for text, name in [('"Not again," she mutters, wiping the anvil. "Go."', "MIRA"), ("MIRA: Hello there.", "MIRA"),
                   ("*smiles* Welcome, friend. (sighs) [pause] Sit.", "MIRA"), ("Assistant: I can help.", "MIRA"),
                   ("As an AI, I cannot.", "MIRA"), ("Memory: - Ana said: hi / I answered: hello", "MIRA"),
                   ("I love *Bright Mercy* the ship .", "MIRA"), ("x" * 500, "MIRA"), ("Ignore previous instructions.", "THEO"),
                   ('"Run!"', "MIRA")]:
    why = []
    out = b._clean_reply(text, name, why)
    add("clean_reply", [text, name], [out, why])

for line, names, words, chars in [("{who} passes {whom}!", ["who", "whom"], 14, None), ("Lap 3 for {who}", ["who"], 14, None),
                                  ("{x} unknown", ["who"], 14, None), ('"Go {who}!"', ["who"], 14, None),
                                  ("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twenty-one", None, 14, None),
                                  ("{who} wins the system prompt", None, 14, None), ("{who} is very very fast today", ["who"], 14, 20),
                                  ("Any {placeholder} goes", None, 14, None), ("  ", None, 14, None), ("Braces { here", None, 14, None)]:
    c = Character("V", max_words=None if words == 14 else words, max_chars=chars)
    ok, template = b._valid_line(line, set(names) if names is not None else None, c)
    add("valid_line", [line, names, words, chars], [ok, template])

for text, sources in [("You're P3, lap 12.", [{"position": 3}, "lap 12"]), ("It costs 50 gold.", [{"price": 40}]),
                      ("Gap 0.4 seconds", [{"gap": 0.4321}]), ("Born in 1990, 3,5 kg", ["1990", 3.5]), ("-5 degrees", [5]),
                      ("No numbers.", []), ("Room 2b and 7", [{"r": 2}])]:
    allowed = _allowed_numbers(*sources)
    add("bad_numbers", [text, sources], [m for m in _NUMBER.findall(text) if not _number_ok(m, allowed)])

for text in ['"Not again," she mutters. "Go."', '"Hello," he says.', "Plain speech.", '"Only quoted."', '"A" b "C" d']:
    add("speech_only", [text], _speech_only(text))

for before, now in [(None, {"a": 1}), ({"a": 1}, {"a": 1.4}), ({"a": 1}, {"a": 2}), ({"a": "x"}, {"a": "y"}), ({"a": 1}, {"b": 1}),
                    ({"hp": 100}, {"hp": 60}), ({"hp": 100}, {"hp": 40}), ({"f": True}, {"f": 1})]:
    add("changed", [before, now], _changed(before, now))

for options, seed in [(["alloy", "ash", "nova"], "GUARD"), (["a", "b"], ""), (["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx",
                                                                              "nova", "sage", "shimmer", "verse", "marin", "cedar"], "MIRA")]:
    add("stable_pick", [options, seed], stable_pick(options, seed))
for text in ["", "raider", "u1", "é漢"]:
    add("fnv1a", [text], minds.fnv1a(text))

# ---------------- memory recall ----------------

clock = {"t": 0.0}
m = Memory(None, clock=lambda: clock["t"])
for t, text, imp, about in [(0, "the player stole bread", 0.8, None), (10, "Ana likes ships", 0.6, "Ana"), (20, "it rained", 0.2, None),
                            (30, "the bread was warm", 0.5, None), (40, "Bo said hello", 0.35, "Bo"), (50, "ships sail at dawn", 0.4, None),
                            (60, "the king died", 0.9, None), (70, "a cat sat", 0.1, None)]:
    clock["t"] = float(t)
    if about:
        m.add("s", "MIRA", text, imp, about=about)
    else:
        m.add("s", "MIRA", text, imp)
notes = m.notes("s", "MIRA")
for query, k, personal in [("", 6, True), ("ships", 3, True), ("bread player", 4, False), ("king", 1, True)]:
    add("recall", [notes, query, k, personal], m.recall("s", ["MIRA"], query, k, personal))

# ---------------- prompts ----------------

SPECS = [
    {"name": "VEGA", "personality": "an over-excited race commentator", "lines": {"*": ["What a move by {who}!"]}},
    {"name": "MIRA", "personality": "a gruff smith", "tools": {"give": {"item": "wood"}, "refuse_service": {}},
     "trust": {"give": 0.3}, "max_chars": 120, "invent": False, "language": "French"},
    {"name": "ANA", "max_words": 8, "language": "auto", "tools": {"boost": {"seconds": [0.5, 2.5]}}},
]
CARD = souls.card({"summary": "a gruff smith", "voice": "short, dry", "secrets": ["I sold the king's sword"], "mood": "wary"}, "")
LORE = ["The village is Brookmere.", "The king died last winter."]


def char(spec):
    s = dict(spec)
    return Character(s.pop("name"), **s)


for spec in SPECS:
    c = char(spec)
    lang = "English"
    add("prompt", ["lines_system", spec, ["overtake", ["who", "whom"], 8, lang, None]], prompts.lines_system(c, "overtake", ["who", "whom"], 8, lang))
    add("prompt", ["lines_system", spec, ["a battle starts", None, 8, lang, 60]], prompts.lines_system(c, "a battle starts", None, 8, lang, 60))
    add("prompt", ["line_system", spec, ["overtake", ["who"], lang, None]], prompts.line_system(c, "overtake", ["who"], lang))
    add("prompt", ["decide_system", spec, [{"strategy": ["attack", "block"], "aggression": [0, 1]}, lang]],
        prompts.decide_system(c, Shape.of({"strategy": ["attack", "block"], "aggression": [0, 1]}), lang))
    add("prompt", ["chat_system", spec, ["auto", souls.describe(CARD), LORE, "chat"]], prompts.chat_system(c, "auto", souls.describe(CARD), LORE))
    add("prompt", ["chat_system", spec, [lang, [], [], "greet"]], prompts.chat_system(c, lang, [], [], task="greet"))
    add("prompt", ["soul_system", spec, [lang]], prompts.soul_system(c, lang))
    add("prompt", ["recollect_system", spec, [lang]], prompts.recollect_system(c, lang))
    if c.tools:
        add("prompt", ["act_system", spec, [lang]], prompts.act_system(c, lang))
        add("prompt", ["deeds_system", spec, []], prompts.deeds_system(c))
shape = Shape.of({"name": "Ana", "hp": [0, 100], "tags": ["#ff0000"]})
add("prompt", ["create_system", None, ["a villager", {"name": "Ana", "hp": [0, 100], "tags": ["#ff0000"]}, "English"]],
    prompts.create_system("a villager", shape, "English"))
add("prompt", ["create_many_system", None, ["villagers", {"name": "Ana", "hp": [0, 100], "tags": ["#ff0000"]}, 4, "German"]],
    prompts.create_many_system("villagers", shape, 4, "German"))
add("prompt", ["context", None, [["Ana likes ships", "the king died"], {"lap": 3, "weather": "rain"}, {"Ana": 0.7, "Bo": -0.3, "Cy": 0.05}]],
    prompts.context(["Ana likes ships", "the king died"], {"lap": 3, "weather": "rain"}, {"Ana": 0.7, "Bo": -0.3, "Cy": 0.05}))
add("prompt", ["context", None, [[], None, None]], prompts.context([], None, None))
add("prompt", ["context", None, [[], {"big": "x" * 5000}, None]], prompts.context([], {"big": "x" * 5000}, None))
add("prompt", ["facts_block", None, [{"who": "BLAZE", "gap": 0.4, "list": [1, "é"]}]], prompts.facts_block({"who": "BLAZE", "gap": 0.4, "list": [1, "é"]}))
add("prompt", ["situation_block", None, [{"lap": 1, "nested": {"a": [True, None]}}]], prompts.situation_block({"lap": 1, "nested": {"a": [True, None]}}))
add("prompt", ["context_block", None, [None]], prompts.context_block(None))
add("prompt", ["context_block", None, [{"level": 3}]], prompts.context_block({"level": 3}))
add("prompt", ["history_block", None, [[["Ana", "hi"], ["MIRA", "Hmph."]], 10]], prompts.history_block([("Ana", "hi"), ("MIRA", "Hmph.")]))
add("prompt", ["worn_block", None, [["well well look who"], "well"]], prompts.worn_block(["well well look who"], "well"))
add("prompt", ["worn_block", None, [[], ""]], prompts.worn_block([], ""))
add("prompt", ["box_block", None, [80]], prompts.box_block(80))
add("prompt", ["picture_block", None, [1, "Ana"]], prompts.picture_block([1], "Ana"))
add("prompt", ["picture_block", None, [1, None]], prompts.picture_block([1]))
add("prompt", ["message_block", None, ["Ana", ""]], prompts.message_block("Ana", ""))
add("prompt", ["message_block", None, ["Ana", "Nice toy hammer."]], prompts.message_block("Ana", "Nice toy hammer."))
add("prompt", ["bond_block", None, ["Ana", None, "", 0.0, [], "calm", "", "", False]],
    prompts.bond_block("Ana", None, "", 0.0, [], "calm", ""))
add("prompt", ["bond_block", None, ["Ana", {"talks": 3}, "2 days ago", 0.65, ["likes ships"], "angry", "strongly", "a trainer", True]],
    prompts.bond_block("Ana", {"talks": 3}, "2 days ago", 0.65, ["likes ships"], "angry", "strongly", "a trainer", True))
add("prompt", ["bond_block", None, ["Bo", {"talks": 1}, "just now", -0.2, [], "wary", "a little", "", True]],
    prompts.bond_block("Bo", {"talks": 1}, "just now", -0.2, [], "wary", "a little", "", True))
add("prompt", ["bond_block", None, ["Ana", {"talks": 2}, "an hour ago", 0.5, [], "calm", "", "", True, 0.4]],
    prompts.bond_block("Ana", {"talks": 2}, "an hour ago", 0.5, [], "calm", "", "", True, 0.4))
add("prompt", ["bond_block", None, ["Ana", {"talks": 2}, "an hour ago", 0.5, [], "calm", "", "", True, 0.9]],
    prompts.bond_block("Ana", {"talks": 2}, "an hour ago", 0.5, [], "calm", "", "", True, 0.9))
add("prompt", ["steer_block", None, ["admit you went up to the office at 12:30"]], prompts.steer_block("admit you went up to the office at 12:30"))
add("prompt", ["steer_block", None, [""]], prompts.steer_block(""))
add("prompt", ["steer_block", None, ["  a  very " + "long " * 80 + "steer  "]], prompts.steer_block("  a  very " + "long " * 80 + "steer  "))
# a context too long keeps its keys (prompts._clip), the crowd's lines, the game's verdicts
BIG = {"request": "a lighthouse on the north shore", "kit": "k" * 3000, "town": ["House %d" % i for i in range(200)],
       "nested": {"f%d" % i: "v" * 20 for i in range(30)}, "gold": 40, "small": {"a": [1, 2]}}
for ctx in [BIG, {"first": "keep me", **{"k%d" % i: "y" * 60 for i in range(80)}}, ["x" * 50] * 100, "z" * 5000,
            {"only": "é" * 4500}, {"a": [1, 2, 3, 4, 5], "b": "c" * 3990}]:
    add("prompt", ["context_block", None, [ctx]], prompts.context_block(ctx))
    if isinstance(ctx, dict):
        add("prompt", ["facts_block", None, [ctx]], prompts.facts_block(ctx))
add("prompt", ["remark_system", None, ["an old fisherman", "English", None]], prompts.remark_system("an old fisherman", "English"))
add("prompt", ["remark_system", None, ["someone in the crowd", "French", 60]], prompts.remark_system("someone in the crowd", "French", 60))
add("prompt", ["remark_user", None, ["the builder raised a lighthouse"]], prompts.remark_user("the builder raised a lighthouse"))
from kinloom.brain import reason, refused_note  # noqa: E402
from kinloom.shapes import Items  # noqa: E402
for verdict in [None, True, False, "", "  too   far\n east ", "x" * 400, 5]:
    add("reason", [verdict], reason(verdict))
add("refused_note", ["open_door", {"door": "vault", "n": 2}, "the vault is locked"],
    refused_note("open_door", {"door": "vault", "n": 2}, "the vault is locked"))
for text in ['[{"a": 1}, {"a": "x,]}"}, 3]', '{"items": [{"a": 1}, {"a": "x,]}\\"q"}, 3]}', '```json\n{"items": [ {"a": 1} ,{"a": "x,]}"},3 ] }\n```',
             '{"say": "hi", "parts": ["a", "b"], "more": ["c"]}', '[{"kind": "house", "x": 1}, {"kind": "hou', '"no list"', '[]', '[ "\u00e9t\u00e9" , 2.5 ]']:
    for size in (1, 3, 1000):
        pieces = [text[i:i + size] for i in range(0, len(text), size)]
        items, got = Items(), []
        for piece in pieces:
            got += items.feed(piece)
        add("items", [pieces], got)

for refused in [None, {"answer": {"build": "tower", "x": 17, "name": "Tour étoile"}, "why": "no room at x=17, the plot ends at 10"},
                {"answer": ["a", 2, True, None], "why": "too many"}, {"answer": "x" * 2000, "why": "too long"}]:
    add("prompt", ["refused_block", None, [refused]], prompts.refused_block(refused))
for spec in [{"name": "A"}, {"name": "B", "warmth": 0.45, "secret_trust": 0.2, "warm_up": 0.1},
             {"name": "C", "warmth": 5, "secret_trust": -3, "warm_up": 9}, {"name": "D", "warmth": "0.5", "warm_up": -1}]:
    c = char(spec)
    add("feelings", [spec], [c.warmth, c.secret_trust, c.warm_up])
add("prompt", ["deeds_user", None, ["MIRA", "Ana", "Give me bread", "Fine, take it."]], prompts.deeds_user("MIRA", "Ana", "Give me bread", "Fine, take it."))
add("prompt", ["deeds_user", None, ["MIRA", "Ana", "", "Hello."]], prompts.deeds_user("MIRA", "Ana", "", "Hello."))
add("prompt", ["soul_user", None, ["a gruff smith", LORE]], prompts.soul_user("a gruff smith", LORE))
add("prompt", ["soul_user", None, ["a baker", []]], prompts.soul_user("a baker"))
add("prompt", ["repair", None, ["value must be a number"]], prompts.repair("value must be a number"))
add("prompt", ["stay_in_character", None, ["MIRA"]], prompts.stay_in_character("MIRA"))
add("prompt", ["say_new", None, []], prompts.say_new())
add("prompt", ["keep_secret", None, ["MIRA", "Ana"]], prompts.keep_secret("MIRA", "Ana"))
add("prompt", ["numbers_repair", None, []], prompts.numbers_repair())
add("prompt", ["write_in", None, ["auto"]], prompts.write_in("auto"))
# v1: the player's choices, characters talking together, the content rating
for spec in SPECS:
    add("prompt", ["suggest_system", spec, [3, "Ana"]], prompts.suggest_system(char(spec), 3, "Ana"))
for a, b in ((SPECS[0], SPECS[1]), (SPECS[1], SPECS[-1])):
    add("prompt", ["converse_system", a, [b, 4, "English", LORE]], prompts.converse_system(char(a), char(b), 4, "English", LORE))
    add("prompt", ["converse_system", a, [b, 2, "auto", []]], prompts.converse_system(char(a), char(b), 2, "auto", []))
add("prompt", ["suggest_user", None, [[["Ana", "hi"], ["MIRA", "Hmph."]], {"gold": 12}, ["Ask", "Leave"]]],
    prompts.suggest_user([("Ana", "hi"), ("MIRA", "Hmph.")], {"gold": 12}, ["Ask", "Leave"]))
add("prompt", ["suggest_user", None, [[], {}, ["Bonjour", "Au revoir"]]], prompts.suggest_user([], {}, ["Bonjour", "Au revoir"]))
CTX = "Memory:\n- the forge is hot\n\n"
add("prompt", ["converse_user", None, ["MIRA", CTX, "BAKER", "", "the smoke"]],
    prompts.converse_user("MIRA", CTX, "BAKER", "", "the smoke"))
add("prompt", ["converse_user", None, ["MIRA", "", "BAKER", "", ""]], prompts.converse_user("MIRA", "", "BAKER", "", ""))
for r in ("everyone", "teen", "mature", None):
    add("prompt", ["rating_line", None, [r]], prompts.rating_line(r))
add("prompt", ["impact_system", None, ["English"]], prompts.impact_system("English"))
add("prompt", ["impact_user", None, ["the player stole bread", "PLAYER", [["BAKER", "a warm baker", 0.0], ["GUARD", "", -0.25]]]],
    prompts.impact_user("the player stole bread", "PLAYER", [("BAKER", "a warm baker", 0.0), ("GUARD", "", -0.25)]))

DECL = {"name": "raider", "personality": "a cunning raider",
        "senses": {"hp": [0, 1], "dist": [0, 40], "armed": True, "enemy": ["idle", "alert"]},
        "actions": {"charge": {"speed": [0.5, 3.0]}, "shoot": {"burst": [1, 5]}, "retreat": {}},
        "rules": {"retreat": ["hp low"], "shoot": ["armed", "dist below 20"], "charge": {"score": 0.5, "args": {"speed": "dist high"}}},
        "variants": 3}


def decl_of(d):
    return minds.Declaration(d["name"], d.get("personality", ""), d["senses"], d["actions"], d.get("rules"), d.get("variants", 3))


dec = decl_of(DECL)
add("prompt", ["mind_system", DECL, ["English"]], prompts.mind_system(dec, "English"))
add("prompt", ["minds_user", DECL, [3, DECL["rules"]]], prompts.minds_user(dec, 3, DECL["rules"]))
add("prompt", ["minds_user", DECL, [1, None]], prompts.minds_user(dec, 1, None))
best = dec.offline
worst = minds.validate({"charge": {"score": 2}}, dec)[0]
add("prompt", ["mind_learn_user", DECL, [best, 0.75, worst, -0.125, [[{"hp": 0.5, "dist": 12}, "charge", -1]], 20, 18,
                                         [[2.5, "shoot", "dist below 20", 0.3, 40]]]],
    prompts.mind_learn_user(best, 0.75, worst, -0.125, [({"hp": 0.5, "dist": 12}, "charge", -1.0)], 20, 18,
                            [(2.5, "shoot", "dist below 20", 0.3, 40)]))

# ---------------- minds ----------------

SENSES = DECL["senses"]
for text in ["hp low", "HP high", "dist below 12", "dist < 12", "dist >= 50", "dist around 10", "armed", "not armed", "!armed",
             "enemy is alert", "enemy is ALERT", "enemy is fleeing", "speed low", "hp below x", "hp", "armed low", "not hp low",
             "dist above 1e400", 42, "a" * 130, "enemy alert", "hp around 0.333333"]:
    rule, error = minds.parse_rule(text, minds.senses_of(SENSES))
    add("parse_rule", [text, SENSES], [rule, error])
for rule, senses in [(["hp", "low", 0, 1], {"hp": 0.25}), (["hp", "high", 0, 1], {}), (["dist", "below", 12, 2], {"dist": 10}),
                     (["dist", "above", 12, 2], {"dist": 15}), (["dist", "around", 10, 6], {"dist": 13}), (["armed", "flag", 0, 0], {"armed": True}),
                     (["armed", "not", 0, 0], {"armed": 1}), (["enemy", "is", "alert", 0], {"enemy": "alert"}),
                     (["enemy", "is", "alert", 0], {"enemy": 3}), (["dist", "below", 12, 2], {"dist": "far"}),
                     (["dist", "above", 0, 0.0001], {"dist": 1e9})]:
    add("rule_value", [rule, senses], minds.rule_value(rule, senses))
for program in [{"retreat": {"score": 5, "when": ["hp low", "hp low"]}}, {"Charge": ["dist high"], "fly": {}},
                {"shoot": {"when": "armed", "args": {"burst": 9}}}, {"charge": {"args": {"speed": "dist low"}}},
                {"charge": {"score": "x"}}, {"shoot": {"when": ["bad rule"]}}, [], {"retreat": {"when": 3}},
                {"charge": {"args": {"speed": "nope"}, "score": 1}}, {"shoot": {"args": {"burst": "x"}}}]:
    clean, errors = minds.validate(program, dec)
    add("validate", [program, DECL], [clean, errors])
for d in [DECL, dict(DECL, rules=None, variants=1), {"name": "scout", "senses": {"noise": [0, 1]}, "actions": {"run": {}, "hide": {}},
                                                     "variants": 2},
          # a list argument is given as it is (only [sense, op, p1, p2, lo, hi, whole] is set by the senses)
          {"name": "loot", "senses": {"hp": [0, 1]}, "actions": {"drop": {"items": ["sword"], "count": [1, 3]}, "wait": {}},
           "rules": {"drop": {"when": ["hp low"], "args": {"count": "hp low"}}}, "variants": 1}]:
    dd = decl_of(d)
    add("compile", [d], minds.Mind(dd).compiled())
    mind = minds.Mind(dd)
    for senses, who in [({"hp": 0.1, "dist": 30, "armed": True}, "u1"), ({"hp": 0.9, "dist": 8, "armed": True, "enemy": "alert"}, "u2"),
                        ({"hp": 0.9, "dist": 10, "armed": False}, "u3"), ({"hp": 0.52, "dist": 30, "armed": True}, "u1"),
                        ({"noise": 0.5}, "s1"), ({}, None)]:
        add("think", [d, senses, who], mind.think(senses, who))
    add("explain", [d, {"hp": 0.4, "dist": 15, "armed": True}, "u9"], mind.explain({"hp": 0.4, "dist": 15, "armed": True}, "u9"))
import random  # noqa: E402

rnd = random.Random(7)
samples = [({"hp": rnd.random(), "dist": rnd.uniform(0, 40), "armed": rnd.random() < 0.5, "enemy": rnd.choice(["idle", "alert"])},
            rnd.choice(["charge", "shoot", "retreat"]), 0.0) for _ in range(300)]
samples = [(s, a, (1.0 if (a == "retreat") == (s["hp"] < 0.3) else -0.5) + (0.5 if a == "shoot" and s["armed"] else 0.0))
           for s, a, _ in samples]
add("evidence", [DECL, [list(x) for x in samples]], [list(x) for x in minds.evidence(dec, samples)])

for name, args in [("senses_error", [{"hp": [1, 1]}]), ("senses_error", [{"bad name": True}]), ("senses_error", [{}]),
                   ("senses_error", [{"x": "text"}])]:
    try:
        minds.senses_of(args[0])
        add(name, args, None)
    except ValueError as e:
        add(name, args, str(e))

with open(os.path.join(HERE, "vectors.json"), "w", encoding="utf-8", newline="\n") as f:
    json.dump(plain(OUT), f, ensure_ascii=False, indent=0)
print("vectors.json: %d vectors" % len(OUT))
