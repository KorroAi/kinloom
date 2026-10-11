"""The same calls, answered by an online `kinloom serve`: for a Python game shipped to players, whose model key must
stay on the developer's server. The game code does not change:

    kl = Kinloom(url="https://your-host", token="<player token>", session=player_id)   # or KINLOOM_URL / KINLOOM_TOKEN

When the server cannot be reached, every call answers from a local offline copy (the game's lines, examples and
offline replies), like the engine clients. Minds run locally (they never need the server to decide).
"""
import collections
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import media as _media
from . import voice as _voice
from .shapes import Shape, clean_text

DOWN = 2.0              # seconds a server that did not answer is left alone (offline answers meanwhile)
MAX_DOWN = 10.0         # a server still not there is left alone longer each time: 2, 4, 8, then 10 s
UP = 5.0                # seconds a server that answered is trusted to be there (no connection check)
LOCAL = ("127.0.0.1", "localhost", "::1")


def _reach(url):
    """True when the server takes connections. A refused connection takes 2-4 s to be seen on Windows (measured:
    2.1 s for 127.0.0.1, 4.1 s for localhost): a short connect, 0.3 s on this machine, 1 s remote, sees it at once."""
    u = urllib.parse.urlsplit(url)
    host = u.hostname or "127.0.0.1"
    port = u.port or (443 if u.scheme == "https" else 80)
    try:
        socket.create_connection(("127.0.0.1" if host == "localhost" else host, port),
                                 0.3 if host in LOCAL else 1.0).close()
        return True
    except OSError:
        return False


def _wire(shapes):
    """{tool: (Shape, doc)} -> {tool: example args}: what the server needs to check the model's actions."""
    return {t: (shape.example if shape is not None else {}) for t, (shape, _doc) in (shapes or {}).items()}


class RemoteBrain:
    def __init__(self, url, token="", timeout=12.0):
        from .brain import Brain
        self.url = url.rstrip("/")
        self.token = token or ""
        self.timeout = timeout
        # offline answers, minds, the thread pools; the player's own system voice when the server has no audio
        self.local = Brain(provider=None, memory_path=None, voice=_voice.detect_voice(
            {"KINLOOM_VOICE": "off" if os.environ.get("KINLOOM_VOICE", "").lower() in ("off", "none", "0") else "system"}))
        self._fg, self._bg = self.local._fg, self.local._bg
        self.memory = self.local.memory
        self._down_until = 0.0
        self._up_until = 0.0
        self._failures = 0
        self._decisions = {}                                     # (session, name, choices) -> [value, at, busy]
        self._declared = {}                                      # (session, name) -> (declaration body, its future)
        self._lock = threading.Lock()
        self._journal = collections.deque(maxlen=200)
        self._waiting = {}                                       # (session, name) -> [_Action] decided in replies
        self._last_decided = {}                                  # (session, name) -> [_Action] of the last reply
        self.listeners = []

    # ---------------- transport ----------------

    def _down(self, unreachable):
        """Offline answers for a while: longer each time the server is still not there (a slow answer: 2 s)."""
        self._failures = self._failures + 1 if unreachable else 0
        wait = min(MAX_DOWN, DOWN * 2 ** max(0, self._failures - 1)) if unreachable else DOWN
        self._down_until = time.monotonic() + wait
        return wait

    def _request(self, session, verb, body, timeout, stream=None, items=None):
        if time.monotonic() < self._down_until:
            return None
        if time.monotonic() >= self._up_until and not _reach(self.url):
            wait = self._down(True)
            self._note("%s: server not reached: offline answers for %.0f s" % (verb, wait))
            return None
        # the session goes in the body (any text); the header only when it is plain ASCII (headers are Latin-1)
        session = str(session)
        headers = {"Content-Type": "application/json"}
        if session.isascii() and session.isprintable():
            headers["X-Kinloom-Session"] = session
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        data = dict(body, session=session)
        if stream is not None or items is not None:
            data["stream"] = True
        req = urllib.request.Request(self.url + "/v1/" + verb, data=json.dumps(data).encode("utf-8"), method="POST",
                                     headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                self._up_until, self._failures = time.monotonic() + UP, 0
                if (stream is None and items is None) or "json" in (r.headers.get("Content-Type") or ""):
                    return json.loads(r.read().decode("utf-8"))   # an older server answers a stream request whole
                done = None
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    ev = json.loads(line[5:].strip())
                    if ev.get("piece") and stream is not None:
                        try:
                            stream(ev["piece"])
                        except Exception:  # a game callback must never break the call
                            pass
                    if "item" in ev and items is not None:
                        items(ev["item"])
                    if ev.get("done"):
                        done = ev
                return done
        except urllib.error.HTTPError as e:
            self._note("%s: HTTP %s" % (verb, e.code))
            return None
        except (OSError, ValueError) as e:
            self._up_until = 0.0
            wait = self._down(False)
            self._note("%s: server not reached (%s): offline answers for %.0f s" % (verb, type(e).__name__, wait))
            return None

    def _note(self, text):
        entry = {"time": time.time(), "kind": "remote", "name": "kinloom", "text": text}
        self._journal.append(entry)
        for listener in list(self.listeners):
            try:
                listener(entry)
            except Exception:  # a listener must never break the game
                pass

    @property
    def online(self):
        """The server answered lately (it may still answer offline itself when it has no model)."""
        return time.monotonic() >= self._down_until

    # ---------------- declarations ----------------

    def character(self, session, name, personality="", lines=None, offline=None, events=None, tools=None, max_words=None,
                  every=8.0, language=None, group=None, soul=None, trust=None, invent=True, voice=None, max_chars=None,
                  warmth=None, secret_trust=None, warm_up=None):
        self.local.character(session, name, personality, lines, offline, events, tools, max_words, every, language, group,
                             soul, trust, invent, voice, max_chars, warmth, secret_trust, warm_up)
        c = self.local._characters.get((session, clean_text(str(name))))
        own = _wire(c.own_tools) if c else {}
        refs = list(c.tool_refs) if c else []
        wire_tools = (refs + ([own] if own else [])) if refs else own      # names of the game's tools travel as names
        body = {"name": name, "personality": personality, "lines": lines, "offline": offline, "events": events,
                "tools": wire_tools or None, "max_words": max_words, "every": every, "language": language, "group": group,
                "soul": soul, "trust": trust, "invent": invent, "voice": voice, "max_chars": max_chars,
                "warmth": warmth, "secret_trust": secret_trust, "warm_up": warm_up}
        body = {k: v for k, v in body.items() if v is not None}
        key = (session, clean_text(str(name)))
        with self._lock:
            self._declared[key] = (body, self._bg.submit(self._request, session, "character", body, 5.0))

    def _ready(self, session, name, r=None):
        """Waits for the character's declaration to reach the server; declares it again when the server says it does
        not know it (restarted meanwhile)."""
        key = (session, clean_text(str(name)))
        with self._lock:
            entry = self._declared.get(key)
        if entry is None:
            return
        body, future = entry
        if r is None:
            try:
                future.result(timeout=5.0)
            except Exception:  # not declared in time: the call goes on, the server flags it
                pass
        elif r.get("declared") is False:
            with self._lock:
                self._declared[key] = (body, self._bg.submit(self._request, session, "character", body, 5.0))

    def _ready_all(self, session):
        """prepare, save and inspect are about every character: they wait (5 s at most in all) for every declaration
        still on its way, as calls naming one character wait for theirs."""
        with self._lock:
            futures = [future for (s, _), (_, future) in self._declared.items() if s == session]
        until = time.monotonic() + 5.0
        for future in futures:
            try:
                future.result(timeout=max(0.0, until - time.monotonic()))
            except Exception:  # not declared in time: the call goes on
                pass

    def lore(self, session, lines=None):
        if lines is None:
            r = self._request(session, "lore", {}, 3.0)
            return r["lore"] if r and isinstance(r.get("lore"), list) else self.local.lore(session)
        self.local.lore(session, lines)
        r = self._request(session, "lore", {"lines": lines}, 3.0)
        return r["lines"] if r and "lines" in r else len(self.local.lore(session))

    # ---------------- the verbs ----------------

    def tools(self, session, tools=None):
        """The game's tools: kept here too (Python functions run here), sent to the server as examples."""
        if tools is None:
            return self.local.tools(session)
        names = self.local.tools(session, tools)
        shapes, _ = self.local._game_tools(session)
        self._bg.submit(self._request, session, "tools", {"tools": _wire(shapes)}, 5.0)
        return names

    def prepare(self, session, timeout=10.0):
        self._ready_all(session)
        r = self._request(session, "prepare", {"timeout": timeout}, (timeout or 0) + 5.0)
        if isinstance(r, dict) and "ready" in r:
            return {"ready": bool(r["ready"]), "waiting": r.get("waiting", 0), "online": bool(r.get("online"))}
        return dict(self.local.prepare(session, 0), online=False)

    def _picture(self, body, image):
        """The picture as a data URI in the request (a bad one is left out and told, like the local brain does)."""
        if image is None:
            return
        try:
            p = _media.picture(image)
        except ValueError as e:
            self._note("image: %s" % e)
            return
        if p is not None:
            body["image"] = p.uri

    def chat(self, session, name, message, facts=None, speaker="player", stream=None, timeout=None, max_chars=None,
             image=None, refused=None, drop=False):
        from .brain import Line, _Action, _TAKE, MAX_WAITING
        body = {"name": name, "message": message or "", "facts": facts or {}, "speaker": speaker, "do": True}
        if max_chars:
            body["max_chars"] = max_chars
        if refused is not None:
            body["refused"], body["drop"] = refused, bool(drop)
            with self._lock, _TAKE:          # what the refused reply decided is taken back here too
                for a in self._last_decided.pop((session, clean_text(str(name))), []):
                    a.taken = True
        self._picture(body, image)
        self._ready(session, name)
        r = self._request(session, "chat", body, timeout or self.timeout, stream=stream)
        if r is not None:
            self._ready(session, name, r)
        if r is None or not isinstance(r.get("text"), str):
            return self.local.chat(session, name, message, facts, speaker, stream, None, max_chars, drop=refused is not None)
        decided = [_Action(a["tool"], a["args"]) for a in (r.get("do") or [])
                   if isinstance(a, dict) and isinstance(a.get("tool"), str) and isinstance(a.get("args"), dict)]
        with self._lock, _TAKE:
            key = (session, clean_text(str(name)))
            self._last_decided[key] = list(decided)  # a refused reply takes back its own actions, never older ones
            if decided:   # the server hands them over once: they wait here for the reply's .do or act()
                waiting = [a for a in self._waiting.get(key, []) if not a.taken]
                self._waiting[key] = waiting[-MAX_WAITING:] + decided
        return Line(r["text"], r.get("source") if r.get("source") in ("model", "prepared", "offline") else "model", decided)

    def say(self, session, name, event, facts=None, fresh=False, max_chars=None):
        from .brain import Line
        self._ready(session, name)
        body = {"name": name, "event": event, "facts": facts or {}, "fresh": fresh}
        if max_chars:
            body["max_chars"] = max_chars
        r = self._request(session, "say", body, 2.0)
        if r is not None:
            self._ready(session, name, r)
        if r and isinstance(r.get("text"), str):
            return Line(r["text"], r.get("source") if r.get("source") in ("model", "prepared", "offline") else "prepared")
        return self.local.say(session, name, event, facts, fresh, max_chars)

    def decide(self, session, name, situation, choices, every=None):
        """Instant: the last decision from the server (the offline one first), refreshed in the background."""
        key = (session, name, json.dumps(choices, sort_keys=True, default=str))
        with self._lock:
            d = self._decisions.get(key)
            if d is None:
                d = self._decisions[key] = [self.local.decide(session, name, situation, choices, every), -1e9, False]
            due = not d[2] and time.monotonic() - d[1] >= 0.25
            if due:
                d[1], d[2] = time.monotonic(), True

        def refresh():
            r = self._request(session, "decide", {"name": name, "situation": situation or {}, "choices": choices,
                                                  "every": every}, 3.0)
            with self._lock:
                if r and isinstance(r.get("decision"), dict):
                    d[0] = r["decision"]
                d[2] = False
        if due:
            self._bg.submit(refresh)
        return d[0]

    def act(self, session, name, situation=None, think=True, check=None):
        self._ready(session, name)
        r = self._request(session, "act", {"name": name, "situation": situation, "think": think}, 3.0)
        if r is not None:
            self._ready(session, name, r)
        from .brain import _TAKE
        with self._lock, _TAKE:              # decided in replies nobody read: they come first, once
            waiting = self._waiting.pop((session, clean_text(str(name))), [])
            mine = [{"tool": a.tool, "args": a.args} for a in waiting if not a.taken]
            for a in waiting:
                a.taken = True
        if r is None:
            return self._run(session, name, mine, check) + self.local.act(session, name, situation, think, check)
        return self._run(session, name, mine + list(r.get("actions") or []), check)

    def _run(self, session, name, actions, check=None):
        """Runs the game's Python tool functions (the actions its check refuses are told to the character instead);
        returns the actions that went through."""
        from .brain import judged, refused_note
        c = self.local._characters.get((session, clean_text(str(name))))
        functions = dict(c.functions) if c is not None else {}
        done = []
        for a in actions:
            if not isinstance(a, dict) or not isinstance(a.get("tool"), str) or not isinstance(a.get("args"), dict):
                continue
            if check is not None:
                why, error = judged(check, a["tool"], dict(a["args"]))
                if error:
                    self._note("act: the game's check failed: " + error)
                if why:
                    self.remember(session, name, refused_note(a["tool"], a["args"], why), 0.6)
                    self._note("act: the game refused %s: %s" % (a["tool"], why))
                    continue
            fn = functions.get(a["tool"])
            if fn is not None:
                try:
                    fn(**a["args"])
                except Exception as e:  # a game function that fails is reported, like in the local brain
                    self._note("tool %s failed: %s" % (a["tool"], e))
                    continue
            done.append((a["tool"], a["args"]))
        return done

    def soul(self, session, name, speaker=None):
        self._ready(session, name)
        r = self._request(session, "soul", {"name": name, "speaker": speaker}, 3.0)
        return r if isinstance(r, dict) and "mood" in r else self.local.soul(session, name, speaker)

    def create(self, session, what, example, context=None, count=None, instant=False, timeout=None, image=None,
               check=None, offline=None, refused=None, retry=True, each=None):
        """The server's model; the game's check runs here (a list item by item, as the server streams it to each()),
        and a refused answer goes back with its reason once."""
        if count and isinstance(example, list) and len(example) == 1:
            example = example[0]
        listed = bool(count) or Shape.of(example).kind == "list"
        item_example = example if count else (example[0] if listed and example else example)
        fallback_item = (lambda: self.local.create(session, what, item_example, offline=offline)) if count else None
        body = {"what": what, "example": example, "context": context, "count": count, "instant": instant,
                "offline": offline, "refused": refused}
        body = {k: v for k, v in body.items() if v is not None}
        self._picture(body, image)
        streamed = []

        def item(x):
            if check is not None and self.local._why(check, x, what, quiet=True):
                return                               # refused: left out (count fills with the offline answer at the end)
            if not count or len(streamed) < count:
                streamed.append(x)
                self.local._give(each, x, what)
        r = self._request(session, "create", body, timeout or self.timeout, items=item if each is not None and listed else None)
        if not (r and "value" in r):
            if streamed:
                return streamed
            return self.local.create(session, what, example, context, count, instant, check=check, offline=offline, each=each)
        value = r["value"]
        if streamed:
            fills = [fallback_item() for _ in range(count - len(streamed))] if count else []
            for x in fills:
                self.local._give(each, x, what)
            return streamed + fills
        if check is not None and r.get("source") != "offline":
            if listed and isinstance(value, list):
                if count:
                    value = [x for x in value if not self.local._why(check, x, what, quiet=True)]
                    value += [fallback_item() for _ in range(count - len(value))]
                else:
                    value = [x for x in value if not self.local._why(check, x, what, quiet=True)] or \
                        self.local.create(session, what, example, offline=offline)
            elif instant:
                if self.local._why(check, value, what, quiet=True):
                    value = self.local.create(session, what, example, offline=offline)
            else:
                why = self.local._why(check, value, what, quiet=True)
                if why and retry:
                    return self.create(session, what, example, context, None, False, timeout, image, check, offline,
                                       {"answer": value, "why": why}, retry=False, each=each)
                if why:
                    value = self.local.create(session, what, example, offline=offline)
        if each is not None:
            for x in (value if listed and isinstance(value, list) else [value]):
                self.local._give(each, x, what)
        return value

    def remark(self, session, about, who=None, facts=None, offline=None, max_chars=None):
        from .brain import Line
        body = {"about": about, "who": who, "facts": facts or {}, "offline": offline, "max_chars": max_chars}
        r = self._request(session, "remark", {k: v for k, v in body.items() if v is not None}, self.timeout)
        if r and isinstance(r.get("text"), str):
            return Line(r["text"], r.get("source") if r.get("source") in ("model", "offline") else "model")
        return self.local.remark(session, about, who, facts, offline, max_chars)

    def speak(self, session, name, text, timeout=None):
        """The server's voice (its key); the player's system voice when it has none or cannot be reached."""
        if name is not None:
            self._ready(session, name)
        r = self._request(session, "speak", {"name": name, "text": text}, timeout or max(self.timeout, 15.0))
        data = _voice.audio_bytes(r.get("audio")) if isinstance(r, dict) and r.get("audio") else None
        if not data or _voice.audio_format(data) != "wav":
            return self.local.speak(session, name, text, timeout)
        path = self.local._audio_path(_voice.hashlib.sha1(data).hexdigest()[:16])
        with open(path, "wb") as f:
            f.write(data)
        return _voice.Audio(data, path, str(r.get("text") or text), str(name or "narrator"))

    def listen(self, session, audio, language=None, timeout=None):
        data = _voice.audio_bytes(audio)
        if not data:
            return ""
        body = {"audio": _voice.base64.b64encode(data).decode("ascii"), "language": language}
        r = self._request(session, "listen", {k: v for k, v in body.items() if v is not None}, timeout or max(self.timeout, 20.0))
        if isinstance(r, dict) and isinstance(r.get("text"), str) and r["text"]:
            return r["text"]
        return self.local.listen(session, data, language, timeout)

    def event(self, session, text, about=None, importance=0.5, by=None, seen_by=None, tag=None, impact=None):
        body = {"text": text, "about": about, "importance": importance, "by": by, "seen_by": seen_by, "tag": tag,
                "impact": impact}
        self._bg.submit(self._request, session, "event", {k: v for k, v in body.items() if v is not None}, 5.0)

    def remember(self, session, name, note, importance=0.6):
        self._bg.submit(self._request, session, "remember", {"name": name, "note": note, "importance": importance}, 5.0)

    def set_state(self, session, state):
        self.local.set_state(session, state)
        self._bg.submit(self._request, session, "state", {"state": state}, 5.0)

    def _value(self, session, verb, body, key, default):
        r = self._request(session, verb, body, 3.0)
        return r[key] if r and key in r else default

    def opinion(self, session, a, b):
        return self._value(session, "opinion", {"a": a, "b": b}, "opinion", 0.0)

    def opinions(self, session, a):
        return self._value(session, "opinions", {"name": a}, "opinions", {})

    def feel(self, session, a, b, change):
        return self._value(session, "feel", {"a": a, "b": b, "change": change}, "opinion", 0.0)

    def reputation(self, session, target, group):
        return self._value(session, "reputation", {"target": target, "group": group}, "reputation", 0.0)

    def meet(self, session, a, b, k=3):
        return self._value(session, "meet", {"a": a, "b": b, "k": k}, "shared", [])

    def spread(self, session, group=None, rounds=1):
        return self._value(session, "spread", {"group": group, "rounds": rounds}, "shared", [])

    def knows(self, session, name, tag):
        return bool(self._value(session, "knows", {"name": name, "tag": tag}, "knows", False))

    def knowledge(self, session, name, tag=None):
        return self._value(session, "knows", {"name": name, "tag": tag or ""}, "notes", [])

    # ---------------- v1 ----------------

    def suggest(self, session, name, examples, speaker="player", facts=None):
        given = self.local.suggest(session, name, examples, speaker, facts)     # checks them; the offline answer
        r = self._request(session, "suggest", {"name": name, "examples": examples, "speaker": speaker, "facts": facts or {}},
                          self.timeout)
        replies = r.get("replies") if isinstance(r, dict) else None
        return replies if isinstance(replies, list) and len(replies) == len(given) else given

    def steer(self, session, name, text):
        self.local.steer(session, name, text)          # offline, the local brain uses it up the same way
        self._ready(session, name)
        self._request(session, "steer", {"name": name, "text": text}, 3.0)

    def converse(self, session, a, b, about="", turns=4):
        r = self._request(session, "converse", {"a": a, "b": b, "about": about, "turns": turns}, self.timeout)
        return r["lines"] if isinstance(r, dict) and isinstance(r.get("lines"), list) else []

    def inspect(self, session):
        self._ready_all(session)
        r = self._request(session, "inspect", {}, 3.0)
        return r if isinstance(r, dict) and "characters" in r else self.local.inspect(session)

    def save_state(self, session):
        self._ready_all(session)
        r = self._request(session, "save", {}, 5.0)
        return r["data"] if isinstance(r, dict) and isinstance(r.get("data"), str) else self.local.save_state(session)

    def load_state(self, session, text):
        self.local.load_state(session, text)                                    # checks it; kept for offline answers
        self._request(session, "load", {"data": text}, 10.0)
        return True

    # ---------------- local: minds, stats ----------------

    def mind(self, *a, **k):
        return self.local.mind(*a, **k)

    def think(self, *a, **k):
        return self.local.think(*a, **k)

    def reward(self, *a, **k):
        return self.local.reward(*a, **k)

    def explain(self, *a, **k):
        return self.local.explain(*a, **k)

    def mind_report(self, *a, **k):
        return self.local.mind_report(*a, **k)

    def stats(self):
        return self.local.stats()

    def status(self):
        return {"mode": "remote", "url": self.url, "down": time.monotonic() < self._down_until}

    def journal(self, n=100):
        return list(self._journal)[-n:]

    def wait_idle(self, timeout=10.0):
        return self.local.wait_idle(timeout)

    def close(self):
        self.local.close()
