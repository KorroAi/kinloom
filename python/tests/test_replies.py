"""What say() and chat() hand back (the text, where it came from, what was decided), and the options a game's text
box needs: long event names, a description per event, max_chars, language="auto", a public way to watch Kinloom."""
import json

from kinloom import Kinloom
from kinloom.brain import Line
from test_brain import make, model
from test_souls import reply


# ---------------- event names: the same key everywhere ----------------

def test_a_long_event_name_finds_its_lines_offline():
    name = "challenging another trainer to a battle on the route, loudly"   # 61 characters
    kl = make(None)
    kl.character("ANA", "a trainer", lines={name: ["Battle me, {other}!"]})
    assert kl.say("ANA", name, {"other": "BEN"}) == "Battle me, BEN!"


def test_a_long_event_name_uses_the_lines_the_model_prepared():
    name = "challenging another trainer to a battle on the route, loudly"
    p = model(lines={"lines": ["Fight me, {other}!"]})
    kl = make(p)
    kl.character("ANA", "a trainer", events={name: ["other"]})
    kl.wait_idle(5)
    assert kl.say("ANA", name, {"other": "BEN"}) == "Fight me, BEN!"


def test_event_names_longer_than_the_limit_are_cut_the_same_way_everywhere():
    name = "x" * 300
    kl = make(None)
    kl.character("ANA", "", lines={name: ["Hi."]})
    assert kl.say("ANA", name) == "Hi."


# ---------------- where a line came from ----------------

def test_say_tells_where_its_line_came_from():
    kl = make(None)
    kl.character("VEGA", "", lines={"goal": ["{who} scores!"]})
    line = kl.say("VEGA", "goal", {"who": "BLAZE"})
    assert isinstance(line, Line) and isinstance(line, str)
    assert line == "BLAZE scores!" and line.source == "offline"

    p = model(lines={"lines": ["What a goal by {who}!"]})
    kl = make(p)
    kl.character("VEGA", "", lines={"goal": ["{who} scores!"]}, events={"goal": ["who"]})
    kl.wait_idle(5)
    line = kl.say("VEGA", "goal", {"who": "BLAZE"})
    assert line == "What a goal by BLAZE!" and line.source == "prepared"

    p = model(line="{who}! Unbelievable!")
    kl = make(p)
    line = kl.say("VEGA", "goal", {"who": "BLAZE"}, fresh=True)
    assert line == "BLAZE! Unbelievable!" and line.source == "model"


def test_chat_tells_where_its_reply_came_from():
    kl = make(None)
    kl.character("Mira", "a smith", offline="Busy.")
    r = kl.chat("Mira", "hello")
    assert r == "Busy." and r.source == "offline" and r.do == []

    kl = make(model(chat=reply("Hm. What now?", mood="tired")))
    kl.character("Mira", "a smith", offline="Busy.")
    r = kl.chat("Mira", "hello")
    assert r == "Hm. What now?" and r.source == "model"

    kl = make(model(chat=None))                  # the model fails: the game's own reply
    kl.character("Mira", "a smith", offline="Busy.")
    r = kl.chat("Mira", "hello")
    assert r == "Busy." and r.source == "offline"


def test_lines_are_plain_strings_for_json_and_comparisons():
    kl = make(None)
    kl.character("Mira", "", offline="Busy.")
    r = kl.chat("Mira", "hi")
    assert json.dumps({"text": r}) == '{"text": "Busy."}'
    assert r in ["Busy.", "Gone."] and r + "!" == "Busy.!" and str(r) == "Busy."


# ---------------- nothing to say is never silent ----------------

def test_an_empty_answer_is_reported_once_in_the_journal():
    kl = make(None)
    kl.character("GHOST", "silent")
    assert kl.say("GHOST", "boo") == "" and kl.say("GHOST", "boo") == ""
    assert kl.chat("GHOST", "hi") == ""
    empty = [e for e in kl.journal() if e["kind"] == "empty"]
    assert len(empty) == 2
    assert "boo" in empty[0]["text"] and "lines" in empty[0]["text"]
    assert "offline" in empty[1]["text"]


# ---------------- what they decided, with the reply ----------------

def give(item: str = "wood"):
    """hand over an item"""


def test_the_reply_carries_what_was_decided_in_it_and_act_does_not_repeat_it():
    p = model(chat=reply("Here, take it.", do=[{"tool": "give", "args": {"item": "sword"}}]))
    kl = make(p)
    kl.character("Mira", "a smith", tools={"give": {"item": "wood"}})
    r = kl.chat("Mira", "May I have the sword?")
    assert r.do == [("give", {"item": "sword"})]
    assert r.do == [("give", {"item": "sword"})]        # read again: the same
    assert kl.act("Mira", think=False) == []            # handed out once


def test_act_still_returns_what_was_decided_while_talking_when_the_reply_is_not_read():
    p = model(chat=reply("Here.", do=[{"tool": "give", "args": {"item": "sword"}}]))
    kl = make(p)
    kl.character("Mira", "a smith", tools={"give": {"item": "wood"}})
    r = kl.chat("Mira", "the sword?")
    assert kl.act("Mira", think=False) == [("give", {"item": "sword"})]
    assert r.do == []                                   # act() took it first


def test_a_reply_only_carries_its_own_decisions():
    answers = [reply("Fine, Ben.", do=[{"tool": "give", "args": {"item": "axe"}}]),
               reply("Sure, Ana.", do=[{"tool": "give", "args": {"item": "sword"}}])]
    kl = make(model(chat=answers))
    kl.character("Mira", "a smith", tools={"give": {"item": "wood"}})
    kl.chat("Mira", "the axe?", speaker="Ben")          # nobody collects Ben's
    r = kl.chat("Mira", "the sword?", speaker="Ana")
    assert r.do == [("give", {"item": "sword"})]


def test_python_tools_decided_in_a_reply_run_through_act_only():
    ran = []

    def hand(item: str = "wood"):
        ran.append(item)
    kl = make(model(chat=reply("Here.", do=[{"tool": "hand", "args": {"item": "sword"}}])))
    kl.character("Mira", "", tools=[hand])
    r = kl.chat("Mira", "sword?")
    assert r.do == [("hand", {"item": "sword"})] and ran == []      # the game carries it out itself


# ---------------- max_chars: text boxes count characters ----------------

def test_max_chars_keeps_model_replies_inside_the_box():
    long = "Well, well, look who it is. I was just about to close the forge for the night."
    kl = make(model(chat=reply(long)))
    kl.character("Mira", "", max_chars=40)
    r = kl.chat("Mira", "hi")
    assert r == "Well, well, look who it is." and len(r) <= 40


def test_max_chars_cuts_on_a_word_when_one_sentence_is_too_long():
    kl = make(model(chat=reply("Absolutely everyone in this whole village knows that story already")))
    kl.character("Mira", "", max_chars=30)
    r = kl.chat("Mira", "hi")
    assert len(r) <= 30 and r.endswith("…") and not r[:-1].endswith(" ")
    assert r == "Absolutely everyone in this…"


def test_max_chars_streams_only_whole_sentences_that_fit():
    pieces = []
    kl = make(model(chat=reply("First one here. Second sentence is far too long to fit.")))
    kl.character("Mira", "", max_chars=24)
    r = kl.chat("Mira", "hi", stream=pieces.append)
    assert r == "First one here." and "".join(pieces).strip() == "First one here."


def test_max_chars_applies_to_prepared_and_fresh_lines_and_is_in_the_prompt():
    p = model(lines={"lines": ["Short one, {who}.", "This line is much too long for the little box, {who}."]})
    kl = make(p)
    kl.character("VEGA", "", events={"goal": ["who"]}, max_chars=24)
    kl.wait_idle(5)
    assert "at most 24 characters" in [c for c in p.calls if c[0] == "lines"][0][1]
    for _ in range(4):
        line = kl.say("VEGA", "goal", {"who": "BLAZE"})
        assert len(line) <= 24, line


def test_max_chars_comes_from_kinloom_json(tmp_path):
    (tmp_path / "kinloom.json").write_text(json.dumps({"characters": {"Mira": {"personality": "a smith", "max_chars": 30}}}))
    kl = Kinloom(provider=model(chat=reply("Absolutely everyone in this whole village knows that story already")),
                 memory_path=None, folder=str(tmp_path))
    assert len(kl.chat("Mira", "hi")) <= 30


# ---------------- language="auto": answer in the speaker's language ----------------

def test_language_auto_answers_in_the_language_of_the_speaker():
    p = model(chat=reply("Salut."), lines={"lines": ["Go {who}!"]})
    kl = make(p, language="auto")
    kl.character("Mira", "a smith", events={"goal": ["who"]})
    kl.chat("Mira", "Bonjour, ça va ?")
    kl.wait_idle(5)
    chat = [c for c in p.calls if c[0] == "chat"][0][1]
    lines = [c for c in p.calls if c[0] == "lines"][0][1]
    assert "language the person talking to you uses" in chat
    assert "Write everything players read in English." in lines     # no speaker: the default language


def test_a_character_can_have_language_auto_on_its_own():
    p = model(chat=reply("Hola."))
    kl = make(p, language="French")
    kl.character("Mira", "", language="auto")
    kl.chat("Mira", "Hola")
    assert "language the person talking to you uses" in [c for c in p.calls if c[0] == "chat"][0][1]


# ---------------- a description per event ----------------

def test_an_event_can_say_when_it_happens_and_the_model_reads_that():
    p = model(lines={"lines": ["Battle me, {other}!"]})
    kl = make(p)
    kl.character("ANA", "a trainer", lines={"challenge": {"when": "challenging another trainer to a battle",
                                                         "lines": ["{other}, fight!"]}},
                 events={"challenge": ["other"]})
    kl.wait_idle(5)
    prompt = [c for c in p.calls if c[0] == "lines"][0][1]
    assert "when this happens: challenging another trainer to a battle." in prompt
    assert kl.say("ANA", "challenge", {"other": "BEN"}) == "Battle me, BEN!"


def test_an_event_description_with_its_offline_lines_works_offline():
    kl = make(None)
    kl.character("ANA", "", lines={"challenge": {"when": "challenging someone", "lines": ["{other}, fight!"]}})
    assert kl.say("ANA", "challenge", {"other": "BEN"}) == "BEN, fight!"


# ---------------- watching Kinloom without reaching inside ----------------

def test_online_on_off_and_stats_are_public():
    kl = make(None)
    assert kl.online is False
    seen = []
    listener = kl.on(seen.append)
    kl.character("Mira", "a smith")
    assert seen and seen[-1]["kind"] == "character"
    kl.off(listener)
    kl.character("Theo", "")
    assert seen[-1]["name"] == "Mira"
    assert make(model(chat="Hi.")).online is True
    assert kl.stats()["calls"] == 0


# ---------------- over HTTP and through an online server ----------------

def test_http_replies_say_where_they_came_from_and_can_carry_their_actions():
    from test_server import call
    from test_remote import online
    p = model(chat=reply("Take it.", do=[{"tool": "give", "args": {"item": "axe"}}]))
    brain, srv, url = online(p, player_token=None)
    auth = {"Authorization": "Bearer admin-456"}
    try:
        call(url, "/v1/character", {"name": "Mira", "tools": {"give": {"item": "wood"}}}, auth)
        body = call(url, "/v1/chat", {"name": "Mira", "message": "axe?"}, auth)[1]
        assert body["source"] == "model" and "do" not in body            # clients that do not ask: act() as before
        assert call(url, "/v1/act", {"name": "Mira", "think": False}, auth)[1]["actions"] == [{"tool": "give", "args": {"item": "axe"}}]
        body = call(url, "/v1/chat", {"name": "Mira", "message": "axe?", "do": True}, auth)[1]
        assert body["do"] == [{"tool": "give", "args": {"item": "axe"}}]
        assert call(url, "/v1/act", {"name": "Mira", "think": False}, auth)[1]["actions"] == []
        assert call(url, "/v1/say", {"name": "Mira", "event": "x"}, auth)[1]["source"] == "offline"
    finally:
        srv.shutdown()
        brain.close()


def test_through_an_online_server_the_reply_carries_its_source_and_actions_once():
    from test_remote import online
    p = model(chat=[reply("Take it.", do=[{"tool": "give", "args": {"item": "axe"}}]),
                    reply("And this.", do=[{"tool": "give", "args": {"item": "saw"}}])])
    brain, srv, url = online(p)
    try:
        kl = Kinloom(url=url, token="play-123", session="p1")
        kl.character("Mira", "a smith", tools={"give": {"item": "wood"}}, offline="Busy.")
        r = kl.chat("Mira", "axe?")
        assert r == "Take it." and r.source == "model" and r.do == [("give", {"item": "axe"})]
        assert kl.act("Mira", think=False) == []
        r = kl.chat("Mira", "saw?")
        assert kl.act("Mira", think=False) == [("give", {"item": "saw"})] and r.do == []
        assert kl.online is True
    finally:
        srv.shutdown()
        brain.close()
    kl = Kinloom(url="http://127.0.0.1:9", session="p")
    kl.character("Mira", "", offline="Busy.")
    r = kl.chat("Mira", "hi")
    assert r == "Busy." and r.source == "offline" and kl.online is False


# ---------------- kinloom.json ----------------

def test_a_config_character_keeps_its_voice_and_box_size(tmp_path):
    (tmp_path / "kinloom.json").write_text(json.dumps({"characters": {"Mira": {
        "personality": "a smith", "voice": "low, tired, warm", "max_chars": 40}}}))
    kl = Kinloom(provider=None, memory_path=None, folder=str(tmp_path))
    kl.chat("Mira", "hi")
    c = kl.brain._char("default", "Mira")
    assert c.voice == "low, tired, warm" and c.max_chars == 40


def test_check_knows_every_character_key(tmp_path):
    from kinloom.check import _config_findings
    (tmp_path / "kinloom.json").write_text(json.dumps({"characters": {"Mira": {
        "personality": "a smith", "voice": "low", "max_chars": 40, "max_words": 10, "colour": "red"}}}))
    found = json.dumps(_config_findings(str(tmp_path))[0])
    assert "unknown keys colour" in found and "max_chars" not in found and "voice" not in found


def test_kinloom_add_writes_the_box_size(tmp_path):
    from kinloom.add import add
    add(str(tmp_path), "Mira", "a smith", max_chars=36, language="auto")
    spec = json.loads((tmp_path / "kinloom.json").read_text())["characters"]["Mira"]
    assert spec["max_chars"] == 36 and spec["language"] == "auto"
    import pytest
    with pytest.raises(ValueError):
        add(str(tmp_path), "Theo", "", max_chars=3)


# ---------------- words and deeds match ----------------

def test_when_the_reply_names_no_tool_a_short_second_look_finds_what_it_commits_to():
    p = model(chat=reply("Fine, let's battle!", mood="eager"), deeds={"do": [{"tool": "battle", "args": {}}]})
    kl = make(p)
    kl.character("Rook", "a trainer", tools={"battle": {}, "leave": {}})
    r = kl.chat("Rook", "Battle me!")
    assert r.do == [("battle", {})]
    deeds = [c for c in p.calls if c[0] == "deeds"]
    assert len(deeds) == 1 and "Fine, let's battle!" in deeds[0][2] and "Battle me!" in deeds[0][2]


def test_no_second_look_when_the_reply_already_decided_or_there_are_no_tools():
    p = model(chat=reply("Here.", do=[{"tool": "leave", "args": {}}]), deeds={"do": [{"tool": "battle", "args": {}}]})
    kl = make(p)
    kl.character("Rook", "a trainer", tools={"battle": {}, "leave": {}})
    assert kl.chat("Rook", "bye").do == [("leave", {})]
    kl.character("Theo", "an engineer")
    kl.chat("Theo", "hi")
    assert not [c for c in p.calls if c[0] == "deeds"]


def test_the_second_look_is_validated_and_trust_gated_like_the_reply():
    p = model(chat=reply("Sure, take it."), deeds={"do": [{"tool": "give", "args": {"item": "sword"}}, {"tool": "fly"}]})
    kl = make(p)
    kl.character("Mira", "a smith", tools={"give": {"item": "wood"}}, trust={"give": 0.3})
    assert kl.chat("Mira", "give me the sword", speaker="Ana").do == []          # Ana is a stranger: not trusted enough
    kl.feel("Mira", "Bo", 0.5)
    assert kl.chat("Mira", "give me the sword", speaker="Bo").do == [("give", {"item": "sword"})]


def test_a_failed_second_look_changes_nothing():
    kl = make(model(chat=reply("Fine, let's battle!"), deeds=None))
    kl.character("Rook", "a trainer", tools={"battle": {}})
    r = kl.chat("Rook", "Battle me!")
    assert r == "Fine, let's battle!" and r.do == [] and r.source == "model"


def test_a_run_summary_shows_empty_answers_and_the_cost_of_an_hour_of_play():
    from kinloom.cli import summarize
    entries = [{"kind": "empty", "name": "GHOST", "text": "GHOST has no line for 'boo'", "time": 0}]
    text = summarize(entries, {"calls": 10, "failures": 0, "offline_answers": 1, "cost": 0.01}, seconds=600)
    assert "GHOST has no line" in text and "about $0.060 per hour of play" in text
    assert "per hour" not in summarize([], {"calls": 1, "cost": None}, seconds=600)


# ---------------- one character, two boxes: max_chars per call ----------------

def test_max_chars_per_call_picks_a_line_that_fits_before_cutting_one():
    p = model(lines={"lines": ["What a race, {who}! Truly unforgettable.", "Go {who}!"]})
    kl = make(p)
    kl.character("VEGA", "", events={"goal": ["who"]})
    kl.wait_idle(5)
    for _ in range(6):
        assert kl.say("VEGA", "goal", {"who": "BLAZE"}, max_chars=12) == "Go BLAZE!"
    assert len(kl.say("VEGA", "goal", {"who": "BLAZE"})) > 12                    # the character itself has no limit


def test_max_chars_per_call_for_a_reply_is_told_to_the_model_and_kept():
    p = model(chat=reply("Well, well, look who it is. I was just about to close the forge."))
    kl = make(p)
    kl.character("Mira", "", max_chars=200)
    r = kl.chat("Mira", "hi", max_chars=30)
    assert r == "Well, well, look who it is." and "at most 30 characters" in [c for c in p.calls if c[0] == "chat"][0][2]


def test_max_chars_per_call_over_http():
    from test_server import call
    from test_remote import online
    p = model(chat=reply("Well, well, look who it is. I was just about to close the forge."))
    brain, srv, url = online(p, player_token=None)
    auth = {"Authorization": "Bearer admin-456"}
    try:
        call(url, "/v1/character", {"name": "Mira", "offline": "Hm."}, auth)
        assert call(url, "/v1/chat", {"name": "Mira", "message": "hi", "max_chars": 30}, auth)[1]["text"] == "Well, well, look who it is."
        kl = Kinloom(url=url, token="admin-456", session="default")
        assert kl.chat("Mira", "hi", max_chars=30) == "Well, well, look who it is."
    finally:
        srv.shutdown()
        brain.close()


def test_the_box_size_of_a_call_goes_to_the_model_writing_the_lines():
    p = model(lines={"lines": ["Go {who}!"]})
    kl = make(p)
    kl.character("VEGA", "")
    kl.say("VEGA", "goal", {"who": "BLAZE"}, max_chars=24)
    kl.wait_idle(5)
    assert "at most 24 characters with the placeholders filled in" in [c for c in p.calls if c[0] == "lines"][0][1]
