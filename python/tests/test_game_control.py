"""The game in control of a conversation: steer (the game decides what happens in the next reply, the model words it),
warmth / secret_trust / warm_up (how fast a character trusts people), reply_timeout, a second look at deeds when the
first one fails, and prompt rules found by playtesting a game. Scripted models only."""
import json

import pytest

from kinloom import Kinloom, prompts
from kinloom.brain import Character
from test_brain import make, model


def reply(text, **inner):
    return text + ("\n~~~\n" + json.dumps(inner) if inner else "")


def chat_calls(p):
    return [c for c in p.calls if c[0] == "chat"]


# ---------------- steer ----------------

def test_steer_tells_the_next_reply_what_the_game_decided():
    p = model(chat="All right. I was up there at half past twelve.")
    kl = make(p)
    kl.character("NINA", "a singer who hides that she went up to the office")
    kl.steer("NINA", "admit you went up to Victor's office at 12:30 AM for your letters")
    kl.chat("NINA", "This glass has your lipstick on it.", speaker="Detective")
    user = chat_calls(p)[-1][2]
    assert "The game decides what happens in this reply: admit you went up to Victor's office at 12:30 AM for your letters" in user
    assert user.index("The game decides") < user.index("Detective says:")
    kl.chat("NINA", "And then?", speaker="Detective")
    assert "The game decides" not in chat_calls(p)[-1][2]          # used once


def test_steer_lets_the_numbers_it_names_be_said():
    p = model(chat="Fine. I went up at 12:30.")
    kl = make(p)
    kl.character("NINA", "a singer")
    kl.steer("NINA", "admit you went up at 12:30")
    assert "12:30" in kl.chat("NINA", "When?", speaker="Detective")


def test_steer_releases_a_secret_the_game_decided_to_reveal():
    secret_reply = reply("All right, I sold the king's sword to pay my debts.", mood="ashamed")
    p = model(chat=[secret_reply, secret_reply, secret_reply])
    kl = make(p)
    kl.character("Mira", soul={"summary": "a smith", "secrets": ["she sold the king's sword to pay her debts"]})
    guarded = kl.chat("Mira", "Did you sell the king's sword?", speaker="Ana")
    assert "sold the king's sword" not in guarded                  # not trusted: the guard keeps it
    kl.steer("Mira", "confess that you sold the king's sword")
    said = kl.chat("Mira", "Did you sell the king's sword?", speaker="Ana")
    assert "sold the king's sword" in said


def test_steer_never_uses_a_prepared_greeting():
    p = model(chat="Detective. I have nothing to hide.", greet=reply("Evening.", mood="calm"))
    kl = make(p)
    kl.character("FRANK", soul={"summary": "a club owner"})
    kl.prepare(5)
    kl.steer("FRANK", "open by saying you have nothing to hide")
    line = kl.chat("FRANK", "", speaker="Detective")
    assert line.source == "model" and "nothing to hide" in line
    assert "nothing to hide" in chat_calls(p)[-1][2]


def test_steer_offline_is_used_up_and_bounded():
    kl = make(None)
    kl.character("NINA", "a singer", offline="Ask my taxi driver.")
    kl.steer("NINA", "x" * 2000)
    assert kl.chat("NINA", "Where were you?") == "Ask my taxi driver."
    assert kl.brain._steers == {}
    kl.steer("NINA", "something")
    kl.steer("NINA", "")                                            # "" takes it back
    assert kl.brain._steers == {}
    with pytest.raises(ValueError):
        kl.steer("NINA", 42)


def test_steer_is_clipped_in_the_prompt():
    assert len(prompts.steer_block("y" * 5000)) < 500
    assert prompts.steer_block("") == ""


# ---------------- warmth, secret_trust, warm_up ----------------

def test_warmth_is_how_they_feel_about_someone_before_any_talk():
    p = model(chat="Hello, dear.")
    kl = make(p)
    kl.character("RUTH", "a night cleaner", warmth=0.45)
    assert kl.opinion("RUTH", "Detective") == 0.45
    kl.chat("RUTH", "Hello Ruth.", speaker="Detective")
    assert "(+0.5)" in chat_calls(p)[-1][2] or "(+0.4)" in chat_calls(p)[-1][2]
    assert kl.soul("RUTH", "Detective")["bonds"]["Detective"]["feeling"] == 0.45
    assert kl.feel("RUTH", "Detective", 0.1) == 0.55               # feel() starts from the warmth too


def test_secret_trust_sets_when_a_secret_may_be_shared():
    p = model(chat="Hm.")
    kl = make(p)
    kl.character("Mira", soul={"summary": "a smith", "secrets": ["the sword"]}, warmth=0.3, secret_trust=0.2)
    kl.chat("Mira", "any secrets?", speaker="Ana")
    assert "trust Ana enough to share a secret" in chat_calls(p)[-1][2]
    kl.character("Bram", soul={"summary": "a baker", "secrets": ["the flour"]}, warmth=0.7, secret_trust=0.9)
    kl.chat("Bram", "any secrets?", speaker="Ana")
    assert "do not trust Ana enough" in chat_calls(p)[-1][2]


def test_warm_up_caps_what_one_conversation_can_win():
    p = model(chat=reply("Thank you.", mood="warm", feel=0.3))
    kl = make(p)
    kl.character("RUTH", "a night cleaner", warm_up=0.1)
    kl.character("LEO", "a bartender")
    for _ in range(3):
        kl.chat("RUTH", "You're brave.", speaker="Detective")
        kl.chat("LEO", "You're brave.", speaker="Detective")
    assert kl.opinion("RUTH", "Detective") == pytest.approx(0.1)
    assert kl.opinion("LEO", "Detective") == pytest.approx(0.3)     # the default, unchanged


def test_trust_settings_are_checked_and_clamped():
    c = Character("A", warmth=5, secret_trust=-3, warm_up=9)
    assert (c.warmth, c.secret_trust, c.warm_up) == (1.0, -1.0, 2.0)
    d = Character("B")
    assert (d.warmth, d.secret_trust, d.warm_up) == (0.0, 0.6, 0.3)
    with pytest.raises(ValueError):
        Character("C", warmth="very")


def test_kinloom_json_characters_take_the_trust_settings(tmp_path):
    (tmp_path / "kinloom.json").write_text(json.dumps({"characters": {
        "RUTH": {"soul": "a night cleaner", "warmth": 0.45, "secret_trust": 0.6, "warm_up": 0.3}}}), encoding="utf-8")
    kl = Kinloom(provider=None, memory_path=None, folder=str(tmp_path))
    assert kl.opinion("RUTH", "Detective") == 0.45


# ---------------- reply_timeout and deeds ----------------

def test_reply_timeout_from_kinloom_json(tmp_path):
    (tmp_path / "kinloom.json").write_text(json.dumps({"reply_timeout": 20}), encoding="utf-8")
    kl = Kinloom(provider=model(chat="Hi."), memory_path=None, folder=str(tmp_path), call_timeout=30)
    assert kl.brain._reply_deadline() == 20
    kl2 = Kinloom(provider=model(chat="Hi."), memory_path=None, folder=str(tmp_path), call_timeout=12)
    assert kl2.brain._reply_deadline() == 12                        # never past the call timeout
    assert make(model(chat="Hi.")).brain._reply_deadline() == 8.0     # the default


def test_a_bad_reply_timeout_is_refused_in_the_journal(tmp_path):
    (tmp_path / "kinloom.json").write_text(json.dumps({"reply_timeout": "slow"}), encoding="utf-8")
    kl = Kinloom(provider=model(chat="Hi."), memory_path=None, folder=str(tmp_path))
    assert kl.brain._reply_deadline() == 8.0
    assert any("reply_timeout" in str(e["text"]) for e in kl.brain.journal() if e["kind"] == "refused")


def test_deeds_are_asked_again_once_when_the_call_fails():
    p = model(chat=reply("Here, take a loaf.", mood="kind"), deeds=[None, {"do": [{"tool": "give", "args": {"item": "bread"}}]}])
    kl = make(p)
    kl.character("BRAM", "a kind baker", tools={"give": {"item": "bread"}})
    kl.chat("BRAM", "Can I have some bread?")
    assert kl.act("BRAM", think=False) == [("give", {"item": "bread"})]
    assert len([c for c in p.calls if c[0] == "deeds"]) == 2


def test_deeds_that_answer_nothing_are_not_asked_again():
    p = model(chat=reply("Maybe later.", mood="busy"), deeds={"do": []})
    kl = make(p)
    kl.character("BRAM", "a kind baker", tools={"give": {"item": "bread"}})
    kl.chat("BRAM", "Can I have some bread?")
    assert len([c for c in p.calls if c[0] == "deeds"]) == 1


# ---------------- prompt rules found by playtesting ----------------

def test_gestures_are_written_about_the_character_and_habits_are_not_spoken():
    c = Character("FRANK", "a club owner", tools={"admit": {"what": ["I came back"]}})
    system = prompts.chat_system(c, "English")
    assert "never I or my" in system
    assert "habits you do go in the gesture, never in your words" in system


def test_deeds_ignore_what_is_hinted_at_or_denied():
    c = Character("FRANK", "a club owner", tools={"admit": {"what": ["I came back"]}})
    assert "hint at it, deny it" in prompts.deeds_system(c)


# ---------------- over HTTP and through an online server ----------------

def test_steer_and_trust_settings_over_http():
    import threading
    from kinloom.brain import Brain
    from kinloom.server import make_server
    from test_server import call
    p = model(chat="All right, I was up there.")
    brain = Brain(provider=p, memory_path=None)
    srv = make_server(brain, host="127.0.0.1", port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        assert call(url, "/v1/character", {"name": "NINA", "personality": "a singer", "warmth": 0.4, "warm_up": 0.1,
                                           "secret_trust": 0.5})[0] == 200
        assert call(url, "/v1/opinion", {"a": "NINA", "b": "Detective"})[1]["opinion"] == 0.4
        assert call(url, "/v1/steer", {"name": "NINA", "text": "admit you went up to the office"})[1] == {"ok": True}
        assert call(url, "/v1/chat", {"name": "NINA", "message": "Well?", "speaker": "Detective"})[0] == 200
        assert "admit you went up to the office" in chat_calls(p)[-1][2]
        assert call(url, "/v1/steer", {"name": "NINA"})[0] == 400
        assert "steer" in call(url, "/v1/openapi.json")[1]["paths"]["/v1/steer"]["post"]["operationId"]
    finally:
        srv.shutdown()
        brain.close()


def test_steer_and_trust_settings_through_an_online_server():
    from test_remote import online
    p = model(chat="Fine. It was his car.")
    brain, srv, url = online(p)
    try:
        kl = Kinloom(url=url, token="play-123", session="player-1")
        kl.character("RUTH", "a night cleaner", warmth=0.45, secret_trust=0.6, warm_up=0.3)
        kl.steer("RUTH", "say it was Frank's green Buick")
        assert brain.opinion("player-1", "RUTH", "Detective") == 0.45
        kl.chat("RUTH", "What did you see?", speaker="Detective")
        assert "say it was Frank's green Buick" in chat_calls(p)[-1][2]
    finally:
        srv.shutdown()
        brain.close()
