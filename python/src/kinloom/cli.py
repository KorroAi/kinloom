"""The `kinloom` command.

    kinloom                    what Kinloom found here and what to ask your coding agent
    kinloom add NAME "who they are" [--tools "give(item)" --trust give=0.3]   a character, written into kinloom.json
    kinloom recipe "any request"      the call and the patterns for one feature, in this game's language
    kinloom hooks <game folder|.dll>  a mod: where Kinloom plugs into a .NET game you have no source of (reads it with REA)
    kinloom run -- <game command>     runs the game with Kinloom, then says what the AI did (calls, errors, refusals)
    kinloom log [-n 40] [--follow]    what the running server did, as text
    kinloom talk NAME "who they are"   talk to a character in the terminal (--web: in the browser)
    kinloom deploy [folder]    an online server for a shipped game: Dockerfile + guide (deploys nothing itself)
    kinloom bundle             Kinloom as a program that needs no Python (kinloom-server/), for non-Python engines
    kinloom init [folder]      set up a game: engine client + instructions for any coding agent
    kinloom serve              the local server every engine talks to (+ live dashboard)
    kinloom try NAME "who they are" [--event E --facts JSON | --chat MSG | --decide JSON | --create WHAT --example JSON]
    kinloom use claude-code [--model haiku]   the model: your coding agent's subscription (claude-code, codex,
                               gemini-cli, opencode) or `kinloom use key` (an API key from the environment)
    kinloom test [--record F | --replay F | --offline]   the game's AI checked like code (kinloom.tests.json)
    kinloom probe NAME         plays a character like a tester would: secrets, manipulation, repeats, length, speed
    kinloom doctor             what Kinloom found: model, key, latency, config
    kinloom guide [engine]     the instructions for coding agents (the calls, rules, 39 patterns)
    kinloom check [folder]     finds integration mistakes (missing await, undeclared characters, keys in code)
    kinloom mcp                tools for coding agents (Claude Code, Codex, Cursor, ...)
    kinloom demo               watch a mind learn to win a fight, offline, in seconds (no key)
    kinloom think MIND.json '{"hp": 0.2}'   run a mind on a moment: the choice and every action's score
"""
import argparse
import errno
import json
import os
import sys
import threading
import time

from . import __version__


def _brain(args):
    from . import config
    from .brain import Brain
    cfg = config.load(getattr(args, "dir", "."))
    memory = getattr(args, "memory", None) or (os.path.join(getattr(args, "dir", "."), cfg["memory"]) if cfg.get("memory") else None)
    if os.environ.get("KINLOOM_SCRIPT") and not getattr(args, "memory", None):
        memory = None      # a scripted model (tests, replays) never writes into the game's real memory
    return Brain(memory_path=memory, folder=getattr(args, "dir", ".")), cfg


def _voice_line(brain):
    v = getattr(brain, "voice", None)
    if v is None:
        return "none: text only (ELEVENLABS_API_KEY or OPENAI_API_KEY gives voices; KINLOOM_VOICE=system the system's)"
    return v.describe()


NO_MODEL = ("Two ways, your choice: an API key in your environment (ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, or "
            "OPENAI_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY... with KINLOOM_MODEL), "
            "or your coding agent's subscription: kinloom use claude-code (or codex, gemini-cli, opencode).")


def _describe(brain):
    from .providers import missing_model
    s = brain.status()
    p = brain.provider
    if s["mode"] == "online" and getattr(p, "kind", None) and hasattr(p, "missing"):     # a coding agent
        if p.missing:
            return ("chosen: %s, but %s. Characters answer offline until it is found (kinloom use key: an API key "
                    "instead)." % (p.kind, p.missing))
        return "online with %s (%s): your coding agent's subscription answers" % (p.kind, p.model or "its default model")
    if s["mode"] == "online":
        extra = ["%s: %s" % (k, v) for k, v in sorted((s.get("models") or {}).items())]
        if s.get("rating"):
            extra.append("rating: %s" % s["rating"])
        return "online with %s (%s)%s" % (s["provider"], s["model"], " [%s]" % ", ".join(extra) if extra else "")
    var = missing_model()
    if var:
        return ("offline: %s is set but no model is named. Set KINLOOM_MODEL to a model of that service (Kinloom never "
                "guesses a model name). Until then characters only say the lines and examples your game gives." % var)
    from .harness import found
    agents = found()
    return ("offline: no model yet. Characters only say the lines and examples your game gives: no AI yet. " + NO_MODEL +
            (" Installed here: %s." % ", ".join(agents) if agents else ""))


def cmd_serve(args):
    from .server import make_server
    brain, cfg = _brain(args)
    port = args.port or (int(os.environ["PORT"]) if os.environ.get("PORT", "").isdigit() else None) or cfg.get("port") or 7717
    host = "0.0.0.0" if args.public else args.host
    token = args.token or os.environ.get("KINLOOM_SERVER_TOKEN")
    player_token = args.player_token or os.environ.get("KINLOOM_PLAYER_TOKEN")
    if args.public and not token:
        print("error: --public needs --token (or KINLOOM_SERVER_TOKEN) so only your game can use your key", file=sys.stderr)
        return 2
    trust_proxy = args.trust_proxy or os.environ.get("KINLOOM_TRUST_PROXY", "").lower() in ("1", "true", "yes")
    player_can = [v.strip() for item in (args.player_can or []) + [os.environ.get("KINLOOM_PLAYER_CAN", "")]
                  for v in item.split(",") if v.strip()] or None        # None: everything in the player's session
    if args.max_cost_per_hour is not None:
        brain.max_cost_per_hour = args.max_cost_per_hour
    if args.max_cost_per_day is not None:
        brain.max_cost_per_day = args.max_cost_per_day
    if (brain.max_cost_per_hour is not None or brain.max_cost_per_day is not None) and not brain.prices:
        print("warning: cost caps need your prices in kinloom.json (\"prices\": {\"input\": ..., \"output\": ..., "
              "\"source\": ...}); without them the caps cannot be enforced", file=sys.stderr)
    try:
        server = make_server(brain, host, port, token, args.public, args.allow_origin, player_token,
                             args.rate_per_session, args.rate_per_ip, trust_proxy, player_can,
                             max_connections=args.max_connections)
    except ValueError as e:
        brain.close()
        print("error: %s" % e, file=sys.stderr)
        return 2
    except OSError as e:
        if getattr(args, "open", False) and _is_kinloom(port):
            brain.close()
            print("Kinloom is already running on port %d: opening http://localhost:%d/talk" % (port, port))
            _open_page("http://localhost:%d/talk" % port)
            return 0
        print("error: port %d is busy (%s). Is kinloom serve already running? Use --port." % (port, e), file=sys.stderr)
        return 1
    print("Kinloom %s serving on http://%s:%d  (dashboard: http://localhost:%d/)" % (__version__, host, port, port))
    print("model: " + _describe(brain))
    print("voice: " + _voice_line(brain))
    if brain.memory.path:
        print("memory: " + os.path.abspath(brain.memory.path))
    print("Ctrl+C to stop\n")
    declare = getattr(args, "declare", None)
    if declare:                                  # kinloom talk NAME "who they are" --web
        name, soul, language, voice = declare
        brain.character("talk", name, soul=soul or True, language=language or None, voice=voice or None,
                        offline="(no model: %s stays silent. Set a key for real conversations.)" % name)
    if getattr(args, "open", False):
        page = "http://localhost:%d/talk%s" % (port, ("#token=" + token) if token else "")
        print("talk to your characters: " + page)
        threading.Timer(0.4, _open_page, [page]).start()

    def show(entry):
        if entry["kind"] in ("say", "chat", "decide", "act", "create", "event", "refused", "budget", "error", "character"):
            print("%s  %-9s %-10s %s" % (time.strftime("%H:%M:%S"), entry["kind"], str(entry["name"])[:10], str(entry["text"])[:140]))
            sys.stdout.flush()

    if not args.quiet:
        brain.listeners.append(show)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        brain.close()
    return 0


def _is_kinloom(port):
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/v1/status" % port, timeout=1) as r:
            return "mode" in json.loads(r.read().decode("utf-8"))
    except Exception:  # not Kinloom, or not answering
        return False


def _open_page(url):
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:  # no browser here: the URL is printed anyway
        pass


def _server_get(port, path):
    import urllib.request
    token = os.environ.get("KINLOOM_SERVER_TOKEN")
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), headers={"Authorization": "Bearer " + token} if token else {})
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def _line(e):
    return "%s  %-8s %-12s %s" % (time.strftime("%H:%M:%S", time.localtime(e.get("time", 0))), e.get("kind", ""),
                                   str(e.get("name", ""))[:12], str(e.get("text", "")).replace("\n", " ")[:160])


def summarize(entries, stats, seconds=None):
    """What the AI did during a run, for the developer's coding agent: counts, problems, cost (and, with declared
    prices and a run of a minute or more, the cost of an hour of play at that pace: what one player costs)."""
    kinds = {}
    for e in entries:
        kinds[e.get("kind")] = kinds.get(e.get("kind"), 0) + 1
    used = ", ".join("%s %d" % (k, kinds[k]) for k in ("chat", "say", "decide", "act", "create", "mind", "think", "event",
                                                        "soul", "character") if kinds.get(k))
    out = ["", "Kinloom during this run: %s" % (used or "no call reached Kinloom (is the client pointed at this server?)"),
           "model calls: %d (%d failed), offline answers: %d, cost: %s" % (
               stats.get("calls", 0), stats.get("failures", 0), stats.get("offline_answers", 0),
               "$%.4f" % stats["cost"] if stats.get("cost") is not None else "set prices in kinloom.json to see it")]
    if stats.get("cost") is not None and seconds and seconds >= 60:
        out.append("at this pace: about $%.3f per hour of play, for one player (%.0f s played)" % (
            stats["cost"] * 3600.0 / seconds, seconds))
    problems = [e for e in entries if e.get("kind") in ("error", "refused", "budget", "cut", "empty")]
    if problems:
        out.append("to look at (%d):" % len(problems))
        out += ["  " + _line(e) for e in problems[-8:]]
    names = sorted({str(e.get("name")) for e in entries if e.get("kind") in ("chat", "say", "decide", "act")})
    if names:
        out.append("characters that spoke or acted: " + ", ".join(names[:20]))
    return "\n".join(out)


def cmd_run(args):
    """Runs the game with a Kinloom server (reuses one already running), then prints what the AI did."""
    import shutil
    import subprocess
    command = [c for c in args.command if c != "--"]
    if not command:
        print("usage: kinloom run -- <the command that starts your game>, e.g. kinloom run -- python main.py", file=sys.stderr)
        return 2
    exe = shutil.which(command[0])
    if exe:
        command[0] = exe
    brain, cfg = _brain(args)
    port = args.port or cfg.get("port") or 7717
    server = None
    if _is_kinloom(port):
        brain.close()
        brain = None
        started = time.time()
        print("kinloom: using the server already running on port %d" % port)
    else:
        from .server import make_server
        try:
            server = make_server(brain, "127.0.0.1", port)
        except OSError as e:
            print("error: port %d is busy (%s); use --port" % (port, e), file=sys.stderr)
            return 1
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print("kinloom: serving on http://127.0.0.1:%d (%s)" % (port, _describe(brain)))
    sys.stdout.flush()
    import tempfile
    fd, run_log = tempfile.mkstemp(prefix="kinloom-run-", suffix=".jsonl")
    os.close(fd)
    played = time.time()
    try:
        code = subprocess.call(command, env=dict(os.environ, KINLOOM_TEST_PORT=str(port), KINLOOM_RUN_LOG=run_log))
    except OSError as e:
        print("error: could not start %s (%s)" % (command[0], e), file=sys.stderr)
        code = 127
    except KeyboardInterrupt:
        code = 130
    played = time.time() - played
    game = _read_run_log(run_log)              # what a Python game did in its own process
    if brain is not None:
        brain.wait_idle(5)
        print(summarize(brain.journal(500) + game, _add_stats(brain.stats(), game), played))
        server.shutdown()
        brain.close()
    else:
        entries = [e for e in _server_get(port, "/v1/journal?n=500").get("entries", []) if e.get("time", 0) >= started - 1]
        status = _server_get(port, "/v1/status")
        stats = dict(status.get("stats") or {}, calls=sum(1 for e in entries if e.get("kind") == "call"),
                     failures=sum(1 for e in entries if e.get("kind") == "call" and "failed" in str(e.get("text"))))
        print(summarize(entries + game, _add_stats(stats, game), played))
    return code


def _read_run_log(path):
    entries = []
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    try:
        os.remove(path)
    except OSError:
        pass
    return entries


def _add_stats(stats, entries):
    """Server stats plus what the game's own process logged."""
    out = dict(stats)
    calls = [e for e in entries if e.get("kind") == "call"]
    out["calls"] = out.get("calls", 0) + len(calls)
    out["failures"] = out.get("failures", 0) + sum(1 for e in calls if "failed" in str(e.get("text")))
    out["offline_answers"] = out.get("offline_answers", 0) + sum(1 for e in entries if e.get("offline"))
    return out


def _port(folder, given=None):
    """The port given, else kinloom.json's, else 7717 (as `kinloom serve` and `kinloom run` choose it)."""
    if given:
        return given
    from . import config
    try:
        return config.load(folder or ".").get("port") or 7717
    except config.ConfigError:
        return 7717


def cmd_log(args):
    port = _port(args.dir, args.port)
    try:
        entries = _server_get(port, "/v1/journal?n=%d" % max(1, min(500, args.n))).get("entries", [])
    except Exception:
        print("no Kinloom server on port %d (start it with `kinloom serve`, or run the game with `kinloom run -- ...`)" % port)
        return 1
    for e in entries:
        print(_line(e))
    if not args.follow:
        return 0
    import urllib.request
    token = os.environ.get("KINLOOM_SERVER_TOKEN")
    req = urllib.request.Request("http://127.0.0.1:%d/v1/stream" % port, headers={"Authorization": "Bearer " + token} if token else {})
    try:
        with urllib.request.urlopen(req) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data: "):
                    print(_line(json.loads(line[6:])))
                    sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_home(args):
    """`kinloom` alone: what is here, what works, what to ask the coding agent."""
    from . import config
    from . import init as _init
    folder = "."
    print("Kinloom %s" % __version__)
    try:
        cfg = config.load(folder)
    except config.ConfigError as e:
        print("kinloom.json: ERROR %s" % e)
        return 1
    brain, _ = _brain(argparse.Namespace(dir=folder, memory=None))
    print("model: " + _describe(brain))
    print("voice: " + _voice_line(brain))
    brain.close()
    chars = cfg.get("characters") if isinstance(cfg.get("characters"), dict) else {}
    print("game: %s%s" % (_init.detect(folder), (", characters in kinloom.json: " + ", ".join(sorted(chars))) if chars else ""))
    port = cfg.get("port") or 7717
    print("server: %s" % ("running on port %d" % port if _is_kinloom(port) else "not running (kinloom serve, or kinloom run -- <game>)"))
    print("""
Ask your coding agent, in plain words, e.g.:
  "the weather follows how I play"      "generate each new level"      "the enemies pick their tactics"
  "a blacksmith I can talk to, who gives items to people she likes"
or type /kinloom <request> (Claude Code, Cursor, Gemini CLI, opencode). It uses kinloom add / recipe / run -- <game>.
Set up a new game first: kinloom init. Hear the voice: kinloom speak "hello".""")
    return 0


def _terminal(stream):
    """A person's terminal: not a pipe or a file, nor Windows' NUL (a character device Python calls a tty)."""
    try:
        if not stream.isatty():
            return False
        if os.name != "nt":
            return True
        import ctypes
        import msvcrt
        mode = ctypes.c_ulong()
        return bool(ctypes.windll.kernel32.GetConsoleMode(msvcrt.get_osfhandle(stream.fileno()), ctypes.byref(mode)))
    except (AttributeError, ImportError, OSError, ValueError):
        return False


def cmd_init(args):
    from . import init as _init
    if not args.yes and not args.engine and _terminal(sys.stdin) and _terminal(sys.stdout):
        return _init.wizard(args.dir, agents=args.agents)
    return _init.run(args.dir, args.engine, args.agents or "auto")


def cmd_add(args):
    from .add import add
    try:
        print(add(args.dir, args.name, args.soul, args.tools, args.trust, args.offline, args.language, args.strict,
                  args.lore, args.engine, args.voice, args.max_chars))
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    return 0


def cmd_talk(args):
    """A conversation in the terminal: the character speaks first; /soul shows who they are, /quit leaves."""
    brain, _ = _brain(args)
    print("model: " + _describe(brain))
    print("voice: " + _voice_line(brain))
    session = "talk"
    brain.character(session, args.name, soul=args.soul or True, language=args.language, voice=args.voice or None,
                    offline="(no model: %s stays silent. Set a key for real conversations.)" % args.name)
    me = args.speaker
    aloud = bool(args.voice) and brain.voice is not None
    if args.voice and brain.voice is None:
        print("(no voice here: replies are only written. %s)" % _voice_line(brain))

    def said(text):
        sys.stdout.write(text)
        sys.stdout.flush()

    def turn(message):
        sys.stdout.write("\n%s: " % args.name)
        streamed = []
        reply = brain.chat(session, args.name, message, speaker=me, stream=lambda p: (streamed.append(p), said(p)))
        if not streamed:
            said(reply)
        soul = brain.soul(session, args.name)
        print("   [%s, feels %+.2f toward %s]" % (soul["mood"]["word"], brain.opinion(session, args.name, me), me))
        if aloud and reply and not reply.startswith("(no model"):
            from .voice import play
            audio = brain.speak(session, args.name, reply)
            if audio is not None:
                play(audio.path)
        for tool, a in brain.act(session, args.name, think=False):
            print("   -> %s %s" % (tool, json.dumps(a)))

    print("(type to talk; /soul: who they are; /quit: leave)")
    turn("")
    while True:
        try:
            line = input("\n%s: " % me).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line in ("/quit", "/exit"):
            break
        if line == "/soul":
            print(json.dumps(brain.soul(session, args.name), indent=1, ensure_ascii=False))
            continue
        turn(line)
    brain.close()
    return 0


def cmd_speak(args):
    """kinloom speak "text": the line said aloud, to hear what the game's characters will sound like."""
    import shutil
    from .voice import play
    brain, _ = _brain(args)
    print("voice: " + _voice_line(brain))
    if brain.voice is None:
        brain.close()
        return 1
    text = " ".join(args.text)
    if args.name or args.voice:
        brain.character("speak", args.name or "voice", voice=args.voice or None)
    start = time.monotonic()
    audio = brain.speak("speak", args.name or ("voice" if args.voice else None), text)
    if audio is None:
        err = [e["text"] for e in brain.journal(10) if e["kind"] in ("error", "refused", "budget")]
        print("not spoken: %s" % (err[-1] if err else "no voice answered"))
        brain.close()
        return 1
    print("%s  (%.1f s of audio, made in %.2f s%s)" % (audio.path, audio.seconds, time.monotonic() - start,
                                                     ", from the cache" if audio.cached else ""))
    if args.out:
        shutil.copyfile(audio.path, args.out)
        print("copied to %s" % args.out)
    if not args.no_play and not play(audio.path):
        print("(no audio player found here: open the file above)")
    brain.close()
    return 0


def cmd_try(args):
    brain, _ = _brain(args)
    print("model: " + _describe(brain))
    print("voice: " + _voice_line(brain))
    session = "try"
    brain.character(session, args.name, args.personality or "", lines=args.line or None, offline=args.offline)
    facts = json.loads(args.facts) if args.facts else {}
    shown = False
    if args.chat:
        start = time.monotonic()
        print("%s: %s   (%.2f s)" % (args.name, brain.chat(session, args.name, args.chat, facts) or "(nothing)", time.monotonic() - start))
        shown = True
    if args.decide:
        brain.decide(session, args.name, facts, json.loads(args.decide))
        brain.wait_idle(20)
        print("%s decides: %s" % (args.name, json.dumps(brain.decide(session, args.name, facts, json.loads(args.decide)))))
        shown = True
    if args.create:
        example = json.loads(args.example) if args.example else "a short text"
        print("created: %s" % json.dumps(brain.create(session, args.create, example, facts), ensure_ascii=False))
        shown = True
    if args.event or not shown:
        event = args.event or "something happens"
        brain._refill(session, brain._char(session, args.name), event, sorted(facts))
        brain.wait_idle(20)
        for _ in range(args.n):
            line = brain.say(session, args.name, event, facts)
            if not line and brain.provider is None:
                print("%s: (offline and no lines to use: set an API key, `kinloom use claude-code` (your agent's plan), or give "
                      "offline lines with --line \"{who} takes the lead!\")" % args.name)
                break
            print("%s: %s" % (args.name, line or "(nothing)"))
    s = brain.stats()
    print("\n%d call(s), %d tokens%s" % (s["calls"], s["input_tokens"] + s["output_tokens"],
                                         (", $%.5f" % s["cost"]) if s["cost"] is not None else ""))
    brain.close()
    return 0


def cmd_doctor(args):
    from . import config
    ok = True
    try:
        cfg = config.load(args.dir)
        print("config: %s" % (cfg.get("_path") or "none (not needed)"))
    except config.ConfigError as e:
        print("config: ERROR %s" % e)
        return 1
    from .providers import HOSTED
    from .harness import found
    for var in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY") + tuple(v for v, _, _ in HOSTED) + \
            ("KINLOOM_BASE_URL", "KINLOOM_MODEL", "KINLOOM_HARNESS"):
        if os.environ.get(var):
            print("found %s (%s)" % (var, "set, not shown" if "KEY" in var else os.environ[var]))
    agents = found()
    print("coding agents installed: %s" % (", ".join(agents) if agents else "none found on PATH"))
    from .mod import rea_command
    rea = rea_command()
    print("mods (kinloom hooks): %s" % ("REA found (%s)" % " ".join(rea) if rea else
                                         "REA not found (optional: only to read a .NET game you have no source of)"))
    brain, _ = _brain(args)
    print("model: " + _describe(brain))
    print("voice: " + _voice_line(brain))
    from .providers import missing_model
    unused = missing_model()
    if unused and brain.provider is not None:
        print("note: %s is set but unused (no KINLOOM_MODEL names a model of that service)" % unused)
    if brain.provider is not None:
        start = time.monotonic()
        r = brain.provider.complete("Kinloom task: ping. Answer with the JSON object {\"ok\": true}.", "ping", json_mode=True,
                                    max_tokens=20, timeout=15)
        print("ping: %s in %.2f s" % ("ok" if r.ok else "FAILED (%s)" % r.error, time.monotonic() - start))
        for switch in getattr(brain.provider, "switched", []):
            print("switched: %s" % switch)
        if r.ok and getattr(brain.provider, "switched", None):
            print("model now: %s" % _describe(brain))
        ok = r.ok
    brain.close()
    return 0 if ok else 1


def cmd_hooks(args):
    from . import mod
    if args.guide or not args.game:
        print(mod.guide())
        return 0
    return mod.run(args.game, args.json, args.top)


def cmd_use(args):
    """Chooses where answers come from: the coding agent's subscription, or an API key from the environment."""
    from . import config
    from .harness import KINDS, Harness
    folder = args.dir
    if args.what == "key":
        try:
            path = config.update(folder, provider=None, model=args.model, command=None, pool=None)
        except config.ConfigError as e:
            print("error: %s" % e, file=sys.stderr)
            return 1
        print("%s: an API key from your environment answers (no \"provider\" set)." % path)
    else:
        if args.what == "command" and not args.command:
            print("error: kinloom use command -- <program> [args...] (the prompt goes to its stdin)", file=sys.stderr)
            return 2
        try:
            h = Harness(args.what, args.model, args.command or None, pool=0)
            path = config.update(folder, provider=args.what, model=args.model, command=args.command or None)
        except (ValueError, config.ConfigError) as e:
            print("error: %s" % e, file=sys.stderr)
            return 2
        print("%s: %s answers%s, with your own plan (no API key needed)." % (path, args.what, (" (%s)" % args.model) if args.model else ""))
        if h.missing:
            print("warning: %s. Until it is, characters answer offline." % h.missing)
        else:
            print("Each call starts the agent (about 2 s with Claude Code once started ahead, more for the others). "
                  "For players of a shipped game, use an API key on a server (kinloom deploy).")
        if args.what in KINDS and args.what != "claude-code":
            print("note: Kinloom's %s setup follows its --help; check it once with `kinloom doctor`." % args.what)
    return 0


def cmd_test(args):
    from . import testing
    if args.new:
        path = os.path.join(args.dir, testing.FILE)
        if os.path.exists(path):
            print("%s already exists: nothing written" % path)
            return 1
        from . import config
        try:
            chars = config.load(args.dir).get("characters")
        except config.ConfigError:
            chars = None
        name = next(iter(chars)) if isinstance(chars, dict) and chars else "NAME"
        text = json.dumps(testing.example(), indent=2).replace('"NAME"', json.dumps(name))
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("wrote %s%s. Run: kinloom test" % (path, "" if name != "NAME" else " (replace NAME with a character)"))
        return 0
    return testing.main(args.dir, args.file, args.record, args.replay, args.offline, args.json, args.wait)


def cmd_bundle(args):
    from . import bundle
    print("building kinloom with PyInstaller (a minute or two)...")
    code, message = bundle.build(args.dir, args.out)
    print(message)
    return code


def cmd_probe(args):
    from . import probe
    return probe.main(args.dir, args.name, args.soul, args.rounds, args.json)


def cmd_guide(args):
    from . import init, mcp
    engine = args.engine or init.detect(args.dir)
    text = init.guide(engine, mcp._client_path(args.dir, engine), args.dir)
    print(text if args.short else text + "\n---\n\n" + init.cookbook())
    return 0


def cmd_demo(args):
    from . import demo
    print("A skirmish: %d units, each against a turret, 30 s per round. They start with the rules anyone writes first:"
          % args.units)
    print("  " + json.dumps(demo.NAIVE))
    print("The game only reports how each choice went (damage dealt minus taken; +1 win, -1 loss or time out).")
    print("No key, no model: Kinloom learns from the rewards (credit, evidence, mutations).\n")
    r = demo.run(minutes=args.minutes, units=args.units, seed=args.seed)
    rows = r["rows"]
    print("\nwon %.0f%% in the first minute, %.0f%% in the last; %d decisions in %.1f s (the fights, thinking and learning), "
          "%d model calls" % (100 * rows[0]["win"], 100 * rows[-1]["win"], r["thinks"], r["seconds"], r["model_calls"]))
    print("\nthe rules it plays now:")
    for action, spec in r["best_rules"].items():
        if spec["score"] > 0:
            print("  %-11s score %.2f when %s" % (action, spec["score"], " and ".join(spec["when"]) or "always"))
    return 0


def cmd_think(args):
    from . import minds
    try:
        with open(args.mind, encoding="utf-8-sig") as f:
            spec = json.load(f)
    except OSError as e:
        print("error: cannot read %s (%s)" % (args.mind, e.strerror or e), file=sys.stderr)
        return 2
    missing = [k for k in ("senses", "actions") if not isinstance(spec, dict) or not isinstance(spec.get(k), dict)]
    if missing:
        print('error: %s needs %s, e.g. {"senses": {"hp": [0, 1]}, "actions": {"charge": {}, "retreat": {}}, '
              '"rules": {"retreat": ["hp low"]}}' % (args.mind, " and ".join('"%s" (an object)' % k for k in missing)),
              file=sys.stderr)
        return 2
    decl = minds.Declaration(spec.get("name", "mind"), spec.get("personality", ""), spec["senses"], spec["actions"],
                             spec.get("rules"), 1)
    for e in decl.rule_errors:
        print("rule error: %s" % e)
    senses = json.loads(args.senses)
    if not isinstance(senses, dict):
        print('error: the moment is a JSON object of senses, e.g. \'{"hp": 0.2}\'', file=sys.stderr)
        return 2
    e = minds.Mind(decl).explain(senses)
    print("choice: %s" % e["action"])
    for action, sc in sorted(e["scores"].items(), key=lambda kv: -kv[1]["score"]):
        rules = ", ".join("%s (%.2f)" % (r, v) for r, v in zip(sc["rules"], sc["values"])) or "no rules"
        print("  %-12s %.3f  %s" % (action, sc["score"], rules))
    return 1 if decl.rule_errors else 0


def _talk_web(a):
    """kinloom talk NAME "who they are" --web: the server with the Talk page, NAME already there."""
    args = ["serve", "--open", "--dir", a.dir] + (["--memory", a.memory] if a.memory else [])
    ns = main_parser().parse_args(args)
    ns.declare = (a.name, a.soul, a.language or "", a.voice or "")
    return cmd_serve(ns)


def _safe_output():
    """Output never crashes on a character the console cannot show (Windows: cp1252). Piped output (coding agents,
    logs) is UTF-8; a console keeps its encoding and replaces what it cannot show."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            tty = stream.isatty()
        except (OSError, ValueError):
            tty = False
        try:
            reconfigure(errors="replace") if tty else reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (OSError, ValueError):
            pass


def _stdout_gone():
    """True when standard output can no longer be written (its reader left)."""
    try:
        sys.stdout.flush()
    except (OSError, ValueError):
        return True
    return False


def _reader_left():
    """The reader of our output left: point stdout at devnull so the exit flush adds no traceback."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError):
        pass
    return 1


def _port_arg(text):
    """--port: a TCP port number (argparse says what is wrong instead of a bind traceback)."""
    try:
        port = int(text)
    except ValueError:
        port = -1
    if not 0 <= port < 65536:
        raise argparse.ArgumentTypeError("%r is not a port (0-65535; 0: any free one)" % text)
    return port


def main_parser():
    """The `kinloom` command line."""
    ap = argparse.ArgumentParser(prog="kinloom", description="Deep AI in any game, any engine, any model, in minutes.")
    ap.add_argument("--version", action="version", version="kinloom " + __version__)
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="the local server every engine talks to, with a live dashboard")
    s.add_argument("--port", type=_port_arg)
    s.add_argument("--host", default="127.0.0.1", help="the address to listen on; beyond this machine it needs --token")
    s.add_argument("--public", action="store_true", help="listen on all interfaces (online server; needs --token)")
    s.add_argument("--token", help="secret the game must send (Authorization: Bearer <token>)")
    s.add_argument("--memory", help="memory file (default .kinloom/memory.json)")
    s.add_argument("--allow-origin", action="append", default=[], metavar="ORIGIN",
                   help="also accept web pages from this origin, e.g. https://html.itch.zone, or null (file:// pages; "
                        "needs --token: any website can send origin null)")
    s.add_argument("--dir", default=".")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(fn=cmd_serve)

    s.add_argument("--open", action="store_true", help="open the Talk page in the browser")
    s.add_argument("--player-token", help="the secret a shipped game carries: plays, cannot read the journal "
                                          "(or KINLOOM_PLAYER_TOKEN)")
    s.add_argument("--rate-per-session", type=int, default=30, help="requests that start model work, a minute per "
                   "player session (player token only; default 30; polling decide/act has 20 times more)")
    s.add_argument("--rate-per-ip", type=int, default=60, help="the same per address (player token only; default 60)")
    s.add_argument("--trust-proxy", action="store_true", help="behind a proxy (Railway, Fly.io...): the player's address "
                   "is read from Fly-Client-IP or X-Forwarded-For (or KINLOOM_TRUST_PROXY=1)")
    s.add_argument("--player-can", action="append", default=[], metavar="WHAT",
                   help="what the player token keeps of feel, remember, state, steer, tools, lore and several speakers "
                        "per session (speakers): default all (a single-player game is the authority of its own "
                        "session); none for a shared world run by your own game server with the admin token; "
                        "comma-separated or repeated (or KINLOOM_PLAYER_CAN)")
    s.add_argument("--max-connections", type=int, default=256, help="connections served at once (default 256)")
    s.add_argument("--max-cost-per-hour", type=float, help="dollars; needs prices in kinloom.json")
    s.add_argument("--max-cost-per-day", type=float, help="dollars; needs prices in kinloom.json")

    dp = sub.add_parser("deploy", help="prepare an online server for a shipped game (Dockerfile + guide; deploys nothing)")
    dp.add_argument("dir", nargs="?", default="kinloom-deploy")
    dp.set_defaults(fn=lambda a: __import__("kinloom.deploy", fromlist=["run"]).run(a.dir))

    tk = sub.add_parser("talk", help="talk to a character in the terminal (the character speaks first)")
    tk.add_argument("name")
    tk.add_argument("soul", nargs="?", default="", help="who they are, in one sentence")
    tk.add_argument("--speaker", default="player", help="your name")
    tk.add_argument("--language")
    tk.add_argument("--dir", default=".")
    tk.add_argument("--memory", help="memory file (they remember you between runs)")
    tk.add_argument("--web", action="store_true", help="talk in the browser instead (starts the server, opens the page)")
    tk.add_argument("--voice", nargs="?", const="natural", default="",
                    help='say the replies aloud (optionally how they sound, e.g. --voice "low, warm")')
    tk.set_defaults(fn=lambda a: _talk_web(a) if a.web else cmd_talk(a))

    sp = sub.add_parser("speak", help="say a line aloud with the voice Kinloom found (a key, or the system's): check your setup")
    sp.add_argument("text", nargs="+")
    sp.add_argument("--name", help="whose voice (a character of kinloom.json, or any name)")
    sp.add_argument("--voice", default="", help='how they sound, e.g. "low, tired, warm"')
    sp.add_argument("--out", help="also copy the WAV here")
    sp.add_argument("--no-play", action="store_true", help="only write the file")
    sp.add_argument("--dir", default=".")
    sp.set_defaults(fn=cmd_speak)

    ad = sub.add_parser("add", help="a character the player can talk to, written into kinloom.json, with the code to call it")
    ad.add_argument("name", nargs="?", default="")
    ad.add_argument("soul", nargs="?", default="", help="who they are, in one sentence")
    ad.add_argument("--tools", default="", help='what they can do in the game, e.g. "give(item), follow, refuse_service"')
    ad.add_argument("--trust", action="append", default=[], help="tool=feeling: a tool only for people they like that much, e.g. give=0.3")
    ad.add_argument("--offline", default="", help="what they say with no model")
    ad.add_argument("--language", help='the language they speak; "auto": the language of whoever talks to them')
    ad.add_argument("--strict", action="store_true", help="never make up names, places or events")
    ad.add_argument("--voice", default="", help='how they sound when they speak, e.g. "low, tired, warm"')
    ad.add_argument("--max-chars", type=int, help="the characters their text box holds: replies never go past it")
    ad.add_argument("--lore", action="append", default=[], help="a world fact every character treats as true (repeatable)")
    ad.add_argument("--dir", default=".")
    ad.add_argument("--engine")
    ad.set_defaults(fn=cmd_add)

    rc = sub.add_parser("recipe", help="any request -> the call and the patterns for it, in this game's language")
    rc.add_argument("request", nargs="+")
    rc.add_argument("--dir", default=".")
    rc.add_argument("--engine")
    rc.set_defaults(fn=lambda a: print(__import__("kinloom.recipe", fromlist=["recipe"]).recipe(
        " ".join(a.request), a.engine or __import__("kinloom.init", fromlist=["detect"]).detect(a.dir))) or 0)

    hk = sub.add_parser("hooks", help="a mod: where Kinloom plugs into a .NET game you have no source of (reads it "
                                      "with REA, never runs it); --guide: mods of every kind")
    hk.add_argument("game", nargs="?", help="the game folder, or its .dll / .exe")
    hk.add_argument("--top", type=int, default=8)
    hk.add_argument("--json", action="store_true")
    hk.add_argument("--guide", action="store_true", help="print the mod guide (mod APIs, .NET, IL2CPP, native, web)")
    hk.set_defaults(fn=cmd_hooks)

    rn = sub.add_parser("run", help="run the game with Kinloom, then see what the AI did: kinloom run -- <game command>")
    rn.add_argument("command", nargs=argparse.REMAINDER)
    rn.add_argument("--port", type=_port_arg)
    rn.add_argument("--dir", default=".")
    rn.add_argument("--memory")
    rn.set_defaults(fn=cmd_run)

    lg = sub.add_parser("log", help="what the running server did, as text")
    lg.add_argument("-n", type=int, default=40)
    lg.add_argument("--follow", action="store_true")
    lg.add_argument("--port", type=_port_arg, help="default: kinloom.json's port, else 7717")
    lg.add_argument("--dir", default=".")
    lg.set_defaults(fn=cmd_log)

    t = sub.add_parser("try", help="hear a character in the terminal")
    t.add_argument("name")
    t.add_argument("personality", nargs="?", default="")
    t.add_argument("--event")
    t.add_argument("--facts", help='JSON, e.g. \'{"who": "BLAZE"}\'')
    t.add_argument("--chat")
    t.add_argument("--decide", help='choices as JSON, e.g. \'{"strategy": ["attack", "block"]}\'')
    t.add_argument("--create")
    t.add_argument("--example", help="JSON example for --create")
    t.add_argument("--line", action="append", help='an offline line, e.g. --line "{who} takes the lead!" (repeatable)')
    t.add_argument("--offline", help="the offline chat reply")
    t.add_argument("-n", type=int, default=3)
    t.add_argument("--dir", default=".")
    t.set_defaults(fn=cmd_try)

    bu = sub.add_parser("bundle", help="Kinloom as a program that needs no Python (for Godot, Unity, Unreal... games)")
    bu.add_argument("--out", default="kinloom-server")
    bu.add_argument("--dir", default=".")
    bu.set_defaults(fn=cmd_bundle)
    te = sub.add_parser("test", help="the game's AI checked like code: steps and checks in kinloom.tests.json")
    te.add_argument("file", nargs="?", default=None, help="default: kinloom.tests.json")
    te.add_argument("--dir", default=".")
    te.add_argument("--new", action="store_true", help="write a starting kinloom.tests.json")
    te.add_argument("--record", metavar="FILE", help="keep the model's answers in FILE")
    te.add_argument("--replay", metavar="FILE", help="run on recorded answers: no model, no cost, same answers")
    te.add_argument("--offline", action="store_true", help="no model: the game's own lines and examples")
    te.add_argument("--json", action="store_true", help="the results as JSON (for coding agents)")
    te.add_argument("--wait", type=float, default=30.0, help="seconds to wait for background work (default 30)")
    te.set_defaults(fn=cmd_test)
    pr = sub.add_parser("probe", help="play a character like a tester would and report problems (uses the model)")
    pr.add_argument("name", help="a character of kinloom.json, or any name with --soul")
    pr.add_argument("--soul", default=None, help="who they are, for a character not in kinloom.json")
    pr.add_argument("--rounds", type=int, default=1, help="times each probe is played (default 1)")
    pr.add_argument("--dir", default=".")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(fn=cmd_probe)
    us = sub.add_parser("use", help="where answers come from: your coding agent's subscription (claude-code, codex, "
                                    "gemini-cli, opencode, command) or `key` (an API key from the environment)")
    us.add_argument("what", choices=["key", "claude-code", "codex", "gemini-cli", "opencode", "command"])
    us.add_argument("--model", default=None, help="the agent's model (e.g. haiku for Claude Code); default: its own")
    us.add_argument("--dir", default=".")
    us.set_defaults(fn=cmd_use, command=[])     # `kinloom use command -- tool --flag`: what follows -- (read below)
    d = sub.add_parser("doctor", help="check the model, key and config")
    d.add_argument("--dir", default=".")
    d.set_defaults(fn=cmd_doctor)

    g = sub.add_parser("guide", help="print the instructions for coding agents (the calls, rules, 39 patterns)")
    g.add_argument("engine", nargs="?", help="godot, unity, dotnet, web, python, love, unreal, other (default: detected)")
    g.add_argument("--dir", default=".")
    g.add_argument("--short", action="store_true", help="without the patterns")
    g.set_defaults(fn=cmd_guide)

    c = sub.add_parser("check", help="check the integration in a game folder (client, characters, await, keys, server)")
    c.add_argument("dir", nargs="?", default=".")
    c.add_argument("--url", default="http://127.0.0.1:7717")
    c.set_defaults(fn=lambda a: __import__("kinloom.check", fromlist=["run"]).run(a.dir, a.url))

    sh = sub.add_parser("ship", help="before a release: keys in the game, how players reach a model, offline answers, "
                                     "caps, rating; drafts the store's AI disclosure")
    sh.add_argument("dir", nargs="?", default=".")
    sh.add_argument("--disclosure", default="kinloom-ai-disclosure.md", help="where to write the draft (\"\": nowhere)")
    sh.set_defaults(fn=lambda a: __import__("kinloom.ship", fromlist=["run"]).run(a.dir, a.disclosure))

    i = sub.add_parser("init", help="set up a game folder: engine client + instructions for any coding agent")
    i.add_argument("dir", nargs="?", default=".")
    i.add_argument("--engine", help="force: godot, unity, dotnet, web, python, love, unreal, other")
    i.add_argument("--agents", choices=["auto", "all", "minimal"], default=None,
                   help="auto (default): AGENTS.md + the files of the agents found here; all: every agent's own file; "
                        "minimal: AGENTS.md, CLAUDE.md and the Claude skill")
    i.add_argument("--yes", action="store_true", help="no questions (agents and scripts never get questions anyway)")
    i.set_defaults(fn=cmd_init)

    m = sub.add_parser("mcp", help="MCP server on stdio for coding agents")
    m.add_argument("--dir", default=".")
    m.set_defaults(fn=lambda a: __import__("kinloom.mcp", fromlist=["serve"]).serve(a.dir))

    dm = sub.add_parser("demo", help="watch a mind learn to win a fight, offline, in seconds (no key)")
    dm.add_argument("--minutes", type=float, default=30.0, help="minutes of play to simulate (default 30)")
    dm.add_argument("--units", type=int, default=40)
    dm.add_argument("--seed", type=int, default=1)
    dm.set_defaults(fn=cmd_demo)

    th = sub.add_parser("think", help="run a mind on one moment: the choice and every action's score")
    th.add_argument("mind", help='a JSON file: {"senses": {...}, "actions": {...}, "rules": {...}}')
    th.add_argument("senses", help='the moment as JSON, e.g. \'{"hp": 0.2, "dist": 12}\'')
    th.set_defaults(fn=cmd_think)

    return ap


def main(argv=None):
    ap = main_parser()
    _safe_output()
    argv = list(sys.argv[1:] if argv is None else argv)
    program = []
    if argv[:1] == ["use"] and "--" in argv:     # the program for `use command` (argparse versions differ on "--")
        program = argv[argv.index("--") + 1:]
        argv = argv[:argv.index("--")]
    args = ap.parse_args(argv)
    if program:
        args.command = program
    if not getattr(args, "cmd", None):     # what is here and what to ask the coding agent
        return cmd_home(args)
    try:
        return args.fn(args) or 0
    except BrokenPipeError:   # `kinloom ... | head`: the reader left; no traceback (the Python docs' recipe)
        return _reader_left()
    except OSError as e:      # Windows: a pipe closed by its reader fails with EINVAL, not EPIPE
        if e.errno == errno.EINVAL and _stdout_gone():
            return _reader_left()
        raise
    except Exception as e:  # a friendly message instead of a traceback for configuration problems
        from .config import ConfigError
        if isinstance(e, (ConfigError, json.JSONDecodeError)):
            print("error: %s" % e, file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
