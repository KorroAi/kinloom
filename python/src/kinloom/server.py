"""`kinloom serve`: the HTTP API any engine speaks, plus the live dashboard.

    POST /v1/character  {name, personality, lines?, offline?, events?, tools?, max_words?, max_chars?, every?, language?,
                        group?, soul?, trust?, invent?, voice?}
    POST /v1/tools      {tools: {name: example args}} -> {tools: [names]}   (the game's tools; characters name them:
                        "tools": ["open_door"] or "all"; POST {} reads them)
    POST /v1/prepare    {timeout?} -> {ready, waiting, online}           (a loading screen: what is written ahead is ready)
    POST /v1/say        {name, event, facts?, fresh?, max_chars?}      -> {text, source, declared}
    POST /v1/chat       {name, message, facts?, speaker?, stream?, do?, max_chars?, image?} -> {text, source, declared, mood, feeling, gesture,
                        do?}  (stream: server-sent events; message "": the speaker came up to the character, who speaks
                        first; do: true -> the actions decided in this reply come back here, [{tool, args}], and
                        /v1/act does not return them again)
                        source: "model" (written now), "prepared" (written earlier by the model) or "offline";
                        image: a picture (base64 or a data URI: PNG, JPEG, GIF, WebP) the model looks at
    POST /v1/lore       {lines: [...] or text} -> {lines: n kept}   (POST {} -> {lore: [...]})
    POST /v1/soul       {name, speaker?} (or GET /v1/soul?name=&speaker=) -> {card, ready, mood, bonds, memories, tools,
                        conversation (with speaker)}
    POST /v1/decide     {name, situation, choices, every?}             -> {decision, declared}
    POST /v1/act        {name, situation?, think?}                             -> {actions: [{tool, args}], declared}
    POST /v1/create     {what, example, context?, count?, instant?, image?} -> {value}
    POST /v1/event      {text, about?, importance?, by?, seen_by?, tag?, impact?}
    POST /v1/mind       {name, personality?, senses, actions, rules?, variants?, learn?} -> {mind}  (compiled: clients run it)
    POST /v1/think      {name, senses, who?}                            -> {action, args, variant}
    POST /v1/reward     {rewards: [{who, mind, variant, id, action?, reward, senses?, done?}]} -> {versions: {mind: version}}
    POST /v1/explain    {name, senses, who?}                            -> {action, variant, scores}
    GET  /v1/mind?name= -> {mind, report}   (or POST /v1/report {name}; {missing: true} when unknown)
    POST /v1/meet       {a, b, k?} -> {shared}     POST /v1/spread {group?, rounds?} -> {shared}
    POST /v1/knows      {name, tag} -> {knows, notes}
    POST /v1/opinion    {a, b} -> {opinion}         POST /v1/opinions {name} -> {opinions}
    POST /v1/feel       {a, b, change} -> {opinion} POST /v1/reputation {target, group} -> {reputation}
    POST /v1/remember   {name, note, importance?}
    POST /v1/state      {state}
    GET  /v1/status · GET /v1/journal · GET /v1/stream (server-sent events) · GET / (dashboard) · GET /talk (talk to characters)
    GET  /v1/openapi.json (this API described for any coding agent or tool)

Session: "session" in the body or the X-Kinloom-Session header (default "default").
Local by default: only pages served from this machine may call it. `--public --token` for an online server.
"""
import collections
import hmac
import json
import os
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

MAX_BODY = 1024 * 1024
VERBS = ["character", "say", "chat", "decide", "act", "create", "event", "remember", "state", "mind", "report", "think", "reward", "explain",
         "meet", "spread", "knows", "opinion", "opinions", "feel", "reputation", "soul", "lore", "speak", "listen", "tools",
         "prepare", "suggest", "converse", "inspect", "save", "load"]
MAX_AUDIO_BODY = 12 * 1024 * 1024     # /v1/listen carries a recording, /v1/chat and /v1/create a picture (base64)
MEDIA_PATHS = ("/v1/listen", "/v1/chat", "/v1/create", "/v1/load")   # and a save slot loaded back
MAX_REWARDS = 1000
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _need(body, *keys):
    for k in keys:
        if k not in body or body[k] in (None, ""):
            raise ApiError(400, "missing '%s'" % k)


def _local_origin(origin):
    try:
        host = urlparse(origin).hostname or ""
    except ValueError:
        return False
    return urlparse(origin).scheme in ("http", "https") and (host in LOCAL_HOSTS or host.endswith(".localhost"))


def dashboard_html(page="dashboard.html"):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), page)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "<!doctype html><title>Kinloom</title><p>Kinloom is running.</p>"


def public_soul(soul, speaker):
    """What a player's game may see of a character: no secrets or inner card, nothing about other players."""
    out = {k: soul.get(k) for k in ("name", "mood", "gesture", "ready", "tools", "lore", "conversation")}
    card = soul.get("card")
    out["card"] = {"summary": card.get("summary", "")} if isinstance(card, dict) else None
    bonds = soul.get("bonds") or {}
    out["bonds"] = {speaker: bonds[speaker]} if speaker and speaker in bonds else {}
    out["memories"] = []
    return out


def _reply_extra(text, body):
    """Where a reply came from and, when the client asked for them (do: true), the actions decided in it."""
    out = {"source": getattr(text, "source", "offline")}
    if body.get("do") is True:
        out["do"] = [{"tool": t, "args": a} for t, a in getattr(text, "do", [])]
    return out


def _feelings(brain, session, name, speaker):
    soul = brain.soul(session, name)
    return {"mood": soul["mood"]["word"], "feeling": brain.opinion(session, name, speaker), "gesture": soul["gesture"]}


def handle(brain, verb, body, session):
    name = body.get("name")
    try:
        if verb == "character":
            _need(body, "name")
            brain.character(session, name, body.get("personality") or "", body.get("lines"), body.get("offline"), body.get("events"),
                            body.get("tools"), body.get("max_words"), 8.0 if body.get("every") is None else body["every"], body.get("language"),
                            body.get("group"), body.get("soul"), body.get("trust"), body.get("invent") is not False,
                            body.get("voice"), body.get("max_chars"))
            return {"ok": True}
        if verb == "say":
            _need(body, "name", "event")
            text = brain.say(session, name, body["event"], _facts(body), bool(body.get("fresh")), body.get("max_chars"))
            return {"text": text, "source": getattr(text, "source", "offline"), "declared": brain.is_declared(session, name)}
        if verb == "chat":
            _need(body, "name")
            if not isinstance(body.get("message"), str):
                raise ApiError(400, "missing 'message' (\"\" when the character speaks first)")
            speaker = body.get("speaker") or "player"
            text = brain.chat(session, name, body["message"], _facts(body), speaker, max_chars=body.get("max_chars"),
                              image=_image(body))
            return dict({"text": text, "declared": brain.is_declared(session, name)}, **_feelings(brain, session, name, speaker),
                        **_reply_extra(text, body))
        if verb == "lore":
            if "lines" not in body and "text" not in body:
                return {"lore": brain.lore(session)}
            return {"lines": brain.lore(session, body.get("lines", body.get("text")))}
        if verb == "soul":
            _need(body, "name")
            return brain.soul(session, name, body.get("speaker"))
        if verb == "decide":
            _need(body, "name", "choices")
            return {"decision": brain.decide(session, name, body.get("situation") or {}, body["choices"], body.get("every")),
                    "declared": brain.is_declared(session, name)}
        if verb == "act":
            _need(body, "name")
            return {"actions": [{"tool": t, "args": a} for t, a in brain.act(session, name, body.get("situation"), body.get("think") is not False)],
                    "declared": brain.is_declared(session, name)}
        if verb == "create":
            _need(body, "what")
            if "example" not in body:
                raise ApiError(400, "missing 'example' (an example answer: it is also the offline answer)")
            return {"value": brain.create(session, body["what"], body["example"], body.get("context"), body.get("count"),
                                          bool(body.get("instant")), image=_image(body))}
        if verb == "tools":
            if "tools" not in body:
                return {"tools": brain.tools(session)}
            if not isinstance(body["tools"], dict):
                raise ApiError(400, "'tools' must be an object {name: example args}")
            return {"tools": brain.tools(session, body["tools"])}
        if verb == "suggest":
            _need(body, "name")
            if "examples" not in body:
                raise ApiError(400, "missing 'examples' (the replies the player could say: also the offline answer)")
            return {"replies": brain.suggest(session, name, body["examples"], body.get("speaker") or "player", _facts(body))}
        if verb == "converse":
            _need(body, "a", "b")
            return {"lines": brain.converse(session, body["a"], body["b"], body.get("about") or "", body.get("turns"))}
        if verb == "inspect":
            return brain.inspect(session)
        if verb == "save":
            return {"data": brain.save_state(session)}
        if verb == "load":
            _need(body, "data")
            return {"ok": brain.load_state(session, body["data"])}
        if verb == "prepare":
            timeout = body.get("timeout")
            if timeout is None:
                timeout = 10.0                   # null: not given (as in every SDK)
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
                raise ApiError(400, "'timeout' must be a number of seconds")
            return brain.prepare(session, min(PREPARE_MAX, max(0.0, float(timeout))))
        if verb == "event":
            _need(body, "text")
            seen_by = body.get("seen_by")
            if seen_by is not None and not isinstance(seen_by, list):
                raise ApiError(400, "'seen_by' must be a list of names")
            brain.event(session, body["text"], body.get("about"), body.get("importance", 0.5), body.get("by"), seen_by,
                        body.get("tag"), body.get("impact"))
            return {"ok": True}
        if verb == "mind":
            _need(body, "name", "senses", "actions")
            actions = body["actions"]
            if isinstance(actions, dict) and isinstance(body.get("order"), list):   # clients whose JSON objects are sorted
                first = [k for k in body["order"] if isinstance(k, str) and k in actions]
                actions = dict([(k, actions[k]) for k in first] + [(k, v) for k, v in actions.items() if k not in first])
            return {"mind": brain.mind(session, name, body.get("personality") or "", body["senses"], actions,
                                       body.get("rules"), body.get("variants", 3), body.get("learn", 30))}
        if verb == "report":
            _need(body, "name")
            mind = brain.mind_compiled(session, name)
            return {"missing": True} if mind is None else {"mind": mind, "report": brain.mind_report(session, name)}
        if verb == "think":
            _need(body, "name")
            return brain.think(session, str(name), body.get("senses") or {}, body.get("who"))
        if verb == "explain":
            _need(body, "name")
            return brain.explain(session, name, body.get("senses") or {}, body.get("who")) or {"error": "unknown mind"}
        if verb == "reward":
            rewards = body.get("rewards")
            if rewards is None and "who" in body:
                rewards = [body]
            if not isinstance(rewards, list):
                raise ApiError(400, "missing 'rewards' (a list of {who, mind, variant, id, reward})")
            for r in rewards[:MAX_REWARDS]:
                if isinstance(r, dict) and r.get("who") is not None:
                    variant = r.get("variant")
                    brain.reward(session, str(r["who"])[:64], r.get("reward"), r.get("mind"),
                                 variant if isinstance(variant, int) and not isinstance(variant, bool) else None,
                                 r.get("id"), r.get("action"), r.get("senses") if isinstance(r.get("senses"), dict) else None,
                                 r.get("done") is True)
            versions = {}
            for m in brain.minds(session):
                c = brain.mind_compiled(session, m)
                if c:
                    versions[m] = c["version"]
            return {"versions": versions}
        if verb == "meet":
            _need(body, "a", "b")
            return {"shared": brain.meet(session, body["a"], body["b"], body.get("k", 3))}
        if verb == "spread":
            return {"shared": brain.spread(session, body.get("group"), body.get("rounds", 1))}
        if verb == "knows":
            _need(body, "name", "tag")
            notes = brain.knowledge(session, name, str(body["tag"]))
            return {"knows": bool(notes), "notes": notes}
        if verb == "opinion":
            _need(body, "a", "b")
            return {"opinion": brain.opinion(session, body["a"], body["b"])}
        if verb == "opinions":
            _need(body, "name")
            return {"opinions": brain.opinions(session, name)}
        if verb == "feel":
            _need(body, "a", "b")
            return {"opinion": brain.feel(session, body["a"], body["b"], body.get("change"))}
        if verb == "reputation":
            _need(body, "target", "group")
            return {"reputation": brain.reputation(session, body["target"], body["group"])}
        if verb == "remember":
            _need(body, "name", "note")
            brain.remember(session, name, body["note"], body.get("importance", 0.6))
            return {"ok": True}
        if verb == "speak":
            if not isinstance(body.get("text"), str):
                raise ApiError(400, "missing 'text' (what to say aloud)")
            audio = brain.speak(session, name, body["text"])
            if audio is None:
                return {"audio": "", "format": "", "text": body["text"]}
            return {"audio": audio.b64, "format": "wav", "seconds": round(audio.seconds, 3), "text": audio.text}
        if verb == "listen":
            if not isinstance(body.get("audio"), str):
                raise ApiError(400, "missing 'audio' (the recording, base64)")
            return {"text": brain.listen(session, body["audio"], body.get("language"))}
        if verb == "state":
            if not isinstance(body.get("state"), dict):
                raise ApiError(400, "missing 'state' (an object)")
            brain.set_state(session, body["state"])
            return {"ok": True}
    except ValueError as e:  # a bad example / choices shape
        raise ApiError(400, "%s: %s" % ("choices" if verb == "decide" else "example" if verb == "create" else verb, e))
    except RecursionError:
        raise ApiError(400, "%s: nested too deeply" % verb)
    except (TypeError, AttributeError, KeyError) as e:  # a field of the wrong type
        raise ApiError(400, "%s: a field has the wrong type (%s)" % (verb, e))
    raise ApiError(404, "unknown verb '%s' (verbs: %s)" % (verb, ", ".join(VERBS)))


def _facts(body):
    """The facts of a request: an object (or nothing)."""
    facts = body.get("facts")
    if facts is not None and not isinstance(facts, dict):
        raise ApiError(400, "'facts' must be an object {name: value}")
    return facts


def _image(body):
    """The picture of a request: base64 or a data URI (checked by the brain: a bad one is told and left out)."""
    image = body.get("image")
    if image is None or image == "":
        return None
    if not isinstance(image, str):
        raise ApiError(400, "'image' must be base64 or a data URI (PNG, JPEG, GIF, WebP)")
    return image


def _local_host(host_header):
    """The Host header names this machine (a page on another name that resolves here is a DNS-rebinding attempt)."""
    host = (host_header or "").strip().lower()
    if host.startswith("["):
        host = host[1:].split("]", 1)[0]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host in LOCAL_HOSTS or host.endswith(".localhost")


# may call a model, or wait for one (prepare): limited for players (a leaked player token must not tie up the server)
MODEL_VERBS = {"say", "chat", "decide", "act", "create", "speak", "listen", "prepare", "suggest", "converse"}
PREPARE_MAX = 30.0                    # seconds a request may wait in /v1/prepare


def make_server(brain, host="127.0.0.1", port=7717, token=None, public=False, allow_origins=(), player_token=None,
                rate_per_session=None, rate_per_ip=None):
    """token: the admin secret (dashboard, journal, everything). player_token: the secret a shipped game carries: it
    plays (every verb) but cannot read the journal, the live stream or the full status, and its model-backed requests
    are limited per session and per address (rate_per_session / rate_per_ip a minute: over it, 429 and the game's
    client answers offline). A leaked player token is bounded by these limits and by the brain's cost caps."""
    allowed = {o.rstrip("/").lower() for o in allow_origins or ()}
    hits = {}                                   # key -> deque of request times (last minute)

    # Saves handed to a player token are signed: a player token loads only a save this server gave, unchanged (a forged
    # save would set feelings, trust and memories at will). The key: the admin token, else a secret kept in the memory.
    def save_key():
        if token:
            return ("kinloom-save:" + token).encode("utf-8")
        key = brain.memory.get("relay", "save_key")
        if not isinstance(key, str):
            key = os.urandom(32).hex()
            brain.memory.put("relay", "save_key", key)
        return key.encode("utf-8")

    def digest(data):
        text = json.dumps({k: v for k, v in data.items() if k != "sig"}, ensure_ascii=False, sort_keys=True)
        return hmac.new(save_key(), text.encode("utf-8"), "sha256").hexdigest()

    def signed(text):
        data = json.loads(text)
        data["sig"] = digest(data)
        return json.dumps(data, ensure_ascii=False, sort_keys=True)

    def verified(text):
        try:
            data = json.loads(text) if isinstance(text, str) else None
        except ValueError:
            data = None
        if not isinstance(data, dict) or not isinstance(data.get("sig"), str) or \
                not hmac.compare_digest(data["sig"], digest(data)):
            raise ApiError(400, "load: data: not a save this server gave, or changed since (a player token loads only "
                                "what save() returned)")
        return data
    hits_lock = threading.Lock()

    def over(key, limit):
        if not limit:
            return False
        now = time.monotonic()
        with hits_lock:
            q = hits.setdefault(key, collections.deque())
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= limit:
                return True
            q.append(now)
            if len(hits) > 100000:                      # forget idle keys rather than grow forever
                for k in [k for k, v in hits.items() if not v][:50000]:
                    del hits[k]
            return False

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "Kinloom"

        def log_message(self, format, *args):
            pass

        # ---------- helpers ----------

        def _origin_ok(self):
            origin = self.headers.get("Origin")
            return public or not origin or _local_origin(origin) or origin.rstrip("/").lower() in allowed

        def _cors(self):
            origin = self.headers.get("Origin")
            if origin and self._origin_ok():
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

        def _send(self, status, payload, ctype="application/json"):
            data = (json.dumps(payload) if ctype == "application/json" else payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        def _role(self):
            """"admin", "player" or None (not allowed)."""
            if not token and not player_token:
                return "admin"
            auth = self.headers.get("Authorization", "")
            given = auth[7:] if auth.startswith("Bearer ") else self.headers.get("X-Kinloom-Token") or \
                (parse_qs(urlparse(self.path).query).get("token") or [""])[0]
            if token and hmac.compare_digest(given.encode("utf-8"), token.encode("utf-8")):
                return "admin"
            if player_token and hmac.compare_digest(given.encode("utf-8"), player_token.encode("utf-8")):
                return "player"
            return None

        def _authorized(self):
            return self._role() is not None

        def _guard(self):
            if not public and not _local_host(self.headers.get("Host")):
                self._send(403, {"error": "this local server only answers requests addressed to localhost"})
                return False
            if not self._origin_ok():
                origin = self.headers.get("Origin")
                hint = (" A page opened from a file has origin null: serve your game over http (for example "
                        "`python -m http.server`), or start `kinloom serve --allow-origin null`.") if origin == "null" else \
                    " To allow it: `kinloom serve --allow-origin %s`." % origin
                self._send(403, {"error": "web pages from other sites may not call this local server." + hint})
                return False
            if urlparse(self.path).path.startswith("/v1/") and not self._authorized():
                self._send(401, {"error": "this server needs its token (Authorization: Bearer <token>)"})
                return False
            return True

        def _limited(self, verb, session):
            """True (and a 429 sent) when a player's model-backed request is over its limits."""
            if verb not in MODEL_VERBS or self._role() != "player":
                return False
            if over(("s", session), rate_per_session) or over(("ip", self.client_address[0]), rate_per_ip):
                self._send(429, {"error": "too many requests from this player: answer offline and try again later"})
                return True
            return False

        # ---------- methods ----------

        def do_OPTIONS(self):
            if not self._origin_ok() or (not public and not _local_host(self.headers.get("Host"))):
                self._send(403, {"error": "origin not allowed"})
                return
            self.send_response(204)
            self._cors()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Kinloom-Session, X-Kinloom-Token")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if not self._guard():
                return
            url = urlparse(self.path)
            session = self.headers.get("X-Kinloom-Session") or (parse_qs(url.query).get("session") or ["default"])[0]
            session = session[:64]
            if self._role() == "player" and url.path in ("/v1/journal", "/v1/stream", "/v1/status", "/v1/inspect"):
                if url.path == "/v1/status":
                    self._send(200, {"mode": brain.status()["mode"]})
                else:
                    self._send(403, {"error": "the player token cannot read this (use the admin token)"})
                return
            if url.path in ("/", "/index.html"):
                self._send(200, dashboard_html(), "text/html")
            elif url.path in ("/talk", "/talk.html"):
                self._send(200, dashboard_html("talk.html"), "text/html")
            elif url.path == "/v1/status":
                status = brain.status()
                status["stats"] = brain.stats()
                status["characters"] = [{"name": c.name, "personality": c.personality, "tools": list(c.tools),
                                         "events": list(c.events), "group": c.group, "opinions": brain.opinions(session, c.name)}
                                        for c in brain.characters(session)]
                status["minds"] = [brain.mind_report(session, m) for m in brain.minds(session)]
                self._send(200, status)
            elif url.path == "/v1/mind":
                name = (parse_qs(url.query).get("name") or [""])[0]
                mind = brain.mind_compiled(session, name)
                if mind is None:
                    self._send(404, {"error": "unknown mind %r (declare it with POST /v1/mind)" % name[:48]})
                else:
                    self._send(200, {"mind": mind, "report": brain.mind_report(session, name)})
            elif url.path == "/v1/soul":
                q = parse_qs(url.query)
                speaker = (q.get("speaker") or [None])[0]
                soul = brain.soul(session, (q.get("name") or [""])[0], speaker)
                self._send(200, public_soul(soul, speaker) if self._role() == "player" else soul)
            elif url.path == "/v1/journal":
                try:
                    n = int((parse_qs(url.query).get("n") or ["200"])[0])
                except ValueError:
                    n = 200
                self._send(200, {"entries": brain.journal(max(1, min(500, n)))})
            elif url.path == "/v1/stream":
                self._stream_journal()
            elif url.path == "/v1/openapi.json":
                from .openapi import spec
                self._send(200, spec())
            else:
                self._send(404, {"error": "not found"})

        def _drain(self, length):
            """Reads (and drops) a body we refuse, so the client gets our answer instead of a connection reset."""
            left = min(length, 16 * MAX_BODY)
            while left > 0:
                chunk = self.rfile.read(min(65536, left))
                if not chunk:
                    break
                left -= len(chunk)
            self.close_connection = True

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0:
                self._send(400, {"error": "bad Content-Length"})
                self.close_connection = True
                return
            if not self._guard():
                self._drain(length)
                return
            path = urlparse(self.path).path
            limit = MAX_AUDIO_BODY if path in MEDIA_PATHS else MAX_BODY
            if length > limit:
                self._drain(length)
                self._send(413, {"error": "request larger than %d bytes" % limit})
                return
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8") or "{}") if length else {}
                if not isinstance(body, dict):
                    raise ValueError("not an object")
            except (ValueError, UnicodeDecodeError):
                self._send(400, {"error": "the body must be a JSON object"})
                return
            if not path.startswith("/v1/"):
                self._send(404, {"error": "unknown path (verbs: %s)" % ", ".join(VERBS)})
                return
            verb = path[4:]
            session = str(body.get("session") or self.headers.get("X-Kinloom-Session") or "default")[:64]
            if self._limited(verb, session):
                return
            if verb == "inspect" and self._role() == "player":
                self._send(403, {"error": "the player token cannot read this (use the admin token)"})
                return
            if verb == "chat" and body.get("stream"):
                self._stream_chat(body, session)
                return
            try:
                player = self._role() == "player"
                if verb == "load" and player:
                    body = dict(body, data=verified(body.get("data")))
                result = handle(brain, verb, body, session)
                if verb == "soul" and player:
                    result = public_soul(result, body.get("speaker"))
                if verb == "save" and player:
                    result = {"data": signed(result["data"])}
                self._send(200, result)
            except ApiError as e:
                self._send(e.status, {"error": str(e)})
            except Exception as e:  # never drop the connection without an answer
                brain._log("error", "server", "%s failed: %s: %s" % (verb, type(e).__name__, e))
                self._send(500, {"error": "internal error in %s (see the kinloom serve log)" % verb})

        # ---------- streaming ----------

        def _sse_start(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self._cors()
            self.end_headers()
            self.close_connection = True

        def _sse(self, obj):
            self.wfile.write(("data: %s\n\n" % json.dumps(obj)).encode("utf-8"))
            self.wfile.flush()

        def _stream_chat(self, body, session):
            if not body.get("name") or not isinstance(body.get("message"), str):
                self._send(400, {"error": "missing 'name' or 'message' (\"\" when the character speaks first)"})
                return
            try:
                image, facts = _image(body), _facts(body)
            except ApiError as e:
                self._send(e.status, {"error": str(e)})
                return
            self._sse_start()
            lock = threading.Lock()

            def piece(text):
                with lock:
                    try:
                        self._sse({"piece": text})
                    except OSError:
                        pass

            speaker = body.get("speaker") or "player"
            try:
                text = brain.chat(session, body["name"], body["message"], facts, speaker, stream=piece,
                                  max_chars=body.get("max_chars"), image=image)
                done = dict({"done": True, "text": text}, **_feelings(brain, session, body["name"], speaker),
                            **_reply_extra(text, body))
            except Exception as e:  # the stream is open: it still ends with a "done" event, never a cut connection
                brain._log("error", "server", "chat (stream) failed: %s: %s" % (type(e).__name__, e))
                done = {"done": True, "text": "", "source": "offline", "error": "internal error in chat (see the kinloom serve log)"}
            with lock:
                try:
                    self._sse(done)
                except OSError:
                    pass

        def _stream_journal(self):
            q = queue.Queue(maxsize=1000)

            def listener(entry):
                try:
                    q.put_nowait(entry)
                except queue.Full:
                    pass

            self._sse_start()
            brain.listeners.append(listener)
            try:
                for entry in brain.journal(50):
                    self._sse(entry)
                while True:
                    try:
                        self._sse(q.get(timeout=15))
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
            except OSError:
                pass
            finally:
                brain.listeners.remove(listener)

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    return Server((host, port), Handler)
