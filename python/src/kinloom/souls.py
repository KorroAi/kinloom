"""Souls: who a character is (the card), how they feel right now (mood), and the one-call reply format.

A reply is what the character says out loud, then a line with ~~~ and one JSON object of what changed inside:
    Hmph. What do you want?
    ~~~
    {"mood": "annoyed", "intensity": 0.7, "feel": -0.1, "remember": "Ana mocked my hammer", "do": []}
Streaming shows only the spoken part (Splitter). A model that forgets the marker still works.
"""
import difflib
import hashlib
import json
import math
import re

from .shapes import clean_text, find_json

TEXT_FIELDS = ("summary", "voice", "backstory", "mood")
LIST_FIELDS = ("values", "fears", "desires", "secrets", "goals", "quirks", "likes", "dislikes")
MAX_TEXT = 300
MAX_ITEM = 200
MAX_ITEMS = 6
MARK = "~~~"
HALF_LIFE = 300.0          # seconds for a mood to lose half its strength
FADED = 0.15               # below this, the character is back to their baseline mood
MAX_FEEL = 0.3             # the most one reply can move a feeling
SECRET_TRUST = 0.6         # the feeling for someone above which a character may share a secret with them
TALK_RISE = 0.3            # the most a feeling can grow in one conversation (trust takes more than one talk)
NEW_TALK = 600.0           # seconds of silence after which talking again counts as a new conversation
KEEP = 20                  # lines of conversation kept word for word; older ones become a remembered summary
SUMMARIZE = 12             # lines summarized at a time
_WORD = re.compile(r"^[^\W\d_]{2,20}$")

CARD_EXAMPLE = {
    "summary": "who they are, in one sentence",
    "voice": "how they talk: rhythm, words they use, verbal tics",
    "backstory": "their past in two or three sentences",
    "values": ["what they care about"], "fears": ["what scares them"], "desires": ["what they want in life"],
    "secrets": ["what they hide"], "goals": ["what they are trying to do these days"], "quirks": ["a habit"],
    "likes": ["something they like"], "dislikes": ["something they dislike"],
    "mood": "their usual mood, one word",
}


def _text(v, limit):
    if isinstance(v, bool) or v is None or isinstance(v, (dict, list, tuple)):
        return ""
    return " ".join(clean_text(str(v)).split())[:limit]


def card(value, seed=""):
    """A clean card from anything (a model's JSON, a game's dict): known fields only, bounded, never the
    example's placeholder texts. Missing: empty. The summary falls back to the seed sentence."""
    value = value if isinstance(value, dict) else {}
    out = {}
    for k in TEXT_FIELDS:
        t = _text(value.get(k), MAX_TEXT)
        out[k] = "" if t == CARD_EXAMPLE[k] else t
    for k in LIST_FIELDS:
        items = value.get(k)
        items = items if isinstance(items, (list, tuple)) else ([items] if isinstance(items, str) else [])
        clean = []
        for x in items[:MAX_ITEMS * 2]:
            t = _text(x, MAX_ITEM)
            if t and t not in CARD_EXAMPLE[k] and t not in clean:
                clean.append(t)
        out[k] = clean[:MAX_ITEMS]
    if not out["summary"]:
        out["summary"] = _text(seed, MAX_TEXT)
    mood = out["mood"].lower()
    out["mood"] = mood if _WORD.match(mood) else ""
    return out


def texts(c):
    """Every text of a card (for the content filter and the numbers the character may say)."""
    return [c[k] for k in TEXT_FIELDS if c.get(k)] + [x for k in LIST_FIELDS for x in c.get(k, [])]


def seed_key(seed):
    return hashlib.sha1(("soul1|" + (seed or "")).encode("utf-8")).hexdigest()[:16]


_LABELS = [("voice", "How you talk"), ("backstory", "Your past"), ("values", "You care about"), ("fears", "You fear"),
           ("desires", "You want"), ("goals", "These days you are trying to"), ("secrets", "Your secrets (you hide them)"),
           ("quirks", "Your habits"), ("likes", "You like"), ("dislikes", "You dislike")]


def describe(c):
    """The card as lines for the system prompt (stable: providers cache it)."""
    lines = ["Who you are: %s" % c["summary"]] if c.get("summary") else []
    for k, label in _LABELS:
        v = c.get(k)
        if v:
            lines.append("%s: %s" % (label, "; ".join(v) if isinstance(v, list) else v))
    return lines


# ---------------- the reply format ----------------

def _trailing_json(text):
    """A JSON object at the end of text (a model that forgot the marker): (text before, the object) or (text, None)."""
    t = text.rstrip()
    if not t.endswith("}"):
        return text, None
    depth = 0
    for i in range(len(t) - 1, -1, -1):
        ch = t[i]
        if ch == "}":
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                data = find_json(t[i:])
                if isinstance(data, dict) and set(data) & {"mood", "feel", "remember", "do", "intensity", "gesture"}:
                    return t[:i], data
                return text, None
    return text, None


_WHOLE = re.compile(r".*[.!?…][\"'”’)\]]*", re.S)


def whole_sentences(text):
    """The text up to its last finished sentence ("" when none is finished)."""
    m = _WHOLE.match((text or "").strip())
    return m.group(0).strip() if m else ""


_CAP_END = re.compile(r"[.!?…]+[\"'”’)\]]*(?=\s)")


def cap(text, words, chars=None):
    """The text up to the end of the sentence that reaches `words` words: game dialogue stays short, whatever the model.
    chars: a text box's size; only whole sentences that fit are kept (a first sentence too long is cut on a word, …)."""
    c = Cap(words, chars)
    return (c.feed((text or "").strip()) + c.finish()).strip()


def fit_chars(text, chars):
    """At most `chars` characters: the whole sentences that fit, else the first one cut on a word with "…"."""
    return cap(" ".join((text or "").split()), 10 ** 6, chars) if chars else (text or "")


def _word_cut(sentence, chars):
    head = sentence[:max(1, chars - 1)]
    if " " in head and len(sentence) > len(head) and not sentence[len(head)].isspace():
        head = head.rsplit(" ", 1)[0]
    return head.rstrip(" ,;:-–—") + "…"


class Cap:
    """Streams a reply up to the end of the sentence that reaches `words` words, then nothing more. With `chars`,
    sentences are shown whole, only while the text still fits in that many characters (call finish() at the end)."""

    def __init__(self, words, chars=None):
        self.words, self.chars, self.shown, self.done = words, chars, "", False
        self.text, self.pos = "", 0

    def feed(self, piece):
        if self.done or not piece:
            return ""
        if self.chars:
            self.text += piece
            out = ""
            while not self.done:
                m = _CAP_END.search(self.text, self.pos)
                if m is None:
                    break
                out += self._sentence(self.text[self.pos:m.end()])
                self.pos = m.end()
            return out
        whole = self.shown + piece
        for m in _CAP_END.finditer(whole):
            if m.end() > len(self.shown) and len(_WORDS.findall(whole[:m.end()])) >= self.words:
                self.done, piece = True, whole[len(self.shown):m.end()]
                break
        self.shown += piece
        return piece

    def _sentence(self, sentence):
        sentence = " ".join(sentence.split())
        if not sentence:
            return ""
        joined = (self.shown + " " + sentence).strip()
        if len(joined) > self.chars:
            self.done = True
            if self.shown:
                return ""
            sentence = _word_cut(sentence, self.chars)
            joined = sentence
        out = (" " if self.shown else "") + sentence
        self.shown = joined
        if len(_WORDS.findall(self.shown)) >= self.words:
            self.done = True
        return out

    def finish(self):
        """What is left once the reply is complete (only with `chars`: the last sentence, if it fits)."""
        if not self.chars or self.done:
            return ""
        rest, self.pos = self.text[self.pos:], len(self.text)
        out = self._sentence(rest)
        self.done = True
        return out


def same_action(a, b):
    """True when two gestures say the same thing ("rubs left thumb over burn scar" / "rubs thumb over the burn scar")."""
    x, y = (set(re.findall(r"\w+", (s or "").lower())) - {"the", "a", "his", "her", "their", "le", "la", "sa", "son"}
            for s in (a, b))
    return bool(x and y) and len(x & y) >= 0.6 * max(len(x), len(y))


def drop_narrated(said, gesture, habits=()):
    """Removes sentences that only narrate the gesture or one of the card's habits ("Taps the barometer three times.")
    wherever they are. Returns (what is said, the first narrated action or "")."""
    actions = [set(re.findall(r"\w+", a.lower())) for a in [gesture or ""] + list(habits or [])]
    actions = [a for a in actions if len(a) >= 2]
    if not actions or not said:
        return said, ""
    firsts = [re.findall(r"\w+", a.lower())[:1] for a in [gesture or ""] + list(habits or [])]
    firsts = {f[0] for f in firsts if f}
    kept, narrated = [], ""
    for sentence in re.findall(r"[^.!?]+[.!?]*\s*", said):
        ordered = re.findall(r"\w+", sentence.lower())
        words = set(ordered)
        # narration starts with the action's own verb ("Taps the barometer..."); speech about it does not
        if ordered and ordered[0] in firsts and any(len(a & words) >= 0.6 * len(a) and len(words) <= len(a) + 3 for a in actions):
            narrated = narrated or sentence.strip().rstrip(".!?")
            continue
        kept.append(sentence)
    return "".join(kept).strip(), narrated


_KEYS = ("mood", "intensity", "feel", "remember", "gesture", "do")
_KEY_LINE = re.compile(r"(?:^|\n)[ \t]*(%s)[ \t]*:[ \t]*([^\n]*)" % "|".join(_KEYS), re.I)


def _inner_of(segment):
    """(the inner part found in a segment: a JSON object or "mood: calm" lines, the text left around it)."""
    at = segment.find("{")
    if at >= 0:
        try:
            obj, end = json.JSONDecoder().raw_decode(segment[at:])
        except ValueError:
            obj, end = None, 0
        if isinstance(obj, dict):
            return obj, segment[:at] + segment[at + end:]
        data = find_json(segment[at:])
        if isinstance(data, dict):
            return data, segment[:at]
    data = {}
    for m in _KEY_LINE.finditer(segment):
        key, value = m.group(1).lower(), m.group(2).strip().strip('",')
        if key == "do":
            try:
                value = json.loads(value)
            except ValueError:
                value = []
        data[key] = value
    return data, _KEY_LINE.sub("", segment) if data else segment


def split(text):
    """(what is said out loud, the inner part as a dict or {}). Small models' habits are read too: the marker written
    first (the reply comes after it), and "mood: calm" lines instead of JSON."""
    text = text or ""
    if MARK in text:
        said, _, rest = text.partition(MARK)
        if said.strip():
            data, _ = _inner_of(rest)
            return said.strip(), data
        inner, speech = {}, ""
        for segment in rest.split(MARK):
            data, left = _inner_of(segment)
            inner.update(data)
            if left.strip():
                speech = left.strip()          # the last spoken segment (an earlier one is often narration)
        return speech, inner
    said, data = _trailing_json(text)
    if data is None:
        lines = _KEY_LINE.search(text)
        if lines:
            data, _ = _inner_of(text[lines.start():])
            said = text[:lines.start()]
    return said.strip(), data or {}


class Guard:
    """Holds back the first words of a streamed reply until they are known to be in character, and stops the stream
    for good as soon as the text steps out of it (the reply is then asked again, never shown half-broken)."""

    def __init__(self, bad, hold=48):
        self.bad, self.hold = bad, hold
        self.text, self.shown, self.blocked = "", 0, False

    def feed(self, piece):
        self.text += piece or ""
        if self.blocked or self.bad.search(self.text):
            self.blocked = True
            return ""
        if len(self.text) < self.hold:
            return ""
        out = self.text[self.shown:]
        self.shown = len(self.text)
        return out

    def finish(self):
        if self.blocked or self.bad.search(self.text):
            self.blocked = True
            return ""
        out = self.text[self.shown:]
        self.shown = len(self.text)
        return out


def _inner_only(segment):
    """True when a segment between two markers is the inner part (JSON or "mood: calm" lines), not speech."""
    t = segment.strip()
    return not t or t.startswith("{") or bool(_KEY_LINE.match("\n" + t))


def _key_start(text):
    """True when text may still become the inner JSON ('{', '{"mo', '{ "feel'): held back until the next piece."""
    compact = re.sub(r"\s+", "", text)
    return any(('{"%s"' % k).startswith(compact) for k in _KEYS)


class Splitter:
    """Streams only the spoken part: pieces go in, what may be shown comes out (a possible start of the marker, or of
    an inner line like "mood:", is held back until the next piece tells). A marker written first is skipped."""

    def __init__(self):
        self.text = ""
        self.start = 0           # where the spoken part begins (after a marker written first)
        self.shown = 0
        self.done = False
        self.first = False       # the reply began with the marker

    def feed(self, piece):
        self.text += piece or ""
        if self.done:
            return ""
        at = self.text.find(MARK, self.start)
        if at >= 0 and self.start == 0 and not self.text[:at].strip():
            self.start = self.shown = at + len(MARK)          # small models: "~~~" first, then the reply
            self.first = True
            at = self.text.find(MARK, self.start)
        while at >= 0 and self.first and not self.text[self.start:self.shown].strip() and _inner_only(self.text[self.start:at]):
            self.start = self.shown = at + len(MARK)          # "~~~", the inner part, "~~~", then the reply
            at = self.text.find(MARK, self.start)
        if at >= 0:
            self.done = True
            out = self.text[self.shown:at]
            self.shown = at
            return out
        keep = 0
        for n in range(min(len(MARK) - 1, len(self.text) - self.start), 0, -1):
            if self.text.endswith(MARK[:n]):
                keep = n
                break
        end = len(self.text) - keep
        brace = self.text.rfind("{", self.shown, end)
        if brace >= 0 and re.match(r'\{\s*"(mood|feel|remember|do|intensity|gesture)"', self.text[brace:]):
            end = brace          # a model that forgot the marker: do not show its JSON
        elif brace >= 0 and _key_start(self.text[brace:]):
            end = brace          # maybe the start of that JSON ('{"mo'): wait for the next piece
        line = _KEY_LINE.search(self.text, self.shown)
        if line and line.start() < end:
            end = line.start()   # "mood: angry": the inner part began
            self.done = True
        else:
            nl = self.text.rfind("\n", self.shown, end)
            last = self.text[nl + 1:end].strip().lower() if nl >= 0 else ""
            if nl >= 0 and last and any(k.startswith(last) or last.startswith(k) for k in _KEYS) and len(last) < 12:
                end = nl         # maybe the start of an inner line: wait
        out = self.text[self.shown:end] if end > self.shown else ""
        self.shown = max(self.shown, end)
        return out

    def finish(self):
        """(said, inner dict, the spoken text still to show)."""
        said, inner = split(self.text)
        if self.done:
            return said, inner, ""
        before = self.text[self.start:self.shown].strip()
        tail = said[len(before):] if said.startswith(before) and len(said) > len(before) else ""
        return said, inner, tail


_OPENERS = {"*": ("*", 200), "(": (")", 200), "[": ("]", 60)}


def stage_keep(inner):
    """What stays of a stage direction: a name in asterisks (*Bright Mercy*: every word capitalized, three at most)
    stays as plain words; anything else (*smiles*, (sighs), [pause]) is dropped: None."""
    inner = inner.strip()
    words = inner.split()
    if inner and len(words) <= 3 and all(w[:1].isupper() for w in words):
        return inner
    return None


class Unstage:
    """Drops stage directions (*smiles*, (sighs), [pause]) from a streamed reply, as the finished reply drops them
    (brain._clean_reply): text from an opening mark is held until its closing mark tells what it is; the space a dropped
    direction leaves is one space, or none before punctuation."""

    def __init__(self):
        self.buf, self.held, self.pending, self.skip, self.started = "", None, "", False, False

    def _emit(self, text):
        if not text:
            return ""
        if self.skip:
            text = text.lstrip()
            if not text:
                return ""
            self.skip = False
            if self.started and text[0] not in ".,!?":
                text = " " + text
        self.started = True
        return text

    def feed(self, piece, final=False):
        self.buf += piece or ""
        out = ""
        while self.buf:
            if self.held is None:
                found = [i for i in (self.buf.find(o) for o in _OPENERS) if i >= 0]
                if not found:
                    out += self._emit(self.buf)
                    self.buf = ""
                    break
                at = min(found)
                kept = self.buf[:at].rstrip()
                self.pending = self.buf[len(kept):at]          # spaces right before the mark wait for what it is
                out += self._emit(kept)
                self.buf, self.held = self.buf[at:], self.buf[at]
            close, limit = _OPENERS[self.held]
            end = self.buf.find(close, 1)
            nl = self.buf.find("\n", 1)
            inside = self.buf[1:end if end >= 0 else len(self.buf)]
            bad = (nl >= 0 and (end < 0 or nl < end)) or len(inside) > limit or (self.held == "(" and "(" in inside)
            if not bad and end < 0:
                if not final:
                    break                                     # the closing mark has not come yet
                bad = True
            if not bad and end == 1:
                bad = True                                    # "**", "()", "[]": not a direction
            if not bad and self.held == "(":
                if end + 1 >= len(self.buf):
                    if not final:
                        break                                 # the next character tells: "(sighs)." or "(a)b"
                elif not (self.buf[end + 1].isspace() or self.buf[end + 1] in ".,!?"):
                    bad = True
            if bad:
                out += self._emit(self.pending + self.held)
                self.pending, self.buf, self.held = "", self.buf[1:], None
                continue
            keep = stage_keep(self.buf[1:end]) if self.held == "*" else None
            if keep is not None:
                out += self._emit(self.pending + keep)
            else:
                self.skip = True
            self.pending, self.buf, self.held = "", self.buf[end + 1:], None
        return out

    def finish(self):
        return self.feed("", final=True)


_END = re.compile(r"[.!?…]+[\"'”’)\]]*\s+")
_WORDS = re.compile(r"[\w'’]+")


def _norm(sentence):
    return tuple(w.replace("’", "'") for w in _WORDS.findall(sentence.lower()))


class Echo:
    """Drops what a character keeps saying, sentence by sentence, as the reply streams: a sentence of four words or
    more it already said in a recent reply (or nearly), and a short one ("Clank.") said again in the same reply.
    Complete sentences go out; the unfinished one waits. `stale` tells a reply with almost nothing new in it (the
    caller asks again rather than show a stub or the same lines)."""

    def __init__(self, before=()):
        said = [_norm(s) for r in before if r for s in _sentences(r)]
        self.before = [n for n in said if len(n) >= 4]
        self.seen = set(said)
        self.buf, self.kept, self.dropped, self.short, self.fresh, self.echoed = "", 0, [], set(), 0, 0
        self.early = 0            # the unfinished sentence already streams from this length on (new words)

    def _repeat(self, sentence):
        n = _norm(sentence)
        if not n:
            return False
        if len(n) <= 3:
            if n in self.short:
                return True
            self.short.add(n)
            return False
        for b in self.before:
            if n == b or (min(len(n), len(b)) >= 4 and
                          difflib.SequenceMatcher(None, n, b, autojunk=False).ratio() >= 0.85):
                self.echoed += 1
                return True
        return False

    def _pass(self, sentence):
        if self._repeat(sentence):
            self.dropped.append(sentence)
            return ""
        self.kept += 1
        n = _norm(sentence)
        if n not in self.seen:
            self.fresh += len(n)
        return sentence

    @property
    def stale(self):
        """Something said before was dropped and fewer than four new words are left."""
        return bool(self.echoed) and self.fresh < 4

    def _new_start(self, partial):
        """True once the unfinished sentence starts unlike anything said before: it can stream at once."""
        words = [w.replace("’", "'") for w in _WORDS.findall(partial.lower())]
        cut = not re.search(r"[\w'’]$", partial)          # the last word is complete
        full, last = (words, None) if cut else (words[:-1], words[-1] if words else None)
        if not full:
            return False
        for k in self.before + list(self.short):
            if tuple(k[:len(full)]) == tuple(full) and (last is None or (len(k) > len(full) and k[len(full)].startswith(last))):
                return False
        return True

    def feed(self, piece):
        self.buf += piece or ""
        out = []
        while True:
            m = _END.search(self.buf)
            if not m:
                break
            sentence, self.buf = self.buf[:m.end()], self.buf[m.end():]
            if self.early:                       # already streaming: it was new from its first words
                out.append(sentence[self.early:])
                self._fresh_one(sentence)
                self.early = 0
            else:
                out.append(self._pass(sentence))
        if self.buf and not self.early and self._new_start(self.buf):
            self.early = len(self.buf)
            out.append(self.buf)
        elif self.early and len(self.buf) > self.early:
            out.append(self.buf[self.early:])
            self.early = len(self.buf)
        return "".join(out)

    def _fresh_one(self, sentence):
        self.kept += 1
        n = _norm(sentence)
        if len(n) <= 3:
            self.short.add(n)
        if n not in self.seen:
            self.fresh += len(n)

    def finish(self):
        rest, self.buf = self.buf, ""
        if self.early:
            self._fresh_one(rest)
            out, self.early = rest[self.early:], 0
            return out
        return self._pass(rest) if rest.strip() else rest


def _sentences(text):
    return [s for s in re.findall(r"[^.!?…]+[.!?…]*[\"'”’)\]]*", text or "") if s.strip()]


def drop_echoes(text, before):
    """The whole-text version of Echo (for replies that were not streamed): (what is left, stale)."""
    e = Echo(before)
    out = (e.feed(text) + e.finish()).strip()
    return out, e.stale


_PLAIN = set("the a an to of and or her his their she he they them it its in on for with that this was is be been from at by"
             " my i me you your not never has have had secretly once who what which when where why how so but as into".split())


_IRREGULAR = {"sold": "sell", "paid": "pay", "stole": "steal", "stolen": "steal", "gave": "give", "given": "give",
              "told": "tell", "hid": "hide", "hidden": "hide", "bought": "buy", "lost": "lose", "killed": "kill",
              "slew": "kill", "slain": "kill", "betrayed": "betra", "owed": "owe", "owes": "owe", "owing": "owe"}


def _stem(w):
    w = w.replace("’", "'").lower()
    w = w[:-2] if w.endswith("'s") else w
    return _IRREGULAR.get(w, w)[:5]


def _marks(secret, public=()):
    """The words that tell a secret: its own words, minus those anyone may hear (the rest of the card)."""
    own = {_stem(w) for w in _WORDS.findall(secret) if w.lower() not in _PLAIN and len(w) >= 3}
    known = {_stem(w) for t in public for w in _WORDS.findall(t or "")}
    telling = own - known
    return telling if len(telling) >= 2 else own


_YES = re.compile(r"^\W*(aye|yes|yeah|yep|yup|true|indeed|i did|so i did|that i did|it is|it was|guilty|oui|si|ja)\b", re.I)


def leaks(text, secrets, public=(), share=0.5, asked=""):
    """The secret this text gives away, or None: half or more of its telling words are said (the king's sword, sold,
    a smuggler), words the rest of the card makes public (her husband, debts) not counted. A short yes ("Aye, I did.")
    to a question about the secret (asked) gives it away too."""
    said = {_stem(w) for w in _WORDS.findall(text or "")}
    first = (_sentences(text) or [""])[0]
    yes = bool(asked) and bool(_YES.match(first)) and len(_WORDS.findall(first)) <= 8
    both = said | {_stem(w) for w in _WORDS.findall(asked)} if yes else said     # a yes repeats the question
    for secret in secrets or []:
        marks = _marks(secret, public)
        if len(marks) >= 2 and (len(marks & said) >= max(2, share * len(marks)) or (yes and len(marks & both) >= 2)):
            return secret
    return None


def keep_secrets(text, secrets, public=(), asked=""):
    """The text without the sentences that give a secret away (the last resort when asking again did not help)."""
    kept = []
    for s in _sentences(text):
        if not leaks(" ".join(kept + [s]), secrets, public, asked=asked):
            kept.append(s)
    return " ".join(x.strip() for x in kept).strip()


def public_texts(c):
    """Everything on a card but its secrets."""
    return [c[k] for k in TEXT_FIELDS if c.get(k)] + [x for k in LIST_FIELDS if k != "secrets" for x in c.get(k, [])]


def worn(replies, recent=6):
    """What a character keeps saying: phrases of four words or more found in two of its recent replies, and the
    opening word when its last two replies began the same way. Small models loop on these; the next prompt forbids them."""
    said = [r for r in replies if r][-recent:]
    words = [re.findall(r"[\w'’]+", r.lower()) for r in said]
    found = {}
    for n in (8, 7, 6, 5, 4):
        seen = {}
        for i, w in enumerate(words):
            for j in range(len(w) - n + 1):
                seen.setdefault(tuple(w[j:j + n]), set()).add(i)
        for gram, where in seen.items():
            if len(where) >= 2 and not any(" ".join(gram) in f for f in found):
                found[" ".join(gram)] = True
    phrases = sorted(found, key=len, reverse=True)[:4]
    opener = words[-1][0] if len(words) >= 2 and words[-1] and words[-2] and words[-1][0] == words[-2][0] else ""
    return phrases, opener


# ---------------- inner life ----------------

def _number(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return f if math.isfinite(f) else None


def inner(data):
    """What changed inside, checked: {mood, intensity, feel, remember, do}. Unusable parts become None / empty."""
    data = data if isinstance(data, dict) else {}
    mood = _text(data.get("mood"), 20).lower()
    intensity = _number(data.get("intensity"))
    feel = _number(data.get("feel"))
    do = data.get("do")
    return {
        "mood": mood if _WORD.match(mood) else None,
        "intensity": 0.6 if intensity is None else max(0.0, min(1.0, intensity)),
        "feel": None if feel is None else max(-MAX_FEEL, min(MAX_FEEL, feel)),
        "remember": _text(data.get("remember"), MAX_ITEM),
        "self": _text(data.get("self"), MAX_ITEM),
        "gesture": _text(data.get("gesture"), 60),
        "do": [x for x in do if isinstance(x, dict)][:3] if isinstance(do, list) else [],
    }


def mood_now(mood, now, baseline):
    """(word, level) after fading: halves every HALF_LIFE seconds, back to the baseline when faint."""
    base = baseline or "calm"
    if not mood:
        return base, 0.0
    level = mood["level"] * 0.5 ** (max(0.0, now - mood["t"]) / HALF_LIFE)
    if level < FADED:
        return base, 0.0
    return mood["word"], round(level, 4)


def strength(level):
    """How strongly a mood is felt, said before it: "very angry", "quite curious", "a little tired"."""
    return "very" if level >= 0.7 else "a little" if level < 0.35 else "quite"


def ago(seconds):
    s = max(0.0, float(seconds))
    for unit, size in (("month", 30 * 86400), ("day", 86400), ("hour", 3600), ("minute", 60)):
        if s >= size:
            n = int(s // size)
            return "%d %s%s ago" % (n, unit, "" if n == 1 else "s")
    return "just now"
