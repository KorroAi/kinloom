"""Model providers, standard library only. Every call has a hard time limit, retries once on transient errors,
never raises, and reports token usage. Chosen automatically by `detect`."""
import http.client
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

DEEPSEEK_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-flash"          # verified live on 2026-09-26
ANTHROPIC_URL = "https://api.anthropic.com"
ANTHROPIC_MODEL = "claude-haiku-4-5"       # default chosen for speed and cost; override with KINLOOM_MODEL
OLLAMA_URL = "http://127.0.0.1:11434"
TRANSIENT = {408, 409, 429, 500, 502, 503, 504, 529}
MAX_ANSWER = 4_000_000        # bytes read from a model endpoint, at most (a broken endpoint must not fill memory)


class Reply:
    def __init__(self, ok, text="", error=None, input_tokens=0, cached_tokens=0, output_tokens=0, latency=0.0):
        self.ok, self.text, self.error = ok, text, error
        self.input_tokens, self.cached_tokens, self.output_tokens = input_tokens, cached_tokens, output_tokens
        self.latency = latency
        self.cut = False          # a conversation reply ended early by the tail guard (Brain._race)
        self.blind = False        # pictures were given but this model could not see them (answered from the text)

    def __repr__(self):
        return "Reply(%s, %r)" % ("ok" if self.ok else "failed: %s" % self.error, self.text[:60])


def _int(d, key):
    v = d.get(key) if isinstance(d, dict) else None
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


class _Http:
    """POST JSON with a deadline; one retry on transient failures; SSE streaming when asked. Connections to a provider
    are kept open and reused (no new TCP and TLS handshake per call: often 100-300 ms saved); one that the server
    closed meanwhile is replaced silently."""

    _idle = {}                 # (scheme, host, port) -> [open connections]
    _lock = threading.Lock()
    MAX_IDLE = 4

    @classmethod
    def warm(cls, url, timeout=5.0):
        """Opens one connection to the host of url and keeps it for the first call."""
        u = urllib.parse.urlsplit(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return
        key = (u.scheme, u.hostname, u.port or (443 if u.scheme == "https" else 80))
        with cls._lock:
            if cls._idle.get(key):
                return
        maker = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        conn = maker(u.hostname, key[2], timeout=timeout)
        conn.connect()
        with cls._lock:
            idle = cls._idle.setdefault(key, [])
            if len(idle) < cls.MAX_IDLE:
                idle.append(conn)
                return
        conn.close()

    @classmethod
    def _take(cls, key, timeout):
        with cls._lock:
            idle = cls._idle.get(key) or []
            conn = idle.pop() if idle else None
        if conn is not None:
            conn.timeout = timeout
            if conn.sock is not None:
                conn.sock.settimeout(timeout)
            return conn, False
        scheme, host, port = key
        maker = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
        return maker(host, port, timeout=timeout), True

    @classmethod
    def _give_back(cls, key, conn, resp):
        if resp.will_close:
            conn.close()
            return
        with cls._lock:
            idle = cls._idle.setdefault(key, [])
            if len(idle) < cls.MAX_IDLE:
                idle.append(conn)
                return
        conn.close()

    @classmethod
    def post(cls, url, headers, body, deadline, stream=False, on_line=None, raw=False):
        """body: a JSON-able value, or bytes sent as they are (headers then carry their Content-Type). raw: the answer
        as bytes (audio) instead of text."""
        if isinstance(body, bytes):
            data, kind = body, headers.get("Content-Type", "application/octet-stream")
        else:
            data, kind = json.dumps(body).encode("utf-8"), "application/json"
        u = urllib.parse.urlsplit(url)
        key = (u.scheme or "http", u.hostname, u.port or (443 if u.scheme == "https" else 80))
        path = (u.path or "/") + ("?" + u.query if u.query else "")
        hdrs = dict(headers, **{"Content-Type": kind, "Host": u.netloc})
        stale_retries = 1
        attempt = 0
        while attempt < 2:
            left = deadline - time.monotonic()
            if left <= 0.05:
                return None, "timed out"
            wait = 0.4
            conn, fresh = cls._take(key, left)
            try:
                conn.request("POST", path, body=data, headers=hdrs)
                resp = conn.getresponse()
            except (http.client.RemoteDisconnected, http.client.BadStatusLine, ConnectionResetError, ConnectionAbortedError,
                    BrokenPipeError) as e:
                conn.close()
                if not fresh and stale_retries:      # the server closed a kept connection: open a new one, same attempt
                    stale_retries -= 1
                    continue
                if attempt == 1:
                    return None, "network error: %s" % e
                attempt += 1
                continue
            except (socket.timeout, TimeoutError):
                conn.close()
                return None, "timed out"
            except OSError as e:
                conn.close()
                if "timed out" in str(e):
                    return None, "timed out"
                if attempt == 1:
                    return None, "network error: %s" % e
                attempt += 1
                if deadline - time.monotonic() <= wait + 0.1:
                    return None, "timed out"
                time.sleep(wait)
                continue
            try:
                if resp.status >= 400:
                    text = resp.read(20_000).decode("utf-8", "replace")
                    conn.close()
                    if attempt == 0 and resp.status in TRANSIENT:
                        ra = resp.getheader("Retry-After")
                        try:
                            wait = min(2.0, float(ra)) if ra else wait
                        except ValueError:
                            pass
                        attempt += 1
                        if deadline - time.monotonic() <= wait + 0.1:
                            return None, "timed out"
                        time.sleep(wait)
                        continue
                    return resp.status, text
                if stream:
                    total = 0
                    while True:
                        raw = resp.readline(MAX_ANSWER)
                        if not raw:
                            break
                        total += len(raw)
                        if time.monotonic() > deadline:
                            conn.close()
                            return None, "timed out"
                        if total > MAX_ANSWER:
                            conn.close()
                            return None, "answer too large"
                        on_line(raw.decode("utf-8", "replace").rstrip("\r\n"))
                    cls._give_back(key, conn, resp)
                    return 200, ""
                out = resp.read(MAX_ANSWER + 1)
                if len(out) > MAX_ANSWER:
                    conn.close()
                    return None, "answer too large"
                cls._give_back(key, conn, resp)
                return resp.status, out if raw else out.decode("utf-8", "replace")
            except (socket.timeout, TimeoutError):
                conn.close()
                return None, "timed out"
            except (http.client.HTTPException, OSError) as e:
                conn.close()
                return None, "network error: %s" % e
        return None, "failed"


class Provider:
    name = "provider"
    model = ""
    base_url = ""

    def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None,
                 images=None):
        """images: [media.Picture] the model looks at with the prompt (chat/create with image=)."""
        raise NotImplementedError

    def describe(self):
        return "%s (%s)" % (self.name, self.model)

    @property
    def local(self):
        """A model on this machine: asking it twice at once only slows both (no hedging)."""
        host = (urllib.parse.urlsplit(self.base_url or "").hostname or "").lower()
        return host in ("127.0.0.1", "localhost", "::1", "0.0.0.0") or self.name == "ollama"

    @property
    def patient(self):
        """Slow to start (a local model, a coding agent): no second request while waiting, longer reply deadlines."""
        return self.local

    def warm(self):
        """Opens the connection now (TCP and TLS), so the first reply does not pay for it."""
        _Http.warm(self.base_url)


def _json_prompt(system, user):
    # JSON mode is refused unless the prompt says "json" (DeepSeek, OpenAI).
    if "json" in (system + user).lower():
        return system
    return system + "\nAnswer with a single JSON object."


class OpenAICompatible(Provider):
    """Any chat-completions endpoint: DeepSeek, OpenAI, OpenRouter, Groq, Together, LM Studio, vLLM, Ollama..."""

    EFFORTS = ("none", "minimal")    # asked in this order; an endpoint that refuses both gets no reasoning_effort

    def __init__(self, base_url, key, model, name="openai-compatible", deepseek=False):
        self.base_url = base_url.rstrip("/")
        self.key, self.model, self.name, self.deepseek = key, model, name, deepseek
        self._adapt = set()   # parameters this endpoint refused once ("max_tokens", "temperature", "response_format")
        # Reasoning models (qwen3, gpt-5, ...) think before answering by default: seconds of hidden tokens, sometimes
        # the whole token budget (an empty answer). Game calls need speed: ask for no reasoning, learn if refused.
        self._effort = 0 if name not in ("deepseek", "openrouter") and not deepseek else len(self.EFFORTS)

    def _body(self, system, user, json_mode, max_tokens, temperature, images=None):
        content = user if not images else [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": p.uri}} for p in images]
        body = {"model": self.model, "messages": [{"role": "system", "content": _json_prompt(system, user) if json_mode else system},
                                                  {"role": "user", "content": content}]}
        body["max_completion_tokens" if "max_tokens" in self._adapt else "max_tokens"] = max_tokens
        if "temperature" not in self._adapt:
            body["temperature"] = temperature
        if json_mode and "response_format" not in self._adapt:
            body["response_format"] = {"type": "json_object"}
        if self.deepseek:
            body["thinking"] = {"type": "disabled"}  # game calls need speed, not reasoning
        if self.name == "openrouter" and "reasoning" not in self._adapt:
            body["reasoning"] = {"enabled": False}   # same on OpenRouter (reasoning models answer 2x slower otherwise)
        if self._effort < len(self.EFFORTS):
            body["reasoning_effort"] = self.EFFORTS[self._effort]
        return body

    _REFUSED = ("unsupported", "not supported", "invalid", "unrecognized", "unknown", "not permitted", "unexpected",
                "not allowed", "extra")

    _BLIND = ("image", "vision", "multimodal", "multi-modal")

    def _learn(self, status, text, images=None):
        """Newer models refuse some parameters (e.g. OpenAI reasoning models: max_tokens, temperature). Learn it once.
        images: pictures were sent; a 400 that names them means this model cannot see (sent without, from now on)."""
        if status != 400:
            return False
        low = text.lower()
        if images and "images" not in self._adapt and any(w in low for w in self._BLIND):
            self._adapt.add("images")
            return True
        if not any(w in low for w in self._REFUSED):
            return False
        if "reasoning_effort" in low and self._effort < len(self.EFFORTS):
            self._effort += 1                        # "none" refused: try "minimal", then send nothing
            return True
        for param in ("max_tokens", "temperature", "response_format", "reasoning"):
            if param in low and param not in self._adapt:
                self._adapt.add(param)
                return True
        return False

    def warm(self):
        """Opens the connection now; a local model is also loaded into memory (the first reply would wait for it)."""
        _Http.warm(self.base_url)
        if self.local:
            self.complete("Kinloom task: warm", "Say OK.", max_tokens=1, timeout=120.0)

    def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None,
                 images=None):
        start = time.monotonic()
        headers = {"Authorization": "Bearer " + self.key} if self.key else {}
        url = self.base_url + "/chat/completions"
        deadline = start + timeout
        status, text = None, "failed"
        for _ in range(7):
            sent = images if images and "images" not in self._adapt else None
            body = self._body(system, user, json_mode, max_tokens, temperature, sent)
            if on_text is not None:
                reply = self._stream(url, headers, body, deadline, start, on_text)
                if not reply.ok and self._learn(400 if (reply.error or "").startswith("HTTP 400") else 0, reply.error or "", sent):
                    continue
                reply.blind = bool(images) and not sent
                return reply
            status, text = _Http.post(url, headers, body, deadline)
            if not self._learn(status, text, sent):
                break
        blind = bool(images) and "images" in self._adapt
        if status != 200:
            return Reply(False, error=("HTTP %s: %s" % (status, text[:200])) if status else text, latency=time.monotonic() - start)
        try:
            root = json.loads(text)
            message = root["choices"][0]["message"]
            content = message.get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError):
            return Reply(False, error="unreadable answer: %s" % text[:200], latency=time.monotonic() - start)
        usage = root.get("usage") or {}
        cached = _int(usage, "prompt_cache_hit_tokens") or _int(usage.get("prompt_tokens_details") or {}, "cached_tokens")
        if not content.strip():
            return Reply(False, error="empty answer", latency=time.monotonic() - start)
        r = Reply(True, content, None, _int(usage, "prompt_tokens"), cached, _int(usage, "completion_tokens"), time.monotonic() - start)
        r.blind = blind
        return r

    def _stream(self, url, headers, body, deadline, start, on_text):
        body = dict(body, stream=True, stream_options={"include_usage": True})
        parts, usage = [], {}

        def line(l):
            if not l.startswith("data:"):
                return
            payload = l[5:].strip()
            if payload == "[DONE]":
                return
            try:
                o = json.loads(payload)
            except ValueError:
                return
            if o.get("usage"):
                usage.update(o["usage"])
            for c in o.get("choices") or []:
                piece = (c.get("delta") or {}).get("content")
                if piece:
                    parts.append(piece)
                    try:
                        on_text(piece)
                    except Exception:  # a game callback must never break the call
                        pass

        status, err = _Http.post(url, headers, body, deadline, stream=True, on_line=line)
        text = "".join(parts)
        if status != 200:
            return Reply(False, text, ("HTTP %s: %s" % (status, err[:200])) if status else (err or "failed"),
                         latency=time.monotonic() - start)
        if not text.strip():
            return Reply(False, error="empty answer", latency=time.monotonic() - start)
        cached = _int(usage, "prompt_cache_hit_tokens") or _int(usage.get("prompt_tokens_details") or {}, "cached_tokens")
        return Reply(True, text, None, _int(usage, "prompt_tokens"), cached, _int(usage, "completion_tokens"),
                     time.monotonic() - start)


class Anthropic(Provider):
    """Claude through the Messages API (raw HTTP, so the package has no dependencies)."""

    def __init__(self, key, model=ANTHROPIC_MODEL, base_url=ANTHROPIC_URL):
        self.key, self.model, self.base_url, self.name = key, model, base_url.rstrip("/"), "anthropic"

    def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None,
                 images=None):
        start = time.monotonic()
        sys_text = system + ("\nAnswer with a single JSON object and nothing else." if json_mode else "")
        content = user if not images else [
            {"type": "image", "source": {"type": "base64", "media_type": p.mime, "data": p.b64}} for p in images] + [
            {"type": "text", "text": user}]
        body = {"model": self.model, "max_tokens": max_tokens,
                "system": [{"type": "text", "text": sys_text, "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": content}]}
        headers = {"x-api-key": self.key, "anthropic-version": "2023-06-01"}
        url = self.base_url + "/v1/messages"
        deadline = start + timeout
        if on_text is not None:
            parts, usage, stop = [], {}, {}

            def line(l):
                if not l.startswith("data:"):
                    return
                try:
                    o = json.loads(l[5:].strip())
                except ValueError:
                    return
                if o.get("type") == "message_start":
                    usage.update((o.get("message") or {}).get("usage") or {})
                elif o.get("type") == "content_block_delta":
                    piece = (o.get("delta") or {}).get("text")
                    if piece:
                        parts.append(piece)
                        try:
                            on_text(piece)
                        except Exception:
                            pass
                elif o.get("type") == "message_delta":
                    usage.update(o.get("usage") or {})
                    stop.update(o.get("delta") or {})

            status, err = _Http.post(url, headers, dict(body, stream=True), deadline, stream=True, on_line=line)
            text = "".join(parts)
            if status != 200 or stop.get("stop_reason") == "refusal" or not text.strip():
                return Reply(False, text, err or "refused or empty", latency=time.monotonic() - start)
            cached = _int(usage, "cache_read_input_tokens")
            return Reply(True, text, None, _int(usage, "input_tokens") + cached + _int(usage, "cache_creation_input_tokens"),
                         cached, _int(usage, "output_tokens"), time.monotonic() - start)
        status, text = _Http.post(url, headers, body, deadline)
        if status != 200:
            return Reply(False, error=("HTTP %s: %s" % (status, text[:200])) if status else text, latency=time.monotonic() - start)
        try:
            root = json.loads(text)
        except ValueError:
            return Reply(False, error="unreadable answer", latency=time.monotonic() - start)
        if root.get("stop_reason") == "refusal":
            return Reply(False, error="refusal", latency=time.monotonic() - start)
        content = "".join(b.get("text", "") for b in root.get("content") or [] if isinstance(b, dict) and b.get("type") == "text")
        usage = root.get("usage") or {}
        cached = _int(usage, "cache_read_input_tokens")
        if not content.strip():
            return Reply(False, error="empty answer", latency=time.monotonic() - start)
        return Reply(True, content, None, _int(usage, "input_tokens") + cached + _int(usage, "cache_creation_input_tokens"),
                     cached, _int(usage, "output_tokens"), time.monotonic() - start)


class Scripted(Provider):
    """Tests and replays: fn(kind, system, user) -> text or None (None = failure). kind: 'json' or 'text'."""

    def __init__(self, fn, name="scripted"):
        self.fn, self.name, self.model = fn, name, name

    def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None,
                 images=None):
        if images:          # a script cannot see: it reads what was shown (tests check the picture reached the model)
            user = user + "\n" + " ".join(p.describe() for p in images)
        try:
            text = self.fn("json" if json_mode else "text", system, user)
        except Exception as e:  # a broken script is a failed call, like a broken model
            return Reply(False, error="script error: %s" % e)
        if text is None:
            return Reply(False, error="no scripted answer")
        if on_text is not None:
            on_text(text)
        return Reply(True, text, None, (len(system) + len(user)) // 4, 0, len(text) // 4, 0.0)


_TASK = re.compile(r"Kinloom task: (\w+)")


def task_of(system):
    m = _TASK.search(system or "")
    return m.group(1) if m else "*"


def from_script_file(path):
    """A scripted model from a JSON file {"task": answer or [answers...], "*": ...}. Answers are used in order per task
    then "*" answers (its last answer repeats). Objects are sent as JSON text. Used for engine tests,
    CI and replays of recorded sessions (KINLOOM_SCRIPT=file)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    queues = {k: (list(v) if isinstance(v, list) else [v]) for k, v in data.items()}
    single = {k for k, v in data.items() if not isinstance(v, list)}  # a single answer repeats forever
    lock = threading.Lock()

    def answer(kind, system, user):
        t = task_of(system)
        with lock:
            own = queues.get(t)
            if own and t in single:
                a = own[0]
            elif own:
                a = own.pop(0)
            else:
                shared = queues.get("*")
                if not shared:
                    return None
                a = shared.pop(0) if len(shared) > 1 else shared[0]
        return a if isinstance(a, str) else json.dumps(a)

    return Scripted(answer, name="script")


class Recording(Provider):
    """Wraps a live provider and appends every successful answer to a JSON file, per task (KINLOOM_RECORD=file).
    Replay it later with KINLOOM_SCRIPT=file: the game's AI becomes deterministic and free in tests."""

    def __init__(self, inner, path):
        self.inner, self.path = inner, path
        self.name, self.model, self.base_url = inner.name + "+record", inner.model, getattr(inner, "base_url", "")
        self._lock = threading.Lock()

    def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None,
                 images=None):
        r = complete(self.inner, system, user, json_mode, max_tokens, temperature, timeout, on_text, images)
        if r.ok:
            with self._lock:
                try:
                    with open(self.path, encoding="utf-8") as f:
                        data = json.load(f)
                except (OSError, ValueError):
                    data = {}
                data.setdefault(task_of(system), []).append(r.text)
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=1)
        return r


def complete(provider, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None,
             images=None):
    """provider.complete, with pictures only when there are some: a game's own provider written before images (no
    `images` argument) still works and answers from the text (Reply.blind)."""
    if not images:
        return provider.complete(system, user, json_mode=json_mode, max_tokens=max_tokens, temperature=temperature,
                                 timeout=timeout, on_text=on_text)
    try:
        return provider.complete(system, user, json_mode=json_mode, max_tokens=max_tokens, temperature=temperature,
                                 timeout=timeout, on_text=on_text, images=images)
    except TypeError as e:
        if "images" not in str(e):
            raise
    r = provider.complete(system, user, json_mode=json_mode, max_tokens=max_tokens, temperature=temperature,
                          timeout=timeout, on_text=on_text)
    r.blind = True
    return r


def _ollama_models(url):
    """Chat models installed in a running Ollama, biggest first (vision and embedding models left out)."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=0.4) as resp:
            models = json.loads(resp.read().decode("utf-8")).get("models") or []
    except Exception:  # not running, not Ollama, or unreachable: no local model
        return []
    out = []
    for m in models:
        if not isinstance(m, dict) or not isinstance(m.get("name"), str) or not m["name"]:
            continue
        details = m.get("details") if isinstance(m.get("details"), dict) else {}
        families = " ".join(str(f) for f in (details.get("families") or [details.get("family") or ""]) if f).lower()
        if "embed" in m["name"].lower() or "bert" in families or "clip" in families or "mllama" in families:
            continue
        size = m.get("size") if isinstance(m.get("size"), (int, float)) else 0
        out.append((size, m["name"]))
    return [n for _, n in sorted(out, key=lambda x: -x[0])]


def _ollama_model(url, wanted=None):
    names = _ollama_models(url)
    if wanted:
        return wanted if wanted in names or (wanted + ":latest") in names else None
    return names[0] if names else None


# Services that speak the chat-completions protocol, found by their usual key variable. None of them has a model
# Kinloom could safely guess, so KINLOOM_MODEL names it (endpoints checked to exist on 2026-09-29).
HOSTED = [
    ("GEMINI_API_KEY", "gemini", "https://generativelanguage.googleapis.com/v1beta/openai"),
    ("GROQ_API_KEY", "groq", "https://api.groq.com/openai/v1"),
    ("MISTRAL_API_KEY", "mistral", "https://api.mistral.ai/v1"),
    ("TOGETHER_API_KEY", "together", "https://api.together.xyz/v1"),
    ("XAI_API_KEY", "xai", "https://api.x.ai/v1"),
    ("FIREWORKS_API_KEY", "fireworks", "https://api.fireworks.ai/inference/v1"),
    ("CEREBRAS_API_KEY", "cerebras", "https://api.cerebras.ai/v1"),
]
DEAD = ("HTTP 401", "HTTP 402", "HTTP 403")      # a key refused or out of credit: no later call will work either


class Fallback(Provider):
    """Several usable providers in order. When the current one refuses the key or has no credit left (401, 402, 403),
    the next one is used from then on, instead of every call failing to the offline answer. Later candidates are
    built only when needed (a local model is looked for then)."""

    def __init__(self, first, rest):
        self.current, self.rest, self.switched = first, list(rest), []
        self._lock = threading.Lock()

    name = property(lambda self: self.current.name)
    model = property(lambda self: self.current.model)
    base_url = property(lambda self: getattr(self.current, "base_url", ""))
    local = property(lambda self: getattr(self.current, "local", False))
    patient = property(lambda self: bool(getattr(self.current, "patient", getattr(self.current, "local", False))))

    def close(self):
        getattr(self.current, "close", lambda: None)()

    def warm(self):
        getattr(self.current, "warm", lambda: None)()

    def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None,
                 images=None):
        start = time.monotonic()
        while True:
            used = self.current
            r = complete(used, system, user, json_mode, max_tokens, temperature, max(0.5, timeout - (time.monotonic() - start)),
                         on_text, images)
            if r.ok or not (r.error or "").startswith(DEAD) or r.text:
                return r
            with self._lock:
                if self.current is used:
                    nxt = None
                    while self.rest and nxt is None:
                        nxt = self.rest.pop(0)()
                    if nxt is None:
                        return r
                    self.switched.append("%s: %s -> %s" % (used.describe(), r.error[:60], nxt.describe()))
                    self.current = nxt
            if time.monotonic() - start >= timeout:
                return r


def detect(env=None, probe_ollama=True, ollama_url=OLLAMA_URL):
    """The provider to use, from what exists (never guessing a model name), or None for offline mode."""
    env = os.environ if env is None else env
    if env.get("KINLOOM_OFFLINE", "").lower() in ("1", "true", "yes"):
        return None
    if env.get("KINLOOM_SCRIPT"):
        return from_script_file(env["KINLOOM_SCRIPT"])
    if env.get("KINLOOM_HARNESS"):          # the developer chose their coding agent's subscription
        from .harness import Harness
        found = Harness(env["KINLOOM_HARNESS"].strip().lower(), env.get("KINLOOM_HARNESS_MODEL") or None)
    else:
        found = _detect(env, probe_ollama, ollama_url)
    if found is not None and env.get("KINLOOM_RECORD"):
        return Recording(found, env["KINLOOM_RECORD"])
    return found


def _candidates(env, probe_ollama, ollama_url):
    """Every usable provider, best first, as functions that build it (or return None)."""
    model = env.get("KINLOOM_MODEL")
    out = []
    if env.get("KINLOOM_BASE_URL") and model:
        key = env.get("KINLOOM_API_KEY") or env.get("DEEPSEEK_API_KEY") or env.get("OPENAI_API_KEY") or ""
        out.append(lambda: OpenAICompatible(env["KINLOOM_BASE_URL"], key, model, name="custom",
                                            deepseek="deepseek" in env["KINLOOM_BASE_URL"]))
    if env.get("OPENROUTER_API_KEY") and model and "/" in model:     # "vendor/model" only exists on OpenRouter
        out.append(lambda: OpenAICompatible("https://openrouter.ai/api/v1", env["OPENROUTER_API_KEY"], model, name="openrouter"))
    if env.get("DEEPSEEK_API_KEY") and (not model or "deepseek" in model.lower() or env.get("DEEPSEEK_BASE_URL")):
        out.append(lambda: OpenAICompatible(env.get("DEEPSEEK_BASE_URL") or DEEPSEEK_URL, env["DEEPSEEK_API_KEY"],
                                            model or DEEPSEEK_MODEL, name="deepseek", deepseek=True))
    if env.get("ANTHROPIC_API_KEY") and (not model or "claude" in model.lower() or env.get("ANTHROPIC_BASE_URL")):
        out.append(lambda: Anthropic(env["ANTHROPIC_API_KEY"], model or ANTHROPIC_MODEL,
                                     env.get("ANTHROPIC_BASE_URL") or ANTHROPIC_URL))
    if env.get("OPENAI_API_KEY") and model:
        out.append(lambda: OpenAICompatible(env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1", env["OPENAI_API_KEY"],
                                            model, name="openai"))
    for var, name, url in HOSTED:
        if env.get(var) and model:
            out.append(lambda var=var, name=name, url=url: OpenAICompatible(url, env[var], model, name=name))
    if env.get("OPENROUTER_API_KEY") and model and "/" not in model:
        out.append(lambda: OpenAICompatible("https://openrouter.ai/api/v1", env["OPENROUTER_API_KEY"], model, name="openrouter"))
    if probe_ollama:
        def local():
            name = _ollama_model(ollama_url, model) or _ollama_model(ollama_url)
            return OpenAICompatible(ollama_url.rstrip("/") + "/v1", "", name, name="ollama") if name else None
        out.append(local)
    return out


def _detect(env, probe_ollama, ollama_url):
    makers = _candidates(env, probe_ollama, ollama_url)
    while makers:
        first = makers.pop(0)()
        if first is not None:
            return Fallback(first, makers) if makers else first
    return None


def missing_model(env=None):
    """A key Kinloom found but cannot use because no model is named (the variable), or None."""
    env = os.environ if env is None else env
    if env.get("KINLOOM_MODEL") or env.get("KINLOOM_SCRIPT"):
        return None
    for var in ["OPENAI_API_KEY", "OPENROUTER_API_KEY"] + [v for v, _, _ in HOSTED]:
        if env.get(var):
            return var
    return None
