"""The Kinloom brain: seven verbs that never break a game.

    character(name, personality, ...)   who speaks, decides or acts
    say(name, event, facts)             an instant line with the real facts filled in (line banks)
    chat(name, message, facts)          a conversation reply grounded in facts and memory
    decide(name, situation, choices)    an instant decision shaped like the choices (refreshed in the background)
    act(name, situation)                tool calls the character chose (validated), returned once
    create(what, example, ...)          content shaped like the example (the example is the offline answer)
    event(text, about)                  something happened; characters remember it

Everything a model returns is validated; every call has a time limit; without a model, the game's own examples answer.
"""
import atexit
import collections
import copy
import collections.abc
import inspect
import itertools
import json
import math
import os
import random
import re
import tempfile
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor

from . import config as _config
from . import harness as _harness
from . import media as _media
from . import minds as _minds
from . import prompts
from . import souls as _souls
from . import voice as _voice
from .memory import Memory
from .providers import Reply
from .providers import complete as _complete
from .shapes import CUT, Items, Shape, clean_text, find_json

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_DIGIT = re.compile(r"\d")
_NUMBER = re.compile(r"(?<![A-Za-z])-?\d+(?:[.,]\d+)?")
_META = re.compile(r"(ignore (all |any |the )?(previous|prior|above|your)|(your|my|these|previous|system|developer) instructions?\b|"
                   r"system prompt|as an ai\b|language model|developer mode|jailbreak|placeholder)", re.I)
SELF = "(self)"          # memory notes about the character's own life, said in a conversation
_PREFIX = re.compile(r"^\s*[\w .'-]{1,24}:\s+")
# Small models copy the prompt's own labels into the reply ("Memory: - Ana said: ... / I answered: ..."): not speech.
_PROMPTISH = re.compile(r"/ I answered:|\bjson object\b|\b(memory|world facts|conversation so far): -|"
                        r"^\s*(memory|facts|game state|conversation so far|feelings|world facts)\s*:", re.I)
_SENTENCE = re.compile(r"[^.!?]+[.!?]*")
_STAGE = re.compile(r"\*([^*\n]{1,200})\*|\(([^()\n]{1,200})\)(?=\s|$|[.,!?])|\[([^\]\n]{1,60})\]")   # *smiles*, (sighs), [pause]


_QUOTE = re.compile('["“”]')


def _speech_only(text):
    """A model writing prose ("Not again," she mutters, wiping the anvil. "Go.") : only the quoted speech is said.
    Only when the text starts or ends with a quote and the quotes pair up; a quote inside speech stays."""
    t = text.strip()
    if not t or (t[0] not in '"“' and t[-1] not in '"”'):
        return text
    parts = _QUOTE.split(t)
    if len(parts) < 3 or len(parts) % 2 == 0:
        return text
    said = [p.strip() for p in parts[1::2] if p.strip()]
    told = " ".join(p.strip() for p in parts[0::2] if p.strip())
    if not said or len(told.split()) < 2:
        return text
    return " ".join(said)


CHAT_KINDS = frozenset(("chat", "greet", "converse", "suggest", "deeds", "line"))   # what players wait for
MAX_SUGGESTIONS = 6


class _Follow:
    """Another model id on whatever provider a Fallback uses now: when a dead key makes it switch, this follows
    instead of calling the dead key forever."""

    def __init__(self, fallback, model):
        self._fallback, self._model, self._made = fallback, model, (None, None)
        self._lock = threading.Lock()

    def _now(self):
        current = self._fallback.current
        with self._lock:
            if self._made[0] is not current:
                self._made = (current, _with_model(current, self._model))
            return self._made[1]

    def complete(self, *args, **kwargs):
        return self._now().complete(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._now(), name)


def _with_model(p, model):
    """The same endpoint and key with another model id."""
    if hasattr(p, "current") and hasattr(p, "rest"):    # several providers: the one in use, now and after a switch
        _with_model(p.current, model)                  # refused now (no provider to share) rather than at the first call
        return _Follow(p, model)
    p = getattr(p, "current", p)
    if isinstance(p, _harness.Harness):
        return _harness.Harness(p.kind, model, p.command)
    if p is None or not hasattr(p, "complete"):
        raise ValueError("models: a model id needs a provider to share (give a provider instead)")
    q = copy.copy(p)
    q.model = str(model)
    if isinstance(getattr(q, "_adapt", None), set):
        q._adapt = set(q._adapt)                       # what one model refuses says nothing about another
    return q


def _models(given, provider):
    """{"chat" | "background": provider}: a model id (same endpoint and key) or a provider."""
    if not given:
        return {}
    if not isinstance(given, dict):
        raise ValueError('models: an object like {"background": "a-cheaper-model"}')
    out = {}
    for bucket, spec in given.items():
        if bucket not in ("chat", "background"):
            raise ValueError('models: "%s" is not a task group (use "chat" and "background")' % bucket)
        if spec is None:
            continue
        if isinstance(spec, str):
            out[bucket] = _with_model(provider, spec.strip()) if provider is not None and spec.strip() else None
        elif hasattr(spec, "complete"):
            out[bucket] = spec
        else:
            raise ValueError("models.%s: a model id or a provider" % bucket)
    return {k: v for k, v in out.items() if v is not None}


def _rating(value):
    if value is None or value == "":
        return None
    v = str(value).strip().lower()
    if v not in prompts.RATINGS:
        raise ValueError('rating: "everyone", "teen" or "mature", got %r' % (value,))
    return v


def _unstage(m):
    """Stage directions go; a name in asterisks (*Bright Mercy*: every word capitalized, three at most) stays, plain."""
    keep = _souls.stage_keep(m.group(1) or "")
    return " " if keep is None else keep
MAX_NAME = 48
MAX_WHAT = 500                                  # characters of create's `what` (more is cut, and journaled)
MAX_EVENT = 160               # event names may describe the moment ("challenging another trainer to a battle")
MAX_CHARACTERS = 5000         # across sessions: past this, unknown names get a throwaway character (nothing grows)
MAX_PER_SESSION = 300         # one session (one player online) never fills the table for everyone else
_CONFIG_KEYS = ("personality", "soul", "lines", "offline", "events", "tools", "max_words", "max_chars", "every", "language",
                "group", "trust", "invent", "voice", "warmth", "secret_trust", "warm_up")
MAX_STEER = 300               # what the game decides for the next reply (steer), in characters
MAX_WHY = 300                 # why the game refused a created answer (create's check), in characters
MAX_ABOUT = 300               # what a remark is about, in characters
REMARK_WORDS = 20             # a remark longer than this is cut to whole sentences
DEFAULT_WHO = "someone in the crowd"
MAX_STREAMED = 200            # items of one list answer handed to each() as they come


def reason(verdict):
    """What a game's check returned, as why it refuses ("" when it accepts): None, "" or True accept; False refuses."""
    if verdict is None or verdict is True or verdict == "":
        return ""
    if verdict is False:
        return "it breaks the game's rules"
    return " ".join(clean_text(str(verdict)).split())[:MAX_WHY] or "refused"


def judged(check, *args):
    """(why, error): reason(check(*args)); a check that raises refuses (error says why), never breaking the call."""
    try:
        return reason(check(*args)), None
    except Exception as e:  # a game callback must never break the call
        return "the game's check failed", "%s: %s" % (type(e).__name__, e)


def refused_note(tool, args, why):
    """What a character remembers when the game refused one of its actions (act's check)."""
    return "The game did not let me %s %s: %s" % (tool, json.dumps(args, ensure_ascii=False), why)
REPLY_TIMEOUT = 8.0           # seconds a spoken reply may take on a hosted model (kinloom.json "reply_timeout")
AUTO = "auto"                 # language="auto": replies in the language of whoever talks to the character
DEFAULT_LANGUAGE = "English"  # what "auto" writes when nobody is talking (prepared lines, decisions, content)
MAX_WAITING = 50              # actions decided while talking that nobody collected yet, per character


def _num(value, what):
    """A finite number from what the game passed (a number, or text holding one); ValueError that says which argument."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s: a number, got %r" % (what, value)) from None
    if isinstance(value, bool) or not math.isfinite(f):
        raise ValueError("%s: a finite number, got %r" % (what, value))
    return f


def _mapping(value, what):
    """{name: value} from what the game passed (None: nothing); TypeError that says which argument."""
    if value is None:
        return {}
    if isinstance(value, collections.abc.Mapping):
        return dict(value)
    raise TypeError("%s: an object {name: value}, got %s" % (what, type(value).__name__))


def _limit(max_chars):
    """A box size given with one call (None: the character's own)."""
    v = _finite(max_chars)
    return max(10, min(2000, int(v))) if v else None


def _event_key(event):
    """The one spelling of an event name used by lines, banks and say() (a long name is cut the same way everywhere)."""
    return clean_text(str(event))[:MAX_EVENT]


_TAKE = threading.Lock()      # an action is handed out once: by the reply that decided it (Line.do) or by act()


class _Action:
    __slots__ = ("tool", "args", "taken")

    def __init__(self, tool, args):
        self.tool, self.args, self.taken = tool, args, False


class Line(str):
    source: str
    _actions: list
    _do: "list | None"
    """What say() and chat() return: the text (a plain string: compare it, show it, send it as JSON) plus

        source   "model" (written for this call), "prepared" (written earlier by the model: line banks, first greetings)
                 or "offline" (the game's own lines and replies: no model, a failure, the budget, nothing usable)
        do       chat: [(tool, args)] the character decided in this reply. Reading it takes them, so act() does not
                 return them again (act() returns what nobody took; Python tool functions run only through act()).
    """

    def __new__(cls, text="", source="offline", actions=None):
        s = str.__new__(cls, text or "")
        s.source = source
        s._actions = list(actions or [])
        s._do = None
        return s

    @property
    def text(self):
        """The text as a plain str (the Line already is one: `reply.text` and `reply` show the same words)."""
        return str.__str__(self)

    @property
    def do(self):
        if self._do is None:
            with _TAKE:
                self._do = [(a.tool, a.args) for a in self._actions if not a.taken]
                for a in self._actions:
                    a.taken = True
        return list(self._do)

    @property
    def offline(self):
        return self.source == "offline"
MAX_SPEAKERS = 500            # people one character keeps bonds and conversations with
BANK_SIZE = 8
POOL_SIZE = 5
MAX_LINE = 140
MAX_REPLY = 400


def fill(template, facts):
    """Replaces {name} placeholders with facts, numbers formatted for people."""
    def value(m):
        v = facts.get(m.group(1), "")
        return format_value(v)
    return _PLACEHOLDER.sub(value, template)


def format_value(v):
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            return ""
        if v.is_integer():
            return str(int(v))
        if abs(v) >= 100:
            return str(int(round(v)))
        r = round(v, 1)
        if r == 0:
            r = round(v, 2)
        return ("%.2f" % r).rstrip("0").rstrip(".") if r != round(v, 1) else ("%.1f" % r)
    return clean_text(str(v))[:80]


def _allowed_numbers(*sources):
    found = []

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            if math.isfinite(x):
                found.append(float(x))
        elif isinstance(x, str):
            for m in _NUMBER.findall(x):
                try:
                    found.append(float(m.replace(",", ".")))
                except ValueError:
                    pass
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    for s in sources:
        walk(s)
    return found


def _number_ok(text_number, allowed):
    try:
        n = float(text_number.replace(",", "."))
    except ValueError:
        return True
    decimals = len(text_number.split(".")[1]) if "." in text_number else (len(text_number.split(",")[1]) if "," in text_number else 0)
    for a in allowed:
        if abs(a - n) < 1e-9 or round(a, decimals) == n or round(abs(a), decimals) == abs(n):
            return True
    return False


def _feeling_setting(value, what, low, high, default):
    """warmth / secret_trust / warm_up: a number clamped to [low, high]; None is the default."""
    if value is None:
        return default
    return max(low, min(high, _num(value, what)))


class Character:
    def __init__(self, name, personality="", lines=None, offline=None, events=None, tools=None, max_words=None, every=8.0, language=None,
                 group=None, trust=None, invent=True, voice=None, max_chars=None, warmth=None, secret_trust=None, warm_up=None):
        self.name = clean_text(str(name))[:MAX_NAME] or "?"
        self.group = clean_text(str(group))[:MAX_NAME] if group else None
        self.personality = clean_text(personality)[:600]
        if isinstance(lines, (list, tuple)):
            lines = {"*": list(lines)}
        if not isinstance(lines, dict):
            lines = {}
        # lines: {event: ["...", ...]} or {event: {"when": "what is happening, for the model", "lines": [...]}}
        self.lines, self.when = {}, {}
        for k, v in list(lines.items())[:50]:
            key = _event_key(k)
            if isinstance(v, dict):
                when = " ".join(clean_text(str(v.get("when") or "")).split())[:200]
                if when:
                    self.when[key] = when
                v = v.get("lines")
            items = v if isinstance(v, (list, tuple)) else ([] if v is None else [v])
            self.lines[key] = [str(x)[:MAX_LINE * 2] for x in items if x is not None][:100]
        # offline: one reply, or several said in turn (never the same twice in a row) when there is no model
        many = [clean_text(str(x))[:MAX_REPLY] for x in offline[:50]] if isinstance(offline, (list, tuple)) else []
        self.offlines = [x for x in many if x]
        self.offline = self.offlines[0] if self.offlines else (clean_text(str(offline))[:MAX_REPLY] if offline else "")
        self._offline_turn = 0
        # events: ["overtake", ...] or {"overtake": ["who", "whom"]} / {"overtake": {"who": "BLAZE"}} (fact names to use)
        if isinstance(events, dict):
            self.events = {_event_key(k): ([str(x) for x in v][:24] if isinstance(v, (list, tuple))
                                           else list((v if isinstance(v, dict) else {}).keys())[:24])
                           for k, v in list(events.items())[:30]}
        else:
            self.events = {_event_key(e): None for e in list(events if isinstance(events, (list, tuple)) else [])[:30]}
        # max_words: how long the character talks; unset, lines ("say") are 14 words at most and replies ("chat") 25
        self.max_words = None if max_words is None else max(3, min(60, int(_num(max_words, "max_words"))))
        self.line_words = self.max_words or 14
        self.reply_words = self.max_words or 25
        # max_chars: the text box's size; what the model writes never goes past it (whole sentences, else cut on a word)
        self.max_chars = None if max_chars is None else max(10, min(2000, int(_num(max_chars, "max_chars"))))
        self.every = max(0.5, _num(every, "every"))
        self.language = language
        # tools: its own ({name: example args} or functions), and/or names of the game's tools (Brain.tools), or "all"
        self.tool_refs = _tool_refs(tools)
        self.own_tools, self.own_functions = _tools(tools)
        self.tools, self.functions = dict(self.own_tools), dict(self.own_functions)
        self.invent = invent is not False     # False: never make up names, places, events or numbers
        # trust: {tool: feeling} a tool is used while talking only for speakers the character feels at least this for
        self.trust_wanted = {str(k): max(-1.0, min(1.0, float(v))) for k, v in (trust.items() if isinstance(trust, dict) else [])
                             if _finite(v) is not None}
        self.trust = {k: v for k, v in self.trust_wanted.items() if k in self.tools}
        # warmth: the feeling for anyone before any talk; warm_up: the most one conversation can win (however sweet the
        # words); secret_trust: the feeling above which the character may share a secret
        self.warmth = _feeling_setting(warmth, "warmth", -1.0, 1.0, 0.0)
        self.warm_up = _feeling_setting(warm_up, "warm_up", 0.0, 2.0, _souls.TALK_RISE)
        self.secret_trust = _feeling_setting(secret_trust, "secret_trust", -1.0, 1.0, _souls.SECRET_TRUST)
        self.card = None          # the soul card (souls.card) when the game asked for a soul
        self.card_ready = False   # False while the model is still writing it
        self.soul_key = None      # what the card was made from: cards and prepared greetings are shared by it
        # voice: how they sound ("low, tired, warm"), or {"id": a provider's voice id, "describe": ...}
        if isinstance(voice, dict):
            self.voice_id = clean_text(str(voice.get("id") or ""))[:120] or None
            self.voice = clean_text(str(voice.get("describe") or ""))[:300]
        else:
            self.voice_id, self.voice = None, clean_text(str(voice or ""))[:300]

    def moment(self, event):
        """What the model reads for an event: its description when the game gave one, else its name."""
        return self.when.get(event, event)


MAX_TOOLS = 100


def _tool_refs(tools):
    """The game's tools a character uses by name: ["open_door", ...], or ["*"] for "all" (True)."""
    if tools is True or (isinstance(tools, str) and tools.strip().lower() == "all"):
        return ["*"]
    if isinstance(tools, (list, tuple)):
        out = []
        for x in tools[:MAX_TOOLS]:
            if isinstance(x, str) and x.strip():
                name = "*" if x.strip().lower() == "all" else clean_text(x.strip())[:MAX_NAME]
                if name not in out:
                    out.append(name)
        return out
    return []


def _tools(tools):
    """{name: Shape of args} and {name: python function} from a dict of examples or a list of functions (names of the
    game's tools in the list are left to Brain.tools)."""
    shapes, functions = {}, {}
    if not tools or isinstance(tools, str) or tools is True:
        return shapes, functions
    if isinstance(tools, dict):
        items = list(tools.items())[:MAX_TOOLS]
    elif isinstance(tools, (list, tuple)):
        items = []                       # functions, {name: example} objects (JSON clients) and names (left out here)
        for f in tools[:MAX_TOOLS]:
            if isinstance(f, dict):
                items.extend(list(f.items())[:MAX_TOOLS])
            elif not isinstance(f, str):
                items.append((getattr(f, "__name__", "tool"), f))
    else:
        raise ValueError("tools: {name: example args}, a list of functions or tool names, or \"all\"")
    for name, spec in items:
        name = clean_text(str(name))[:MAX_NAME]
        if callable(spec):
            functions[name] = spec
            example, doc = _signature_example(spec)
            shapes[name] = (Shape.of(example) if example else None, doc)
        else:
            shapes[name] = (Shape.of(spec) if spec else None, "")
    return shapes, functions


def _signature_example(fn):
    example = {}
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return {}, ""
    for p in sig.parameters.values():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        if p.default is not inspect.Parameter.empty and p.default is not None:
            example[p.name] = p.default
        else:
            ann = p.annotation
            example[p.name] = {float: 0.0, int: 0, bool: False}.get(ann, "text")
    return example, clean_text(inspect.getdoc(fn) or "")[:200]


class _Bank:
    def __init__(self):
        self.templates, self.unused, self.recent = [], [], collections.deque(maxlen=3)
        self.filling = False
        self.failures = 0


class _Decision:
    def __init__(self, value):
        self.value, self.at, self.situation, self.thinking = value, None, None, False


MIN_SAMPLES = 12      # rewards each variant needs before minds compare them
MIN_EPISODES = 6      # finished fights (rounds, lives) each variant needs, when the game says when they end
GAMMA = 0.8           # a decision also earns the rewards that follow it, discounted (credit for setting things up)
CREDIT_CUTOFF = GAMMA ** 10
COMPOUND = 0.4       # share of offline learning steps that try two changes at once
BUFFER = 4000         # recent (senses, action, return) moments a mind learns from
HEARSAY = 0.5         # a rumor moves opinions half as much as seeing it (times trust in the teller)
RUMOR_DECAY = 0.8     # a rumor's importance on each hop
MIN_RUMOR = 0.1       # below this importance nobody bothers to tell


def _name(x):
    return clean_text(str(x))[:MAX_NAME] if x not in (None, "") else None


MAX_KEYS = 2000     # entries per cache (decisions, banks, pools...): games that put live data in keys stay bounded


def _trim(table, cap=MAX_KEYS):
    """The oldest entries go once a table passes its cap (dicts keep insertion order). Called under the brain's lock."""
    while len(table) > cap:
        del table[next(iter(table))]


def _finite(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _bound(score, side):
    """The mean plus (side=1) or minus (side=-1) one standard error."""
    n, total, squares = score
    mean = total / n
    return mean + side * math.sqrt(max(squares / n - mean * mean, 1e-9) / n)


def _learn_every(learn):
    """Seconds between learning steps; 0/None/False: never learn."""
    f = _finite(learn)
    return max(1.0, f) if f else 0.0


class _MindState:
    def __init__(self, decl, mind, sig, learn):
        self.decl, self.mind, self.sig, self.learn = decl, mind, sig, learn
        self._next = 1
        self.ids = [self.new_id() for _ in mind.variants]   # a birth id per variant: rewards for a replaced one are ignored
        self.reset_stats(len(mind.variants))
        self.units = {}                   # who -> (variant, id, action, senses) of the last think
        self.trace = {}                   # who -> [[senses, action, return so far, weight], ...] decisions still earning
        self.buffer = collections.deque(maxlen=BUFFER)
        self.last_learn = None
        self.busy = False
        self.generation = 0
        self.episodic = False             # the game marks the end of fights (reward(..., done=True))
        self.curve = []                   # mean reward between learning steps
        self.window = [0, 0.0]
        self.rnd = random.Random(_minds.fnv1a(decl.name))

    def new_id(self):
        self._next += 1
        return self._next - 1

    def reset_stats(self, n):
        self.stats = [[0, 0.0, 0.0] for _ in range(n)]     # per decision: count, total, total of squares
        self.episodes = [[0, 0.0, 0.0] for _ in range(n)]  # per finished episode (when the game passes done)
        self.samples = [collections.deque(maxlen=12) for _ in range(n)]
        self.open = {}                                      # who -> [variant, id, return so far] of an episode under way

    def scores(self):
        """(count, total) per variant: whole episodes when the game marks their end (a round's outcome counts once,
        however long it lasted), else single decisions (continuous games)."""
        return self.episodes if self.episodic else self.stats


class Brain:
    """Shared engine: provider, budget, workers, memory and every session's state. Use `Kinloom` (a session view)."""

    def __init__(self, provider="auto", memory_path="auto", language=None, calls_per_minute=None,
                 prices=None, clock=time.monotonic, call_timeout=12.0, workers=4, folder=".", content_filter=None, voice="auto",
                 models=None, rating=None):
        cfg = _config.load(folder)          # optional kinloom.json; explicit arguments win
        self.provider = _config.provider(cfg) if provider == "auto" else provider
        # models: {"chat" | "background": a model id on the same endpoint, or a provider}: the main model for what players
        # wait for, a cheaper one for the rest. rating: "everyone" | "teen" | "mature", a rule in every prompt.
        # given here: a mistake raises; in kinloom.json: refused in the journal (like every SDK), the game still starts
        refused = []
        try:
            self.models = _models(models if models is not None else cfg.get("models"), self.provider)
        except ValueError as e:
            if models is not None:
                raise
            self.models, refused = {}, refused + ["kinloom.json: %s" % e]
        try:
            self.rating = _rating(rating if rating is not None else cfg.get("rating"))
        except ValueError as e:
            if rating is not None:
                raise
            self.rating, refused = None, refused + ["kinloom.json: %s" % e]
        # voice: found from the environment with the model (a provider given by hand, as in tests, means no voice
        # unless one is given too); None: no audio, the text still works
        self.voice = (_voice.detect_voice() if provider == "auto" else None) if voice == "auto" else voice
        self._voice_dir = None
        self.language = language or cfg["language"]
        # a language someone chose (here or in kinloom.json) guides voices and recognition; the default one does not
        chosen = language or (cfg["language"] if cfg["language"] != _config.DEFAULTS["language"] else None)
        self.voice_language = chosen
        self.limit = max(1, int(calls_per_minute or cfg["calls_per_minute"]))
        self.prices = prices or cfg.get("prices")
        if self.prices is not None and not (isinstance(self.prices, dict) and all(
                _finite(v) is not None and v >= 0 for k, v in self.prices.items() if k in ("input", "output", "cached_input"))):
            if prices is not None:
                raise ValueError('prices: {"input": $/M tokens, "output": ..., "cached_input": ...} as numbers, got %r' % (prices,))
            refused.append('kinloom.json: prices must be {"input": n, "output": n, "cached_input": n} in dollars per '
                           'million tokens, got %r (no cost is counted)' % (self.prices,))
            self.prices = None
        # Content filter: banned words from kinloom.json and/or a function text -> True (allowed) / False (blocked).
        words = [w for w in (cfg.get("banned_words") or []) if isinstance(w, str) and w.strip()]
        self._banned = re.compile(r"\b(%s)\b" % "|".join(re.escape(w.strip()) for w in words), re.I) if words else None
        self.content_filter = content_filter
        if memory_path == "auto":
            memory_path = os.path.join(folder, cfg["memory"]) if cfg.get("memory") else None
        self.clock = clock
        self.wall = time.time                  # wall clock for bonds ("last time: 2 days ago"), survives restarts
        self.call_timeout = call_timeout
        self.hedge_after = 2.5                 # seconds without a first word before a conversation asks again
        self.stall_after = 3.0                 # seconds without a new word before a started reply is cut
        self.inner_grace = 1.5                 # seconds the inner part may take once the reply itself is said
        self._spent = collections.deque()      # (time, dollars) of recent calls, for the cost caps
        self.max_cost_per_hour = _finite(cfg.get("max_cost_per_hour"))   # dollars; needs declared prices
        self.max_cost_per_day = _finite(cfg.get("max_cost_per_day"))
        # reply_timeout: how long a spoken reply may take on a hosted model (never past call_timeout)
        self.reply_timeout = REPLY_TIMEOUT
        if cfg.get("reply_timeout") is not None:
            rt = _finite(cfg.get("reply_timeout")) if not isinstance(cfg.get("reply_timeout"), bool) else None
            if rt is None or rt <= 0:
                refused.append("kinloom.json: reply_timeout must be a number of seconds, got %r" % (cfg.get("reply_timeout"),))
            else:
                self.reply_timeout = max(1.0, min(120.0, rt))
        self.memory = Memory(memory_path)
        self._lock = threading.RLock()
        self._characters = {}                  # (session, name) -> Character
        self._per_session = {}                 # session -> how many of them
        self._session_used = {}                # session -> when it last used a character (the idlest goes first)
        self._ticks = itertools.count()        # an order of use (clocks can tie)
        self._declared = set()                 # (session, name) declared by the game (not created on the fly)
        self._banks, self._decisions, self._pending, self._pools, self._history, self._state = {}, {}, {}, {}, {}, {}
        self._last_decided, self._remark_turns = {}, {}
        self._last_undo = {}                   # (session, name) -> what the last reply changed inside (chat's check)
        self._minds = {}                       # (session, name) -> _MindState
        self._opinions = {}                    # session -> {holder: {target: -1..1}}
        self._moods = {}                       # (session, name) -> {word, level, t}
        self._gestures = {}                    # (session, name) -> the visible gesture of the last reply
        self._lore = {}                        # session -> [world facts] set by the game (False: never set)
        self.folder = folder
        self.config_every = 1.0                # seconds between checks of kinloom.json for edits
        self._cfg_checked, self._cfg_mtime = -1e9, -1.0
        self._cfg_chars, self._cfg_lore = {}, []   # name -> (spec, its JSON); world facts from kinloom.json
        self._cfg_tools, self._cfg_tools_json = ({}, {}), None   # the game's tools from kinloom.json ("tools")
        self._tool_sets = {}                   # session -> (shapes, functions) the game declared with tools()
        self._blind_told = False               # "this model cannot see pictures" told once
        self._cfg_declared = {}                # (session, name) -> the spec JSON it was declared from
        self._game_declared = set()            # (session, name) the game declared itself
        self._gesture_seen = {}                # (session, name) -> the last gesture the model gave (shown or not)
        self._card_waiters = {}                # soul key -> [(session, character)] waiting for the card being written
        self._greetings = {}                   # (name, soul key) -> (text, inner): a first line to a stranger, ready
        self._greeting_busy = set()
        self._bonds = {}                       # session -> {name: {speaker: {talks, first, last}}}
        self._said = {}                        # (session, name) -> their last replies, to anyone (no echoes)
        self._clips = set()                    # (name, label) already journaled as too long
        self._switches = 0                     # provider switches already told in the journal
        self._rises = {}                       # (session, name, speaker) -> (since, feeling gained, last) this conversation
        self._steers = {}                      # (session, name) -> what the game decided for the next reply (steer)
        self._events = 0
        self._spreads = 0
        self._empty_told = set()               # (session, name, what) whose empty answer was told in the journal
        self._calls = collections.deque()
        self._stats = {"calls": 0, "failures": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "latency": 0.0,
                       "offline_answers": 0, "by_kind": {},
                       "hedged": 0, "cut_replies": 0}
        self._journal = collections.deque(maxlen=500)
        self._run_log = os.environ.get("KINLOOM_RUN_LOG")
        self._run_lock = threading.Lock()
        self.listeners = []
        self._fg = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="kinloom-fg")
        self._bg = ThreadPoolExecutor(max_workers=max(1, workers - 1), thread_name_prefix="kinloom-bg")
        self._busy = 0
        self._idle = threading.Condition(self._lock)
        self._closed = False
        # A weak reference: a brain the game drops (one per scene, per request) is freed, not kept alive until exit
        me = weakref.ref(self)
        atexit.register(lambda: me() is not None and me().close())
        for why in refused:
            self._log("refused", "kinloom", why)
        if self.memory.problem:
            self._log("error", "kinloom", self.memory.problem)
        self._refresh_config()
        if getattr(self.provider, "base_url", None) or getattr(self.provider, "starts_ahead", False):
            threading.Thread(target=_warm, args=(self.provider,), daemon=True, name="kinloom-warm").start()

    # ---------------- plumbing ----------------

    # ---------------- characters from kinloom.json ----------------

    def _refresh_config(self):
        """Reloads characters and lore from kinloom.json when the file changed (checked at most every config_every s)."""
        now = time.monotonic()
        if now - self._cfg_checked < self.config_every:
            return
        self._cfg_checked = now
        path = os.path.join(self.folder, _config.FILE)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        if mtime == self._cfg_mtime:
            return
        self._cfg_mtime = mtime
        try:
            cfg = _config.load(self.folder) if mtime is not None else {}
        except _config.ConfigError as e:
            self._log("error", "kinloom.json", "not reloaded: %s" % e)
            return
        chars = {}
        for name, spec in (cfg.get("characters") or {}).items() if isinstance(cfg.get("characters"), dict) else []:
            if not isinstance(spec, dict):
                self._log("refused", str(name)[:MAX_NAME], "kinloom.json: a character must be an object")
                continue
            spec = {k: v for k, v in spec.items() if k in _CONFIG_KEYS}
            chars[clean_text(str(name))[:MAX_NAME]] = (spec, json.dumps(spec, sort_keys=True, default=str))
        lore = cfg.get("lore")
        tools_json = json.dumps(cfg.get("tools"), sort_keys=True, default=str)
        game_tools = None
        if tools_json != self._cfg_tools_json:
            try:
                game_tools = _tools(cfg.get("tools") if isinstance(cfg.get("tools"), dict) else {})
            except ValueError as e:
                self._log("refused", "kinloom.json", "tools: %s" % e)
                game_tools = ({}, {})
        with self._lock:
            self._cfg_chars = chars
            self._cfg_lore = [str(x) for x in lore] if isinstance(lore, list) else ([str(lore)] if isinstance(lore, str) else [])
            if game_tools is not None:
                self._cfg_tools, self._cfg_tools_json = game_tools, tools_json
                rebind = [(s, c) for (s, _), c in self._characters.items() if c.tool_refs and s not in self._tool_sets]
            else:
                rebind = []
        for s, c in rebind:
            self._bind_tools(s, c)
        for name in chars:                     # ready before the first meeting (cards and greetings are shared by sessions)
            self._from_config("default", name)

    def _from_config(self, session, name):
        """Declares (or declares again, after an edit) a kinloom.json character in this session, unless the game
        declared it itself."""
        self._refresh_config()
        with self._lock:
            entry = self._cfg_chars.get(name)
            key = (session, name)
            if entry is None or key in self._game_declared or self._cfg_declared.get(key) == entry[1]:
                return
            self._cfg_declared[key] = entry[1]
        spec = entry[0]
        try:
            self.character(session, name, **dict(spec, _config=True))
        except (TypeError, ValueError) as e:
            self._log("refused", name, "kinloom.json: %s" % e)
            safe = {k: v for k, v in spec.items() if k in ("personality", "offline", "soul", "language", "group", "voice")}
            try:
                self.character(session, name, **dict(safe, _config=True))
            except (TypeError, ValueError):
                pass

    def _char(self, session, name):
        name = clean_text(str(name))[:MAX_NAME] or "?"
        self._from_config(session, name)
        with self._lock:
            c = self._characters.get((session, name))
            if c is None:
                c = Character(name)
                self._store(session, c)
            elif session in self._session_used:
                self._session_used[session] = next(self._ticks)
            return c

    def _store(self, session, c):
        """Keeps a character (under the lock). A full table first lets go of the oldest one the game never declared
        (made on the fly from a name); a session past its share keeps nothing more. False: not stored (a throwaway)."""
        key = (session, c.name)
        if key in self._characters:
            self._characters[key] = c
            return True
        if self._per_session.get(session, 0) >= MAX_PER_SESSION:
            return False
        if len(self._characters) >= MAX_CHARACTERS:
            old = next((k for k in self._characters if k not in self._declared), None)
            if old is not None:
                self._evict(old)
            else:
                # All declared: the session used least recently lets go of its characters (a player gone for long;
                # back, their game declares them again), never the one asking
                idle = min((s for s in self._session_used if s != session), key=self._session_used.get, default=None)
                if idle is None:
                    return False
                for k in [k for k in self._characters if k[0] == idle]:
                    self._evict(k)
                self._log("refused", "kinloom", "too many characters (%d): session %r, idle the longest, let go of "
                          "its characters" % (MAX_CHARACTERS, idle[:40]))
        self._characters[key] = c
        self._per_session[session] = self._per_session.get(session, 0) + 1
        self._session_used[session] = next(self._ticks)
        return True

    def _evict(self, key):
        """A character and what it said and felt go (under the lock): nothing grows past the caps."""
        del self._characters[key]
        self._declared.discard(key)
        self._game_declared.discard(key)
        self._cfg_declared.pop(key, None)
        for table in (self._moods, self._gestures, self._said, self._gesture_seen, self._pending, self._steers):
            table.pop(key, None)
        for table in (self._history, self._rises):
            for k in [k for k in table if k[:2] == key]:
                del table[k]
        (self._bonds.get(key[0]) or {}).pop(key[1], None)
        self._per_session[key[0]] -= 1
        if not self._per_session[key[0]]:
            del self._per_session[key[0]]
            self._session_used.pop(key[0], None)

    def stored(self, session, name):
        """True when this character is kept (declared or met), False for a throwaway (tables full) or an unknown name."""
        with self._lock:
            return (session, clean_text(str(name))[:MAX_NAME] or "?") in self._characters

    def _log(self, kind, name, text, **detail):
        entry = {"time": time.time(), "kind": kind, "name": name, "text": text}
        entry.update(detail)
        self._journal.append(entry)
        if self._run_log:                      # `kinloom run` reads what an in-process (Python) game did
            try:
                with self._run_lock, open(self._run_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, default=str) + "\n")
            except OSError:
                pass
        for listener in list(self.listeners):
            try:
                listener(entry)
            except Exception:  # a dashboard listener must never break the game
                pass

    def _allow(self, foreground):
        """Sliding one-minute budget; background work keeps 30 % of it free for the player. With declared prices,
        max_cost_per_hour / max_cost_per_day stop model calls once reached (offline answers until the window moves)."""
        now = time.monotonic()
        with self._lock:
            while self._spent and now - self._spent[0][0] > 86400:
                self._spent.popleft()
            for cap, window, label in ((self.max_cost_per_hour, 3600, "hour"), (self.max_cost_per_day, 86400, "day")):
                if cap is not None and self.prices and sum(d for t, d in self._spent if now - t <= window) >= cap:
                    self._log("budget", "kinloom", "cost cap reached ($%.2f per %s): answered offline" % (cap, label))
                    return False
            while self._calls and now - self._calls[0] > 60:
                self._calls.popleft()
            cap = self.limit if foreground else self.limit - max(1, int(math.ceil(0.3 * self.limit)))
            if len(self._calls) >= cap:
                return False
            self._calls.append(now)
            return True

    def _call(self, kind, name, system, user, json_mode, foreground, max_tokens=400, on_text=None, timeout=None, images=None):
        """One model call with a hard time limit, budget and stats. Returns a Reply (never raises). images: pictures
        the model looks at (a model that cannot see answers from the text: told once in the journal)."""
        if self.provider is None:
            return Reply(False, error="offline")
        if not self._allow(foreground):
            self._log("budget", name, "over budget: answered offline")
            return Reply(False, error="over budget")
        limit = timeout or self.call_timeout
        box = {}
        done = threading.Event()
        provider, system = self._provider_for(kind), self._rated(system)

        gate = threading.Lock()

        def run():
            try:
                r = _complete(provider, system, user, json_mode=json_mode, max_tokens=max_tokens,
                              timeout=limit, on_text=on_text, images=images)
            except Exception as e:  # providers never raise, but a custom one might
                r = Reply(False, error="%s: %s" % (type(e).__name__, e))
            with gate:
                box["r"] = r
                late = box.get("gave_up")
                done.set()
            if late:
                self._late(r)

        threading.Thread(target=run, daemon=True, name="kinloom-call").start()
        done.wait(limit + 0.25)
        with gate:
            if not done.is_set():
                box["gave_up"] = True
            r = box.get("r") or Reply(False, error="timed out after %.1f s" % limit)
        self._account(kind, name, r)
        return r

    def _late(self, r):
        """A call given up on that answered later: its tokens were billed all the same, so they count (and the caps)."""
        with self._lock:
            s = self._stats
            s["input_tokens"] += r.input_tokens
            s["cached_tokens"] += r.cached_tokens
            s["output_tokens"] += r.output_tokens
            self._spent.append((time.monotonic(), self._price(r)))

    def _provider_for(self, kind):
        """The model of a task: conversations and what players wait for use "chat", the rest "background"."""
        return self.models.get("chat" if kind in CHAT_KINDS else "background") or self.provider

    def _rated(self, system):
        line = prompts.rating_line(self.rating)
        return system + "\n" + line if line else system

    def _account(self, kind, name, r):
        with self._lock:
            s = self._stats
            s["calls"] += 1
            s["by_kind"][kind] = s["by_kind"].get(kind, 0) + 1
            s["input_tokens"] += r.input_tokens
            s["cached_tokens"] += r.cached_tokens
            s["output_tokens"] += r.output_tokens
            s["latency"] += r.latency
            if not r.ok:
                s["failures"] += 1
            self._spent.append((time.monotonic(), self._price(r)))
        self._log("call", name, ("%s ok" % kind) if r.ok else ("%s failed: %s" % (kind, r.error)),
                  latency=round(r.latency, 3), tokens=r.input_tokens + r.output_tokens)
        if getattr(r, "blind", False):
            with self._lock:
                told, self._blind_told = self._blind_told, True
            if not told:
                self._log("refused", name, "%s: this model cannot see pictures; it answered from the text (use a model "
                          "that reads images to send image=)" % kind)
        switched = getattr(self.provider, "switched", None) or []
        with self._lock:
            fresh, self._switches = switched[self._switches:], len(switched)
        for s in fresh:            # a dead key was replaced by the next provider: say it once
            self._log("provider", name, "switched " + s)

    def _price(self, r):
        p = self.prices
        if not p:
            return 0.0
        fresh = max(0, r.input_tokens - r.cached_tokens)
        return (fresh * p.get("input", 0) + r.cached_tokens * p.get("cached_input", p.get("input", 0)) +
                r.output_tokens * p.get("output", 0)) / 1e6

    def _race(self, kind, name, system, user, max_tokens, show, deadline, images=None):
        """A streamed call with a guard on its tail, for replies players wait for. If nothing is said after
        `hedge_after` seconds, the same request starts again and whichever speaks first is kept (only its words are
        shown). A reply that stalls for `stall_after` seconds, or runs past the deadline, ends with the text said so
        far (Reply.cut: the caller keeps complete sentences). Every started call is counted when it finishes."""
        if self.provider is None:
            return Reply(False, error="offline")
        if not self._allow(True):
            self._log("budget", name, "over budget: answered offline")
            return Reply(False, error="over budget")
        lock = threading.Lock()
        runs, state = [], {"winner": None}
        start = time.monotonic()
        provider, system = self._provider_for(kind), self._rated(system)

        def launch():
            run = {"text": "", "last": None, "mark": None, "reply": None, "done": threading.Event()}

            def on_text(piece):
                with lock:
                    run["text"] += piece
                    run["last"] = time.monotonic()
                    if run["mark"] is None and _souls.MARK in run["text"]:
                        run["mark"] = run["last"]            # the reply itself is complete
                    if state["winner"] is None:
                        state["winner"] = run
                    mine = state["winner"] is run
                if mine and show is not None:
                    show(piece)

            def work():
                try:
                    r = _complete(provider, system, user, json_mode=False, max_tokens=max_tokens, timeout=deadline,
                                  on_text=on_text, images=images)
                except Exception as e:  # providers never raise, but a custom one might
                    r = Reply(False, error="%s: %s" % (type(e).__name__, e))
                self._account(kind, name, r)     # counted before the caller can see the reply (stats read right after)
                run["reply"] = r
                run["done"].set()

            runs.append(run)
            threading.Thread(target=work, daemon=True, name="kinloom-call").start()

        launch()
        while True:
            time.sleep(0.02)
            now = time.monotonic()
            with lock:
                winner = state["winner"]
                if winner is None:
                    finished = [r for r in runs if r["done"].is_set()]
                    good = [r for r in finished if r["reply"].ok and r["reply"].text]
                    if good:                                  # a provider that answers without streaming
                        state["winner"] = winner = good[0]
                        if show is not None:
                            show(winner["reply"].text)
            if winner is not None:
                if winner["done"].is_set():
                    return winner["reply"]
                said_all = winner["mark"] is not None and now - winner["mark"] >= self._grace()
                if said_all or now - winner["last"] >= self.stall_after or now - start >= deadline:
                    with lock:
                        text = winner["text"]
                    with self._lock:                                  # stats are shared by every thread
                        self._stats["cut_replies"] += 1
                    self._log("cut", name, "%s: %s after %.1f s; kept what was said" %
                              (kind, "inner part late" if said_all else "stalled" if now - start < deadline else "deadline",
                               now - start))
                    r = Reply(True, text, latency=now - start)
                    r.cut = True
                    return r
                continue
            if all(r["done"].is_set() for r in runs):
                return runs[-1]["reply"]
            if len(runs) == 1 and now - start >= self.hedge_after and now - start < deadline - 1 and \
                    not self._patient() and self._allow(True):   # a local model or a coding agent: only slower
                with self._lock:
                    self._stats["hedged"] += 1
                self._log("hedge", name, "%s: nothing said after %.1f s, asking again" % (kind, now - start))
                launch()
            if now - start >= deadline:
                return Reply(False, error="timed out after %.1f s" % deadline, latency=now - start)

    def _patient(self):
        """A model slow to start or to write (on this machine, or a coding agent's command line): no hedging, more time."""
        p = self.provider
        return bool(getattr(p, "patient", getattr(p, "local", False)))

    def _grace(self):
        """A local model writes the inner part slower than a hosted one: without more time it is always cut."""
        return max(self.inner_grace, 5.0) if self._patient() else self.inner_grace

    def _reply_deadline(self):
        """How long a spoken reply may take: reply_timeout (8 s) hosted; at least 15 s on this machine's own model or a
        coding agent; never past call_timeout."""
        base = min(self.call_timeout, self.reply_timeout)
        return base if not self._patient() else max(base, 15.0)

    def _pictures(self, name, image):
        """[Picture] from what the game passed (bytes, a path, base64, a data URI); a bad one is told and left out."""
        try:
            p = _media.picture(image)
        except ValueError as e:
            self._log("refused", name, "image: %s" % e)
            return []
        return [p] if p is not None else []

    def _background(self, fn):
        with self._lock:
            self._busy += 1

        def run():
            try:
                fn()
            except Exception as e:  # background work must never surface in the game
                self._log("error", "kinloom", "background task failed: %s" % e)
            finally:
                with self._lock:
                    self._busy -= 1
                    self._idle.notify_all()

        try:
            self._bg.submit(run)
        except RuntimeError:  # closed
            with self._lock:
                self._busy -= 1

    def wait_idle(self, timeout=10.0):
        """Waits until background work (banks, decisions, pools) is done. For tests, warm-up screens and tools."""
        end = time.monotonic() + timeout
        with self._lock:
            while self._busy > 0:
                left = end - time.monotonic()
                if left <= 0:
                    return False
                self._idle.wait(left)
        return True

    def _context(self, session, name, query="", personal=True):
        with self._lock:
            state = self._state.get(session)
        notes = self.memory.recall(session, [name, "world"] if name else ["world"], query, personal=personal)
        return prompts.context(notes, state, self.opinions(session, name) if name else None)

    # ---------------- character ----------------

    def character(self, session, name, personality="", lines=None, offline=None, events=None, tools=None, max_words=None, every=8.0,
                  language=None, group=None, soul=None, trust=None, invent=True, voice=None, max_chars=None, warmth=None,
                  secret_trust=None, warm_up=None, _config=False):
        c = Character(name, personality, lines, offline, events, tools, max_words, every, language, group, trust, invent,
                      voice, max_chars, warmth, secret_trust, warm_up)
        with self._lock:
            if not self._store(session, c):
                self._log("refused", c.name, "too many characters (%d in all, %d per session): not stored" % (
                    MAX_CHARACTERS, MAX_PER_SESSION))
                return c
            self._declared.add((session, c.name))
            if not _config:
                self._game_declared.add((session, c.name))      # the game's own declaration wins over kinloom.json
        self._log("character", c.name, c.personality)
        if c.tool_refs:
            self._bind_tools(session, c, tell=bool(self._game_tools(session)[0]))
        self._give_soul(session, c, soul)
        for event, names in c.events.items():
            self._refill(session, c, event, names)
        return c

    # ---------------- the game's tools ----------------

    def _game_tools(self, session):
        """(shapes, functions) of the tools the game declared for this session, else those of kinloom.json."""
        self._refresh_config()
        with self._lock:
            return self._tool_sets.get(session) or self._cfg_tools

    def _bind_tools(self, session, c, tell=False):
        """Gives a character the game's tools it names (its own tools win over a game tool of the same name)."""
        shapes, functions = self._game_tools(session)
        names = list(shapes) if "*" in c.tool_refs else [n for n in c.tool_refs if n != "*"]
        tools, fns = dict(c.own_tools), dict(c.own_functions)
        missing = []
        for n in names:
            if n in c.own_tools:
                continue
            if n in shapes:
                tools[n] = shapes[n]
                if n in functions:
                    fns[n] = functions[n]
            else:
                missing.append(n)
        with self._lock:
            c.tools, c.functions = tools, fns
            c.trust = {k: v for k, v in c.trust_wanted.items() if k in tools}
        if missing and tell:
            self._log("refused", c.name, "tools: %s not declared by the game (kl.tools({...}) or \"tools\" in "
                      "kinloom.json)" % ", ".join(missing))

    def tools(self, session, tools=None):
        """The game's tools, declared once: {name: example args} and/or Python functions. Characters use them by
        name (tools=["open_door"]) or all of them (tools="all"). tools=None reads the names. Returns the names."""
        if tools is None:
            return sorted(self._game_tools(session)[0])
        parsed = _tools(tools)
        with self._lock:
            self._tool_sets[session] = parsed
            using = [c for (s, _), c in self._characters.items() if s == session and c.tool_refs]
        for c in using:
            self._bind_tools(session, c, tell=True)
        self._log("tools", "game", ", ".join(sorted(parsed[0])) or "none")
        return sorted(parsed[0])

    # ---------------- ready before play ----------------

    def prepare(self, session, timeout=10.0):
        """Waits (a loading screen) until the work Kinloom does ahead is done: soul cards, first greetings, line banks,
        pools, background decisions. {"ready": bool, "waiting": background tasks still running, "online": bool}."""
        self._refresh_config()
        done = self.wait_idle(max(0.0, min(300.0, float(_finite(timeout) or 0.0))))
        with self._lock:
            waiting = self._busy
            writing = [c.name for (s, _), c in self._characters.items() if s == session and c.card is not None and not c.card_ready]
        return {"ready": bool(done and not writing), "waiting": waiting, "online": self.provider is not None}

    # ---------------- souls ----------------

    def _give_soul(self, session, c, soul):
        """soul: True (the personality is the seed), a sentence, or a card (dict) written by the game."""
        if soul is None or soul is False:
            return
        if isinstance(soul, dict):
            card = _souls.card(soul, c.personality)
            if not self._allowed(card):
                self._log("refused", c.name, "soul: blocked by the content filter")
                card = _souls.card({}, c.personality)
            c.card, c.card_ready = card, True
            c.soul_key = _souls.seed_key(json.dumps(card, sort_keys=True))
            if not c.personality:
                c.personality = card["summary"]
            self._prepare_greeting(session, c)
            return
        seed = c.personality if soul is True else clean_text(str(soul))[:600]
        if not seed:
            return
        if not c.personality:
            c.personality = seed
        key = _souls.seed_key(seed + "|" + " / ".join(self.lore(session)))    # new lore: the card is written again
        c.soul_key = key
        with self._lock:
            saved = self.memory.get("souls", key)          # shared by every session: one card for all players
            if isinstance(saved, dict) and isinstance(saved.get("card"), dict):
                c.card, c.card_ready = _souls.card(saved["card"], seed), True
                found = True
            else:
                found = False
                c.card = _souls.card({}, seed)              # the sentence until the model's card is ready
                c.card_ready = self.provider is None
                waiting = self._card_waiters.setdefault(key, []) if self.provider is not None else None
                if waiting is not None:
                    waiting.append((session, c))
                    if len(waiting) > 1:                     # already being written for another session
                        return
        if found:
            self._prepare_greeting(session, c)
            return
        if self.provider is None:
            return

        def work():
            card = None
            try:
                r = self._call("soul", c.name, prompts.soul_system(c, self._lang(c)), prompts.soul_user(seed, self.lore(session)),
                               True, False, 900)
                data = find_json(r.text) if r.ok else None
                if not isinstance(data, dict):
                    self._log("refused", c.name, "soul: no usable card (%s)" % (r.error or "not JSON"))
                    return
                card = _souls.card(data, seed)
                if not self._allowed(card):
                    self._log("refused", c.name, "soul: blocked by the content filter")
                    card = None
                    return
                self.memory.put("souls", key, {"card": card})
                self._log("soul", c.name, card["summary"])
            finally:
                with self._lock:
                    waiting = self._card_waiters.pop(key, [])
                for s, ch in waiting:
                    if card is not None:
                        ch.card = card
                    ch.card_ready = True
                    self._prepare_greeting(s, ch)
        self._background(work)

    def _prepare_greeting(self, session, c):
        """Writes, in the background, what the character says to someone new who walks up: chat(name, "") with a
        stranger then answers at once. One call per character, then one after each greeting used."""
        key = (c.name, getattr(c, "soul_key", None))
        if self.provider is None or c.card is None or key[1] is None:
            return
        with self._lock:
            if key in self._greetings or key in self._greeting_busy:
                return
            self._greeting_busy.add(key)

        def work():
            try:
                word, level = self._mood(session, c)
                system = prompts.chat_system(c, self._lang(c, chat=True), self._card_lines(c), self.lore(session), task="greet")
                user = self._context(session, c.name, "", personal=False) + prompts.bond_block(
                    "this stranger", None, "", c.warmth, [], word, _souls.strength(level) if level else "",
                    secrets=bool((c.card or {}).get("secrets")), secret_trust=c.secret_trust) + \
                    prompts.message_block("A stranger", "")
                r = self._call("greet", c.name, system, user, False, False, 400)
                if not r.ok:
                    return
                said, inner = _souls.split(r.text)
                said, _ = _souls.drop_narrated(said, _souls.inner(inner)["gesture"], (c.card or {}).get("quirks"))
                text = _souls.cap(self._clean_reply(said, c.name), c.reply_words, c.max_chars)
                allowed = _allowed_numbers(self._state.get(session), c.personality, _souls.texts(c.card or {}))
                if text and not [m for m in _NUMBER.findall(text) if not _number_ok(m, allowed)]:
                    with self._lock:
                        if len(self._greetings) < MAX_CHARACTERS:
                            self._greetings[key] = (text, inner)
            finally:
                with self._lock:
                    self._greeting_busy.discard(key)
        self._background(work)

    def lore(self, session, lines=None):
        """World facts the designer locks: every character takes them as true and never contradicts them; souls are
        written to fit them. lines: a list or a text (one fact per line) replaces them (saved in the memory file);
        None reads them. Returns the list (read) or how many were kept (write): at most 60 facts of 300 characters."""
        if lines is None:
            with self._lock:
                cached = self._lore.get(session)
            if cached is None:
                saved = self.memory.get("lore", session)
                cached = [str(x) for x in saved] if isinstance(saved, list) else None
                with self._lock:
                    self._lore[session] = cached if cached is not None else False
            if not cached and cached != []:                   # never set by the game: kinloom.json's lore
                self._refresh_config()
                with self._lock:
                    return list(self._cfg_lore)
            return list(cached)
        items = lines.splitlines() if isinstance(lines, str) else (lines if isinstance(lines, (list, tuple)) else [])
        clean = [x for x in (" ".join(clean_text(str(i)).split())[:300] for i in items) if x][:60]
        with self._lock:
            self._lore[session] = clean
        self.memory.put("lore", session, clean)
        self._log("lore", "world", "%d facts" % len(clean))
        return len(clean)

    def _card_lines(self, c):
        if not c.card:
            return []
        lines = _souls.describe(c.card)
        if lines and c.card.get("summary") == c.personality:
            lines = lines[1:]
        return lines

    def _mood(self, session, c):
        with self._lock:
            mood = self._moods.get((session, c.name))
        return _souls.mood_now(mood, self.clock(), (c.card or {}).get("mood"))

    def _bond_table(self, session):
        with self._lock:
            table = self._bonds.get(session)
            if table is None:
                saved = self.memory.get("bonds", session)
                table = {}
                if isinstance(saved, dict):
                    for a, row in saved.items():
                        if isinstance(row, dict):
                            # Each value checked: a hand-edited file or a loaded save never breaks chat() later
                            table[str(a)] = {str(b): {"talks": max(1, int(min(1e9, _finite(v.get("talks")) or 1))),
                                                      "first": _finite(v.get("first")) or float(v["last"]),
                                                      "last": float(v["last"])}
                                             for b, v in row.items() if isinstance(v, dict) and _finite(v.get("last")) is not None}
                self._bonds[session] = table
            return table

    def _known(self, session, name, speaker, k=6):
        notes = [n for n in self.memory.notes(session, name) if n.get("about") == speaker and n["importance"] >= 0.6]
        notes.sort(key=lambda n: (n["importance"], n["t"]), reverse=True)
        return [n["text"] for n in sorted(notes[:k], key=lambda n: n["t"])]

    def _inner(self, session, c, speaker, data, undo=None):
        """Applies what changed inside the character (from the reply's JSON), each part checked. Returns the actions
        decided in this reply (waiting for the reply's .do or act()). undo: a dict filled with what to put back if the
        game refuses the reply (chat's check)."""
        i = _souls.inner(data)
        undo = {} if undo is None else undo
        undo["notes"] = []
        if i["mood"] and self._allowed(i["mood"]):
            with self._lock:
                undo["mood"] = self._moods.get((session, c.name))
                self._moods[(session, c.name)] = {"word": i["mood"], "level": i["intensity"], "t": self.clock()}
        if i["feel"]:
            change = i["feel"]
            if change > 0:     # warming up is slow: at most warm_up (0.3) per conversation, however sweet the words
                with self._lock:
                    now = self.wall()
                    undo["rise"] = self._rises.get((session, c.name, speaker))
                    start, gained, last = self._rises.get((session, c.name, speaker), (now, 0.0, -1e18))
                    if now - last > _souls.NEW_TALK:
                        start, gained = now, 0.0
                    change = max(0.0, min(change, c.warm_up - gained))
                    self._rises[(session, c.name, speaker)] = (start, gained + change, now)
                    _trim(self._rises)
                if change < i["feel"]:
                    self._log("refused", c.name, "feel: %s already won %+.1f this conversation" % (speaker, c.warm_up))
            if change:
                before = self.opinion(session, c.name, speaker)
                undo["feel"] = self.feel(session, c.name, speaker, change) - before
        if i["self"] and self._allowed(i["self"]):
            # said to one, true for everyone after: an important memory, recalled like the others (a rule
            # "keep to what you said" in every prompt made replies flatter, proof/souls/quality.py v3 vs v4)
            self.memory.add(session, c.name, i["self"], 0.9, about=SELF)
            undo["notes"].append(i["self"])
        if i["remember"]:
            if self._allowed(i["remember"]):
                self.memory.add(session, c.name, i["remember"], 0.8, about=speaker)
                undo["notes"].append(i["remember"])
            else:
                self._log("refused", c.name, "remember: blocked by the content filter")
        with self._lock:
            key = (session, c.name)
            undo["gesture"] = (self._gesture_seen.get(key), self._gestures.get(key))
            fresh = i["gesture"] and self._allowed(i["gesture"]) and not _souls.same_action(i["gesture"], self._gesture_seen.get(key))
            self._gesture_seen[key] = i["gesture"].lower()
            if fresh:
                self._gestures[key] = i["gesture"]            # a new visible gesture: the game may animate it
            else:
                self._gestures.pop(key, None)                 # none, or the same as last time: nothing new to show
        if i["do"] and c.tools:
            actions = self._valid_actions(c, json.dumps({"actions": i["do"]}))
            feeling = self.opinion(session, c.name, speaker)
            for tool, _ in [a for a in actions if feeling < c.trust.get(a[0], -2.0)]:
                self._log("refused", c.name, "%s: needs a feeling of %+.1f for %s (has %+.2f)" % (tool, c.trust[tool], speaker, feeling))
            actions = [a for a in actions if feeling >= c.trust.get(a[0], -2.0)]
            if actions:
                decided = [_Action(tool, args) for tool, args in actions]
                with self._lock, _TAKE:
                    entry = self._pending.setdefault((session, c.name), {"actions": [], "at": None, "thinking": False})
                    waiting = [a for a in entry["actions"] if not a.taken]
                    entry["actions"] = waiting[-(MAX_WAITING - len(decided)):] + decided if len(decided) < MAX_WAITING else decided
                for tool, args in actions:
                    self._log("act", c.name, "%s(%s) while talking to %s" % (tool, json.dumps(args), speaker))
                return decided
        return []

    def _recollect(self, session, c, speaker, lines):
        """Old conversation lines become one remembered summary (background)."""
        if self.provider is None or not lines:
            return

        def work():
            user = "Conversation with %s:\n%s\n" % (speaker, "\n".join("%s: %s" % (who, text) for who, text in lines))
            r = self._call("recollect", c.name, prompts.recollect_system(c, self._lang(c)), user, True, False, 250)
            data = find_json(r.text) if r.ok else None
            summary = _souls._text(data.get("summary"), 280) if isinstance(data, dict) else ""
            if summary and self._allowed(summary):
                self.memory.add(session, c.name, "Earlier with %s: %s" % (speaker, summary), 0.65, about=speaker)
        self._background(work)

    def soul(self, session, name, speaker=None):
        """Everything a game or a dashboard may show: card, mood, bonds (with feelings), recent memories, and the
        conversation with speaker (lines kept word for word) when one is given."""
        c = self._char(session, name)
        word, level = self._mood(session, c)
        table = self._bond_table(session)
        with self._lock:
            row = {k: dict(v) for k, v in table.get(c.name, {}).items()}
        for who, b in row.items():
            b["feeling"] = self.opinion(session, c.name, who)
        return {"name": c.name, "personality": c.personality, "card": dict(c.card) if c.card else None,
                "ready": bool(c.card_ready) if c.card else True, "mood": {"word": word, "level": level}, "bonds": row,
                "memories": self.memory.all(session, c.name)[-20:], "tools": sorted(c.tools),
                "gesture": self._gestures.get((session, c.name), ""), "lore": len(self.lore(session)),
                "conversation": [list(x) for x in self._history.get((session, c.name, _name(speaker) or ""), [])] if speaker else []}

    # ---------------- say ----------------

    def say(self, session, name, event, facts=None, fresh=False, max_chars=None):
        """A Line (a str with .source): fresh, a model line written now; else a prepared one; else the game's own.
        max_chars: this box's size (else the character's): a line that fits is picked first, else one is cut."""
        c = self._char(session, name)
        facts = _mapping(facts, "facts")
        self._clip_note(c.name, "facts", facts)
        event = _event_key(event)
        limit = _limit(max_chars) or c.max_chars

        def fitting(templates):
            return [t for t in templates if len(fill(t, facts)) <= limit] if limit else templates
        if fresh and self.provider is not None:
            r = self._call("line", c.name, prompts.line_system(c, c.moment(event), sorted(facts), self._lang(c), limit),
                           self._context(session, c.name, event) + prompts.facts_block(facts), False, True, max_tokens=120)
            if r.ok:
                text = find_json(r.text)
                # Only a text line counts: {"line": null}, {"text": ...} or a list is a failed answer, never "None" shown
                line = text.get("line") if isinstance(text, dict) else None if text is not None else r.text
                ok, template = self._valid_line(line, set(facts), c) if isinstance(line, str) else (False, None)
                if ok:
                    said = _souls.fit_chars(fill(template, facts), limit)
                    self._log("say", c.name, said, event=event, source="fresh")
                    return Line(said, "model")
        key = (session, c.name, event)
        names = set(facts)
        with self._lock:
            bank = self._banks.get(key)
            if bank is None:
                bank = self._banks[key] = _Bank()
                _trim(self._banks)
            usable = [t for t in bank.unused if set(_PLACEHOLDER.findall(t)) <= names]
            known = [t for t in bank.templates if set(_PLACEHOLDER.findall(t)) <= names]
            template = None
            fresh_ones, old_ones = fitting(usable), fitting(known)
            if fresh_ones or (usable and not old_ones):          # an unused line that fits (or none fits at all)
                template = random.choice(fresh_ones or usable)
                bank.unused.remove(template)
            elif old_ones or known:
                pool = old_ones or known
                template = random.choice([t for t in pool if t not in bank.recent] or pool)
            if template is not None:
                bank.recent.append(template)
            low = len(usable) - (1 if template in usable else 0) < 3
        if low:
            self._refill(session, c, event, sorted(names), limit)
        if template is not None:
            said = _souls.fit_chars(fill(template, facts), limit)
            self._log("say", c.name, said, event=event, source="bank")
            return Line(said, "prepared")
        said = self._offline_line(c, event, facts, limit)
        with self._lock:
            self._stats["offline_answers"] += 1
        self._log("say", c.name, said, event=event, source="offline")
        if not said:
            self._tell_empty(session, c.name, "say " + event, "%s has no line for %r: say() answered \"\" (give it lines "
                             "for this event, or \"*\" lines, that only use the facts passed)" % (c.name, event))
        return Line(said, "offline")

    def _tell_empty(self, session, name, what, text):
        """An empty answer is told once in the journal (kind "empty"): a game showing nothing should know why."""
        key = (session, name, what)
        with self._lock:
            if key in self._empty_told:
                return
            if len(self._empty_told) < 2000:
                self._empty_told.add(key)
        self._log("empty", name, text)

    def _offline_line(self, c, event, facts, limit=None):
        """One of the game's own lines for the event (or "*"); with a box size, one that fits when there is one."""
        options = c.lines.get(_event_key(event)) or c.lines.get("*") or []
        usable = [t for t in options if set(_PLACEHOLDER.findall(t)) <= set(facts)]
        fits = [t for t in usable if len(fill(t, facts)) <= limit] if limit else []
        return fill(random.choice(fits or usable), facts) if usable else ""

    def _written(self):
        """The language of text nobody is talking to (content, minds): the game's, English under "auto"."""
        return DEFAULT_LANGUAGE if str(self.language).strip().lower() == AUTO else self.language

    def _lang(self, c, chat=False):
        """The language the model writes in. "auto": a conversation answers in the speaker's language; anything else
        (prepared lines, decisions, content) is written in English."""
        lang = c.language or self.language
        if str(lang).strip().lower() == AUTO:
            return AUTO if chat else DEFAULT_LANGUAGE
        return lang

    def _allowed(self, value):
        """False when any text in the value is blocked by the content filter (banned words or the game's function)."""
        if self._banned is None and self.content_filter is None:
            return True
        texts = []

        def walk(x):
            if isinstance(x, str):
                texts.append(x)
            elif isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, (list, tuple)):
                for v in x:
                    walk(v)

        walk(value)
        for t in texts:
            if self._banned is not None and self._banned.search(t):
                return False
            if self.content_filter is not None:
                try:
                    if not self.content_filter(t):
                        return False
                except Exception:  # a broken filter blocks rather than lets through
                    return False
        return True

    def _valid_line(self, line, fact_names, c):
        line = clean_text(line).strip().strip('"').strip()
        if not self._allowed(line):
            return False, None
        if not line or len(line) > MAX_LINE or len(line.split()) > c.line_words + 6:
            return False, None
        if c.max_chars and len(_PLACEHOLDER.sub("", line)) > c.max_chars:      # too long for the box whatever the facts
            return False, None
        names = set(_PLACEHOLDER.findall(line))
        if fact_names is not None and not names <= fact_names:
            return False, None
        rest = _PLACEHOLDER.sub("", line)
        if _DIGIT.search(rest) or "{" in rest or "}" in rest or _META.search(rest):
            return False, None
        return True, line

    def _refill(self, session, c, event, names, chars=None):
        """Asks the model for a batch of lines in the background. names: the fact names the game passes (None = unknown yet:
        any placeholder is kept, and only lines whose placeholders the game provides are ever said)."""
        key = (session, c.name, event)
        if self.provider is None:
            return
        with self._lock:
            bank = self._banks.setdefault(key, _Bank())
            _trim(self._banks)
            if bank.filling or bank.failures >= 3:
                return
            bank.filling = True

        def work():
            try:
                r = self._call("lines", c.name, prompts.lines_system(c, c.moment(event), names, BANK_SIZE, self._lang(c), chars),
                               self._context(session, c.name, event), True, False, max_tokens=700)
                added = 0
                if r.ok:
                    data = find_json(r.text)
                    lines = data.get("lines") if isinstance(data, dict) else data if isinstance(data, list) else None
                    for line in (lines or [])[: BANK_SIZE * 2]:
                        ok, template = self._valid_line(str(line), set(names) if names is not None else None, c)
                        with self._lock:
                            if ok and template not in bank.templates:
                                bank.templates.append(template)
                                bank.unused.append(template)
                                added += 1
                with self._lock:
                    bank.failures = 0 if added else bank.failures + 1
                self._log("bank", c.name, "%d new lines for %s" % (added, event), event=event)
            finally:
                with self._lock:
                    bank.filling = False

        self._background(work)

    # ---------------- decide ----------------

    def decide(self, session, name, situation, choices, every=None):
        c = self._char(session, name)
        shape = Shape.of(choices if isinstance(choices, dict) else {"choice": choices})
        key = (session, c.name, shape.signature())
        situation = situation if isinstance(situation, dict) else {"situation": situation}
        self._clip_note(c.name, "situation", situation)
        every = c.every if every is None else max(0.2, _num(every, "every"))
        now = self.clock()
        with self._lock:
            d = self._decisions.get(key)
            if d is None:
                d = self._decisions[key] = _Decision(shape.default())
                _trim(self._decisions)
            due = not d.thinking and (d.at is None or now - d.at >= every or
                                      (now - d.at >= every / 4 and _changed(d.situation, situation)))
            if due:
                d.thinking = True
                d.situation = dict(situation)
            value = d.value
        if due and self.provider is not None:
            def work():
                try:
                    system = prompts.decide_system(c, shape, self._lang(c))
                    user = self._context(session, c.name, json.dumps(situation, default=str)) + prompts.situation_block(situation)
                    result = self._structured("decide", c.name, system, user, shape, False)
                    with self._lock:
                        if result is not None:
                            d.value = result if isinstance(choices, dict) else result["choice"]
                            self._log("decide", c.name, json.dumps(d.value))
                        d.at = self.clock()
                finally:
                    with self._lock:
                        d.thinking = False
            self._background(work)
        elif due:
            with self._lock:
                d.thinking = False
                d.at = now
        return value if isinstance(choices, dict) or not isinstance(value, dict) else value.get("choice", value)

    def _structured(self, kind, name, system, user, shape, foreground, max_tokens=500, timeout=None, images=None,
                    on_text=None, used=None):
        """Asks for JSON matching the shape; one repair with the exact problem; None when it still fails.
        on_text: the answer's pieces as they come; used(): true when part of it was already used (then no repair)."""
        r = self._call(kind, name, system, user, True, foreground, max_tokens, on_text=on_text, timeout=timeout, images=images)
        if not r.ok:
            return None
        ok, value, error = shape.parse(r.text)
        if ok and not self._allowed(value):
            self._log("refused", name, "%s: blocked by the content filter" % kind)
            return None
        if ok:
            return value
        if used is not None and used():
            return None
        self._log("repair", name, "%s: %s" % (kind, error))
        if error == CUT:                 # stopped by the token limit: the second try gets room to finish
            max_tokens = min(4000, max_tokens * 2)
        r = self._call(kind, name, system, user + prompts.repair(error), True, foreground, max_tokens, timeout=timeout,
                       images=images)
        if not r.ok:
            return None
        ok, value, error = shape.parse(r.text)
        if not ok:
            self._log("refused", name, "%s: %s" % (kind, error))
        elif not self._allowed(value):
            self._log("refused", name, "%s: blocked by the content filter" % kind)
            return None
        return value if ok else None

    # ---------------- voice ----------------

    def _voice_of(self, session, name, text):
        """What the voice provider gets for this character: a stable seed, how they sound (the game's words, then
        how the soul talks, then the mood of the moment) and their language."""
        if name is None:
            return {"seed": "narrator", "describe": "", "id": None, "language": None}
        c = self._char(session, name)
        parts = [c.voice] if c.voice else []
        talk = (c.card or {}).get("voice") if c.card else None
        if talk:
            parts.append("speaks like this: %s" % str(talk)[:200])
        word = self._mood(session, c)[0] if (c.voice or c.card) else None
        if word and word not in ("calm", "neutral"):
            parts.append("right now: %s" % word)
        # the character's own language, else the one the text is written in (the voice provider guesses it)
        return {"seed": c.name, "describe": "; ".join(parts), "id": c.voice_id, "language": c.language or self.voice_language}

    def _audio_path(self, key):
        if self._voice_dir is None:
            base = os.path.dirname(self.memory.path) if getattr(self.memory, "path", None) else None
            self._voice_dir = os.path.join(base, "voice") if base else os.path.join(
                tempfile.gettempdir(), "kinloom-voice-%d" % os.getpid())
        os.makedirs(self._voice_dir, exist_ok=True)
        return os.path.join(self._voice_dir, key + ".wav")

    def speak(self, session, name, text, timeout=None):
        """Text said aloud in the character's voice (name None: a neutral narrator voice): an Audio (WAV) or None
        when no voice can speak it. The same line in the same voice is made once, then read from the cache."""
        text = " ".join(clean_text(str(text or "")).split())[:_voice.MAX_TEXT]
        who = "voice" if name is None else clean_text(str(name))[:MAX_NAME]
        if not text or self.voice is None or not self.voice.can_speak:
            return None
        if not self._allowed(text):
            self._log("refused", who, "speak: blocked by the content filter")
            return None
        spec = self._voice_of(session, name, text)
        key = _souls.seed_key(json.dumps([self.voice.describe(), spec, text], sort_keys=True))
        path = self._audio_path(key)
        try:
            with open(path, "rb") as f:
                return _voice.Audio(f.read(), path, text, spec["seed"], cached=True)
        except OSError:          # not cached yet, or being replaced by another thread (Windows): spoken again
            pass
        if not self.voice.local() and not self._allow(True):
            self._log("budget", who, "over budget: not spoken")
            return None
        start = time.monotonic()
        try:
            data, err = self.voice.speak(text, spec, timeout or max(self.call_timeout, 15.0))
        except Exception as e:  # providers never raise, but a custom one might
            data, err = None, "%s: %s" % (type(e).__name__, e)
        took = time.monotonic() - start
        with self._lock:
            self._stats["by_kind"]["speak"] = self._stats["by_kind"].get("speak", 0) + 1
            if data is None:
                self._stats["failures"] += 1
        if data is None:
            self._log("error", who, "speak: %s" % err)
            return None
        # The cache is a convenience: the same line spoken from two threads, or a file locked by a player (Windows),
        # never costs the game its audio
        tmp = "%s.%d-%d.part" % (path, os.getpid(), threading.get_ident())
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            path = None
        self._voice_writes = getattr(self, "_voice_writes", 0) + 1
        if self._voice_writes % 100 == 0:
            _voice.prune(self._voice_dir)
        audio = _voice.Audio(data, path, text, spec["seed"])
        self._log("speak", who, "%s (%.1f s of audio in %.2f s, %s)" % (
            text[:80], audio.seconds, took, getattr(self.voice, "last", None) or self.voice.name))
        return audio

    def listen(self, session, audio, language=None, timeout=None):
        """What was said in a recording (WAV, WebM, OGG, MP3: bytes, a file path, or base64 text): the text, or ""
        when nothing could be understood (the game keeps its keyboard)."""
        data = _voice.audio_bytes(audio)
        if not data or self.voice is None or not self.voice.can_listen:
            return ""
        if len(data) > _voice.MAX_AUDIO:
            self._log("refused", "listen", "recording larger than %d bytes" % _voice.MAX_AUDIO)
            return ""
        if not self.voice.local() and not self._allow(True):
            self._log("budget", "listen", "over budget: not heard")
            return ""
        fmt = _voice.audio_format(data)
        start = time.monotonic()
        try:
            text, err = self.voice.listen(data, fmt, language or self.voice_language, timeout or max(self.call_timeout, 20.0))
        except Exception as e:
            text, err = None, "%s: %s" % (type(e).__name__, e)
        with self._lock:
            self._stats["by_kind"]["listen"] = self._stats["by_kind"].get("listen", 0) + 1
            if text is None:
                self._stats["failures"] += 1
        if text is None:
            self._log("error", "listen", "listen: %s" % err)
            return ""
        text = " ".join(clean_text(text).split())[:2000]
        seconds = _voice.wav_seconds(data) if fmt == "wav" else 0.0
        self._log("listen", "listen", "%r (%s, %.1f s of audio in %.2f s)" % (
            text[:80], fmt or "audio", seconds, time.monotonic() - start))
        return text

    # ---------------- act ----------------

    def act(self, session, name, situation=None, think=True, check=None):
        """Actions the character chose: in conversation (chat) and, when think is true, on its own every `every`
        seconds (a background model call). Returned once, Python tools already run. check(tool, args): the game's
        rules; an action it refuses is not returned (nor run) and the character remembers why."""
        c = self._char(session, name)
        if not c.tools:
            return []
        key = (session, c.name)
        situation = situation if isinstance(situation, dict) else ({"situation": situation} if situation is not None else {})
        self._clip_note(c.name, "situation", situation)
        now = self.clock()
        with self._lock, _TAKE:
            entry = self._pending.setdefault(key, {"actions": [], "at": None, "thinking": False})
            ready = [(a.tool, a.args) for a in entry["actions"] if not a.taken]
            for a in entry["actions"]:
                a.taken = True
            entry["actions"] = []
            due = think and not entry["thinking"] and (entry["at"] is None or now - entry["at"] >= c.every)
            if due:
                entry["thinking"] = True
        if due and self.provider is not None:
            def work():
                try:
                    system = prompts.act_system(c, self._lang(c))
                    user = self._context(session, c.name, json.dumps(situation, default=str)) + prompts.situation_block(situation)
                    r = self._call("act", c.name, system, user, True, False, 500)
                    actions = self._valid_actions(c, r.text) if r.ok else []
                    with self._lock, _TAKE:
                        entry["actions"] = entry["actions"][-MAX_WAITING:] + [_Action(t, a) for t, a in actions]
                        entry["at"] = self.clock()
                    for tool, args in actions:
                        self._log("act", c.name, "%s(%s)" % (tool, json.dumps(args)))
                finally:
                    with self._lock:
                        entry["thinking"] = False
            self._background(work)
        elif due:
            with self._lock:
                entry["thinking"] = False
                entry["at"] = now
        done = []
        for tool, args in ready:
            if check is not None:
                why, error = judged(check, tool, copy.deepcopy(args))
                if error:
                    self._log("error", c.name, "act: the game's check failed: " + error)
                if why:
                    self.remember(session, c.name, refused_note(tool, args, why), 0.6)
                    self._log("refused", c.name, "act: the game refused %s: %s" % (tool, why))
                    continue
            fn = c.functions.get(tool)
            if fn is not None:
                try:
                    fn(**args)
                except Exception as e:  # a game function that fails is reported, not propagated into Kinloom
                    self._log("error", c.name, "tool %s failed: %s" % (tool, e))
                    continue
            done.append((tool, args))
        return done

    def _valid_actions(self, c, text):
        data = find_json(text)
        items = data.get("actions") if isinstance(data, dict) else data if isinstance(data, list) else []
        out = []
        for item in (items or [])[:5]:
            if not isinstance(item, dict):
                continue
            tool = item.get("tool") or item.get("name")
            if not isinstance(tool, str) or tool not in c.tools:
                self._log("refused", c.name, "unknown tool %r" % (tool,))
                continue
            shape, _ = c.tools[tool]
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
            if shape is None:
                out.append((tool, {}))
                continue
            ok, value, error = shape.check(args)
            if ok and not self._allowed(value):
                self._log("refused", c.name, "%s: blocked by the content filter" % tool)
            elif ok:
                out.append((tool, value))
            else:
                self._log("refused", c.name, "%s: %s" % (tool, error))
        return out

    # ---------------- minds ----------------

    def mind(self, session, name, personality="", senses=None, actions=None, rules=None, variants=3, learn=30.0):
        """Declares a mind (utility AI the game runs locally). Returns its compiled form. Raises ValueError on bad shapes."""
        decl = _minds.Declaration(name, personality, senses, actions, rules, variants)
        key = (session, decl.name)
        sig = "%08x" % _minds.fnv1a(json.dumps([senses, actions, rules, decl.variants, decl.personality], sort_keys=True, default=str))
        with self._lock:
            old = self._minds.get(key)
            if old is not None and old.sig == sig:
                old.learn = _learn_every(learn)
                return self._compiled(old)
            if old is None and len(self._minds) >= MAX_CHARACTERS:
                raise ValueError("too many minds (%d)" % MAX_CHARACTERS)
        for e in decl.rule_errors:
            self._log("refused", decl.name, "rules: %s" % e)
        saved = self.memory.get("minds", "%s/%s" % (session, decl.name))
        programs = None
        if isinstance(saved, dict) and saved.get("sig") == sig and isinstance(saved.get("variants"), list):
            programs = [p for p in (_minds.validate(v, decl)[0] for v in saved["variants"][:decl.variants]) if p is not None]
            programs = (programs + [decl.offline] * decl.variants)[:decl.variants] if programs else None
        state = _MindState(decl, _minds.Mind(decl, programs), sig, _learn_every(learn))
        state.args = (personality, senses, actions, rules, variants, learn)
        if programs is not None:
            state.generation = int(saved.get("generation") or 0)
            state.curve = [x for x in (saved.get("curve") or []) if isinstance(x, (int, float))][-200:]
        with self._lock:
            self._minds[key] = state
        self._log("mind", decl.name, "%d actions, %d senses, %d variants%s" % (
            len(decl.order), len(decl.senses), decl.variants, " (learned, generation %d)" % state.generation if programs else ""))
        count = decl.variants - (1 if decl.rules else 0)
        if programs is None and count > 0 and self.provider is not None:
            state.busy = True
            self._background(lambda: self._write_variants(session, state, count))
        return self._compiled(state)

    def _compiled(self, state):
        c = dict(state.mind.compiled())
        c["ids"] = list(state.ids)
        return c

    def mind_compiled(self, session, name):
        with self._lock:
            state = self._minds.get((session, clean_text(str(name))[:MAX_NAME]))
        return self._compiled(state) if state else None

    def _mind_programs(self, name, decl, user):
        """Asks the model for mind programs; validated; one repair with the exact problems. [] when it fails."""
        system = prompts.mind_system(decl, self._written())
        for _ in (0, 1):
            r = self._call("mind", name, system, user, True, False, 1500)
            if not r.ok:
                return []
            data = find_json(r.text)
            raw = data.get("variants") if isinstance(data, dict) and "variants" in data else \
                [data.get("mind")] if isinstance(data, dict) and "mind" in data else data if isinstance(data, list) else [data]
            good, errors = [], []
            for p in (raw or [])[:_minds.MAX_VARIANTS]:
                prog, errs = _minds.validate(p, decl)
                errors += errs
                if prog is not None and self._allowed(prog):
                    good.append(prog)
            if errors:
                self._log("refused", name, "mind: %s" % "; ".join(errors[:3]))
            if good:
                return good
            user = user + prompts.repair("; ".join(errors[:6]) or "no valid variant")
        return []

    def _write_variants(self, session, state, count):
        try:
            decl = state.decl
            progs = self._mind_programs(decl.name, decl, prompts.minds_user(decl, count, decl.rules))
            if progs:
                base = [decl.offline] if decl.rules else []
                programs = (base + progs[:count] + [decl.offline] * decl.variants)[:decl.variants]
                with self._lock:
                    state.mind.set_variants(programs)
                    state.ids = [state.new_id() for _ in programs]
                    state.reset_stats(len(programs))
                self._log("mind", decl.name, "the model wrote %d variants" % len(progs[:count]))
                self._save_mind(session, state)
        finally:
            with self._lock:
                state.busy = False

    def think(self, session, name, senses, who=None):
        """Instant: the mind's choice for this unit, {"action", "args", "variant"}. Never calls a model."""
        state = self._minds.get((session, name))
        if state is None:
            state = self._minds.get((session, clean_text(str(name))[:MAX_NAME]))
            if state is None:
                return {"action": None, "args": {}, "variant": 0}
        choice = state.mind.think(senses, who)
        if who is not None:
            units = state.units
            if len(units) >= _minds.MAX_UNITS and who not in units:
                units.clear()
            units[who] = (choice["variant"], state.ids[choice["variant"]], choice["action"],
                          dict(senses) if isinstance(senses, dict) else {})
        return choice

    def explain(self, session, name, senses, who=None):
        with self._lock:
            state = self._minds.get((session, clean_text(str(name))[:MAX_NAME]))
        return state.mind.explain(senses, who) if state else None

    def reward(self, session, who, value, mind=None, variant=None, vid=None, action=None, senses=None, done=False):
        """The game scores what a unit did (higher is better). Minds that are rewarded learn. done: the unit's fight
        (life, round, episode) is over, so later rewards are not credited to its earlier decisions."""
        v = _finite(value)
        if v is None:
            return False
        v = max(-1000.0, min(1000.0, v))
        with self._lock:
            states = [s for (sess, n), s in self._minds.items() if sess == session and (mind is None or n == mind)]
        state, unit = None, None
        for s in states:
            if variant is not None and mind is not None:
                state, unit = s, (variant, vid, action, senses if isinstance(senses, dict) else {})
                break
            if who in s.units:
                state, unit = s, s.units[who]
                break
        if state is None:
            return False
        index, vid, action, senses = unit
        with self._lock:
            if not isinstance(index, int) or not 0 <= index < len(state.ids):
                return False
            if vid is not None and vid != state.ids[index]:
                return False   # that variant was replaced since: its rewards say nothing about the new one
            st = state.stats[index]
            st[0] += 1
            st[1] += v
            st[2] += v * v
            state.window[0] += 1
            state.window[1] += v
            state.samples[index].append((senses, action, v))
            self._credit(state, who, senses, action, v, done)
            ep = state.open.get(who)
            if ep is None:
                if len(state.open) >= _minds.MAX_UNITS:
                    state.open.clear()
                ep = state.open[who] = [index, state.ids[index], 0.0]
            ep[2] += v
            if done:
                state.episodic = True
                del state.open[who]
                if ep[1] == state.ids[ep[0]]:          # one program played the whole episode: it earned this outcome
                    e = state.episodes[ep[0]]
                    e[0] += 1
                    e[1] += ep[2]
                    e[2] += ep[2] * ep[2]
            now = self.clock()
            if state.last_learn is None:
                state.last_learn = now
            need = MIN_EPISODES if state.episodic else MIN_SAMPLES
            due = (state.learn and not state.busy and len(state.ids) >= 2 and now - state.last_learn >= state.learn and
                   all(sc[0] >= need for sc in state.scores()))
            if due:
                state.busy = True
        if due:
            self._learn(session, state)
        return True

    @staticmethod
    def _credit(state, who, senses, action, v, done):
        """Each decision earns its reward plus the discounted rewards that follow it (under the brain lock)."""
        trace = state.trace.get(who)
        if trace is None:
            if len(state.trace) >= _minds.MAX_UNITS:
                state.trace.clear()
            trace = state.trace[who] = []
        if not trace or trace[-1][0] != senses or trace[-1][1] != action:   # the same moment rewarded twice: one decision
            trace.append([senses, action, 0.0, 1.0])
        for e in trace:
            e[2] += e[3] * v
            e[3] *= GAMMA
        while trace and (done or trace[0][3] < CREDIT_CUTOFF):
            e = trace.pop(0)
            state.buffer.append((e[0], e[1], e[2]))

    def _learn(self, session, state):
        decl = state.decl
        with self._lock:
            scores = state.scores()
            means = [sc[1] / sc[0] for sc in scores]
            # Judged with their uncertainty: the parent is the one surely good (highest lower bound); the one replaced
            # is the one surely bad (lowest upper bound), so a newcomer is not thrown away after a few unlucky rounds.
            best = max(range(len(means)), key=lambda i: (_bound(scores[i], -1), -i))
            worst = min((i for i in range(len(means)) if i != best), key=lambda i: (_bound(scores[i], 1), -i))
            state.curve.append(round(state.window[1] / state.window[0], 4) if state.window[0] else 0.0)
            del state.curve[:-200]
            state.window = [0, 0.0]
            best_prog, worst_prog = state.mind.variants[best], state.mind.variants[worst]
            samples = sorted(state.samples[worst], key=lambda x: x[2])[:6]
            n_best, n_worst = state.scores()[best][0], state.scores()[worst][0]
            moments = list(state.buffer)

        def replace(prog, how):
            with self._lock:
                state.mind.set_variant(worst, prog)
                state.ids[worst] = state.new_id()
                state.stats[worst] = [0, 0.0, 0.0]
                state.episodes[worst] = [0, 0.0, 0.0]
                state.samples[worst].clear()
                state.generation += 1
                state.last_learn = self.clock()
                state.busy = False
            self._log("learn", decl.name, "generation %d: variant %d (mean %.3f) replaced by %s of the best (mean %.3f)" % (
                state.generation, worst, means[worst], how, means[best]), generation=state.generation)
            self._save_mind(session, state)

        def local():
            """Without a model: changes the data supports (most of the time), else random ones (exploration); sometimes
            two at once, because good tactics often need two changes together (advance *and* take cover)."""
            prog, hows = best_prog, []
            for _ in range(2 if state.rnd.random() < COMPOUND else 1):
                step = _minds.propose(prog, decl, moments, state.rnd) if state.rnd.random() < 0.6 else None
                if step is not None:
                    prog, how = step, "a change the data supports"
                else:
                    prog, how = _minds.mutate(prog, decl, state.rnd), "a mutation"
                hows.append(how)
            return prog, " and ".join(hows)

        if self.provider is None:
            replace(*local())
            return

        def work():
            try:
                user = prompts.mind_learn_user(best_prog, means[best], worst_prog, means[worst], samples, n_best, n_worst,
                                               _minds.evidence(decl, moments))
                progs = self._mind_programs(decl.name, decl, user)
                prog = next((p for p in progs if p != best_prog), None)
                if prog is not None:
                    replace(prog, "the model's rewrite")
                else:
                    replace(*local())
            finally:
                with self._lock:
                    state.busy = False

        self._background(work)

    def _save_mind(self, session, state):
        with self._lock:
            data = {"sig": state.sig, "variants": list(state.mind.variants), "generation": state.generation,
                    "curve": list(state.curve)}
        self.memory.put("minds", "%s/%s" % (session, state.decl.name), data)

    def mind_report(self, session, name):
        """How a mind is doing: variants with their mean reward, generations, the mean reward per generation."""
        with self._lock:
            state = self._minds.get((session, clean_text(str(name))[:MAX_NAME]))
            if state is None:
                return None
            return {"name": state.decl.name, "version": state.mind.version, "generation": state.generation,
                    "curve": list(state.curve),
                    "per": "episode" if state.episodic else "decision",
                    "variants": [{"id": state.ids[i], "rewards": n, "episodes": state.episodes[i][0],
                                  "mean": round(sc[1] / sc[0], 4) if sc[0] else None,
                                  "rules": json.loads(json.dumps(state.mind.variants[i]))}
                                 for i, ((n, _, _), sc) in enumerate(zip(state.stats, state.scores()))]}

    def minds(self, session):
        with self._lock:
            return [n for (s, n) in self._minds if s == session]

    # ---------------- create ----------------

    def create(self, session, what, example, context=None, count=None, instant=False, timeout=None, image=None,
               check=None, offline=None, refused=None, each=None):
        """Content shaped like the example (the example is the offline answer). image: a picture the model looks at
        (bytes, a path, base64 or a data URI); not used with instant (those items are made ahead).
        check(answer): the game's own rules. None, "" or True accept the answer; a reason (text) or False refuses it:
        the model gets the reason once, then the offline answer is used. With count/instant, refused items are replaced
        by the offline answer. A list answer (count, or a list example) is checked item by item: refused items are
        left out (count: replaced by the offline answer). offline: the game's own offline answer, shaped like the example
        (or one item of it). refused: {"answer", "why"}, an answer the game refused last time (what relay clients send).
        each(item): called for every item of a list answer, in order, as soon as the model has written it (the game can
        build while the model writes); other answers: called once with the answer."""
        return self.create_sourced(session, what, example, context, count, instant, timeout, image, check, offline, refused,
                                   each=each)[0]

    def create_sourced(self, session, what, example, context=None, count=None, instant=False, timeout=None, image=None,
                       check=None, offline=None, refused=None, retry=True, each=None):
        """create, and where the answer came from: (value, "model" or "offline")."""
        if each is not None and not callable(each):
            raise ValueError("create: each must be a function taking one item, got %r" % (each,))
        value, source, given = self._create(session, what, example, context, count, instant, timeout, image, check, offline,
                                            refused, retry, each)
        if each is not None:
            for item in (value if isinstance(value, list) and (count or Shape.of(example).kind == "list") else [value])[given:]:
                self._give(each, item, what)
        return value, source

    def _give(self, each, item, what):
        """Hands one item to the game's each(); a failing callback is journaled, never raised into Kinloom."""
        try:
            each(copy.deepcopy(item))
        except Exception as e:
            self._log("error", "create", "each(%s) failed: %s: %s" % (what[:40], type(e).__name__, e))

    def _streamer(self, item_shape, check, each, what, kept, limit):
        """on_text for a list answer: each finished item is checked and handed to each() at once."""
        items = Items()
        gate, open_ = threading.Lock(), [True]

        def feed(piece):
            with gate:                   # close() waits for an item being handed over
                if not open_[0]:
                    return               # a call given up on (timed out) keeps streaming: nothing after the answer
                for text in items.feed(piece):
                    if len(kept) >= limit:
                        return
                    ok, value, _ = item_shape.parse(text)
                    if not ok or not self._allowed(value) or (check is not None and self._why(check, value, what)):
                        continue
                    kept.append(value)
                    self._give(each, value, what)

        def close():
            with gate:
                open_[0] = False
        feed.close = close
        return feed

    def _create(self, session, what, example, context, count, instant, timeout, image, check, offline, refused, retry, each):
        """(value, source, how many of its items each() already got)."""
        if count and isinstance(example, list) and len(example) == 1:
            example = example[0]         # [item] with count: count items like it (agents write it; a list of lists never is)
        shape = Shape.of(example)
        fallback = self._offline_answer(shape, offline)
        if check is not None and not callable(check):
            raise ValueError("create: check must be a function taking the answer, got %r" % (check,))
        refused = self._refusal(refused)
        what = clean_text(what)
        self._clip_note(what[:MAX_WHAT], "what", what, MAX_WHAT, True)
        self._clip_note(what[:MAX_WHAT], "context", context)
        what = what[:MAX_WHAT]
        pictures = self._pictures(what, image) if image is not None else []
        if instant:
            if pictures:
                self._log("refused", what, "image: not used with instant=True (those items are made ahead)")
            item = self._from_pool(session, what, shape, context)
            if item is not None and check is not None:
                item = self._kept(shape, item, check, what)
            return ((item, "model") if item is not None else (copy.deepcopy(fallback), "offline")) + (0,)
        if count:
            count = max(1, min(50, int(_num(count, "count"))))
            streamed = []
            feed = self._streamer(shape, check, each, what, streamed, count) if each is not None else None
            items = self._create_many(session, what, shape, context, count, True, timeout, pictures, feed)
            if feed is not None:
                feed.close()
            if streamed:
                items = list(streamed)
            elif check is not None:
                items = [x for x in items if not self._why(check, x, what)]
            return (items + [copy.deepcopy(fallback) for _ in range(count - len(items))], "model" if items else "offline",
                    len(streamed))
        if self.provider is None:
            return copy.deepcopy(fallback), "offline", 0
        if refused:
            self._log("refused", what, "create: the game refused it: " + refused["why"])
        system = prompts.create_system(what, shape, self._written())
        user = (self._context(session, None, what) + prompts.context_block(context) + prompts.picture_block(pictures)
                + prompts.refused_block(refused))
        listed = shape.kind == "list"
        streamed = []
        feed = self._streamer(shape.info["item"], check, each, what, streamed, MAX_STREAMED) if each is not None and listed else None
        value = self._structured("create", what, system, user, shape, True, 1500, timeout, pictures, feed,
                                 (lambda: bool(streamed)) if feed is not None else None)
        if feed is not None:
            feed.close()
        if streamed:
            value = list(streamed)
        elif value is not None and listed and check is not None:
            value = self._kept(shape, value, check, what)        # a list is checked item by item, no second try
        if value is None:
            with self._lock:
                self._stats["offline_answers"] += 1
            return copy.deepcopy(fallback), "offline", 0
        self._log("create", what, json.dumps(value)[:300])
        why = self._why(check, value, what, quiet=retry) if check is not None and not listed else ""
        if why and retry:
            # the game's rules in the loop: the model hears why, once
            return self._create(session, what, example, context, None, False, timeout, image, check, offline,
                                {"answer": value, "why": why}, False, None)
        if why:
            return copy.deepcopy(fallback), "offline", 0
        return value, "model", len(streamed)

    def _kept(self, shape, value, check, what):
        """A list answer without the items the game refuses (None when none is left); anything else, checked whole."""
        if shape.kind != "list":
            return None if self._why(check, value, what) else value
        kept = [x for x in value if not self._why(check, x, what)]
        return kept or None

    def _offline_answer(self, shape, offline):
        """The game's own offline answer (create's offline=), checked against the example's shape."""
        if offline is None:
            return shape.default()
        ok, value, error = shape.check(offline)
        if not ok:
            raise ValueError("create: offline must be shaped like the example: %s" % error)
        return value

    @staticmethod
    def _refusal(refused):
        if refused is None:
            return None
        if not isinstance(refused, dict) or "answer" not in refused or not isinstance(refused.get("why"), str):
            raise ValueError('create: refused must be {"answer": the refused answer, "why": "the reason"}, got %r' % (refused,))
        why = " ".join(clean_text(refused["why"]).split())[:MAX_WHY]
        return {"answer": refused["answer"], "why": why} if why else None

    def _why(self, check, value, what, quiet=False, verb="create"):
        """Why the game's check refuses an answer ("" when it accepts it)."""
        why, error = judged(check, copy.deepcopy(value))
        if error:
            self._log("error", what, "%s: the game's check failed: %s" % (verb, error))
        if why and not quiet:
            self._log("refused", what, "%s: the game refused it: %s" % (verb, why))
        return why

    def _create_many(self, session, what, shape, context, count, foreground, timeout=None, pictures=None, on_text=None):
        if self.provider is None:
            return []
        system = prompts.create_many_system(what, shape, count, self._written())
        user = self._context(session, None, what) + prompts.context_block(context) + prompts.picture_block(pictures)
        r = self._call("create", what, system, user, True, foreground, min(4000, 200 + 150 * count), on_text=on_text,
                       timeout=timeout, images=pictures)
        if not r.ok:
            return []
        data = find_json(r.text)
        raw = data.get("items") if isinstance(data, dict) else data if isinstance(data, list) else []
        items = []
        for item in raw or []:
            ok, value, _ = shape.check(item)
            if ok and self._allowed(value):
                items.append(value)
            if len(items) >= count:
                break
        self._log("create", what, "%d items" % len(items))
        return items

    def _from_pool(self, session, what, shape, context):
        key = (session, what, shape.signature())
        with self._lock:
            pool = self._pools.setdefault(key, {"items": collections.deque(), "filling": False, "failures": 0})
            _trim(self._pools)
            item = pool["items"].popleft() if pool["items"] else None
            low = len(pool["items"]) < 2 and not pool["filling"] and pool["failures"] < 3 and self.provider is not None
            if low:
                pool["filling"] = True
        if low:
            def work():
                try:
                    items = self._create_many(session, what, shape, context, POOL_SIZE, False)
                    with self._lock:
                        pool["items"].extend(items)
                        pool["failures"] = 0 if items else pool["failures"] + 1
                finally:
                    with self._lock:
                        pool["filling"] = False
            self._background(work)
        return item

    # ---------------- chat ----------------

    def steer(self, session, name, text):
        """What the game decides for name's next reply (used once, by the next chat); "" takes it back."""
        if not isinstance(text, str):
            raise ValueError("steer: text must be a string, got %r" % (text,))
        c = self._char(session, name)
        text = " ".join(clean_text(text).split())[:MAX_STEER]
        with self._lock:
            if text:
                self._steers[(session, c.name)] = text
            else:
                self._steers.pop((session, c.name), None)
        if text:
            self._log("steer", c.name, text)

    def chat(self, session, name, message, facts=None, speaker="player", stream=None, timeout=None, max_chars=None,
             image=None, refused=None, drop=False):
        """A reply in character. An empty message: the speaker came up to the character, who speaks first.
        One model call gives the reply and what changed inside (mood, feeling, a memory, actions for act()).
        max_chars: this box's size (else the character's). image: a picture that comes with the message (what the
        speaker shows, or what the character sees now). refused: {"answer", "why"}, the reply to this same message the
        game refused: it is taken back (words, memory of it, its actions) and the model answers again knowing why;
        drop: take it back and answer offline (the game refused twice)."""
        c = self._char(session, name)
        refused = self._refusal(refused)
        if refused is not None:
            self._take_back(session, c, _name(speaker) or "player", clean_text(message or "")[:1000], str(refused["answer"]))
            self._log("refused", c.name, "chat: the game refused the reply: " + refused["why"])
        began = time.monotonic()
        pictures = self._pictures(c.name, image) if image is not None else []
        limit = _limit(max_chars) or c.max_chars
        message = clean_text(message or "")[:1000]
        speaker = _name(speaker) or "player"
        facts = _mapping(facts, "facts")
        self._clip_note(c.name, "facts", facts)
        hkey = (session, c.name, speaker)
        now = self.wall()
        table = self._bond_table(session)
        self._from_config(session, speaker)                 # another character of the game may be talking
        with self._lock:
            history = list(self._history.get(hkey, []))
            state = self._state.get(session)
            bond = dict(table[c.name][speaker]) if speaker in table.get(c.name, {}) else None
            other = self._characters.get((session, speaker))
            who = ((other.card or {}).get("summary") or other.personality) if other is not None and other is not c else ""
        reply, inner = None, {}
        prepared = None
        source = "model"
        with self._lock:
            steer = self._steers.pop((session, c.name), "")       # what the game decided for this reply: used once
        if not message and not facts and bond is None and not who and not pictures and not steer:   # someone new walks up: the prepared first line
            with self._lock:
                prepared = self._greetings.pop((c.name, getattr(c, "soul_key", None)), None)
        if prepared is not None:
            reply, inner = prepared
            reply = _souls.fit_chars(reply, limit)
            source = "prepared"
            if stream is not None:
                stream(reply)
        elif self.provider is not None and not drop:
            word, level = self._mood(session, c)
            system = prompts.chat_system(c, self._lang(c, chat=True), self._card_lines(c), self.lore(session))
            # The conversation only grows, so it comes first: providers (and local models) reuse its cached start.
            # What changes every reply (memories recalled for this message, feelings, mood, facts) comes after it.
            user = prompts.history_block(history, _souls.KEEP) + self._context(session, c.name, message) + \
                prompts.facts_block(facts) + \
                prompts.bond_block(speaker, bond, _souls.ago(now - bond["last"]) if bond else "",
                                   self.opinion(session, c.name, speaker), self._known(session, c.name, speaker),
                                   word, _souls.strength(level) if level else "", who,
                                   bool((c.card or {}).get("secrets")), c.secret_trust) + \
                prompts.worn_block(*_souls.worn([t for who, t in history if who == c.name])) + \
                prompts.steer_block(steer) + \
                prompts.picture_block(pictures, speaker) + prompts.message_block(speaker, message) + \
                prompts.box_block(_limit(max_chars))
            allowed = _allowed_numbers(facts, state, message, steer, c.personality, _souls.texts(c.card or {}),
                                       self.memory.recall(session, [c.name, "world"], message), self._known(session, c.name, speaker))
            repair = ("\n\n" + prompts.refused_block(refused)) if refused else ""
            streamed = False
            with self._lock:     # what they said lately, to anyone: not said again
                mine = list(self._said.get((session, c.name), ()))[-6:]
            # Secrets are kept by the code, not only asked of the model: a reply that gives one away to someone not
            # trusted enough is stopped as it streams and asked again (then cut, if the model insists).
            # A steer is the game's own decision: it may reveal a secret.
            hidden = (c.card or {}).get("secrets") or [] if self.opinion(session, c.name, speaker) < c.secret_trust and not steer else []
            public = _souls.public_texts(c.card or {}) + [c.personality or ""]
            for attempt in (0, 1):
                splitter = _souls.Splitter() if stream is not None and not streamed else None
                guard = _souls.Guard(_META) if splitter is not None else None
                unstage = _souls.Unstage() if splitter is not None else None
                echo = _souls.Echo(mine) if splitter is not None else None
                cut = _souls.Cap(c.reply_words, limit)
                gate = {"shown": "", "shut": False}
                show = None
                if splitter is not None:
                    def show(piece, splitter=splitter, guard=guard, unstage=unstage, echo=echo, cut=cut, gate=gate):
                        nonlocal streamed
                        shown = cut.feed(echo.feed(unstage.feed(guard.feed(splitter.feed(piece)))))
                        if shown and not gate["shut"]:
                            # Nothing reaches the player before the checks the final reply gets: secrets, content filter
                            if hidden and _souls.leaks(gate["shown"] + shown, hidden, public, asked=message) or \
                                    not self._allowed(gate["shown"] + shown):
                                gate["shut"] = True
                                return
                            gate["shown"] += shown
                            streamed = True
                            stream(shown)
                r = self._race("chat", c.name, system, user + repair, 500, show, timeout or self._reply_deadline(), pictures)
                if splitter is not None:
                    tail = cut.feed(echo.feed(unstage.feed(guard.feed(splitter.finish()[2]) + guard.finish()) + unstage.finish()) +
                                    echo.finish())
                    tail += cut.finish()
                    if hidden and _souls.leaks(gate["shown"] + tail, hidden, public, asked=message) or \
                            tail and not self._allowed(gate["shown"] + tail):
                        tail = ""
                    if tail and r.ok and not r.cut and not gate["shut"]:
                        streamed = True
                        stream(tail)
                if not r.ok:
                    break
                said, inner = _souls.split(r.text)
                said, narrated = _souls.drop_narrated(said, _souls.inner(inner)["gesture"], (c.card or {}).get("quirks"))
                if narrated and not _souls.inner(inner)["gesture"]:
                    inner = dict(inner, gesture=narrated)        # a habit told in words becomes a gesture for the game
                if r.cut and _souls.MARK not in r.text:
                    said, inner = _souls.whole_sentences(said), {}     # a cut reply keeps its finished sentences
                    if not said:
                        break
                why = []
                text = self._clean_reply(said, c.name, why)
                turn = re.search(r"(^|\s)%s\s*:" % re.escape(speaker), text) if text else None
                if turn:                                   # the model went on writing the other person's lines
                    text = text[:turn.start()].strip()
                text = _souls.cap(text, c.reply_words, limit)
                if text:
                    left, stale = _souls.drop_echoes(text, mine)
                    if stale and attempt == 0:          # nothing new in it: ask once for new words
                        repair = prompts.say_new()
                        self._log("repair", c.name, "chat: only said again what was said before; asked again")
                        continue
                    text = text if stale else left       # still nothing new: the whole reply beats a stub
                if hidden and text and _souls.leaks(text, hidden, public, asked=message):
                    if attempt == 0:
                        repair = prompts.keep_secret(c.name, speaker)
                        self._log("repair", c.name, "chat: gave a secret away to %s; asked again" % speaker)
                        continue
                    text = _souls.keep_secrets(text, hidden, public, asked=message)
                    self._log("refused", c.name, "chat: a secret was cut out of the reply")
                if "character" in why and attempt == 0:
                    repair = prompts.stay_in_character(c.name)
                    self._log("repair", c.name, "chat: stepped out of character; asked again")
                    continue
                bad = [m for m in _NUMBER.findall(text) if not _number_ok(m, allowed)]
                if not bad and text:
                    reply = text
                    break
                if not text:
                    break
                if streamed:
                    self._log("repair", c.name, "chat: numbers the game did not give; the reply shown will change")
                repair = prompts.numbers_repair()
                if bad and attempt == 1:
                    kept = " ".join(s.strip() for s in _SENTENCE.findall(text)
                                    if s.strip() and all(_number_ok(m, allowed) for m in _NUMBER.findall(s)))
                    reply = kept or None
                    self._log("refused", c.name, "chat: numbers the game did not give (%s)" % ", ".join(bad))
        with self._lock:
            stored = self._characters.get((session, c.name)) is c   # past MAX_CHARACTERS: a throwaway, keep no state
        decided = []
        if reply is not None and stored:
            if c.tools and source == "model" and not _souls.inner(inner)["do"]:
                # what the reply agreed to, within what is left of the reply's time (a player is waiting)
                left = (timeout or self._reply_deadline()) - (time.monotonic() - began)
                found = self._deeds(c, speaker, message, reply, max(1.5, left))
                if found:
                    inner = dict(inner or {}, do=found)
            undo = {}
            decided = self._inner(session, c, speaker, inner, undo)
            with self._lock:
                self._last_decided[(session, c.name)] = list(decided)
                self._last_undo[(session, c.name)] = undo
                _trim(self._last_decided)
                _trim(self._last_undo)
            if source == "prepared":
                # the next stranger's greeting, written now that this one changed the mood (not before: a race)
                self._prepare_greeting(session, c)
        elif reply is None:
            inner = None                             # offline: nothing new inside, nothing worth remembering
            source = "offline"
            reply = (self._offline_line(c, "greet", facts, limit) if not message else "") or self._next_offline(c)
            with self._lock:
                self._stats["offline_answers"] += 1
            if not reply:
                self._tell_empty(session, c.name, "chat", "%s has no offline reply: chat() answered \"\" (give it "
                                 "offline=\"...\" or a list of replies, said when no model answers)" % c.name)
        with self._lock:
            row = table.setdefault(c.name, {}) if stored else {}
            known = stored and (speaker in row or len(row) < MAX_SPEAKERS)   # else: a reply, but no trace kept
            if known:
                b = row.setdefault(speaker, {"talks": 0, "first": now, "last": now})
                if b["talks"] == 0 or now - b["last"] > _souls.NEW_TALK:
                    b["talks"] += 1
                b["last"] = now
            snapshot = {x: {y: dict(v) for y, v in r.items()} for x, r in table.items()}
            h = self._history.setdefault(hkey, []) if known else []
            if message:
                h.append((speaker, message))
            if reply:
                h.append((c.name, reply))
                if inner is not None and stored:
                    said = self._said.setdefault((session, c.name), collections.deque(maxlen=8))
                    said.append(reply)
            old = []
            if len(h) > _souls.KEEP:
                old = h[:_souls.SUMMARIZE]
                del h[:_souls.SUMMARIZE]
        if stored:
            self.memory.put("bonds", session, snapshot)
        self._recollect(session, c, speaker, old)
        if reply and message and inner is not None and stored:
            self.memory.add(session, c.name, "%s said: %s / I answered: %s" % (speaker, message[:120], reply[:160]), 0.35,
                            about=speaker)
        self._log("chat", c.name, reply, message=message, speaker=speaker, **({"offline": True} if inner is None else {}))
        return Line(reply, source, decided)

    def _take_back(self, session, c, speaker, message, answer):
        """The reply the game refused: out of the conversation, the memory and the actions waiting for act()."""
        with self._lock, _TAKE:
            h = self._history.get((session, c.name, speaker))
            if h and h[-1] == (c.name, answer):
                h.pop()
                if message and h and h[-1] == (speaker, message):
                    h.pop()
            said = self._said.get((session, c.name))
            if said and said[-1] == answer:
                said.pop()
            for a in self._last_decided.pop((session, c.name), []):
                a.taken = True
            undo = self._last_undo.pop((session, c.name), None) or {}
            key = (session, c.name)
            if "mood" in undo:
                if undo["mood"] is None:
                    self._moods.pop(key, None)
                else:
                    self._moods[key] = undo["mood"]
            if "rise" in undo:
                if undo["rise"] is None:
                    self._rises.pop((session, c.name, speaker), None)
                else:
                    self._rises[(session, c.name, speaker)] = undo["rise"]
            if "gesture" in undo:
                seen, shown = undo["gesture"]
                for table, value in ((self._gesture_seen, seen), (self._gestures, shown)):
                    if value is None:
                        table.pop(key, None)
                    else:
                        table[key] = value
        if undo.get("feel"):                 # the feeling it moved, the memories it wrote: not kept either
            self.feel(session, c.name, speaker, -undo["feel"])
        for note in undo.get("notes", []):
            self.memory.take_back(session, c.name, note)
        if message:
            self.memory.take_back(session, c.name, "%s said: %s / I answered: %s" % (speaker, message[:120], answer[:160]))

    def remark(self, session, about, who=None, facts=None, offline=None, max_chars=None):
        """A short line said out loud by someone in the crowd (no character to declare) about what just happened: a
        Line. offline: the game's own lines ({fact} placeholders), taken in turn when no model answers."""
        if not isinstance(about, str):
            raise ValueError("remark: about must be a string (what just happened), got %r" % (about,))
        about = " ".join(clean_text(about).split())[:MAX_ABOUT]
        who = " ".join(clean_text(str(who or "")).split())[:MAX_NAME] or DEFAULT_WHO
        facts = _mapping(facts, "facts")
        self._clip_note(who, "facts", facts)
        if offline is None:
            lines = []
        elif isinstance(offline, str):
            lines = [offline]
        elif isinstance(offline, (list, tuple)) and all(isinstance(x, str) for x in offline):
            lines = list(offline)
        else:
            raise ValueError('remark: offline must be a line or a list of lines, like ["Would you look at that!"], got %r' % (offline,))
        limit = _limit(max_chars)
        if self.provider is not None and about:
            r = self._call("remark", who, prompts.remark_system(who, self._written(), limit),
                           self._context(session, None, about) + prompts.facts_block(facts) + prompts.remark_user(about),
                           True, True, max_tokens=120)
            data = find_json(r.text) if r.ok else None
            line = data.get("line") if isinstance(data, dict) else None
            said = self._valid_remark(line, facts, about, limit) if isinstance(line, str) else ""
            if said:
                self._log("remark", who, said, about=about)
                return Line(said, "model")
        usable = [t for t in lines if set(_PLACEHOLDER.findall(t)) <= set(facts)]
        said = ""
        if usable:
            with self._lock:
                turn = self._remark_turns.get((session, who), 0)
                self._remark_turns[(session, who)] = turn + 1
                _trim(self._remark_turns)
            said = _souls.fit_chars(fill(usable[turn % len(usable)], facts), limit)
        with self._lock:
            self._stats["offline_answers"] += 1
        self._log("remark", who, said, about=about, source="offline")
        if not said:
            self._tell_empty(session, who, "remark", "remark by %s answered \"\" (give it offline=[...] lines, said "
                             "when no model answers)" % who)
        return Line(said, "offline")

    def _valid_remark(self, line, facts, about, limit):
        """The remark as said: one short line, the filter passed, no numbers the game did not give; else ""."""
        text = clean_text(line).strip().strip('"').strip()
        if not text or not self._allowed(text) or _META.search(text) or _PROMPTISH.search(text) or "{" in text:
            return ""
        allowed = _allowed_numbers(facts, about)
        if any(not _number_ok(m, allowed) for m in _NUMBER.findall(text)):
            return ""
        return _souls.cap(text, REMARK_WORDS, limit)

    def _deeds(self, c, speaker, message, reply, budget=10.0):
        """What a reply that named no tool commits the character to: one small call, only for characters with tools.
        Measured on a real model (proof/replies): replies said yes in words and left "do" empty most of the time.
        budget: seconds for everything here (the asking again included)."""
        system, user = prompts.deeds_system(c), prompts.deeds_user(c.name, speaker, message, reply)
        start = time.monotonic()
        r = self._call("deeds", c.name, system, user, True, True, 150, timeout=min(self.call_timeout, 5.0, budget))
        left = budget - (time.monotonic() - start)
        if not r.ok and left >= 1.0:  # a slow or failed call: what was agreed must not be lost, ask once more if time is left
            self._log("repair", c.name, "deeds: %s; asked again" % (r.error or "failed"))
            r = self._call("deeds", c.name, system, user, True, True, 150, timeout=min(self.call_timeout, 5.0, left))
        data = find_json(r.text) if r.ok else None
        found = data.get("do") if isinstance(data, dict) else None
        return [x for x in found if isinstance(x, dict)][:3] if isinstance(found, list) else []

    def _next_offline(self, c):
        """The offline reply: the one given, or the next of several (never the same twice in a row)."""
        if len(getattr(c, "offlines", [])) < 2:
            return c.offline
        with self._lock:
            c._offline_turn += 1
            return c.offlines[c._offline_turn % len(c.offlines)]

    def _clean_reply(self, text, name, why=None):
        """The spoken reply, cleaned; "" when unusable (why gets "filter" or "character": out of character)."""
        why = why if why is not None else []
        text = _speech_only(clean_text(text).strip()).strip().strip('"').strip()
        text = " ".join(_STAGE.sub(_unstage, text).split())    # *smiles*, (sighs), [pause]: stage directions go
        text = re.sub(r"\s+([.,!?])", r"\1", text)
        if not self._allowed(text):
            self._log("refused", name, "chat: blocked by the content filter")
            why.append("filter")
            return ""
        if text.lower().startswith(name.lower() + ":"):
            text = text[len(name) + 1:].strip()
        elif _PREFIX.match(text) and text.split(":")[0].strip().lower() in (name.lower(), "assistant", "ai", "i", "me"):
            text = _PREFIX.sub("", text, 1)
        if _META.search(text) or _PROMPTISH.search(text):
            why.append("character")
            return ""
        return text[:MAX_REPLY]

    # ---------------- memory and state ----------------

    # ---------------- v1: the player's choices, characters talking together, a snapshot, saves ----------------

    def suggest(self, session, name, examples, speaker="player", facts=None):
        """What the player could say now to name, one reply per example and in its order (each example's intent, written
        for this moment). Offline, or anything wrong with an answer: the example itself."""
        c = self._char(session, name)
        facts = _mapping(facts, "facts")
        self._clip_note(c.name, "facts", facts)
        if isinstance(examples, str) or not isinstance(examples, (list, tuple)):
            raise ValueError('examples: a list of short replies the player could say, like ["Ask about her past", "Leave"]')
        given = [clean_text(str(x))[:80] for x in examples[:MAX_SUGGESTIONS] if x is not None and clean_text(str(x))]
        if not given:
            raise ValueError('examples: give at least one reply, like ["Ask about her past", "Leave"]')
        speaker = _name(speaker) or "player"
        if self.provider is None:
            return given
        with self._lock:
            talk = list(self._history.get((session, c.name, speaker), []))
        r = self._call("suggest", c.name, prompts.suggest_system(c, len(given), speaker),
                       prompts.suggest_user(talk, facts, given), True, True, max_tokens=60 + 40 * len(given))
        data = find_json(r.text) if r.ok else None
        got = data.get("replies") if isinstance(data, dict) else data if isinstance(data, list) else None
        out = []
        for i, example in enumerate(given):
            text = got[i] if isinstance(got, list) and i < len(got) and isinstance(got[i], str) else ""
            text = clean_text(text).strip().strip('"').strip()
            if (not text or len(text) > 80 or len(text.split()) > 14 or _META.search(text) or _PROMPTISH.search(text)
                    or not self._allowed(text)):
                text = example
            out.append(text)
        if r.ok and out == given:
            self._log("refused", c.name, "suggest: no usable replies; the examples were used")
        return out

    def converse(self, session, a, b, about="", turns=4):
        """A short exchange between two characters (one model call), remembered by both: [{"who", "text"}].
        Offline: []."""
        ca, cb = self._char(session, a), self._char(session, b)
        n = max(2, min(8, int(_num(4 if turns is None else turns, "turns"))))
        about = clean_text("" if about is None else str(about))[:300]
        if self.provider is None or ca is cb:
            return []
        lang = self._lang(ca)
        system = prompts.converse_system(ca, cb, n, lang, self.lore(session))
        user = prompts.converse_user(ca.name, self._context(session, ca.name, about or cb.name), cb.name,
                                     self._context(session, cb.name, about or ca.name), about)
        r = self._call("converse", ca.name, system, user, True, True, max_tokens=80 + 70 * n)
        data = find_json(r.text) if r.ok else None
        items = data.get("lines") if isinstance(data, dict) else data if isinstance(data, list) else None
        allowed = _allowed_numbers(self._state.get(session), ca.personality, cb.personality, about,
                                   _souls.texts(ca.card or {}), _souls.texts(cb.card or {}))
        out = []
        for item in items if isinstance(items, list) else []:
            if len(out) >= n:
                break
            if not isinstance(item, dict):
                continue
            who = _name(item.get("who")) or ""
            c = ca if who.lower() == ca.name.lower() else cb if who.lower() == cb.name.lower() else None
            if c is None or not isinstance(item.get("text"), str):
                continue
            text = _souls.cap(self._clean_reply(item["text"], c.name), c.reply_words, c.max_chars)
            if text and not [m for m in _NUMBER.findall(text) if not _number_ok(m, allowed)]:
                out.append({"who": c.name, "text": text})
        if not out:
            self._log("refused", ca.name, "converse: no usable lines" + ("" if r.ok else " (%s)" % r.error))
            return []
        said = " / ".join("%s: %s" % (x["who"], x["text"]) for x in out)
        for c, other in ((ca, cb), (cb, ca)):
            self.memory.add(session, c.name, "Talked with %s: %s" % (other.name, said[:240]), 0.4, about=other.name)
        self._log("converse", ca.name, said[:300], other=cb.name)
        return out

    def inspect(self, session):
        """Everything a debug overlay shows: per character mood, feelings, last words, memories, waiting actions; per
        mind its generation and variants; whether a model answers."""
        with self._lock:
            names = sorted(name for (s, name) in self._characters if s == session)
            minds = sorted(name for (s, name) in self._minds if s == session)
        chars = {}
        for name in names:
            soul = self.soul(session, name)
            with self._lock:
                said = list(self._said.get((session, name), []))
                waiting = [a.tool for a in (self._pending.get((session, name)) or {}).get("actions", []) if not a.taken]
            chars[name] = {"personality": soul["personality"], "mood": soul["mood"], "gesture": soul["gesture"],
                           "feelings": {k: v for k, v in sorted(self.opinions(session, name).items())},
                           "talks": {k: v.get("talks", 0) for k, v in sorted(soul["bonds"].items())},
                           "last_words": said[-1] if said else "", "memories": soul["memories"][-5:], "waiting": waiting}
        out_minds = {}
        for name in minds:
            report = self.mind_report(session, name) or {}
            out_minds[name] = {"generation": report.get("generation", 0), "variants": len(report.get("variants", [])),
                               "per": report.get("per", "decision")}
        stats = self.stats()
        return {"online": self.online, "characters": chars, "minds": out_minds,
                "calls": stats["calls"], "failures": stats["failures"], "cost": stats.get("cost")}

    def save_state(self, session):
        """Everything Kinloom knows about this session (memories, feelings, bonds, moods, conversations, lore, learned
        minds, the game state it was given) as one JSON text, for the game's own save slot."""
        with self._lock:
            moods = {}
            for (s, name), m in self._moods.items():
                if s == session:
                    word, level = _souls.mood_now(m, self.clock(), "")
                    if level:
                        moods[name] = {"word": word, "level": level}
            history = [[name, speaker, [list(x) for x in lines]] for (s, name, speaker), lines in self._history.items()
                       if s == session and lines]
            said = {name: list(v) for (s, name), v in self._said.items() if s == session and v}
            state = self._state.get(session)
            mind_names = [name for (s, name) in self._minds if s == session]
        minds = {}
        for name in mind_names:
            saved = self.memory.get("minds", "%s/%s" % (session, name))
            if saved is not None:
                minds[name] = saved
        data = {"kinloom": 1, "notes": self.memory.session_notes(session),
                "bonds": self.memory.get("bonds", session), "opinions": self.memory.get("opinions", session),
                "lore": self.memory.get("lore", session), "minds": minds, "moods": moods, "history": history,
                "said": said, "state": state}
        return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)

    def load_state(self, session, text):
        """Puts back what save_state gave (this session's previous contents are replaced). ValueError when the text is
        not a Kinloom save."""
        try:
            data = json.loads(text) if isinstance(text, str) else text
        except ValueError:
            data = None
        if not isinstance(data, dict) or data.get("kinloom") != 1:
            raise ValueError("data: not a Kinloom save (give what save() returned)")
        notes = data.get("notes") if isinstance(data.get("notes"), dict) else {}
        self.memory.replace_session(session, notes)
        for section in ("bonds", "opinions", "lore"):
            value = data.get(section)
            if value is None:
                self.memory.delete(section, session)
            else:
                self.memory.put(section, session, value)
        minds = data.get("minds") if isinstance(data.get("minds"), dict) else {}
        now = self.clock()
        with self._lock:
            for key in [k for k in list(self._moods) + list(self._said) + list(self._gestures) + list(self._gesture_seen)
                        if k[0] == session]:
                for table in (self._moods, self._said, self._gestures, self._gesture_seen):
                    table.pop(key, None)
            for key in [k for k in list(self._history) + list(self._rises) if k[0] == session]:
                self._history.pop(key, None)
                self._rises.pop(key, None)
            self._bonds.pop(session, None)
            self._opinions.pop(session, None)
            self._lore.pop(session, None)
            for name, m in (data.get("moods") or {}).items() if isinstance(data.get("moods"), dict) else []:
                if isinstance(m, dict) and isinstance(m.get("word"), str) and isinstance(m.get("level"), (int, float)):
                    self._moods[(session, str(name))] = {"word": m["word"], "level": max(0.0, min(1.0, float(m["level"]))), "t": now}
            for item in data.get("history") or [] if isinstance(data.get("history"), list) else []:
                if isinstance(item, list) and len(item) == 3 and isinstance(item[2], list):
                    lines = [tuple(x) for x in item[2] if isinstance(x, list) and len(x) == 2 and all(isinstance(y, str) for y in x)]
                    self._history[(session, str(item[0]), str(item[1]))] = lines[-_souls.KEEP:]
            for name, v in (data.get("said") or {}).items() if isinstance(data.get("said"), dict) else []:
                if isinstance(v, list):
                    self._said[(session, str(name))] = collections.deque([x for x in v if isinstance(x, str)], maxlen=8)
            if isinstance(data.get("state"), dict):
                self._state[session] = data["state"]
            else:
                self._state.pop(session, None)
            redo = [(name, st.args) for (s, name), st in self._minds.items() if s == session and getattr(st, "args", None)]
        for name in [n for (s, n) in self.memory_keys("minds") if s == session]:
            self.memory.delete("minds", "%s/%s" % (session, name))
        for name, saved in minds.items():
            if isinstance(saved, dict):
                self.memory.put("minds", "%s/%s" % (session, name), saved)
        for name, args in redo:                       # minds declared before: rebuilt from what was loaded
            with self._lock:
                self._minds.pop((session, name), None)
            self.mind(session, name, *args)
        self._log("load", "kinloom", "save loaded: %d memories, %d minds" % (sum(len(v) for v in notes.values() if isinstance(v, list)), len(minds)))
        return True

    def memory_keys(self, section):
        """(session, name) pairs of a memory section keyed "session/name" (learned minds)."""
        with self.memory._lock:
            keys = list(self.memory._extra.get(section, {}))
        return [tuple(k.split("/", 1)) for k in keys if "/" in k]

    def event(self, session, text, about=None, importance=0.5, by=None, seen_by=None, tag=None, impact=None):
        """Something happened. Public (everyone may know) unless seen_by names the witnesses. by: who did it;
        impact (-1..1): how it changes the witnesses' opinion of `by` (estimated by the model from their personality
        when not given)."""
        text = clean_text(text)[:300]
        if not text:
            return
        by = _name(by)
        tag = _name(tag)
        with self._lock:
            names = [n for (s, n) in self._characters if s == session]
            self._events += 1
            eid = "e%x-%d" % (_minds.fnv1a(text + repr(time.time())), self._events)
        impact_value = _finite(impact)
        if impact_value is not None:
            impact_value = round(max(-1.0, min(1.0, impact_value)), 4)
        meta = {"eid": eid, "tag": tag, "by": by, "src": "seen", "orig": text, "impact": impact_value}
        if isinstance(seen_by, str):
            seen_by = [seen_by]
        if seen_by is not None and not isinstance(seen_by, (list, tuple, set)):
            raise TypeError("seen_by: a list of names, got %s" % type(seen_by).__name__)
        if seen_by is not None:
            witnesses = [n for n in (_name(x) for x in list(seen_by)[:100]) if n]
            knowers = witnesses + ([by] if by and by not in witnesses else [])
            for name in dict.fromkeys(knowers):
                self.memory.add(session, name, text, importance, **meta)
        else:
            targets = [n for n in (_name(x) for x in list(about)[:100]) if n] if about else \
                [n for n in names if re.search(r"\b%s\b" % re.escape(n), text, re.I)]
            for name in dict.fromkeys(targets + ([by] if by and by not in targets else [])):
                self.memory.add(session, name, text, importance, **meta)
            self.memory.add(session, "world", text, importance, **dict(meta, src="public"))
            witnesses = names
        witnesses = [w for w in dict.fromkeys(witnesses) if w != by]
        self._log("event", ",".join(witnesses[:8]) if seen_by is not None else "world", text, tag=tag, by=by)
        if not by or not witnesses:
            return
        if impact_value is not None:
            for w in witnesses:
                self.feel(session, w, by, impact_value)
        elif self.provider is not None:
            self._background(lambda: self._estimate_impact(session, text, by, witnesses[:12], eid))

    def _estimate_impact(self, session, text, by, witnesses, eid):
        with self._lock:
            people = [(w, getattr(self._characters.get((session, w)), "personality", ""), self.opinion(session, w, by))
                      for w in witnesses]
        shape = Shape.of({"impact": {w: (-1.0, 1.0) for w in witnesses}})
        value = self._structured("impact", by, prompts.impact_system(self._written()), prompts.impact_user(text, by, people),
                                 shape, False, 300)
        if value is None:
            return
        for w, v in value["impact"].items():
            v = round(v, 4)
            if v:
                self.feel(session, w, by, v)
                self.memory.annotate(session, w, eid, impact=v)
        self._log("impact", by, json.dumps(value["impact"]))

    def _opinion_table(self, session):
        with self._lock:
            table = self._opinions.get(session)
            if table is None:
                saved = self.memory.get("opinions", session)
                table = {}
                if isinstance(saved, dict):
                    for a, row in saved.items():
                        if isinstance(row, dict):
                            table[str(a)] = {str(b): max(-1.0, min(1.0, float(v))) for b, v in row.items() if _finite(v) is not None}
                self._opinions[session] = table
            return table

    def _warmth(self, session, a):
        """What a character feels for someone it has no opinion of yet: its warmth (0 for anyone else)."""
        if not a:
            return 0.0
        self._from_config(session, a)
        with self._lock:
            c = self._characters.get((session, a))
        return c.warmth if c is not None else 0.0

    def opinion(self, session, a, b):
        """What a thinks of b, -1..1 (no opinion yet: a's warmth, 0 unless the game gave one)."""
        a, b = _name(a), _name(b)
        table = self._opinion_table(session)
        with self._lock:
            row = table.get(a, {})
            if b in row:
                return row[b]
        return self._warmth(session, a)

    def opinions(self, session, a):
        table = self._opinion_table(session)
        with self._lock:
            return dict(table.get(_name(a), {}))

    def feel(self, session, a, b, change):
        """Moves a's opinion of b by change (clamped to -1..1). Returns the new opinion."""
        a, b = _name(a), _name(b)
        table = self._opinion_table(session)
        v = _finite(change)
        start = self._warmth(session, a)
        with self._lock:
            old = table.get(a, {}).get(b, start)
            if v is None or not a or not b or a == b:
                return old
            if a not in table and len(table) >= MAX_CHARACTERS:
                return old
            new = round(max(-1.0, min(1.0, old + v)), 4)
            table.setdefault(a, {})[b] = new
            snapshot = {x: dict(row) for x, row in table.items()}
        self.memory.put("opinions", session, snapshot)
        return new

    def reputation(self, session, target, group):
        """A group's average opinion of target (members without an opinion count 0)."""
        members = [c.name for c in self.characters(session) if c.group == _name(group)]
        if not members:
            return 0.0
        return round(sum(self.opinion(session, m, target) for m in members) / len(members), 4)

    def knowledge(self, session, name, tag=None):
        """What name knows (from the world layer): [{text, tag, source, by, importance, impact}]."""
        name = _name(name)
        out = []
        for scope in (name, "world"):
            for n in self.memory.notes(session, scope):
                if not n.get("eid") or (tag is not None and tag not in (n.get("tag"), n.get("eid"))):
                    continue
                if scope == "world" and any(o["eid"] == n["eid"] for o in out):
                    continue
                out.append({"text": n.get("orig") or n["text"], "tag": n.get("tag"), "source": n.get("src"), "by": n.get("by"),
                            "importance": n["importance"], "impact": n.get("impact"), "eid": n["eid"]})
        return out

    def knows(self, session, name, tag):
        return bool(self.knowledge(session, name, _name(tag)))

    def meet(self, session, a, b, k=3):
        """a and b tell each other the most important things the other does not know yet. Rumors lose importance
        on each hop; the listener's opinion of the doer moves by impact x 0.5 x trust in the teller."""
        a, b = _name(a), _name(b)
        shared = []
        if not a or not b or a == b:
            return shared
        for teller, listener in ((a, b), (b, a)):
            known = {n.get("eid") for n in self.memory.notes(session, listener) if n.get("eid")}
            news = [n for n in self.memory.notes(session, teller)
                    if n.get("eid") and n["eid"] not in known and n["importance"] >= MIN_RUMOR]
            news.sort(key=lambda n: (-n["importance"], -n["t"]))
            for n in news[:max(1, min(10, int(_num(k, "k"))))]:
                orig = n.get("orig") or n["text"]
                self.memory.add(session, listener, "%s told me: %s" % (teller, orig), round(n["importance"] * RUMOR_DECAY, 4),
                                eid=n["eid"], tag=n.get("tag"), by=n.get("by"), src=teller, orig=orig, impact=n.get("impact"))
                doer, impact = n.get("by"), _finite(n.get("impact"))
                if doer and impact is not None and doer != listener:
                    trust = (1.0 + self.opinion(session, listener, teller)) / 2.0
                    if trust > 0:
                        self.feel(session, listener, doer, impact * HEARSAY * trust)
                shared.append({"from": teller, "to": listener, "text": orig, "tag": n.get("tag")})
        if shared:
            self._log("meet", "%s+%s" % (a, b), "; ".join("%s -> %s: %s" % (s["from"], s["to"], s["text"]) for s in shared)[:300])
        return shared

    def spread(self, session, group=None, rounds=1):
        """Rounds of talk inside a group (or among every character): each member meets another, in turn."""
        members = [c.name for c in self.characters(session) if group is None or c.group == _name(group)]
        shared = []
        n = len(members)
        if n < 2:
            return shared
        times = 1 if rounds is None else int(_num(rounds, "rounds"))     # null: one round; not a number: ValueError
        for _ in range(max(1, min(20, times))):
            with self._lock:
                self._spreads += 1
                offset = (self._spreads - 1) % (n - 1) + 1
            for i in range(n):
                shared += self.meet(session, members[i], members[(i + offset) % n], 1)
        return shared

    def remember(self, session, name, note, importance=0.6):
        self.memory.add(session, str(name), note, importance)

    def _clip_note(self, name, label, value, limit=prompts.CLIP, text=False):
        """Journals, once per name and label, that the model reads only the start of something too long."""
        if not value:
            return
        size = len(value) if text else len(json.dumps(value, ensure_ascii=False, default=str))
        if size <= limit:
            return
        with self._lock:
            if (name, label) in self._clips:
                return
            self._clips.add((name, label))
        self._log("clipped", name, "%s: %d characters, the model reads the first %d" % (label, size, limit))

    def set_state(self, session, state):
        state = _mapping(state, "state")
        self._clip_note("state", "state", state)
        with self._lock:
            self._state[session] = state

    # ---------------- reporting ----------------

    def stats(self):
        with self._lock:
            s = json.loads(json.dumps(self._stats))
        s["cost"] = None
        if self.prices:
            p = self.prices
            fresh = max(0, s["input_tokens"] - s["cached_tokens"])
            s["cost"] = round((fresh * p.get("input", 0) + s["cached_tokens"] * p.get("cached_input", p.get("input", 0)) +
                               s["output_tokens"] * p.get("output", 0)) / 1e6, 6)
            s["price_source"] = p.get("source")
        s["avg_latency"] = round(s["latency"] / s["calls"], 3) if s["calls"] else 0.0
        return s

    @property
    def online(self):
        return self.provider is not None

    def status(self):
        p = self.provider
        return {"mode": "online" if p else "offline", "provider": getattr(p, "name", None), "model": getattr(p, "model", None),
                "calls_per_minute": self.limit, "language": self.language, "memory": self.memory.path,
                "voice": self.voice.describe() if self.voice is not None else None,
                "models": {k: getattr(v, "model", None) for k, v in sorted(self.models.items())}, "rating": self.rating}

    def journal(self, n=100):
        return list(self._journal)[-n:]

    def is_declared(self, session, name):
        self._from_config(session, clean_text(str(name))[:MAX_NAME] or "?")
        with self._lock:
            return (session, clean_text(str(name))[:MAX_NAME] or "?") in self._declared

    def characters(self, session):
        with self._lock:
            return [c for (s, _), c in self._characters.items() if s == session]

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.memory.save()
        self._bg.shutdown(wait=False)
        self._fg.shutdown(wait=False)
        if self.voice is not None:
            try:
                self.voice.close()
            except Exception:  # a custom voice provider must not break closing
                pass
        close = getattr(self.provider, "close", None)
        if close is not None:
            try:
                close()                        # a coding agent's processes started ahead
            except Exception:  # a custom provider must not break closing
                pass


def checked_chat(ask, check, stream=None, log=None):
    """chat with the game's check: ask(**more) asks once more (refused=..., drop=...); one retry, then offline.
    log(text): where a check that fails is told."""
    reply = ask()
    for drop in (False, True):
        why, error = judged(check, str(reply)) if reply.source != "offline" else ("", None)
        if error and log is not None:
            log("chat: the game's check failed: " + error)
        if not why:
            break
        reply = ask(refused={"answer": str(reply), "why": why}, drop=drop)
    if stream is not None and reply:
        try:
            stream(str(reply))
        except Exception:  # a game callback must never break the call
            pass
    return reply


def _warm(provider):
    """Opens the connection to the provider now (TCP and TLS; a local model is also loaded), so the first reply does
    not pay for it."""
    from .providers import _Http
    try:
        warm = getattr(provider, "warm", None)
        if warm is not None:
            warm()
        else:
            _Http.warm(provider.base_url)
    except Exception:  # warming is a bonus: any failure just means the first call connects itself
        pass


def _changed(before, now):
    """A situation changed a lot: a label changed, a key appeared, or a number moved by more than half its size."""
    if before is None:
        return True
    if set(before) != set(now):
        return True
    for k, v in now.items():
        b = before.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or isinstance(b, bool) or not isinstance(b, (int, float)):
            if b != v:
                return True
        elif abs(v - b) > 0.5 * max(abs(b), 1.0):
            return True
    return False


class Kinloom:
    """The game's handle on Kinloom, for one session (a player, a match, a save).

        kl = Kinloom()                      # finds a key or a local model, else runs offline
        kl.character("VEGA", "an over-excited commentator")
        kl.say("VEGA", "overtake", {"who": "BLAZE", "whom": "NOVA"})
    """

    def __init__(self, provider="auto", session="default", memory_path="auto", language=None,
                 calls_per_minute=None, prices=None, clock=time.monotonic, call_timeout=12.0, brain=None, folder=".",
                 content_filter=None, url=None, token=None, voice="auto", models=None, rating=None):
        """content_filter: optional function(text) -> bool; False blocks a model's text (the offline answer is used).
        url (or KINLOOM_URL): an online `kinloom serve` answers every call (a shipped game: the key stays on that
        server); token (or KINLOOM_TOKEN): its player token. Same calls; offline answers when it cannot be reached."""
        url = url or (os.environ.get("KINLOOM_URL") if brain is None and provider == "auto" else None)
        if brain is None and url:
            from .remote import RemoteBrain
            brain = RemoteBrain(url, token or os.environ.get("KINLOOM_TOKEN", ""), call_timeout)
        self.brain = brain or Brain(provider, memory_path, language, calls_per_minute, prices, clock, call_timeout, folder=folder,
                                    content_filter=content_filter, voice=voice, models=models, rating=rating)
        self.id = str(session)
        self._decide_refused, self._decide_ok = {}, {}       # decide's check: what was refused, what was accepted

    def session(self, session):
        """Another player's or match's view: same model and budget, separate memory, banks and decisions."""
        return Kinloom(session=session, brain=self.brain)

    def character(self, name, personality="", lines=None, offline=None, events=None, tools=None, max_words=None, every=8.0, language=None,
                  group=None, soul=None, trust=None, invent=True, voice=None, max_chars=None, warmth=None, secret_trust=None,
                  warm_up=None):
        """lines: {"event": ["..."], "*": [...]} the game's own lines ({fact} placeholders), or {"event": {"when": "what is
        happening, in words", "lines": [...]}}. max_words / max_chars: how long a line or reply may be (max_chars: a text
        box's size; the model's text never goes past it). language: "auto" answers in the speaker's language.
        voice: how they sound when they speak ("low, tired, warm"; their soul and mood are added), or {"id": a voice
        of the voice provider}. invent=False: the character never makes up names of people, places, events or numbers (only its card, the
        lore, the facts and what it is told). trust: {tool: feeling}, e.g. {"give": 0.3}: while talking, that tool is only used for speakers the character
        feels at least that for (feelings go from -1 to 1 and move at most 0.3 per reply).
        soul: a sentence (or True: the personality) the model turns once into a full inner life (card, saved in
        memory), or a card dict written by the game. Every character has a mood and bonds; a soul makes them deep.
        warmth: their feeling for anyone before any talk (-1..1, default 0); warm_up: the most one conversation can win
        (default 0.3); secret_trust: the feeling above which they may share a secret of their card (default 0.6)."""
        self.brain.character(self.id, name, personality, lines, offline, events, tools, max_words, every, language, group, soul,
                             trust, invent, voice, max_chars, warmth, secret_trust, warm_up)
        return self

    def steer(self, name, text):
        """What the game decides happens in name's next reply ("admit you were in the office at 12:30"): the model says it
        in the character's voice, even a secret of their card. Used by the next chat only; "" takes it back."""
        self.brain.steer(self.id, name, text)
        return self

    def lore(self, lines=None):
        """World facts every character takes as true (a list, or a text with one fact per line). lore() reads them."""
        return self.brain.lore(self.id, lines)

    def soul(self, name, speaker=None):
        """{name, personality, card, ready, mood: {word, level}, bonds: {speaker: {talks, first, last, feeling}},
        memories, tools, conversation}: what the character is and feels, for the game's UI or a debug panel."""
        return self.brain.soul(self.id, name, speaker)

    def say(self, name, event, facts=None, fresh=False, max_chars=None):
        """A line in character with the facts filled in: a Line (a str; .source is "model", "prepared" or "offline").
        max_chars: the size of the box it goes in this time (else the character's)."""
        return self.brain.say(self.id, name, event, facts, fresh, max_chars)

    def chat(self, name, message, facts=None, speaker="player", stream=None, timeout=None, max_chars=None, image=None,
             check=None):
        """A reply in character: a Line (a str; .source "model", "prepared" or "offline"; .do the actions decided in
        it, [(tool, args)], handed out once: reading .do takes them, else act() returns them). max_chars: the size of
        the box it goes in this time (else the character's). image: a picture with the message (bytes, a file path,
        base64 or a data URI: PNG, JPEG, GIF, WebP), for a model that reads images. check(text): the game's rules for
        what is said; a reply it refuses is taken back and asked again once with the reason, then the offline reply is
        used (with check, a stream gets the reply once it is accepted)."""
        if check is None:
            return self.brain.chat(self.id, name, message, facts, speaker, stream, timeout, max_chars, image)
        return checked_chat(lambda **more: self.brain.chat(self.id, name, message, facts, speaker, None, timeout, max_chars,
                                                           image, **more), check, stream,
                            lambda text: self.brain._log("error", str(name), text))

    def chat_async(self, name, message, facts=None, speaker="player", stream=None, max_chars=None, image=None):
        return self.brain._fg.submit(self.brain.chat, self.id, name, message, facts, speaker, stream, None, max_chars, image)

    def decide(self, name, situation, choices, every=None, check=None):
        """check(decision): the game's rules. A decision it refuses is not used (the last one it accepted is, else the
        example) and the next decisions are made knowing why."""
        if check is None:
            return self.brain.decide(self.id, name, situation, choices, every)
        key = (name, json.dumps(choices, sort_keys=True, default=str))
        note = self._decide_refused.get(key)
        if note is not None:
            situation = dict(situation if isinstance(situation, dict) else {"situation": situation},
                             **{"the game refused your last decision": note})
        value = self.brain.decide(self.id, name, situation, choices, every)
        why, error = judged(check, copy.deepcopy(value))
        if error:
            self.brain._log("error", str(name), "decide: the game's check failed: " + error)
        if not why:
            self._decide_refused.pop(key, None)
            self._decide_ok[key] = value
            _trim(self._decide_ok)
            return value
        if note is None or note.get("decision") != value:
            self.brain._log("refused", str(name), "decide: the game refused it: " + why)
        self._decide_refused[key] = {"decision": value, "why": why}
        _trim(self._decide_refused)
        if key in self._decide_ok:
            return copy.deepcopy(self._decide_ok[key])
        default = Shape.of(choices if isinstance(choices, dict) else {"choice": choices}).default()
        return default if isinstance(choices, dict) else default["choice"]

    def speak(self, name, text, timeout=None):
        """text said aloud in name's voice (None: a narrator voice). An Audio (audio.data: WAV bytes, audio.path: a
        cached file, audio.seconds), or None when no voice can speak (show the text). ~0.5-2 s with a hosted voice:
        off the frame loop (speak_async), or let Talk(voice=True) speak replies sentence by sentence."""
        return self.brain.speak(self.id, name, text, timeout)

    def speak_async(self, name, text):
        return self.brain._fg.submit(self.brain.speak, self.id, name, text)

    def listen(self, audio, language=None, timeout=None):
        """What someone said in a recording (WAV/WebM/OGG/MP3 bytes, a path, or base64): the text, "" if nothing."""
        return self.brain.listen(self.id, audio, language, timeout)

    def listen_async(self, audio, language=None):
        return self.brain._fg.submit(self.brain.listen, self.id, audio, language)

    def act(self, name, situation=None, think=True, check=None):
        """think=False: only what the character decided while talking (no model call of its own). check(tool, args):
        the game's rules; a refused action is not returned (nor run) and the character remembers why."""
        return self.brain.act(self.id, name, situation, think, check)

    def create(self, what, example, context=None, count=None, instant=False, timeout=None, image=None, check=None,
               offline=None, each=None):
        """Content shaped like the example, which is also the offline answer. image: a picture the model looks at.
        check(answer): the game's rules; return a reason (or False) to refuse it, and the model tries once more with that
        reason (a list is checked item by item). offline: the game's own offline answer instead of the example.
        each(item): every item of a list answer as soon as the model has written it (build while it writes)."""
        return self.brain.create(self.id, what, example, context, count, instant, timeout, image, check, offline, each=each)

    def remark(self, about, who=None, facts=None, offline=None, max_chars=None):
        """A short line from someone in the crowd about what just happened (no character to declare), ~1 s: a Line.
        who: who says it ("an old fisherman"); offline: your own lines, said in turn when no model answers."""
        return self.brain.remark(self.id, about, who, facts, offline, max_chars)

    def tools(self, tools=None):
        """What the game can do, declared once: {"open_door": {"door": "north"}, ...} and/or functions. Characters use
        them by name: character(..., tools=["open_door"]) or tools="all". tools() reads the names."""
        return self.brain.tools(self.id, tools)

    def prepare(self, timeout=10.0):
        """For a loading screen: waits until what Kinloom writes ahead is ready (soul cards, first greetings, line
        banks). {"ready", "waiting", "online"}."""
        return self.brain.prepare(self.id, timeout)

    def suggest(self, name, examples, speaker="player", facts=None, check=None):
        """What the player could say now to name (for games without a keyboard): one reply per example, in its order,
        each keeping that example's intent, written for this moment. Offline: the examples. check(text): the game's
        rules; a reply it refuses is replaced by its example."""
        replies = self.brain.suggest(self.id, name, examples, speaker, facts)
        if check is None:
            return replies
        out = []
        for i, r in enumerate(replies):
            why, error = judged(check, r)
            if error:
                self.brain._log("error", str(name), "suggest: the game's check failed: " + error)
            out.append(str(examples[i]) if why and i < len(examples) else r)
        return out

    def converse(self, a, b, about="", turns=4):
        """A short exchange between two characters, remembered by both: [{"who", "text"}] ([] offline)."""
        return self.brain.converse(self.id, a, b, about, turns)

    def inspect(self):
        """A snapshot for a debug overlay: each character's mood, feelings, last words, memories, waiting actions;
        each mind's generation and variants; whether a model answers; calls and cost."""
        return self.brain.inspect(self.id)

    def save(self):
        """Everything Kinloom knows about this session (memories, feelings, bonds, moods, conversations, lore, learned
        minds) as one text for the game's own save slot."""
        return self.brain.save_state(self.id)

    def load(self, data):
        """Puts back what save() gave (this session's state is replaced). ValueError when it is not a Kinloom save."""
        return self.brain.load_state(self.id, data)

    def mind(self, name, personality="", senses=None, actions=None, rules=None, variants=3, learn=30.0):
        """Utility AI the game runs locally (see kinloom.minds). senses/actions by example; rules: the offline mind
        ({"retreat": ["hp low"], "shoot": ["has_ammo", "dist below 20"]}); variants: temperaments in a crowd;
        learn: seconds between learning steps when the game calls reward (0: never)."""
        self.brain.mind(self.id, name, personality, senses, actions, rules, variants, learn)
        return self

    def think(self, name, senses, who=None):
        """Instant, never calls a model: {"action", "args", "variant"} for this unit (who: a stable id per unit)."""
        return self.brain.think(self.id, name, senses, who)

    def reward(self, who, value, mind=None, done=False):
        """How well the unit's last choice went (higher is better). Rewarded minds learn. done=True when the unit's
        fight, life or round is over (its next rewards start a new story)."""
        return self.brain.reward(self.id, who, value, mind, done=done)

    def explain(self, name, senses, who=None):
        """Every action's score and the rules behind it."""
        return self.brain.explain(self.id, name, senses, who)

    def mind_report(self, name):
        return self.brain.mind_report(self.id, name)

    def create_async(self, what, example, context=None, count=None, image=None):
        return self.brain._fg.submit(self.brain.create, self.id, what, example, context, count, False, None, image)

    def event(self, text, about=None, importance=0.5, by=None, seen_by=None, tag=None, impact=None):
        """Something happened. seen_by: only these witnesses know (else public). by + impact (-1..1): how it changes the
        witnesses' opinion of the doer (a model estimates it from their personality when you leave it out)."""
        self.brain.event(self.id, text, about, importance, by, seen_by, tag, impact)

    def meet(self, a, b, k=3):
        """a and b share what they know (rumors spread, trust-weighted). Returns [{from, to, text, tag}]."""
        return self.brain.meet(self.id, a, b, k)

    def spread(self, group=None, rounds=1):
        return self.brain.spread(self.id, group, rounds)

    def knows(self, name, tag):
        return self.brain.knows(self.id, name, tag)

    def knowledge(self, name, tag=None):
        return self.brain.knowledge(self.id, name, tag)

    def opinion(self, a, b):
        return self.brain.opinion(self.id, a, b)

    def opinions(self, a):
        return self.brain.opinions(self.id, a)

    def feel(self, a, b, change):
        return self.brain.feel(self.id, a, b, change)

    def reputation(self, target, group):
        return self.brain.reputation(self.id, target, group)

    def remember(self, name, note, importance=0.6):
        self.brain.remember(self.id, name, note, importance)

    def memories(self, name):
        return self.brain.memory.all(self.id, str(name))

    def state(self, state):
        self.brain.set_state(self.id, state)

    def stats(self):
        """Calls, failures, tokens, offline answers, cost (with declared prices), average latency."""
        return self.brain.stats()

    def status(self):
        return self.brain.status()

    @property
    def online(self):
        """True when a model answers (a key or a local model was found, or the online server is reachable)."""
        return bool(self.brain.online)

    def on(self, listener):
        """listener(entry) for everything Kinloom does (the journal: calls, lines, replies, refusals, "empty"...).
        Returns the listener (for off). A listener that raises is ignored."""
        self.brain.listeners.append(listener)
        return listener

    def off(self, listener):
        if listener in self.brain.listeners:
            self.brain.listeners.remove(listener)

    def journal(self, n=100):
        return self.brain.journal(n)

    def wait_idle(self, timeout=10.0):
        return self.brain.wait_idle(timeout)

    def close(self):
        self.brain.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
