"""Minds: utility AI that a model (or a person, or a coding agent) writes as readable rules, and the game runs locally.

    senses  = {"hp": (0.0, 1.0), "enemy_dist": (0, 40), "has_ammo": True, "enemy": ["idle", "alert", "fleeing"]}
    actions = {"charge": {"speed": (1.0, 3.0)}, "shoot": {"burst": (1, 5)}, "retreat": {}}
    rules   = {"retreat": ["hp low"], "shoot": ["has_ammo", "enemy_dist below 20"],
               "charge": {"score": 0.4, "args": {"speed": "enemy_dist high"}}}

Each action scores `score × (product of its rule values) ^ (1 / number of rules)`; the best score wins; ties go to the
declared order; a unit's current action gets `× (1 + STICK)` so it does not dither. Rules:

    hp low / hp high                 the sense, scaled over its range (low = 1 - high)
    d below 12 / d above 5           a smooth step at the threshold (d < 12, d >= 5 also work)
    d around 10                      a bell centered on 10
    has_ammo / not has_ammo          a flag (1 or 0)
    enemy is fleeing                 an option (1 or 0)

A sense that is missing or of the wrong type counts 0.5 (neutral): a game never crashes a mind.
Everything here is pure and deterministic: no model, no clock, no I/O.
"""
import math
import random
import re

from .shapes import Shape

STICK = 0.1
MAX_RULES = 6
MAX_SENSES = 64
MAX_ACTIONS = 32
MAX_VARIANTS = 8
MAX_SCORE = 3.0
MAX_UNITS = 10000
STEP = 0.05          # width of a below/above step, as a share of the sense range
BELL = 0.15          # width of an around bell, as a share of the sense range

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,47}$")
_RULE = re.compile(r"^\s*(?:(not)\s+|(!)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:(high|low|above|below|around|is|>=|<=|==|>|<|~|=)\s*(.*?))?\s*$",
                   re.I)
_WORDS = {">": "above", ">=": "above", "<": "below", "<=": "below", "~": "around", "=": "is", "==": "is"}


def fnv1a(text):
    """FNV-1a 32-bit over UTF-8: which variant a unit gets, identical in every client."""
    h = 0x811C9DC5
    for b in str(text).encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


def _num(x):
    return "%d" % x if float(x).is_integer() else ("%.3f" % x).rstrip("0").rstrip(".")


def _finite(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


# ---------------- senses and actions ----------------

def senses_of(example):
    """{"hp": (0, 1), "armed": True, "mood": ["calm", "angry"]} -> {name: ("range", lo, hi) | ("flag",) | ("options", [...])}."""
    if not isinstance(example, dict) or not example:
        raise ValueError("senses: give an object like {\"hp\": [0, 1], \"armed\": true, \"mood\": [\"calm\", \"angry\"]}")
    out = {}
    for name, ex in list(example.items())[:MAX_SENSES]:
        name = str(name)
        if not _NAME.match(name):
            raise ValueError("sense %r: use letters, digits and _ only" % name)
        if isinstance(ex, bool):
            out[name] = ("flag",)
        elif isinstance(ex, (list, tuple)) and len(ex) == 2 and all(_finite(x) is not None for x in ex):
            lo, hi = sorted(float(x) for x in ex)
            if hi - lo <= 0:
                raise ValueError("sense %r: the range needs two different numbers" % name)
            out[name] = ("range", lo, hi)
        elif isinstance(ex, (list, tuple)) and len(ex) >= 2 and all(isinstance(x, str) for x in ex):
            out[name] = ("options", [str(x)[:48] for x in ex][:32])
        else:
            raise ValueError("sense %r: give a range [lo, hi], true/false, or a list of options" % name)
    return out


def actions_of(example):
    """{"charge": {"speed": (1, 3)}, "wait": {}} -> {name: {arg: Shape}} (declared order kept)."""
    if isinstance(example, (list, tuple)):
        example = {str(a): {} for a in example}
    if not isinstance(example, dict) or not example:
        raise ValueError("actions: give an object like {\"attack\": {\"power\": [0, 1]}, \"wait\": {}}")
    out = {}
    for name, args in list(example.items())[:MAX_ACTIONS]:
        name = str(name)
        if not _NAME.match(name):
            raise ValueError("action %r: use letters, digits and _ only" % name)
        if args in (None, {}, True):
            out[name] = {}
        elif isinstance(args, dict):
            out[name] = {str(k): Shape.of(v) for k, v in args.items()}
        else:
            raise ValueError("action %r: give its arguments as an object of examples, or {}" % name)
    return out


class Declaration:
    def __init__(self, name, personality="", senses=None, actions=None, rules=None, variants=3):
        self.name = str(name)[:48]
        self.personality = str(personality or "")[:600]
        self.senses_example = senses
        self.actions_example = actions
        self.senses = senses_of(senses)
        self.actions = actions_of(actions)
        self.order = list(self.actions)
        self.variants = max(1, min(MAX_VARIANTS, int(variants or 1)))
        self.rules = rules
        base, self.rule_errors = validate(rules, self) if rules else (None, [])
        # No rules at all: every action scores 1 and the first one wins (the game's declared order is its preference).
        self.offline = base or {a: {"score": 1.0, "when": [], "args": {}} for a in self.order}


# ---------------- rules ----------------

def parse_rule(text, senses):
    """(compiled rule, None) or (None, reason). Compiled: [sense, op, p1, p2]."""
    if not isinstance(text, str) or len(text) > 120:
        return None, "a rule is short text like \"hp low\""
    m = _RULE.match(text)
    if not m:
        return None, "cannot read rule %r (examples: \"hp low\", \"dist below 12\", \"armed\", \"mood is angry\")" % text
    neg, sense, op, arg = m.group(1) or m.group(2), m.group(3), (m.group(4) or "").lower(), (m.group(5) or "").strip()
    real = next((s for s in senses if s.lower() == sense.lower()), None)
    if real is None:
        return None, "rule %r: unknown sense %r (senses: %s)" % (text, sense, ", ".join(senses))
    kind = senses[real]
    op = _WORDS.get(op, op)
    if kind[0] == "flag":
        if op or arg:
            return None, "rule %r: %s is true/false: write \"%s\" or \"not %s\"" % (text, real, real, real)
        return [real, "not" if neg else "flag", 0, 0], None
    if neg:
        return None, "rule %r: \"not\" only goes with a true/false sense" % text
    if kind[0] == "options":
        if op != "is":
            return None, "rule %r: %s is one of %s: write \"%s is <option>\"" % (text, real, ", ".join(kind[1]), real)
        opt = next((o for o in kind[1] if o.lower() == arg.lower()), None)
        if opt is None:
            return None, "rule %r: %s is one of %s" % (text, real, ", ".join(kind[1]))
        return [real, "is", opt, 0], None
    lo, hi = kind[1], kind[2]
    if op in ("high", "low"):
        if arg:
            return None, "rule %r: \"%s %s\" takes no number" % (text, real, op)
        return [real, op, lo, hi], None
    if op in ("above", "below", "around"):
        try:
            t = float(arg)
        except ValueError:
            return None, "rule %r: \"%s %s\" needs a number from %s to %s" % (text, real, op, _num(lo), _num(hi))
        if not math.isfinite(t):
            return None, "rule %r: the number must be finite" % text
        t = min(max(t, lo), hi)
        t = float(_num(t))
        return [real, op, t, (hi - lo) * (BELL if op == "around" else STEP)], None
    return None, "rule %r: %s is a number: use low, high, below N, above N or around N" % (text, real)


def rule_text(rule):
    sense, op, p1 = rule[0], rule[1], rule[2]
    if op in ("high", "low"):
        return "%s %s" % (sense, op)
    if op in ("above", "below", "around"):
        return "%s %s %s" % (sense, op, _num(p1))
    if op == "flag":
        return sense
    if op == "not":
        return "not " + sense
    return "%s is %s" % (sense, p1)


def rule_value(rule, senses):
    """0..1. Missing or wrong-typed senses are neutral (0.5)."""
    sense, op, p1, p2 = rule[0], rule[1], rule[2], rule[3]
    v = senses.get(sense) if isinstance(senses, dict) else None
    if op in ("flag", "not"):
        if isinstance(v, bool):
            on = v
        elif _finite(v) is not None:
            on = v != 0
        else:
            return 0.5
        return 1.0 if on == (op == "flag") else 0.0
    if op == "is":
        if not isinstance(v, str):
            return 0.5
        return 1.0 if v == p1 else 0.0
    x = _finite(v)
    if x is None:
        return 0.5
    if op in ("high", "low"):
        y = min(max((x - p1) / (p2 - p1), 0.0), 1.0)
        return y if op == "high" else 1.0 - y
    if op == "around":
        z = (x - p1) / p2
        return math.exp(-z * z)
    z = max(-60.0, min(60.0, (x - p1) / p2))
    up = 1.0 / (1.0 + math.exp(-z))
    return up if op == "above" else 1.0 - up


# ---------------- programs ----------------

def validate(program, decl):
    """A model's (or a person's) program -> (clean program with every declared action, errors) or (None, errors).
    An action with any broken rule or argument is dropped whole (score 0): a bad rule never widens an action."""
    errors = []
    if not isinstance(program, dict) or not program:
        return None, ["a mind is an object: {action: {\"score\": 1, \"when\": [rules], \"args\": {...}}}"]
    out = {a: {"score": 0.0, "when": [], "args": {}} for a in decl.order}
    given = 0
    for name, spec in list(program.items())[:MAX_ACTIONS * 2]:
        action = next((a for a in decl.order if a.lower() == str(name).lower()), None)
        if action is None:
            errors.append("unknown action %r (actions: %s)" % (name, ", ".join(decl.order)))
            continue
        if isinstance(spec, (list, tuple, str)):
            spec = {"when": spec}
        if not isinstance(spec, dict):
            errors.append("%s: give {\"score\", \"when\", \"args\"}" % action)
            continue
        score = _finite(spec.get("score", 1.0))
        if score is None:
            errors.append("%s: score must be a number from 0 to 3" % action)
            continue
        when = spec.get("when", [])
        when = [when] if isinstance(when, str) else when
        if not isinstance(when, (list, tuple)):
            errors.append("%s: when must be a list of rules" % action)
            continue
        rules, broken = [], False
        for text in when:
            rule, error = parse_rule(text, decl.senses)
            if error:
                errors.append("%s: %s" % (action, error))
                broken = True
                break
            t = rule_text(rule)
            if t not in rules:
                rules.append(t)
        args, bad = _args(spec.get("args"), decl.actions[action], decl.senses, action, errors)
        if broken or bad:
            continue
        out[action] = {"score": round(min(max(score, 0.0), MAX_SCORE), 3), "when": rules[:MAX_RULES], "args": args}
        given += 1
    return (out if given else None), errors


def _args(given, shapes, senses, action, errors):
    if given in (None, {}):
        return {}, False
    if not isinstance(given, dict):
        errors.append("%s: args must be an object" % action)
        return {}, True
    out = {}
    for name, value in given.items():
        shape = shapes.get(str(name))
        if shape is None:
            continue  # extras are dropped, as everywhere in Kinloom
        if isinstance(value, str) and shape.kind == "range":
            rule, error = parse_rule(value, senses)
            if error:
                errors.append("%s.%s: %s" % (action, name, error))
                return {}, True
            out[str(name)] = rule_text(rule)
            continue
        ok, v, error = shape.check(value, "%s.%s" % (action, name))
        if not ok:
            errors.append(error)
            return {}, True
        out[str(name)] = v
    return out, False


def compile_program(program, decl):
    """The form clients run: numbers and strings only, every argument filled."""
    out = {}
    for action in decl.order:
        spec = program.get(action) or {"score": 0.0, "when": [], "args": {}}
        rules = [parse_rule(t, decl.senses)[0] for t in spec.get("when", [])]
        args = {}
        for name, shape in decl.actions[action].items():
            v = spec.get("args", {}).get(name)
            if isinstance(v, str) and shape.kind == "range":
                r = parse_rule(v, decl.senses)[0]
                args[name] = r + [shape.info["lo"], shape.info["hi"], bool(shape.info["whole"])]
            elif v is None:
                args[name] = shape.default()
            else:
                args[name] = v
        out[action] = {"score": float(spec.get("score", 0.0)), "when": [r for r in rules if r], "args": args}
    return out


def score_action(spec, senses):
    rules = spec["when"]
    if not rules:
        return spec["score"]
    product = 1.0
    for r in rules:
        product *= rule_value(r, senses)
    return spec["score"] * (product ** (1.0 / len(rules)) if product > 0 else 0.0)


_RULE_OPS = ("high", "low", "above", "below", "around", "is", "flag", "not")


def is_mapped(v):
    """An argument the senses set: [sense, op, p1, p2, lo, hi, whole]. Any other list is the argument itself."""
    return (isinstance(v, list) and len(v) == 7 and isinstance(v[0], str) and v[1] in _RULE_OPS
            and isinstance(v[6], bool))


def run_compiled(compiled, senses, who, units):
    """One decision from the compiled form. units: {who: last action} (hysteresis), bounded by the caller."""
    variants = compiled["variants"]
    index = fnv1a("" if who is None else who) % len(variants) if len(variants) > 1 else 0
    program = variants[index]
    last = units.get(who) if who is not None else None
    best, best_score = None, -1.0
    for action in compiled["order"]:
        s = score_action(program[action], senses if isinstance(senses, dict) else {})
        if action == last:
            s *= 1.0 + compiled["stick"]
        if s > best_score + 1e-12:
            best, best_score = action, s
    args = {}
    for name, v in program[best]["args"].items():
        if is_mapped(v):
            y = rule_value(v[:4], senses if isinstance(senses, dict) else {})
            x = v[4] + y * (v[5] - v[4])
            args[name] = int(math.floor(x + 0.5)) if v[6] else x
        else:
            args[name] = v
    if who is not None:
        if len(units) >= MAX_UNITS and who not in units:
            units.clear()
        units[who] = best
    return {"action": best, "args": args, "variant": index}


class Mind:
    """A declaration plus its current variants (programs). Pure: learning and models live in the brain."""

    def __init__(self, decl, variants=None):
        self.decl = decl
        progs = [p for p in (variants or []) if isinstance(p, dict)]
        self.variants = (progs or [decl.offline] * decl.variants)[:MAX_VARIANTS]
        self.version = 1
        self._units = {}
        self._compiled = None

    def set_variant(self, index, program):
        self.variants[index] = program
        self.version += 1
        self._compiled = None

    def set_variants(self, programs):
        self.variants = list(programs)[:MAX_VARIANTS]
        self.version += 1
        self._compiled = None

    def compiled(self):
        if self._compiled is None:
            self._compiled = {"name": self.decl.name, "version": self.version, "order": list(self.decl.order), "stick": STICK,
                              "variants": [compile_program(p, self.decl) for p in self.variants]}
        return self._compiled

    def think(self, senses, who=None):
        return run_compiled(self.compiled(), senses, who, self._units)

    def explain(self, senses, who=None):
        c = self.compiled()
        index = fnv1a("" if who is None else who) % len(c["variants"]) if len(c["variants"]) > 1 else 0
        prog = self.variants[index]
        senses = senses if isinstance(senses, dict) else {}
        scores = {}
        for action in self.decl.order:
            spec = c["variants"][index][action]
            scores[action] = {"score": round(score_action(spec, senses), 4), "rules": list(prog.get(action, {}).get("when", [])),
                              "values": [round(rule_value(r, senses), 4) for r in spec["when"]]}
        best = max(self.decl.order, key=lambda a: (scores[a]["score"], -self.decl.order.index(a)))
        return {"action": best, "variant": index, "scores": scores}


# ---------------- mutation (learning without a model) ----------------

def _random_rule(decl, rnd):
    sense = rnd.choice(list(decl.senses))
    kind = decl.senses[sense]
    if kind[0] == "flag":
        return sense if rnd.random() < 0.5 else "not " + sense
    if kind[0] == "options":
        return "%s is %s" % (sense, rnd.choice(kind[1]))
    op = rnd.choice(["high", "low", "above", "below", "around"])
    if op in ("high", "low"):
        return "%s %s" % (sense, op)
    return "%s %s %s" % (sense, op, _num(round(rnd.uniform(kind[1], kind[2]), 3)))


def mutate(program, decl, rnd=None):
    """A small random change (score, threshold, direction, a rule added or dropped, an argument). Always valid."""
    rnd = rnd or random.Random()
    for _ in range(12):
        child = {a: {"score": s["score"], "when": list(s["when"]), "args": dict(s["args"])} for a, s in program.items()}
        action = rnd.choice(decl.order)
        spec = child.setdefault(action, {"score": 0.0, "when": [], "args": {}})
        move = rnd.random()
        if move < 0.25:
            spec["score"] = round(min(MAX_SCORE, max(0.0, spec["score"] * rnd.uniform(0.6, 1.5) if spec["score"] > 0.05
                                                     else rnd.uniform(0.2, 1.0))), 3)
        elif move < 0.45 and spec["when"]:
            i = rnd.randrange(len(spec["when"]))
            rule = parse_rule(spec["when"][i], decl.senses)[0]
            if rule[1] in ("above", "below", "around"):
                lo, hi = decl.senses[rule[0]][1], decl.senses[rule[0]][2]
                rule[2] = min(hi, max(lo, rule[2] + rnd.choice((-1, 1)) * rnd.uniform(0.05, 0.25) * (hi - lo)))
                rule[2] = round(rule[2], 3)
            else:
                rule[1] = {"high": "low", "low": "high", "flag": "not", "not": "flag"}.get(rule[1], rule[1])
                if rule[1] == "is":
                    rule[2] = rnd.choice(decl.senses[rule[0]][1])
            spec["when"][i] = rule_text(rule)
        elif move < 0.55 and spec["when"]:
            i = rnd.randrange(len(spec["when"]))
            rule = parse_rule(spec["when"][i], decl.senses)[0]
            rule[1] = {"above": "below", "below": "above", "high": "low", "low": "high", "flag": "not", "not": "flag"}.get(rule[1], rule[1])
            spec["when"][i] = rule_text(rule)
        elif move < 0.68 and spec["when"]:
            spec["when"].pop(rnd.randrange(len(spec["when"])))
        elif move < 0.88 and len(spec["when"]) < MAX_RULES:
            spec["when"].append(_random_rule(decl, rnd))
            if spec["score"] <= 0.05:
                spec["score"] = round(rnd.uniform(0.3, 1.2), 3)
        elif decl.actions[action]:
            name = rnd.choice(list(decl.actions[action]))
            shape = decl.actions[action][name]
            if shape.kind == "range" and rnd.random() < 0.5:
                spec["args"][name] = rnd.choice([r for r in (_random_rule(decl, rnd) for _ in range(8))
                                                 if decl.senses[r.replace("not ", "").split()[0]][0] == "range"] or [None])
                if spec["args"][name] is None:
                    del spec["args"][name]
            elif shape.kind == "range":
                v = rnd.uniform(shape.info["lo"], shape.info["hi"])
                spec["args"][name] = int(math.floor(v + 0.5)) if shape.info["whole"] else round(v, 3)
            elif shape.kind == "options":
                spec["args"][name] = rnd.choice(shape.info["options"])
            elif shape.kind == "boolean":
                spec["args"][name] = not bool(spec["args"].get(name, shape.default()))
            else:
                continue
        else:
            continue
        clean, _ = validate(child, decl)
        if clean is not None and clean != program:
            return clean
    return program


# ---------------- credit: what the data says (learning from rewards, with or without a model) ----------------

def _conditions(decl, samples):
    """Candidate rules from the data: thresholds at the quantiles of what units sensed, flags, options."""
    out = []
    for name, kind in decl.senses.items():
        if kind[0] == "flag":
            out += [name, "not " + name]
        elif kind[0] == "options":
            out += ["%s is %s" % (name, o) for o in kind[1]]
        else:
            values = sorted(v for v in (_finite(s.get(name)) for s, _, _ in samples) if v is not None)
            if len(values) < 20:
                continue
            for q in (0.2, 0.4, 0.6, 0.8):
                t = _num(round(values[int(q * (len(values) - 1))], 3))
                out += ["%s above %s" % (name, t), "%s below %s" % (name, t)]
    return list(dict.fromkeys(out))


def _grid(decl):
    """Rules across each number sense's whole declared range, including places units have not been yet."""
    out = []
    for name, kind in decl.senses.items():
        if kind[0] == "range":
            for q in (0.1, 0.25, 0.5, 0.75, 0.9):
                t = _num(round(kind[1] + q * (kind[2] - kind[1]), 3))
                out += ["%s above %s" % (name, t), "%s below %s" % (name, t)]
        elif kind[0] == "flag":
            out += [name, "not " + name]
        else:
            out += ["%s is %s" % (name, o) for o in kind[1]]
    return out


def evidence(decl, samples, min_n=12, top=8):
    """Where an action did better or worse than the others, from (senses, action, return) samples:
    [(z, action, rule, advantage, n)], strongest first. z: the advantage in standard errors."""
    if len(samples) < 40:
        return []
    returns = [g for _, _, g in samples]
    mean = sum(returns) / len(returns)
    std = math.sqrt(sum((g - mean) ** 2 for g in returns) / len(returns)) or 1e-9
    found = []
    for text in _conditions(decl, samples):
        rule = parse_rule(text, decl.senses)[0]
        if rule is None:
            continue
        inside = [(a, g) for s, a, g in samples if rule_value(rule, s) > 0.5]
        if len(inside) < 2 * min_n:
            continue
        base = sum(g for _, g in inside) / len(inside)
        by_action = {}
        for a, g in inside:
            acc = by_action.setdefault(a, [0, 0.0])
            acc[0] += 1
            acc[1] += g
        for a, (n, total) in by_action.items():
            if n >= min_n and a in decl.actions:
                adv = total / n - base
                found.append((adv * math.sqrt(n) / std, a, text, adv, n))
    found.sort(key=lambda x: -abs(x[0]))
    return found[:top]


def _negate(text, decl):
    rule = parse_rule(text, decl.senses)[0]
    flip = {"above": "below", "below": "above", "flag": "not", "not": "flag", "high": "low", "low": "high"}.get(rule[1])
    if flip is None:
        return None
    rule[1] = flip
    return rule_text(rule)


def propose(program, decl, samples, rnd=None, min_z=2.0):
    """A change the data supports: make an action win where it did clearly better than the others, or keep it
    away from where it did clearly worse. None when the data shows nothing significant."""
    rnd = rnd or random.Random()
    tried = {}
    for _, a, _ in samples:
        tried[a] = tried.get(a, 0) + 1
    untried = [a for a in decl.order if tried.get(a, 0) < 12]
    if untried and len(samples) >= 40 and rnd.random() < 0.5:
        # No data can recommend an action nobody plays: try one where the data says units often are.
        conditions = _conditions(decl, samples) + _grid(decl)
        return _prefer(program, decl, rnd.choice(untried), rnd.choice(conditions), rnd)
    # Useful changes only: make an action win where it did better, or keep an action that plays away from where it did
    # worse (restricting an action that never plays changes nothing).
    found = [e for e in evidence(decl, samples, top=16) if abs(e[0]) >= min_z and
             (e[3] > 0 or program.get(e[1], {}).get("score", 0) > 0.05)]
    if not found:
        return None
    better = [e for e in found if e[3] > 0]      # making the better action win beats only restricting the worse one
    z, action, text, adv, n = rnd.choice((better or found)[:4])
    if adv < 0:
        text = _negate(text, decl)
        if text is None:
            return None
    if adv > 0:
        return _prefer(program, decl, action, text, rnd)
    child = {a: {"score": s["score"], "when": list(s["when"]), "args": dict(s["args"])} for a, s in program.items()}
    spec = child.setdefault(action, {"score": 0.0, "when": [], "args": {}})
    sense = text.replace("not ", "").split()[0]
    spec["when"] = [r for r in spec["when"] if r.replace("not ", "").split()[0] != sense][-(MAX_RULES - 1):] + [text]
    clean, _ = validate(child, decl)
    return clean if clean is not None and clean != program else None


def _prefer(program, decl, action, text, rnd):
    """The action gets the rule (replacing its rule on the same sense) and a score that lets it win there."""
    child = {a: {"score": s["score"], "when": list(s["when"]), "args": dict(s["args"])} for a, s in program.items()}
    spec = child.setdefault(action, {"score": 0.0, "when": [], "args": {}})
    sense = text.replace("not ", "").split()[0]
    spec["when"] = [r for r in spec["when"] if r.replace("not ", "").split()[0] != sense][-(MAX_RULES - 1):] + [text]
    top = max((s["score"] for a, s in child.items() if a != action), default=1.0)
    spec["score"] = round(min(MAX_SCORE, max(spec["score"], top, 1.0) * rnd.uniform(1.05, 1.4)), 3)
    clean, _ = validate(child, decl)
    return clean if clean is not None and clean != program else None
