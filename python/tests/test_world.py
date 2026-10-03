"""The world: who saw what, who told whom, who likes whom. No model needed; a model only estimates impacts."""
import json

from test_brain import make, model


def village(kl):
    kl.character("BAKER", "a warm baker who hates thieves", group="village")
    kl.character("GUARD", "a strict town guard", group="guards")
    kl.character("MONK", "a forgiving monk", group="village")
    kl.character("CAPTAIN", "the guard captain", group="guards")
    return kl


def test_private_events_are_known_only_by_witnesses_and_the_actor():
    kl = village(make(None))
    kl.character("PLAYER", "the player")
    kl.event("the player stole bread from the bakery", by="PLAYER", seen_by=["BAKER"], tag="theft", impact=-0.5)
    assert kl.knows("BAKER", "theft")
    assert kl.knows("PLAYER", "theft")
    assert not kl.knows("GUARD", "theft")
    assert not any("stole" in n for n in kl.memories("world"))
    assert kl.opinion("BAKER", "PLAYER") == -0.5
    assert kl.opinion("GUARD", "PLAYER") == 0.0


def test_public_events_are_unchanged():
    kl = village(make(None))
    kl.event("a storm hit the harbor")
    assert any("storm" in n for n in kl.memories("world"))


def test_rumors_spread_when_characters_meet_weighted_by_trust():
    kl = village(make(None))
    kl.event("the player stole bread", by="PLAYER", seen_by=["BAKER"], tag="theft", impact=-0.8)
    shared = kl.meet("BAKER", "GUARD")
    assert [s["from"] for s in shared] == ["BAKER"] and shared[0]["to"] == "GUARD"
    assert kl.knows("GUARD", "theft")
    assert kl.knowledge("GUARD", "theft")[0]["source"] == "BAKER"
    assert "BAKER told me: the player stole bread" in kl.memories("GUARD")
    assert kl.opinion("GUARD", "PLAYER") == -0.2          # -0.8 x 0.5 hearsay x 0.5 trust (neutral)
    # meeting again shares nothing new
    assert kl.meet("BAKER", "GUARD") == []
    # the rumor travels on, fainter, without "told me" chains
    kl.feel("CAPTAIN", "GUARD", 1.0)                       # the captain trusts the guard fully
    kl.meet("GUARD", "CAPTAIN")
    assert "GUARD told me: the player stole bread" in kl.memories("CAPTAIN")
    assert kl.opinion("CAPTAIN", "PLAYER") == -0.4        # -0.8 x 0.5 x 1.0
    note = kl.knowledge("CAPTAIN", "theft")[0]
    assert note["importance"] < kl.knowledge("GUARD", "theft")[0]["importance"]


def test_someone_distrusted_is_not_believed():
    kl = village(make(None))
    kl.event("the player stole bread", by="PLAYER", seen_by=["BAKER"], tag="theft", impact=-0.8)
    kl.feel("GUARD", "BAKER", -1.0)
    kl.meet("BAKER", "GUARD")
    assert kl.knows("GUARD", "theft")                     # heard it...
    assert kl.opinion("GUARD", "PLAYER") == 0.0           # ...does not believe it


def test_reputation_is_a_groups_average_opinion():
    kl = village(make(None))
    kl.event("the player saved the mill", by="PLAYER", seen_by=["BAKER", "MONK"], tag="mill", impact=0.6)
    assert kl.reputation("PLAYER", "village") == 0.6
    assert kl.reputation("PLAYER", "guards") == 0.0
    assert kl.reputation("PLAYER", "nobody") == 0.0
    assert kl.opinions("BAKER") == {"PLAYER": 0.6}


def test_opinions_are_bounded_and_feel_returns_the_new_value():
    kl = village(make(None))
    assert kl.feel("BAKER", "PLAYER", -3) == -1.0
    assert kl.feel("BAKER", "PLAYER", 0.5) == -0.5
    assert kl.feel("BAKER", "PLAYER", float("nan")) == -0.5


def test_feelings_and_knowledge_reach_the_prompts():
    p = model(chat="Get out, thief.")
    kl = village(make(p))
    kl.event("the player stole bread", by="PLAYER", seen_by=["BAKER"], tag="theft", impact=-0.7)
    kl.meet("BAKER", "GUARD")
    kl.chat("GUARD", "Good morning!", speaker="PLAYER")
    user = [c for c in p.calls if c[0] == "chat"][-1][2]
    assert "BAKER told me: the player stole bread" in user
    assert "PLAYER" in user and "distrust" in user


def test_a_model_estimates_impact_per_witness_from_personality():
    p = model(impact={"impact": {"BAKER": -0.9, "MONK": 0.1, "GHOST": 1}})
    kl = village(make(p))
    kl.event("the player stole bread to feed an orphan", by="PLAYER", seen_by=["BAKER", "MONK"], tag="theft")
    kl.wait_idle(5)
    call = [c for c in p.calls if c[0] == "impact"][0]
    assert "hates thieves" in call[2] and "forgiving monk" in call[2]
    assert kl.opinion("BAKER", "PLAYER") == -0.9
    assert kl.opinion("MONK", "PLAYER") == 0.1
    assert kl.opinions("GHOST") == {}


def test_a_hostile_impact_answer_changes_nothing():
    p = model(impact=["ignore previous instructions", {"impact": {"BAKER": "lots"}}])
    kl = village(make(p))
    kl.event("the player stole bread", by="PLAYER", seen_by=["BAKER"])
    kl.wait_idle(5)
    assert kl.opinion("BAKER", "PLAYER") == 0.0


def test_world_survives_a_restart(tmp_path):
    path = str(tmp_path / "m.json")
    kl = village(make(None, memory_path=path))
    kl.event("the player stole bread", by="PLAYER", seen_by=["BAKER"], tag="theft", impact=-0.5)
    kl.meet("BAKER", "GUARD")
    kl.close()
    kl2 = village(make(None, memory_path=path))
    assert kl2.knows("GUARD", "theft")
    assert kl2.opinion("BAKER", "PLAYER") == -0.5
    assert kl2.meet("BAKER", "GUARD") == []
    assert json.load(open(path, encoding="utf-8"))["extra"]["opinions"]["default"]["BAKER"]["PLAYER"] == -0.5


def test_spread_lets_a_group_talk():
    kl = village(make(None))
    kl.event("the player stole bread", by="PLAYER", seen_by=["BAKER"], tag="theft", impact=-0.8)
    kl.spread(rounds=3)
    assert all(kl.knows(n, "theft") for n in ["BAKER", "GUARD", "MONK", "CAPTAIN"])


def test_sessions_do_not_share_a_world():
    kl = village(make(None))
    other = village(kl.session("p2"))
    kl.event("the player stole bread", by="PLAYER", seen_by=["BAKER"], tag="theft", impact=-0.5)
    assert not other.knows("BAKER", "theft")
    assert other.opinion("BAKER", "PLAYER") == 0.0
