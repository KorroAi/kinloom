"""A Python game shipped to players: the same calls answered by an online `kinloom serve` (the key stays there),
with the player token, and offline answers when the server cannot be reached."""
import threading
import time

from kinloom import Kinloom
from kinloom.brain import Brain
from kinloom.server import make_server
from kinloom.talk import Talk
from test_brain import model


def online(provider, player_token="play-123", **kw):
    brain = Brain(provider=provider, memory_path=None)
    srv = make_server(brain, host="127.0.0.1", port=0, token="admin-456", public=True, player_token=player_token, **kw)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return brain, srv, "http://127.0.0.1:%d" % srv.server_address[1]


def test_the_same_game_code_talks_through_an_online_server():
    p = model(chat='Evening, keeper.\n~~~\n{"mood": "warm", "feel": 0.3, "do": [{"tool": "give_wood", "args": {}}]}')
    brain, srv, url = online(p)
    try:
        given = []

        def give_wood():
            """hand the keeper an armful of wood"""
            given.append(1)
        kl = Kinloom(url=url, token="play-123", session="player-7")
        kl.character("Wren", soul="an old fire keeper", offline="Hm.", tools=[give_wood], trust={"give_wood": 0.2})

        pieces = []
        assert kl.chat("Wren", "Hello Wren.", speaker="Ana", stream=pieces.append) == "Evening, keeper."
        assert "".join(pieces).strip() == "Evening, keeper."
        assert kl.act("Wren", think=False) == [("give_wood", {})] and given == [1]   # the game's function ran here
        assert kl.soul("Wren", speaker="Ana")["mood"]["word"] == "warm"
        assert brain.opinion("player-7", "Wren", "Ana") == 0.3                      # the state lives on the server
        assert [c for c in p.calls if c[0] == "chat"]                               # the model was called there
    finally:
        srv.shutdown()
        brain.close()


def test_prepare_save_and_inspect_wait_for_declarations_on_their_way(monkeypatch):
    # found by proof/mod: character() then prepare() reached the server first on a slow network, which answered
    # "ready" before knowing the characters, so nothing was written ahead
    from kinloom import remote
    sent, real = [], remote.RemoteBrain._request

    def slow(self, session, verb, body, timeout, *a, **kw):
        if verb == "character":
            time.sleep(0.3)
        sent.append(verb)
        return real(self, session, verb, body, timeout, *a, **kw)
    monkeypatch.setattr(remote.RemoteBrain, "_request", slow)
    brain, srv, url = online(model(lines={"lines": ["Lamps lit."]}))
    try:
        kl = Kinloom(url=url, token="play-123", session="p1")
        for verb, call in (("prepare", lambda: kl.prepare(5)), ("inspect", kl.inspect), ("save", kl.save)):
            sent.clear()
            kl.character("LAMP%s" % verb, "a lamplighter", lines={"dusk": ["Lamps lit."]})
            call()
            assert "character" in sent and sent.index("character") < sent.index(verb), sent
        assert kl.say("LAMPprepare", "dusk") == "Lamps lit."
    finally:
        srv.shutdown()
        brain.close()


def test_a_wrong_token_or_no_server_gives_the_offline_answers():
    brain, srv, url = online(model(chat="Hi.\n~~~\n{}"))
    try:
        kl = Kinloom(url=url, token="wrong", session="p")
        kl.character("Wren", "an old fire keeper", offline=["Hm.", "Mind the fire."])
        assert kl.chat("Wren", "hello?") in ("Hm.", "Mind the fire.")
    finally:
        srv.shutdown()
        brain.close()
    kl = Kinloom(url="http://127.0.0.1:9", session="p")
    kl.character("VEGA", "commentator", lines={"*": ["What a race, {who}!"]})
    assert kl.say("VEGA", "overtake", {"who": "BLAZE"}) == "What a race, BLAZE!"
    assert kl.decide("VEGA", {}, {"mood": ["calm", "wild"]}) == {"mood": "calm"}
    talk = Talk(kl, "VEGA", speaker="Ana")
    talk.send("hi")
    for _ in range(200):
        talk.update()
        if not talk.waiting:
            break
        time.sleep(0.01)
    assert talk.lines[0] == ("Ana", "hi") and not talk.waiting


def test_kinloom_url_in_the_environment_is_enough(monkeypatch):
    brain, srv, url = online(model(chat="Aye.\n~~~\n{}"), player_token=None)
    try:
        monkeypatch.setenv("KINLOOM_URL", url)
        monkeypatch.setenv("KINLOOM_TOKEN", "admin-456")
        kl = Kinloom(session="s")
        assert kl.status()["mode"] == "remote"
        kl.character("Wren", "an old fire keeper", offline="Hm.")

        assert kl.chat("Wren", "hi") == "Aye."
    finally:
        srv.shutdown()
        brain.close()


def test_a_restarted_server_gets_the_character_again():
    p = model(chat="Aye.\n~~~\n{}")
    brain, srv, url = online(p)
    try:
        kl = Kinloom(url=url, token="play-123", session="s")
        kl.character("Wren", soul="an old fire keeper", offline="Hm.")
        kl.chat("Wren", "hi")
        brain._characters.clear()                       # as if the server restarted
        brain._declared.clear()
        kl.chat("Wren", "hi again")                     # answered by an undeclared Wren, flagged: declared again
        kl.brain.wait_idle(2)
        time.sleep(0.3)
        assert brain.is_declared("s", "Wren")
    finally:
        srv.shutdown()
        brain.close()
