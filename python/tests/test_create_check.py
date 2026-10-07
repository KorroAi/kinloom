"""create with the game's rules in the loop (check=) and the game's own offline answer (offline=): learned from the
demos, where a town plan, a carved room or a wish item must fit the game before it is used."""
import json

import pytest

from kinloom import Kinloom
from test_brain import make, model
from test_remote import online

PLAN = {"build": "tower", "x": [0, 20]}


def _fits(plan):
    return "" if plan["x"] <= 10 else "no room at x=%d, the plot ends at 10" % plan["x"]


def test_an_answer_the_game_accepts_is_used_as_it_is():
    p = model(create={"build": "tower", "x": 4})
    kl = make(p)
    assert kl.create("a building", PLAN, check=_fits) == {"build": "tower", "x": 4}
    assert len(p.calls) == 1


def test_a_refused_answer_goes_back_once_with_the_reason_then_the_new_one_is_used():
    p = model(create=[{"build": "tower", "x": 17}, {"build": "tower", "x": 9}])
    kl = make(p)
    assert kl.create("a building", PLAN, check=_fits) == {"build": "tower", "x": 9}
    retry = p.calls[1][2]
    assert "The game refused your last answer: no room at x=17, the plot ends at 10" in retry
    assert 'The refused answer: {"build": "tower", "x": 17}' in retry
    assert any(e["kind"] == "refused" and "no room at x=17" in e["text"] for e in kl.journal())


def test_refused_twice_gives_the_games_own_offline_answer():
    p = model(create=[{"build": "tower", "x": 17}, {"build": "tower", "x": 18}])
    kl = make(p)
    got = kl.create("a building", PLAN, check=_fits, offline={"build": "hut", "x": 1})
    assert got == {"build": "hut", "x": 1} and len(p.calls) == 2
    assert sum(1 for e in kl.journal() if e["kind"] == "refused") == 2


def test_false_refuses_and_true_accepts():
    kl = make(model(create=[{"build": "tower", "x": 3}, {"build": "tower", "x": 4}]))
    assert kl.create("a building", PLAN, check=lambda v: False, offline={"build": "hut", "x": 1}) == {"build": "hut", "x": 1}
    kl = make(model(create={"build": "tower", "x": 3}))
    assert kl.create("a building", PLAN, check=lambda v: True) == {"build": "tower", "x": 3}


def test_the_offline_answer_is_the_games_own_and_must_fit_the_shape():
    kl = make(None)
    assert kl.create("a building", PLAN, offline={"build": "hut", "x": 2}) == {"build": "hut", "x": 2}
    assert kl.create("a building", PLAN) == {"build": "tower", "x": 10}
    with pytest.raises(ValueError, match="offline must be shaped like the example"):
        kl.create("a building", PLAN, offline={"x": "far"})
    with pytest.raises(ValueError, match="check must be a function"):
        kl.create("a building", PLAN, check="no towers")
    assert make(model(create=None)).create("a building", PLAN, offline={"build": "hut", "x": 2}) == {"build": "hut", "x": 2}


def test_lists_keep_what_the_game_accepts_and_fill_with_the_offline_answer():
    p = model(create={"items": [{"build": "a", "x": 2}, {"build": "b", "x": 15}, {"build": "c", "x": 7}]})
    kl = make(p)
    got = kl.create("buildings", PLAN, count=3, check=_fits, offline={"build": "hut", "x": 1})
    assert got == [{"build": "a", "x": 2}, {"build": "c", "x": 7}, {"build": "hut", "x": 1}]


def test_instant_items_the_game_refuses_are_not_used():
    kl = make(model(create={"items": [{"build": "far", "x": 19}] * 8}))
    first = kl.create("a building", PLAN, instant=True, check=_fits, offline={"build": "hut", "x": 1})
    assert first == {"build": "hut", "x": 1}            # nothing made yet: the offline answer
    kl.brain.wait_idle()
    assert kl.create("a building", PLAN, instant=True, check=_fits, offline={"build": "hut", "x": 1}) == {"build": "hut", "x": 1}


def test_through_a_server_the_check_runs_in_the_game_and_the_server_hears_why():
    p = model(create=[{"build": "tower", "x": 17}, {"build": "tower", "x": 9}])
    brain, srv, url = online(p)
    try:
        kl = Kinloom(url=url, token="play-123", session="s")
        seen = []

        def check(plan):
            seen.append(plan["x"])
            return _fits(plan)
        assert kl.create("a building", PLAN, check=check, offline={"build": "hut", "x": 1}) == {"build": "tower", "x": 9}
        assert seen == [17, 9]
        assert "The game refused your last answer: no room at x=17" in p.calls[1][2]
        assert any(e["kind"] == "refused" and "no room at x=17" in e["text"] for e in brain.journal())
    finally:
        srv.shutdown()
        brain.close()


def test_through_a_server_an_offline_answer_is_never_checked_or_retried():
    brain, srv, url = online(model(create=None))
    try:
        kl = Kinloom(url=url, token="play-123", session="s")
        assert kl.create("a building", PLAN, check=lambda v: "never", offline={"build": "hut", "x": 1}) == {"build": "hut", "x": 1}
    finally:
        srv.shutdown()
        brain.close()


def test_the_http_answer_says_where_it_came_from():
    from test_server import call
    brain, srv, url = online(model(create={"build": "tower", "x": 3}))
    try:
        h = {"Authorization": "Bearer admin-456"}
        status, body, _ = call(url, "/v1/create", {"what": "a building", "example": PLAN}, h)
        assert status == 200 and body == {"value": {"build": "tower", "x": 3}, "source": "model"}
        status, body, _ = call(url, "/v1/create", {"what": "a building", "example": PLAN,
                                                   "refused": {"answer": {"x": 99}, "why": "too far"}}, h)
        assert status == 200
        status, body, _ = call(url, "/v1/create", {"what": "a building", "example": PLAN, "refused": "too far"}, h)
        assert status == 400 and "refused must be" in json.dumps(body)
    finally:
        srv.shutdown()
        brain.close()
