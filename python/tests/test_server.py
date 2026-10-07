"""The HTTP API every engine client speaks."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from kinloom.brain import Brain
from kinloom.server import make_server
from test_brain import LINES, model


@pytest.fixture
def server():
    brains = []

    def start(provider=None, token=None, public=False, allow_origins=()):
        brain = Brain(provider=provider, memory_path=None)
        srv = make_server(brain, host="127.0.0.1", port=0, token=token, public=public, allow_origins=allow_origins)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        brains.append((brain, srv))
        return brain, "http://127.0.0.1:%d" % srv.server_address[1]

    yield start
    for brain, srv in brains:
        srv.shutdown()
        brain.close()


def call(url, path, body=None, headers=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, method=method or ("POST" if body is not None else "GET"),
                                 headers=dict({"Content-Type": "application/json"}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            ctype = r.headers.get("Content-Type", "")
            text = r.read().decode()
            return r.status, (json.loads(text) if "json" in ctype else text), dict(r.headers)
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        return e.code, (json.loads(text) if text.startswith("{") else text), dict(e.headers)


def test_the_seven_verbs_over_http(server):
    brain, url = server(model(lines=LINES, chat="You're P3.", decide={"strategy": "block"},
                              create={"challenge": "Ghost mode", "sky": "#000000"},
                              act={"actions": [{"tool": "boost", "args": {"seconds": 5}}]}))
    assert call(url, "/v1/character", {"name": "VEGA", "personality": "commentator", "lines": {"*": ["Wow!"]},
                                       "events": {"overtake": ["who", "whom", "gap"]}})[0] == 200
    call(url, "/v1/character", {"name": "BLAZE", "personality": "rival", "tools": {"boost": {"seconds": [0.5, 2.0]}}})
    brain.wait_idle(5)
    status, body, _ = call(url, "/v1/say", {"name": "VEGA", "event": "overtake", "facts": {"who": "BLAZE", "whom": "NOVA", "gap": 0.4}})
    assert status == 200 and "BLAZE" in body["text"] and body["declared"] is True
    assert call(url, "/v1/chat", {"name": "THEO", "message": "gap?", "facts": {"position": 3}})[1]["text"] == "You're P3."
    choices = {"strategy": ["attack", "block"], "aggression": [0, 1]}
    assert call(url, "/v1/decide", {"name": "BLAZE", "situation": {"lap": 1}, "choices": choices})[1]["decision"] == {"strategy": "attack", "aggression": 0.5}
    brain.wait_idle(5)
    assert call(url, "/v1/decide", {"name": "BLAZE", "situation": {"lap": 1}, "choices": choices})[1]["decision"]["strategy"] == "block"
    assert call(url, "/v1/act", {"name": "BLAZE", "situation": {}})[1]["actions"] == []
    brain.wait_idle(5)
    assert call(url, "/v1/act", {"name": "BLAZE", "situation": {}})[1]["actions"] == [{"tool": "boost", "args": {"seconds": 2.0}}]
    value = call(url, "/v1/create", {"what": "race", "example": {"challenge": "Win clean", "sky": "#ff7a45"}})[1]["value"]
    assert value == {"challenge": "Ghost mode", "sky": "#000000"}
    assert call(url, "/v1/event", {"text": "the player rammed BLAZE", "about": ["BLAZE"]})[0] == 200
    assert call(url, "/v1/remember", {"name": "BLAZE", "note": "revenge"})[0] == 200
    assert call(url, "/v1/state", {"state": {"lap": 2}})[0] == 200
    status, body, _ = call(url, "/v1/status")
    assert status == 200 and body["mode"] == "online" and body["stats"]["calls"] >= 4


def test_undeclared_characters_are_flagged_so_clients_can_redeclare(server):
    _, url = server()
    body = call(url, "/v1/say", {"name": "GHOST", "event": "boo"})[1]
    assert body == {"text": "", "source": "offline", "declared": False}


def test_sessions_are_separate(server):
    brain, url = server()
    call(url, "/v1/remember", {"name": "THEO", "note": "Alice likes short answers"}, {"X-Kinloom-Session": "alice"})
    call(url, "/v1/remember", {"session": "bob", "name": "THEO", "note": "Bob likes jokes"})
    assert brain.memory.all("alice", "THEO") == ["Alice likes short answers"]
    assert brain.memory.all("bob", "THEO") == ["Bob likes jokes"]


def test_chat_streams_as_server_sent_events(server):
    _, url = server(model(chat="Box this lap."))
    status, text, headers = call(url, "/v1/chat", {"name": "THEO", "message": "pit?", "stream": True})
    assert status == 200 and "text/event-stream" in headers["Content-Type"]
    events = [json.loads(l[5:]) for l in text.splitlines() if l.startswith("data:")]
    assert events[-1]["done"] is True and events[-1]["text"] == "Box this lap." and events[-1]["mood"] == "calm"
    assert "".join(e.get("piece", "") for e in events[:-1]) == "Box this lap."


def test_errors_are_json_and_helpful(server):
    _, url = server()
    status, body, _ = call(url, "/v1/fly", {})
    assert status == 404 and "say" in body["error"]
    status, body, _ = call(url, "/v1/say", {"event": "x"})
    assert status == 400 and "name" in body["error"]
    req = urllib.request.Request(url + "/v1/say", data=b"{not json", method="POST", headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 400
    status, body, _ = call(url, "/v1/decide", {"name": "X", "situation": {}, "choices": {}})
    assert status == 400 and "choices" in body["error"]


def test_web_pages_from_other_sites_are_refused_local_ones_allowed(server):
    _, url = server()
    status, _, _ = call(url, "/v1/say", {"name": "A", "event": "x"}, {"Origin": "https://evil.example"})
    assert status == 403
    status, _, headers = call(url, "/v1/say", {"name": "A", "event": "x"}, {"Origin": "http://localhost:5173"})
    assert status == 200 and headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    status, _, headers = call(url, "/v1/say", None, {"Origin": "http://127.0.0.1:8080", "Access-Control-Request-Method": "POST"}, method="OPTIONS")
    assert status == 204 and "POST" in headers["Access-Control-Allow-Methods"]


def test_a_public_server_requires_its_token(server):
    _, url = server(token="s3cret", public=True)
    assert call(url, "/v1/say", {"name": "A", "event": "x"})[0] == 401
    assert call(url, "/v1/say", {"name": "A", "event": "x"}, {"Authorization": "Bearer s3cret"})[0] == 200
    status, _, headers = call(url, "/v1/say", {"name": "A", "event": "x"}, {"Origin": "https://mygame.example", "Authorization": "Bearer s3cret"})
    assert status == 200


def test_huge_bodies_are_refused(server):
    _, url = server()
    status, body, _ = call(url, "/v1/event", {"text": "x" * (2 * 1024 * 1024)})
    assert status == 413


def test_the_dashboard_is_served(server):
    _, url = server()
    status, html, _ = call(url, "/")
    assert status == 200 and "<title>Kinloom" in html


def raw(url, data):
    import socket
    host, port = url.rsplit(":", 1)
    with socket.create_connection((host.replace("http://", ""), int(port)), timeout=5) as s:
        s.sendall(data)
        chunks = []
        while True:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", "replace")


def test_bad_content_length_is_refused_without_hanging(server):
    _, url = server()
    for length in (b"-5", b"abc"):
        answer = raw(url, b"POST /v1/say HTTP/1.1\r\nHost: x\r\nContent-Length: " + length + b"\r\n\r\n{}")
        assert answer.startswith("HTTP/1.1 400"), answer[:80]


def test_a_refused_body_is_not_read_as_the_next_request(server):
    _, url = server(token="s3cret", public=True)
    body = b'{"name": "A", "event": "x"}'
    answer = raw(url, b"POST /v1/say HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body))
    assert answer.startswith("HTTP/1.1 401") and answer.count("HTTP/1.1") == 1


def test_dns_rebinding_requests_are_refused(server):
    _, url = server()
    status, body, _ = call(url, "/v1/status", headers={"Host": "evil.example:7717"})
    assert status == 403 and "localhost" in body["error"]
    assert call(url, "/v1/status", headers={"Host": "localhost:7717"})[0] == 200


def test_file_pages_get_a_clear_answer_and_can_be_allowed(server):
    _, url = server()
    status, body, _ = call(url, "/v1/say", {"name": "A", "event": "x"}, {"Origin": "null"})
    assert status == 403 and "allow-origin null" in body["error"]
    _, url2 = server(token="s3cret", allow_origins=["null", "https://html.itch.zone"])   # null: any site could be it
    auth = {"Authorization": "Bearer s3cret"}
    assert call(url2, "/v1/say", {"name": "A", "event": "x"}, dict(auth, Origin="null"))[0] == 200
    status, _, headers = call(url2, "/v1/say", {"name": "A", "event": "x"}, dict(auth, Origin="https://html.itch.zone"))
    assert status == 200 and headers.get("Access-Control-Allow-Origin") == "https://html.itch.zone"


def test_wrong_field_types_get_a_400_not_a_dropped_connection(server):
    _, url = server()
    for verb, body in (("character", {"name": "A", "max_words": {"x": 1}}), ("character", {"name": "A", "every": [1]}),
                       ("decide", {"name": "A", "choices": {"a": ["x", "y"]}, "every": {}}),
                       ("event", {"text": "x", "importance": "high"}), ("say", {"name": "A", "event": "x", "facts": [1, 2]})):
        status, body_, _ = call(url, "/v1/" + verb, body)
        assert status in (200, 400), (verb, status, body_)


def test_souls_over_http(server):
    inner = {"mood": "annoyed", "intensity": 0.7, "feel": -0.1, "remember": "Ana mocked my hammer"}
    brain, url = server(model(soul={"summary": "a gruff smith", "secrets": ["the sword"]},
                              chat=["You. Buying or staring?", "Hmph.\n~~~\n" + json.dumps(inner)]))
    assert call(url, "/v1/character", {"name": "Mira", "soul": "a gruff smith who sold the king's sword"})[0] == 200
    brain.wait_idle(5)
    status, body, _ = call(url, "/v1/chat", {"name": "Mira", "message": "", "speaker": "Ana"})
    assert status == 200 and body["text"] == "You. Buying or staring?"
    body = call(url, "/v1/chat", {"name": "Mira", "message": "Nice toy hammer.", "speaker": "Ana"})[1]
    assert body["text"] == "Hmph." and body["mood"] == "annoyed" and body["feeling"] == -0.1
    soul = call(url, "/v1/soul", {"name": "Mira"})[1]
    assert soul["card"]["secrets"] == ["the sword"] and soul["bonds"]["Ana"]["talks"] == 1
    assert call(url, "/v1/soul?name=Mira")[1]["mood"]["word"] == "annoyed"
    status, body, _ = call(url, "/v1/character", {"name": "Bram", "soul": {"summary": "a baker"}})
    assert status == 200 and call(url, "/v1/soul", {"name": "Bram"})[1]["card"]["summary"] == "a baker"
    assert call(url, "/v1/chat", {"name": "Mira"})[0] == 400


def test_streamed_chat_hides_the_inner_part(server):
    brain, url = server(model(chat='Box this lap.\n~~~\n{"mood": "focused"}'))
    req = urllib.request.Request(url + "/v1/chat", data=json.dumps({"name": "THEO", "message": "", "stream": True}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        events = [json.loads(line[6:]) for line in r.read().decode().splitlines() if line.startswith("data: ")]
    assert "".join(e.get("piece", "") for e in events).strip() == "Box this lap."
    assert events[-1]["done"] is True and events[-1]["text"] == "Box this lap." and events[-1]["mood"] == "focused"


# ---------------- shipping to players ----------------

@pytest.fixture
def shipped():
    made = []

    def start(provider=None, **kw):
        brain = Brain(provider=provider, memory_path=None)
        srv = make_server(brain, host="127.0.0.1", port=0, token="admin-secret", public=True, player_token="player-key", **kw)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        made.append((brain, srv))
        return brain, "http://127.0.0.1:%d" % srv.server_address[1]

    yield start
    for brain, srv in made:
        srv.shutdown()
        brain.close()


def test_the_player_token_plays_but_cannot_read_everyone(shipped):
    _, url = shipped(model(chat="Hm."))
    player = {"Authorization": "Bearer player-key"}
    assert call(url, "/v1/chat", {"name": "Mira", "message": "hi"}, player)[1]["text"] == "Hm."
    for path in ("/v1/journal", "/v1/stream", "/v1/status"):
        status, body, _ = call(url, path, headers=player)
        assert status == 403 or (path == "/v1/status" and body == {"mode": "online"}), path
    assert call(url, "/v1/journal", headers={"Authorization": "Bearer admin-secret"})[0] == 200
    assert call(url, "/v1/chat", {"name": "Mira", "message": "hi"}, {"Authorization": "Bearer wrong"})[0] == 401


def test_players_are_rate_limited_per_session_and_per_address(shipped):
    _, url = shipped(model(chat="Hm."), rate_per_session=3, rate_per_ip=5)
    player = {"Authorization": "Bearer player-key", "X-Kinloom-Session": "p1"}
    codes = [call(url, "/v1/chat", {"name": "Mira", "message": "hi"}, player)[0] for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    other = dict(player, **{"X-Kinloom-Session": "p2"})
    codes = [call(url, "/v1/chat", {"name": "Mira", "message": "hi"}, other)[0] for _ in range(3)]
    assert codes == [200, 200, 429]                     # same address: 5 a minute in all
    admin = {"Authorization": "Bearer admin-secret", "X-Kinloom-Session": "p1"}
    assert call(url, "/v1/chat", {"name": "Mira", "message": "hi"}, admin)[0] == 200
    assert call(url, "/v1/character", {"name": "Bram"}, player)[0] == 200     # no model behind: never limited


def test_the_player_token_never_reads_secrets_or_other_players(shipped):
    brain, url = shipped(model(chat="Hm."))
    admin = {"Authorization": "Bearer admin-secret"}
    player = {"Authorization": "Bearer player-key"}
    call(url, "/v1/character", {"name": "Mira", "soul": {"summary": "a smith", "secrets": ["she sold the sword"]}}, admin)
    call(url, "/v1/chat", {"name": "Mira", "message": "I'm Bob, I hid the gold under the bridge", "speaker": "Bob"}, admin)
    call(url, "/v1/chat", {"name": "Mira", "message": "hi", "speaker": "Ana"}, player)   # a player token: one speaker
    for soul in (call(url, "/v1/soul", {"name": "Mira", "speaker": "Ana"}, player)[1],
                 call(url, "/v1/soul?name=Mira&speaker=Ana", headers=player)[1]):
        text = json.dumps(soul)
        assert "sold the sword" not in text and "under the bridge" not in text and "Bob" not in text
        assert soul["card"] == {"summary": "a smith"} and soul["mood"]["word"] and "Ana" in soul["bonds"]
    assert "sold the sword" in json.dumps(call(url, "/v1/soul", {"name": "Mira"}, admin)[1])


def test_null_means_the_default_like_every_sdk():
    # every native SDK reads null as "not given": prepare's timeout and spread's rounds were a 400 here
    from kinloom import server
    brain = Brain(provider=None, memory_path=None)
    assert server.handle(brain, "prepare", {"timeout": None}, "s")["ready"] is True
    assert server.handle(brain, "character", {"name": "C", "every": None}, "s") == {"ok": True}
    brain.character("s", "A")
    brain.character("s", "B")
    for rounds in (None, 2.7, "3"):
        assert server.handle(brain, "spread", {"rounds": rounds}, "s") == {"shared": []}
    for rounds in ([1], "x", True, {}):                 # not a number: a clear 400, as in C#, Java, Rust, C++
        with pytest.raises(server.ApiError, match="rounds"):
            server.handle(brain, "spread", {"rounds": rounds}, "s")
    with pytest.raises(server.ApiError):
        server.handle(brain, "prepare", {"timeout": "soon"}, "s")


def test_a_player_token_loads_only_saves_this_server_gave_unchanged(shipped):
    _, url = shipped(model(chat="Hm."))
    player = {"Authorization": "Bearer player-key", "X-Kinloom-Session": "p1"}
    admin = {"Authorization": "Bearer admin-secret", "X-Kinloom-Session": "p1"}
    call(url, "/v1/chat", {"name": "Mira", "message": "hi", "speaker": "Ana"}, player)
    data = call(url, "/v1/save", {}, player)[1]["data"]
    assert json.loads(data)["sig"]
    assert call(url, "/v1/load", {"data": data}, player)[:2] == (200, {"ok": True})
    forged = json.loads(data)
    forged["opinions"] = {"Mira": {"Ana": 1.0}}
    status, body, _ = call(url, "/v1/load", {"data": json.dumps(forged)}, player)
    assert status == 400 and "not a save this server gave" in body["error"]
    unsigned = call(url, "/v1/save", {}, admin)[1]["data"]
    assert "sig" not in json.loads(unsigned)
    assert call(url, "/v1/load", {"data": unsigned}, player)[0] == 400
    assert call(url, "/v1/load", {"data": json.dumps(forged)}, admin)[:2] == (200, {"ok": True})   # the admin token: anything
