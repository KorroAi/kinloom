"""Shapes by example: the developer shows an example answer; Kinloom validates model answers against it,
clamps what can be clamped, and uses the example itself as the offline answer.

    ["attack", "block"]        one of these (2 or more strings)
    (0.0, 1.0) or [0.0, 1.0]   a number in this range (2 numbers; integers give whole numbers)
    3 / 0.5                    a whole number / a number
    True                       true or false
    "#ff7a45"                  a color
    "some text"                short text (the example is the default)
    ["#ff0000"], [{...}]       a list of that (one example item)
    {"k": ...}                 an object with those fields (missing fields get their default, extras are dropped)
"""
import json
import math
import re

MAX_DEPTH = 12
MAX_LIST = 50
MAX_TEXT = 200
MAX_INT = 2**31 - 1
MAX_NUMBER = 1e9              # a free number (no range) beyond this is refused: games get ranges for anything critical
_COLOR = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f\u202a-\u202e\u2066-\u2069]")  # + bidi overrides (spoofed text)
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _fmt(n):
    return str(int(n)) if float(n).is_integer() else ("%g" % n)


def _number(v):
    """A finite float from a number or a numeric string, else None (booleans are not numbers)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
    elif isinstance(v, str):
        try:
            f = float(v.strip())
        except ValueError:
            return None
    else:
        return None
    return f if math.isfinite(f) else None


class Shape:
    def __init__(self, kind, example, **info):
        self.kind = kind
        self.example = example
        self.info = info

    # ---------- building ----------

    @staticmethod
    def of(example, _depth=0):
        if _depth > MAX_DEPTH:
            raise ValueError("example nested too deeply (max %d levels)" % MAX_DEPTH)
        if isinstance(example, Shape):
            return example
        if isinstance(example, bool):
            return Shape("boolean", example)
        if isinstance(example, int):
            return Shape("integer", example)
        if isinstance(example, float):
            if not math.isfinite(example):
                raise ValueError("examples must be finite numbers")
            return Shape("number", example)
        if isinstance(example, str):
            if _COLOR.match(example) and example.startswith("#"):
                return Shape("color", example.lower())
            limit = MAX_TEXT if len(example) <= MAX_TEXT else min(2000, len(example) * 2)
            return Shape("text", example, max=limit)
        if isinstance(example, (list, tuple)):
            items = list(example)
            if len(items) == 2 and all(_number(x) is not None and not isinstance(x, str) for x in items):
                lo, hi = sorted(float(x) for x in items)
                # Whole numbers only when both ends are integers at least 2 apart: (1, 5) is 1..5, (0, 1) is 0.0..1.0.
                whole = all(isinstance(x, int) and not isinstance(x, bool) for x in items) and hi - lo >= 2
                return Shape("range", example, lo=lo, hi=hi, whole=whole)
            if len(items) >= 2 and all(isinstance(x, str) for x in items):
                options = []
                for x in items:
                    if x not in options:
                        options.append(x)
                return Shape("options", example, options=options)
            if len(items) >= 1:
                return Shape("list", example, item=Shape.of(items[0], _depth + 1))
            raise ValueError("an empty list says nothing about its items: give one example item")
        if isinstance(example, dict):
            if not example:
                raise ValueError("an empty object says nothing: give example fields")
            fields = {str(k): Shape.of(v, _depth + 1) for k, v in example.items()}
            return Shape("object", example, fields=fields)
        raise ValueError("unsupported example %r (use text, numbers, true/false, lists, ranges or objects)" % (example,))

    # ---------- defaults ----------

    def default(self):
        k = self.kind
        if k == "options":
            return self.info["options"][0]
        if k == "range":
            mid = (self.info["lo"] + self.info["hi"]) / 2
            return int(math.floor(mid + 0.5)) if self.info["whole"] else mid
        if k == "object":
            return {name: f.default() for name, f in self.info["fields"].items()}
        if k == "list":
            return [self.info["item"].check(x)[1] if self.info["item"].check(x)[0] else self.info["item"].default() for x in self.example]
        return self.example

    # ---------- checking ----------

    def check(self, value, path="value"):
        """(ok, cleaned value, error). Numbers are clamped into ranges; text is cleaned; object extras are dropped."""
        k = self.kind
        if k == "options":
            if isinstance(value, str):
                v = value.strip()
                for o in self.info["options"]:
                    if o == v or o.lower() == v.lower():
                        return True, o, None
            return False, None, "%s must be one of %s" % (path, ", ".join('"%s"' % o for o in self.info["options"]))
        if k == "range":
            n = _number(value)
            if n is None:
                return False, None, "%s must be a number from %s to %s" % (path, _fmt(self.info["lo"]), _fmt(self.info["hi"]))
            n = min(max(n, self.info["lo"]), self.info["hi"])
            return True, (int(math.floor(n + 0.5)) if self.info["whole"] else n), None
        if k == "integer":
            n = _number(value)
            if n is None or abs(n - round(n)) > 1e-9 or abs(n) > MAX_INT:
                return False, None, "%s must be a whole number" % path
            return True, int(round(n)), None
        if k == "number":
            n = _number(value)
            if n is None or abs(n) > MAX_NUMBER:
                return False, None, "%s must be a number" % path
            return True, n, None
        if k == "boolean":
            if isinstance(value, bool):
                return True, value, None
            if isinstance(value, str) and value.strip().lower() in ("true", "yes", "false", "no"):
                return True, value.strip().lower() in ("true", "yes"), None
            return False, None, "%s must be true or false" % path
        if k == "color":
            if isinstance(value, str) and _COLOR.match(value.strip()):
                v = value.strip().lower()
                return True, v if v.startswith("#") else "#" + v, None
            return False, None, '%s must be a color like "#rrggbb"' % path
        if k == "text":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                value = str(value)
            if not isinstance(value, str):
                return False, None, "%s must be text" % path
            v = clean_text(value)
            if not v:
                return False, None, "%s must not be empty" % path
            if len(v) > self.info["max"]:
                return False, None, "%s must be at most %d characters" % (path, self.info["max"])
            return True, v, None
        if k == "list":
            if isinstance(value, dict):
                # JSON mode makes models wrap a list in an object ({"list": [...]}, {"stalls": [...]}) or answer one item
                lists = [v for v in value.values() if isinstance(v, list)]
                if lists:
                    value = lists[0]            # the first list, as items stream it (Items)
                elif self.info["item"].kind == "object":
                    ok, v, _ = self.info["item"].check(value, path + "[0]")
                    if ok:
                        return True, [v], None
            if not isinstance(value, list):
                return False, None, "%s must be a list" % path
            if len(value) > MAX_LIST:
                return False, None, "%s must have at most %d items" % (path, MAX_LIST)
            out = []
            for i, item in enumerate(value):
                ok, v, err = self.info["item"].check(item, "%s[%d]" % (path, i))
                if not ok:
                    return False, None, err
                out.append(v)
            if not out:
                return False, None, "%s must not be empty" % path
            return True, out, None
        if k == "object":
            if not isinstance(value, dict):
                return False, None, "%s must be an object with %s" % (path, ", ".join(self.info["fields"]))
            fields = self.info["fields"]
            lower = {}
            for key in value:
                lower.setdefault(str(key).lower(), key)
            found = {name: (name if name in value else lower.get(name.lower())) for name in fields}
            if fields and all(k is None for k in found.values()):
                inner = next(iter(value.values())) if len(value) == 1 else None
                if isinstance(inner, dict):               # {"item": {...}}: the answer wrapped once
                    return self.check(inner, path)
                # None of the fields: not an answer (the example would come back silently as the model's)
                return False, None, "%s must be an object with %s" % (path, ", ".join(fields))
            out = {}
            for name, field in fields.items():
                if found[name] is not None:
                    ok, v, err = field.check(value[found[name]], name)
                    if not ok:
                        return False, None, err
                    out[name] = v
                else:
                    out[name] = field.default()
            return True, out, None
        return False, None, "unknown shape"

    def parse(self, text):
        """Finds the JSON in a model answer (code fences, chatter around it) and checks it."""
        data = find_json(text)
        if data is None:
            return False, None, CUT if cut_off(text) else "the answer was not JSON"
        return self.check(data)

    # ---------- describing ----------

    def describe(self, indent=""):
        k = self.kind
        if k == "options":
            return "one of " + ", ".join('"%s"' % o for o in self.info["options"])
        if k == "range":
            word = "whole number" if self.info["whole"] else "number"
            return "%s from %s to %s" % (word, _fmt(self.info["lo"]), _fmt(self.info["hi"]))
        if k == "integer":
            return "whole number, e.g. %d" % self.example
        if k == "number":
            return "number, e.g. %s" % _fmt(self.example)
        if k == "boolean":
            return "true or false"
        if k == "color":
            return 'color like "#rrggbb"'
        if k == "text":
            return "short text (max %d characters), e.g. %s" % (self.info["max"], json.dumps(self.example))
        if k == "list":
            return "list (1 to %d items) of: %s" % (MAX_LIST, self.info["item"].describe(indent))
        if k == "object":
            inner = indent + "  "
            lines = ['%s"%s": %s' % (inner, name, f.describe(inner)) for name, f in self.info["fields"].items()]
            return "{\n" + ",\n".join(lines) + "\n" + indent + "}"
        return "anything"

    def signature(self):
        """A stable key for caches (same shape, same key)."""
        return json.dumps(_plain(self.example), sort_keys=True)


def _plain(x):
    if isinstance(x, tuple):
        return {"__range__": list(x)}
    if isinstance(x, list):
        return [_plain(i) for i in x]
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    return x


def clean_text(text):
    """One tidy line: control characters (terminal escapes, NUL...) removed, whitespace collapsed."""
    text = _CONTROL.sub("", _ANSI.sub("", str(text)))
    return " ".join(text.split())


class Items:
    """The elements of the first JSON list in a text that arrives in pieces (a list, or a list value of the top object:
    {"items": [...]}), each one as soon as it is complete. feed(piece) returns the texts of the new elements."""

    def __init__(self):
        self.buf = ""
        self.i = 0
        self.stack = []
        self.string = False
        self.escape = False
        self.level = None
        self.start = 0
        self.done = False

    def feed(self, piece):
        out = []
        if self.done or not piece:
            return out
        self.buf += piece
        while self.i < len(self.buf):
            ch = self.buf[self.i]
            if self.string:
                if self.escape:
                    self.escape = False
                elif ch == "\\":
                    self.escape = True
                elif ch == '"':
                    self.string = False
            elif ch == '"':
                self.string = True
            elif ch == "[" or ch == "{":
                self.stack.append(ch)
                if ch == "[" and self.level is None and (len(self.stack) == 1 or (len(self.stack) == 2 and self.stack[0] == "{")):
                    self.level = len(self.stack)
                    self.start = self.i + 1
            elif ch == "]" or ch == "}":
                if ch == "]" and self.level is not None and len(self.stack) == self.level:
                    self._emit(self.buf[self.start:self.i], out)
                    self.done = True
                    self.i += 1
                    return out
                if self.stack:
                    self.stack.pop()
            elif ch == "," and self.level is not None and len(self.stack) == self.level:
                self._emit(self.buf[self.start:self.i], out)
                self.start = self.i + 1
            self.i += 1
        return out

    @staticmethod
    def _emit(text, out):
        text = text.strip()
        if text:
            out.append(text)


def find_json(text, limit=100_000):
    """The first JSON object or array in a model answer, or None. Never raises."""
    if not isinstance(text, str) or not text.strip():
        return None
    t = text.strip()
    if len(t) > limit:
        return None
    fence = t.find("```")
    if fence >= 0:
        start = t.find("\n", fence)
        end = t.find("```", start + 1) if start >= 0 else -1
        if start >= 0 and end > start:
            t = t[start + 1:end].strip()
    try:
        return json.loads(t)
    except (ValueError, RecursionError):
        pass
    # The first complete JSON object (or array) in the text, even with chatter or braces after it; never one nested in
    # JSON that stops before its end (an answer cut by the token limit: its first inner object is not the answer).
    stop = _unclosed(t)
    decoder = json.JSONDecoder()
    for open_ch in ("{", "["):
        at, tries = t.find(open_ch), 0
        while 0 <= at and (stop < 0 or at < stop) and tries < 20:
            try:
                return decoder.raw_decode(t, at)[0]
            except (ValueError, RecursionError):
                end = _close(t, at)
                if end > at:            # it closes but does not parse: a trailing comma? (never its inner object)
                    try:
                        return json.loads(_no_trailing_commas(t[at:end + 1]))
                    except (ValueError, RecursionError):
                        pass
                at, tries = t.find(open_ch, at + 1), tries + 1
    return None


def _close(t, at):
    """Where the bracket opened at `at` closes (brackets in strings skipped), or -1."""
    depth, k, quoted, n = 0, at, False, len(t)
    while k < n:
        ch = t[k]
        if quoted:
            if ch == "\\":
                k += 1
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return k
        k += 1
    return -1


def _no_trailing_commas(t):
    """The text without commas right before } or ] (outside strings): what models often write."""
    out, k, quoted, n = [], 0, False, len(t)
    while k < n:
        ch = t[k]
        if quoted:
            if ch == "\\" and k + 1 < n:
                out.append(t[k:k + 2])
                k += 2
                continue
            if ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
        elif ch == ",":
            j = k + 1
            while j < n and t[j] in " \t\r\n":
                j += 1
            if j < n and t[j] in "}]":
                k += 1
                continue
        out.append(ch)
        k += 1
    return "".join(out)


CUT = "the answer was cut off before its end: write it shorter and complete"


def _unclosed(t):
    """Where the first JSON-looking object or array that never closes starts ({" or [ followed by a value), or -1."""
    i, n = 0, len(t)
    while i < n:
        c = t[i]
        if c in "{[":
            j = i + 1
            while j < n and t[j] in " \t\r\n":
                j += 1
            if j < n and (t[j] in '"}' if c == "{" else t[j] in '"{[]-0123456789tfn'):
                depth, k, quoted = 0, i, False
                while k < n:
                    ch = t[k]
                    if quoted:
                        if ch == "\\":
                            k += 1
                        elif ch == '"':
                            quoted = False
                    elif ch == '"':
                        quoted = True
                    elif ch in "{[":
                        depth += 1
                    elif ch in "}]":
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                if k >= n:
                    return i
                i = k
        i += 1
    return -1


def cut_off(text):
    """True when a model answer stops in the middle of its JSON (the token limit): no complete JSON before that."""
    return isinstance(text, str) and find_json(text) is None and _unclosed(text.strip()) >= 0
