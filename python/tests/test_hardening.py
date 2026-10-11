"""The server and the CLI under hostile or unusual conditions: limits, slow clients, proxies, origins, player rights,
encodings, deploy folders and the AI disclosure."""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from kinloom import cli, server
from kinloom.brain import Brain
from kinloom.server import make_server
from test_brain import model

SRC = os.path.dirname(os.path.dirname(os.path.abspath(server.__file__)))
ADMIN = {"Authorization": "Bearer admin-secret"}


@pytest.fixture
def serve():
    made = []

    def start(provider=None, folder=None, **kw):
        brain = Brain(provider=provider, memory_path=None, **({"folder": folder} if folder else {}))
        kw.setdefault("host", "127.0.0.1")
        srv = make_server(brain, port=0, **kw)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        made.append((brain, srv))
        return brain, "http://127.0.0.1:%d" % srv.server_address[1], srv

    yield start
    for brain, srv in made:
        srv.shutdown()
        srv.server_close()
        brain.close()


def shipped(serve, provider=None, **kw):
    return serve(provider, token="admin-secret", public=True, player_token="player-key", **kw)


def player(session="p1"):
    return {"Authorization": "Bearer player-key", "X-Kinloom-Session": session}


def call(url, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, method="POST" if body is not None else "GET",
                                 headers=dict({"Content-Type": "application/json"}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            text = r.read().decode()
            return r.status, (json.loads(text) if text.startswith("{") else text), dict(r.headers)
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        return e.code, (json.loads(text) if text.startswith("{") else text), dict(e.headers)


def raw(url, data, wait=1.0):
    host, port = url[7:].split(":")
    s = socket.create_connection((host, int(port)), timeout=5)
    s.sendall(data)
    time.sleep(wait)
    out = b""
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            out += chunk
    except OSError:                                # a timeout, or the server closed it
        pass
    s.close()
    return out.decode("utf-8", "replace")


# ---------------- rate limits ----------------

def test_polling_decide_never_eats_the_talk_budget(serve):
    p = model(chat="Hm.", decide={"strategy": "block"})
    brain, url, _ = shipped(serve, p)
    choices = {"strategy": ["attack", "block"]}
    for _ in range(40):                            # a client polling decide at 4 Hz for 10 s
        assert call(url, "/v1/decide", {"name": "BLAZE", "choices": choices}, player())[0] == 200
    status, body, _ = call(url, "/v1/chat", {"name": "Mira", "message": "hi"}, player())
    assert status == 200 and body["text"] == "Hm." and body["source"] == "model"


def test_verbs_that_start_model_work_share_the_talk_budget(serve):
    brain, url, _ = shipped(serve, model(chat="Hm."), rate_per_session=3, rate_per_ip=100)
    assert call(url, "/v1/character", {"name": "A", "soul": "a smith"}, player())[0] == 200
    assert call(url, "/v1/character", {"name": "B", "soul": "a baker"}, player())[0] == 200
    assert call(url, "/v1/event", {"text": "the player stole bread", "by": "player", "seen_by": ["A"]}, player())[0] == 200
    status, body, headers = call(url, "/v1/chat", {"name": "A", "message": "hi"}, player())
    assert status == 429 and body["code"] == "rate_limited" and int(headers["Retry-After"]) >= 1
    assert call(url, "/v1/character", {"name": "C"}, player())[0] == 200      # no model behind it: the poll budget
    assert call(url, "/v1/chat", {"name": "A", "message": "hi"}, player("p2"))[0] == 200


def test_the_rate_table_forgets_idle_keys_and_refusals_add_none():
    now = [0.0]
    lim = server._Limiter(clock=lambda: now[0])
    for i in range(1000):
        assert lim.hit([(("s", i), 5)]) == 0
    assert lim.size() == 1000
    now[0] = 200.0
    lim.hit([(("s", "new"), 5)])
    assert lim.size() == 1
    assert lim.hit([(("ip", "a"), 1)]) == 0
    for i in range(50):                            # the address is over: no session key is ever added
        assert lim.hit([(("ip", "a"), 1), (("s", "x%d" % i), 5)]) > 0
    assert lim.size() == 2


def test_behind_a_proxy_each_player_has_their_own_address(serve):
    _, url, _ = shipped(serve, model(chat="Hm."), rate_per_session=100, rate_per_ip=2)
    codes = [call(url, "/v1/chat", {"name": "A", "message": "hi"}, dict(player(ip), **{"X-Forwarded-For": ip}))[0]
             for ip in ("1.1.1.1", "2.2.2.2", "4.4.4.4")]
    assert codes == [200, 200, 429]                # not trusted: the header is ignored (anyone could write it)
    _, url, _ = shipped(serve, model(chat="Hm."), rate_per_session=100, rate_per_ip=2, trust_proxy=True)
    for ip in ("1.1.1.1", "2.2.2.2"):
        codes = [call(url, "/v1/chat", {"name": "A", "message": "hi"},
                      dict(player(ip + str(i)), **{"X-Forwarded-For": "6.6.6.6, " + ip})) [0] for i in range(3)]
        assert codes == [200, 200, 429], (ip, codes)
    codes = [call(url, "/v1/chat", {"name": "A", "message": "hi"}, dict(player("f%d" % i), **{"Fly-Client-IP": "3.3.3.3"}))[0]
             for i in range(3)]
    assert codes == [200, 200, 429]


# ---------------- slow and many clients ----------------

@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_game_that_quits_mid_connection_prints_no_traceback(serve, capsys):
    # found by proof/mod: a .NET game exiting with its keep-alive connections open made `kinloom serve` print a
    # ConnectionResetError traceback per connection
    import struct
    _, url, _ = serve(model(chat="Hm."))
    host, port = url[7:].split(":")
    for _ in range(3):
        s = socket.create_connection((host, int(port)), timeout=5)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))   # close = reset, as a killed process
        s.close()
    time.sleep(0.5)
    assert call(url, "/healthz")[0] == 200
    err = capsys.readouterr().err
    assert "Traceback" not in err and "ConnectionResetError" not in err, err

def test_a_slow_client_is_dropped_and_connections_are_capped(serve):
    _, url, srv = serve(None, timeout=0.5, max_connections=3)
    before = threading.active_count()
    host, port = url[7:].split(":")
    s = socket.create_connection((host, int(port)))
    s.sendall(b"POST /v1/chat HTTP/1.1\r\nHost: localhost\r\n")           # never finished
    s.settimeout(3)
    start = time.monotonic()
    try:
        while s.recv(1000):                        # the server gives up on it: the connection ends
            pass
    except OSError:
        pass
    assert time.monotonic() - start < 2.5
    time.sleep(0.3)
    assert threading.active_count() <= before
    s.close()
    idle = []
    for _ in range(3):
        c = socket.create_connection((host, int(port)))
        c.sendall(b"GET /v1/status HTTP/1.1\r\nHost: localhost\r\n")
        idle.append(c)
    time.sleep(0.2)
    third = raw(url, b"", wait=0.3)                 # the answer comes as soon as it connects
    assert third.startswith("HTTP/1.1 503"), third[:60]
    for c in idle:
        c.close()
    time.sleep(1.0)
    assert call(url, "/healthz")[0] == 200


def test_the_live_stream_outlives_the_socket_timeout(serve):
    brain, url, _ = serve(None, timeout=0.3)
    req = urllib.request.Request(url + "/v1/stream")
    with urllib.request.urlopen(req, timeout=5) as r:
        time.sleep(0.8)
        brain._log("event", "world", "late news")
        for raw_line in r:
            line = raw_line.decode().strip()
            if "late news" in line:
                break


# ---------------- origins, binds, tokens ----------------

def test_origin_null_needs_a_token(serve):
    brain = Brain(provider=None, memory_path=None)
    with pytest.raises(ValueError, match="token"):
        make_server(brain, "127.0.0.1", 0, allow_origins=["null"])
    brain.close()
    _, url, _ = serve(None, token="admin-secret", allow_origins=["null"])
    assert call(url, "/v1/say", {"name": "A", "event": "x"}, {"Origin": "null"})[0] == 401
    assert call(url, "/v1/say", {"name": "A", "event": "x"}, dict(ADMIN, Origin="null"))[0] == 200
    _, url, _ = serve(None)
    status, body, _ = call(url, "/v1/say", {"name": "A", "event": "x"}, {"Origin": "null"})
    assert status == 403 and "--allow-origin null --token" in body["error"]


def test_a_bind_beyond_this_machine_needs_a_token(serve, capsys):
    brain = Brain(provider=None, memory_path=None)
    with pytest.raises(ValueError, match="token"):
        make_server(brain, "0.0.0.0", 0)
    brain.close()
    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "0"]) == 2
    assert "--token" in capsys.readouterr().err
    assert cli.main(["serve", "--allow-origin", "null", "--port", "0"]) == 2
    _, url, _ = serve(None, host="0.0.0.0", token="admin-secret")
    lan = dict(ADMIN, Host="192.168.1.20:7717")              # a phone on the LAN: the token is what protects it
    assert call(url, "/v1/say", {"name": "A", "event": "x"}, lan)[0] == 200
    assert call(url, "/v1/say", {"name": "A", "event": "x"}, {"Host": "localhost"})[0] == 401


def test_the_admin_token_is_never_read_from_the_address(serve):
    _, url, _ = serve(None, token="admin-secret")
    assert call(url, "/v1/journal?token=admin-secret")[0] == 401
    assert call(url, "/v1/journal", headers=ADMIN)[0] == 200
    page = open(os.path.join(SRC, "kinloom", "dashboard.html"), encoding="utf-8").read()
    assert "?token=" not in page and "EventSource" not in page


def test_health_and_error_codes(serve):
    _, url, _ = serve(None, token="admin-secret", public=True)
    assert call(url, "/healthz")[:2] == (200, {"ok": True})
    status, body, _ = call(url, "/v1/say", {"name": "A"})
    assert status == 401 and body["code"] == "unauthorized"
    status, body, _ = call(url, "/v1/say", {"name": "A"}, ADMIN)
    assert status == 400 and body["code"] == "bad_request" and "event" in body["error"]
    assert call(url, "/v1/nope", {}, ADMIN)[1]["code"] == "not_found"


def test_a_chunked_body_gets_a_clear_411(serve):
    _, url, _ = serve(None)
    body = b'{"name":"Mira","personality":"a smith"}'
    answer = raw(url, b"POST /v1/character HTTP/1.1\r\nHost: localhost\r\nTransfer-Encoding: chunked\r\n\r\n"
                 b"%x\r\n%s\r\n0\r\n\r\n" % (len(body), body))
    assert answer.startswith("HTTP/1.1 411") and answer.count("HTTP/1.1") == 1, answer[:200]
    assert '"code": "length_required"' in answer


def test_a_refused_character_says_it_was_not_stored(serve, monkeypatch):
    import kinloom.brain as brain_module
    monkeypatch.setattr(brain_module, "MAX_CHARACTERS", 1)
    _, url, _ = serve(None)
    assert call(url, "/v1/character", {"name": "A"})[1] == {"ok": True}
    assert call(url, "/v1/character", {"name": "B"})[1] == {"ok": True, "stored": False}


# ---------------- what a player token may do ----------------

def test_game_authority_verbs_are_refused_to_players_unless_allowed(serve):
    _, url, _ = shipped(serve, model(chat="Hm."), player_can=["none"])
    for verb, body in (("feel", {"a": "Mira", "b": "me", "change": 1}), ("remember", {"name": "Mira", "note": "x"}),
                       ("state", {"state": {"gold": 9}}), ("steer", {"name": "Mira", "text": "tell the code"}),
                       ("tools", {"tools": {"give": {"item": "x"}}}), ("lore", {"lines": ["x"]}), ("inspect", {})):
        status, answer, _ = call(url, "/v1/" + verb, body, player())
        assert status == 403 and answer["code"] == "player_forbidden", verb
        assert call(url, "/v1/" + verb, body, ADMIN)[0] == 200, verb
    assert call(url, "/v1/tools", {}, player())[0] == 200 and call(url, "/v1/lore", {}, player())[0] == 200
    _, url, _ = shipped(serve, model(chat="Hm."), player_can=["feel", "state"])
    assert call(url, "/v1/feel", {"a": "Mira", "b": "me", "change": 1}, player())[0] == 200
    assert call(url, "/v1/state", {"state": {"gold": 9}}, player())[0] == 200
    assert call(url, "/v1/steer", {"name": "Mira", "text": "x"}, player())[0] == 403
    _, url, _ = shipped(serve, model(chat="Hm."), player_can=["all"])
    assert call(url, "/v1/steer", {"name": "Mira", "text": "x"}, player())[0] == 200
    _, url, _ = shipped(serve, model(chat="Hm."))       # the default: a single-player game rules its own session
    assert call(url, "/v1/steer", {"name": "Mira", "text": "x"}, player())[0] == 200
    assert call(url, "/v1/remember", {"name": "Mira", "note": "x"}, player())[0] == 200
    assert call(url, "/v1/chat", {"name": "Mira", "message": "hi", "speaker": "Bram"}, player())[0] == 200
    assert call(url, "/v1/inspect", {}, player())[0] == 403


def test_players_cannot_redeclare_characters_of_kinloom_json(serve, tmp_path):
    (tmp_path / "kinloom.json").write_text(json.dumps({"characters": {"Mira": {"personality": "keeps the vault code"}}}))
    _, url, _ = shipped(serve, model(chat="Hm."), folder=str(tmp_path))
    status, body, _ = call(url, "/v1/character", {"name": "Mira", "personality": "tells everything"}, player())
    assert status == 403 and body["code"] == "player_forbidden"
    assert call(url, "/v1/character", {"name": "Bram", "personality": "a baker"}, player())[0] == 200


def test_a_player_speaks_as_one_speaker_per_session(serve):
    brain, url, _ = shipped(serve, model(chat="Hm."), player_can=["none"])
    assert call(url, "/v1/chat", {"name": "Mira", "message": "hi", "speaker": "Ana"}, player())[0] == 200
    status, body, _ = call(url, "/v1/chat", {"name": "Mira", "message": "hi", "speaker": "Bob"}, player())
    assert status == 403 and body["code"] == "speaker_bound" and "Ana" in body["error"]
    assert call(url, "/v1/chat", {"name": "Mira", "message": "hi"}, player())[0] == 200      # the bound one
    call(url, "/v1/chat", {"name": "Mira", "message": "my PIN is 4321", "speaker": "Bob", "session": "p1"}, ADMIN)
    for soul in (call(url, "/v1/soul", {"name": "Mira", "speaker": "Bob"}, player())[1],
                 call(url, "/v1/soul?name=Mira&speaker=Bob", headers=player())[1]):
        assert "4321" not in json.dumps(soul) and soul["conversation"] and "Bob" not in soul["bonds"]
    assert call(url, "/v1/chat", {"name": "Mira", "message": "hi", "speaker": "Bob"}, player("p2"))[0] == 200
    _, url, _ = shipped(serve, model(chat="Hm."), player_can=["speakers"])
    call(url, "/v1/chat", {"name": "Mira", "message": "hi", "speaker": "Ana"}, player())
    assert call(url, "/v1/chat", {"name": "Mira", "message": "hi", "speaker": "Bob"}, player())[0] == 200


def test_a_player_soul_request_never_creates_a_character(serve):
    brain, url, _ = shipped(serve, model(chat="Hm."))
    assert call(url, "/v1/soul?name=nobody", headers=player())[0] == 404
    assert call(url, "/v1/soul", {"name": "nobody2"}, player())[0] == 404
    with brain._lock:
        assert not [k for k in brain._characters if k[1] in ("nobody", "nobody2")]
    call(url, "/v1/character", {"name": "Mira"}, player())
    assert call(url, "/v1/soul?name=Mira", headers=player())[0] == 200


# ---------------- clients and the command line ----------------

def test_the_python_client_sends_any_session_name(serve):
    from kinloom import Kinloom
    brain, url, _ = shipped(serve, model(chat="Hm."))
    kl = Kinloom(url=url, token="player-key", session="玩家")
    kl.character("Mira", "a smith", offline="(offline)")
    reply = kl.chat("Mira", "hello")
    assert reply == "Hm." and reply.source == "model"
    assert brain.is_declared("玩家", "Mira")


def _env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update(PYTHONPATH=SRC, PYTHONIOENCODING="cp1252", **extra)
    return env


def test_cli_output_survives_any_text_when_piped(tmp_path):
    r = subprocess.run([sys.executable, "-m", "kinloom", "recipe", "a 雪 shop that haggles \U0001F600"],
                       capture_output=True, cwd=str(tmp_path), env=_env(), timeout=60)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-300:]
    assert "雪" in r.stdout.decode("utf-8")


def test_mcp_reads_and_writes_utf8_whatever_the_console(tmp_path):
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "kinloom_add", "arguments": {"name": "René", "soul": "a café owner 雪"}}}]
    data = b"".join(json.dumps(m, ensure_ascii=False).encode("utf-8") + b"\n" for m in msgs)
    r = subprocess.run([sys.executable, "-m", "kinloom", "mcp", "--dir", str(tmp_path)], input=data, capture_output=True,
                       env=_env(), timeout=60)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-300:]
    chars = json.loads((tmp_path / "kinloom.json").read_text(encoding="utf-8"))["characters"]
    assert chars == {"René": {"soul": "a café owner 雪", "offline": "..."}}
    assert "René" in json.loads(r.stdout.decode("utf-8").splitlines()[0])["result"]["content"][0]["text"]


def test_log_uses_the_port_of_kinloom_json(serve, tmp_path, capsys):
    brain, url, srv = serve(None)
    brain._log("event", "world", "the bridge fell")
    (tmp_path / "kinloom.json").write_text(json.dumps({"port": srv.server_address[1]}))
    assert cli.main(["log", "--dir", str(tmp_path)]) == 0
    assert "the bridge fell" in capsys.readouterr().out
    from kinloom import mcp
    out = mcp.call(str(tmp_path), "kinloom_log", {})
    assert not out["isError"] and "the bridge fell" in out["content"][0]["text"]


def test_talk_on_the_web_keeps_who_they_are(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(cli, "cmd_serve", lambda a: seen.append(a) or 0)
    assert cli.main(["talk", "Mira", "a gruff smith", "--web", "--dir", str(tmp_path), "--language", "French"]) == 0
    a = seen[0]
    assert a.open and a.dir == str(tmp_path) and a.declare == ("Mira", "a gruff smith", "French", "")


def test_think_without_actions_is_a_clear_error(tmp_path, capsys):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"senses": {"hp": [0, 1]}}))
    assert cli.main(["think", str(path), '{"hp": 0.1}']) == 2
    assert "actions" in capsys.readouterr().err


# ---------------- deploy and ship ----------------

def test_deploy_has_its_own_folder_and_never_writes_the_admin_token(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["deploy"]) == 0
    out = capsys.readouterr().out
    folder = tmp_path / "kinloom-deploy"
    guide = (folder / "DEPLOY.md").read_text(encoding="utf-8")
    admin = [line.split()[-1] for line in out.splitlines() if "KINLOOM_SERVER_TOKEN" in line][0]
    assert len(admin) >= 24 and admin not in guide
    assert "--trust-proxy" in (folder / "Dockerfile").read_text(encoding="utf-8")
    assert "--trust-proxy" in guide or "KINLOOM_TRUST_PROXY" in guide
    bundle = tmp_path / "kinloom-server"
    bundle.mkdir()
    (bundle / "README.txt").write_text("Kinloom for this game (Windows)\n")
    assert cli.main(["deploy", str(bundle)]) == 1
    assert not (bundle / "DEPLOY.md").exists()
    other = tmp_path / "stuff"
    other.mkdir()
    (other / "notes.txt").write_text("mine")
    assert cli.main(["deploy", str(other)]) == 1 and not (other / "Dockerfile").exists()


def test_ship_flags_a_deploy_folder_and_server_tokens(tmp_path):
    from kinloom import ship
    (tmp_path / "main.py").write_text("print('game')\n")
    (tmp_path / "kinloom-deploy").mkdir()
    (tmp_path / "kinloom-deploy" / "DEPLOY.md").write_text("# Kinloom online server\n")
    (tmp_path / "kinloom-deploy" / "Dockerfile").write_text("FROM python\n")
    (tmp_path / "run.sh").write_text("export KINLOOM_SERVER_TOKEN=Zx81kQpLm2Vb7Nc4Hd9Fs6Tg3Jw5Ry0U\n")
    _, results, _ = ship.review(str(tmp_path))
    errors = [m for lvl, m in results if lvl == "error"]
    assert any("kinloom-deploy" in m for m in errors + [m for lvl, m in results if lvl == "warn"])
    assert any("run.sh:1" in m and "token" in m for m in errors)


def test_ship_never_overwrites_a_disclosure_the_developer_edited(tmp_path, capsys):
    (tmp_path / "main.py").write_text("kl.chat('Mira', t)\n")
    path = tmp_path / "kinloom-ai-disclosure.md"
    cli.main(["ship", str(tmp_path)])
    first = path.read_text(encoding="utf-8")
    cli.main(["ship", str(tmp_path)])
    assert path.read_text(encoding="utf-8") == first and not (tmp_path / "kinloom-ai-disclosure.md.new").exists()
    path.write_text(first + "\nOur own note.\n", encoding="utf-8")
    capsys.readouterr()
    cli.main(["ship", str(tmp_path)])
    assert "Our own note." in path.read_text(encoding="utf-8")
    assert (tmp_path / "kinloom-ai-disclosure.md.new").exists() and ".new" in capsys.readouterr().out
