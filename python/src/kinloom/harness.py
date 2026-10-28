"""The developer's coding agent as Kinloom's model: the subscription they already pay for answers the game's calls,
instead of an API key (their choice: `"provider": "claude-code"` in kinloom.json, or KINLOOM_HARNESS=claude-code).
The agent's model: "model" next to it, or KINLOOM_HARNESS_MODEL; never KINLOOM_MODEL, which names an API's model.

    claude-code  Claude Code 2.1.286, run live while building this: `claude -p` in stream-json, no tools, safe mode.
                 Processes are started ahead and each answers one call (measured: 5.2 s cold, 2.05 s started ahead).
    codex        Codex CLI 0.159.3      `codex exec` (read-only sandbox, prompt on stdin, last message from -o FILE)
    gemini-cli   Gemini CLI 0.62.0      `gemini -p` (plan mode: read-only, prompt on stdin)
    opencode     opencode 1.18.34       `opencode run --pure` (the prompt in an attached file)
    command      any program: "command": ["tool", "--flag", ...]; the prompt on stdin, the answer on stdout

codex, gemini-cli and opencode were written from their --help (those versions), not run with a login. Player text
never goes on a command line (Windows runs .cmd shims through cmd.exe): prompts go through stdin or a file. Every
agent runs in an empty temporary folder. Never chosen automatically: it spends the developer's plan.
"""
import atexit
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from .providers import Provider, Reply

KINDS = ("claude-code", "codex", "gemini-cli", "opencode", "command")
EXES = {"claude-code": "claude", "codex": "codex", "gemini-cli": "gemini", "opencode": "opencode"}
SEES = ("claude-code", "codex", "opencode")        # agents that take a picture with the prompt
SYSTEM = ("You are the model inside a video game. Each message gives, between <system> tags, the system prompt for this "
          "one answer, then the input. Follow that system prompt exactly, as if it were yours, and answer only with the "
          "text it asks for: no preamble, no notes about the answer, no narration of what you are doing.")
INSTRUCTION = "Follow the instructions given above exactly and answer only with what they ask for."
INSTRUCTION_FILE = "Follow the instructions in the attached file exactly and answer only with what they ask for."
NO_THINKING = '{"alwaysThinkingEnabled": false}'
POOL = 2                    # claude-code processes started ahead
MAX_AGE = 600.0             # seconds a process started ahead may wait before it is replaced
MAX_RUNNING = 4             # agent processes at once
MAX_OUT = 2_000_000         # bytes read from an agent's answer, at most
_MODEL = re.compile(r"^[\w.:/@\[\]-]{1,120}$")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _which(exe):
    return shutil.which(exe)


def _kill(p):
    """Stops an agent and what it started (a .cmd shim starts node under cmd.exe: the whole tree goes)."""
    if p.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10, creationflags=_NO_WINDOW)
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        p.kill()
    except OSError:
        pass


class Harness(Provider):
    """A coding agent's command line as a provider. Never raises; every call has its deadline (the agent is stopped)."""

    patient = True          # slow to start: no second request while waiting (it would spend the plan twice)

    def __init__(self, kind, model=None, command=None, exe=None, pool=None):
        if kind not in KINDS:
            raise ValueError("unknown coding agent %r (%s)" % (kind, ", ".join(KINDS)))
        if model is not None and not _MODEL.match(str(model)):
            raise ValueError("model %r: letters, digits and . : / @ - _ only" % (model,))
        if kind == "command":
            if not isinstance(command, (list, tuple)) or not command or not all(isinstance(x, str) and x for x in command):
                raise ValueError('provider "command" needs "command": ["program", "arg", ...] in kinloom.json')
            self.command = list(command)
        else:
            self.command = None
        self.kind, self.name = kind, kind
        self.model = str(model) if model else ""
        program = self.command[0] if self.command else EXES[kind]
        # exe: the program found on PATH, or given (a path, or a list such as [python, script.py] for tests)
        self.exe = exe or _which(program)
        self._prefix = list(self.exe) if isinstance(self.exe, (list, tuple)) else [self.exe]
        self.missing = None if self.exe else "%s not found (install it, or check PATH)" % program
        self.base_url = ""
        self._pool_size = (POOL if pool is None else max(0, min(8, int(pool)))) if kind == "claude-code" else 0
        self._pool = []
        self._lock = threading.Lock()
        self._running = threading.BoundedSemaphore(MAX_RUNNING)
        self._dir = None
        self._closed = False
        atexit.register(self.close)

    def describe(self):
        return "%s (%s)" % (self.kind, self.model or "its default model")

    @property
    def sees(self):
        return self.kind in SEES

    @property
    def starts_ahead(self):
        """Processes are started when Kinloom starts (Brain warms the provider), not at the first call."""
        return bool(self._pool_size and self.exe)

    # ---------------- processes ----------------

    def _folder(self):
        with self._lock:
            if self._dir is None:
                self._dir = tempfile.mkdtemp(prefix="kinloom-agent-")
            return self._dir

    def _env(self):
        env = dict(os.environ)
        env["NO_COLOR"] = "1"
        if self.kind == "claude-code":
            env["MAX_THINKING_TOKENS"] = "0"
        return env

    def _popen(self, args, merge=False):
        return subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT if merge else subprocess.PIPE, cwd=self._folder(),
                                env=self._env(), creationflags=_NO_WINDOW)

    def _claude_args(self):
        # Thinking off: measured with haiku on a chat prompt, 700-1100 thinking tokens took 8-12 s before the first
        # word; without, 0.9 s to the first word (proof/agents). Both the setting and the variable turn it off.
        args = self._prefix + ["-p", "--safe-mode", "--tools", "", "--no-session-persistence", "--system-prompt", SYSTEM,
                               "--settings", NO_THINKING,
                "--input-format", "stream-json", "--output-format", "stream-json", "--include-partial-messages", "--verbose"]
        return args + (["--model", self.model] if self.model else [])

    def _spawn(self):
        return self._popen(self._claude_args(), merge=True), time.monotonic()

    def _take(self):
        """A claude-code process: one started ahead when there is one still alive, else a new one."""
        stale = []
        proc = None
        with self._lock:
            while self._pool:
                p, born = self._pool.pop(0)
                if p.poll() is None and time.monotonic() - born < MAX_AGE:
                    proc = p
                    break
                stale.append(p)
        for p in stale:
            _kill(p)
        if proc is None:
            proc = self._spawn()[0]
        self._refill()
        return proc

    def _refill(self):
        if not self._pool_size or self._closed:
            return

        def work():
            with self._lock:
                if self._closed:
                    return
                need = self._pool_size - len(self._pool)
            for _ in range(max(0, need)):
                try:
                    entry = self._spawn()
                except OSError:
                    return
                with self._lock:
                    if self._closed or len(self._pool) >= self._pool_size:
                        _kill(entry[0])
                        return
                    self._pool.append(entry)
        threading.Thread(target=work, daemon=True, name="kinloom-agent-pool").start()

    def warm(self):
        """Starts processes ahead, so the first call does not wait for the agent to start."""
        if self.exe and not self._closed:
            self._refill()

    def close(self):
        with self._lock:
            self._closed = True
            pool, self._pool = self._pool, []
            folder, self._dir = self._dir, None
        for p, _ in pool:
            _kill(p)
        if folder:
            shutil.rmtree(folder, ignore_errors=True)

    # ---------------- calls ----------------

    def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None,
                 images=None):
        start = time.monotonic()
        deadline = start + timeout
        if self.missing:
            return Reply(False, error=self.missing)
        if self._closed:
            return Reply(False, error="closed")
        rules = system
        if json_mode and "json" not in (system + user).lower():
            rules += "\nAnswer with a single JSON object."
        if json_mode:
            rules += "\nAnswer with the JSON object only, no other text."
        # The system prompt goes in the message, marked as such (the agent's own is fixed when it starts, ahead of
        # the call). Measured with haiku before the tags: a reply began "...no setup, just what Mira says:".
        prompt = "<system>\n%s\n</system>\n\n%s" % (rules, user)
        pictures = list(images or []) if self.sees else []
        blind = bool(images) and not pictures
        if not self._running.acquire(timeout=max(0.0, deadline - time.monotonic())):
            return Reply(False, error="too many agent calls at once", latency=time.monotonic() - start)
        try:
            if self.kind == "claude-code":
                r = self._claude(prompt, pictures, deadline, start, on_text)
            else:
                r = self._once(prompt, pictures, deadline, start)
                if r.ok and on_text is not None:
                    try:
                        on_text(r.text)
                    except Exception:  # a game callback must never break the call
                        pass
        except OSError as e:
            r = Reply(False, error="could not start %s: %s" % (self.kind, e), latency=time.monotonic() - start)
        except Exception as e:  # a provider never raises: an unexpected failure is a failed call
            r = Reply(False, error="%s: %s: %s" % (self.kind, type(e).__name__, e), latency=time.monotonic() - start)
        finally:
            self._running.release()
        r.blind = blind
        return r

    def _claude(self, prompt, pictures, deadline, start, on_text):
        content = [{"type": "image", "source": {"type": "base64", "media_type": p.mime, "data": p.b64}} for p in pictures]
        content.append({"type": "text", "text": prompt})
        message = {"type": "user", "message": {"role": "user", "content": content}}
        p = self._take()
        lines = queue.Queue()

        def read():
            total = 0
            try:
                for raw in p.stdout:
                    total += len(raw)
                    if total > MAX_OUT:
                        lines.put(None)
                        return
                    lines.put(raw)
            except (OSError, ValueError):
                pass
            lines.put(b"")

        try:
            p.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
            p.stdin.close()                 # one call per process: it answers, then ends
        except OSError as e:
            _kill(p)
            return Reply(False, error="%s stopped: %s" % (self.kind, e), latency=time.monotonic() - start)
        threading.Thread(target=read, daemon=True, name="kinloom-agent-read").start()
        parts, other, result = [], [], None
        try:
            while result is None:
                left = deadline - time.monotonic()
                if left <= 0:
                    return Reply(False, "".join(parts), "timed out", latency=time.monotonic() - start)
                try:
                    raw = lines.get(timeout=left)
                except queue.Empty:
                    continue
                if raw is None:
                    return Reply(False, error="answer too large", latency=time.monotonic() - start)
                if raw == b"":
                    break
                try:
                    o = json.loads(raw.decode("utf-8", "replace"))
                except ValueError:
                    other.append(raw.decode("utf-8", "replace").strip())
                    continue
                if not isinstance(o, dict):
                    continue
                if o.get("type") == "stream_event":
                    ev = o.get("event") if isinstance(o.get("event"), dict) else {}
                    delta = ev.get("delta") if isinstance(ev.get("delta"), dict) else {}
                    if ev.get("type") == "content_block_delta" and delta.get("type") == "text_delta" and delta.get("text"):
                        parts.append(delta["text"])
                        if on_text is not None:
                            try:
                                on_text(delta["text"])
                            except Exception:  # a game callback must never break the call
                                pass
                elif o.get("type") == "result":
                    result = o
        finally:
            if result is None:
                _kill(p)                 # late, too large or ended: stopped now (it would keep spending the plan)
            else:
                threading.Thread(target=self._finish, args=(p,), daemon=True).start()
        text = "".join(parts)
        if result is None:
            said = " ".join(x for x in other if x)[-200:]
            return Reply(False, text, "%s ended without an answer%s" % (self.kind, (": " + said) if said else ""),
                         latency=time.monotonic() - start)
        if result.get("is_error"):
            why = result.get("result") if isinstance(result.get("result"), str) else result.get("subtype")
            return Reply(False, text, "%s: %s" % (self.kind, str(why or "error")[:200]), latency=time.monotonic() - start)
        if not text.strip() and isinstance(result.get("result"), str):
            text = result["result"]
            if on_text is not None and text:
                try:
                    on_text(text)
                except Exception:  # a game callback must never break the call
                    pass
        if not text.strip():
            return Reply(False, error="empty answer", latency=time.monotonic() - start)
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        cached = _int(usage, "cache_read_input_tokens")
        return Reply(True, text, None, _int(usage, "input_tokens") + cached + _int(usage, "cache_creation_input_tokens"),
                     cached, _int(usage, "output_tokens"), time.monotonic() - start)

    @staticmethod
    def _finish(p):
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            _kill(p)

    def _once(self, prompt, pictures, deadline, start):
        """codex, gemini-cli, opencode, command: one process per call, the answer when it ends."""
        folder = self._folder()
        tag = "%d-%d" % (os.getpid(), threading.get_ident())
        made = []

        def keep(name, data):
            path = os.path.join(folder, "%s-%s" % (tag, name))
            with open(path, "wb") as f:
                f.write(data)
            made.append(path)
            return path

        images = [keep("image%d.%s" % (i, p.mime.split("/")[1]), p.data) for i, p in enumerate(pictures)]
        model = ["-m", self.model] if self.model else []
        stdin = prompt.encode("utf-8")
        out_file = None
        if self.kind == "codex":
            out_file = os.path.join(folder, "%s-answer.txt" % tag)
            made.append(out_file)
            args = self._prefix + ["exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "--color", "never",
                    "-o", out_file] + model + ["-"] + sum((["-i", x] for x in images), [])   # -: prompt on stdin
        elif self.kind == "gemini-cli":
            args = self._prefix + ["-p", INSTRUCTION, "-o", "text", "--approval-mode", "plan", "--skip-trust"] + model
        elif self.kind == "opencode":
            prompt_file = keep("prompt.md", stdin)
            stdin = b""
            args = self._prefix + ["run", INSTRUCTION_FILE, "--pure"] + model + ["-f", prompt_file] + \
                sum((["-f", x] for x in images), [])
        else:
            args = self._prefix + self.command[1:]
        try:
            p = self._popen(args)
            try:
                out, err = p.communicate(stdin, timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                _kill(p)
                return Reply(False, error="timed out", latency=time.monotonic() - start)
            text = ""
            if out_file and os.path.exists(out_file):
                with open(out_file, "rb") as f:
                    text = f.read(MAX_OUT).decode("utf-8", "replace")
            if not text.strip():
                text = out[:MAX_OUT].decode("utf-8", "replace")
            text = _ANSI.sub("", text).strip()
            if p.returncode != 0 and not text:
                said = _ANSI.sub("", err[-2000:].decode("utf-8", "replace")).strip().splitlines()
                return Reply(False, error="%s failed (exit %s)%s" % (self.kind, p.returncode, (": " + said[-1][:200]) if said else ""),
                             latency=time.monotonic() - start)
            if not text:
                return Reply(False, error="empty answer", latency=time.monotonic() - start)
            # the tokens are not reported by these agents: estimated like the scripted model (4 characters a token)
            return Reply(True, text, None, len(prompt) // 4, 0, len(text) // 4, time.monotonic() - start)
        finally:
            for path in made:
                try:
                    os.remove(path)
                except OSError:
                    pass


def _int(d, key):
    v = d.get(key) if isinstance(d, dict) else None
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def from_config(kind, model=None, command=None, pool=None):
    """The agent named in kinloom.json or KINLOOM_HARNESS; ValueError for a bad name or setting."""
    return Harness(kind, model, command, pool=pool)


def found():
    """Coding agents installed on this machine (their command is on PATH), for `kinloom init` and `kinloom doctor`."""
    return [k for k in KINDS if k != "command" and _which(EXES[k])]


if __name__ == "__main__":     # python -m kinloom.harness claude-code [model]: one live call, timed
    h = Harness(sys.argv[1] if len(sys.argv) > 1 else "claude-code", sys.argv[2] if len(sys.argv) > 2 else None)
    t = time.monotonic()
    print(h.complete("Kinloom task: check\nAnswer in one short sentence.", "Say hello to a traveller.", timeout=60))
    print("%.2f s" % (time.monotonic() - t))
    h.close()
