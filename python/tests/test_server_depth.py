"""Minds and the world over HTTP."""
from test_server import call, server  # noqa: F401  (fixture)

SENSES = {"d": [0, 10], "armed": True}
ACTIONS = {"a": {}, "b": {"power": [0.0, 1.0]}}


def test_minds_over_http(server):
    brain, url = server()
    status, body, _ = call(url, "/v1/mind", {"name": "toy", "senses": SENSES, "actions": ACTIONS,
                                            "rules": {"a": ["d below 5"], "b": {"when": ["d above 5"], "args": {"power": "d high"}}},
                                            "variants": 2})
    assert status == 200
    mind = body["mind"]
    assert mind["order"] == ["a", "b"] and len(mind["variants"]) == 2 and len(mind["ids"]) == 2
    assert mind["variants"][0]["b"]["args"]["power"] == ["d", "high", 0.0, 10.0, 0.0, 1.0, False]
    got = call(url, "/v1/think", {"name": "toy", "senses": {"d": 8}, "who": "u1"})[1]
    assert got["action"] == "b" and got["args"] == {"power": 0.8} and got["variant"] in (0, 1)
    s, got, _ = call(url, "/v1/mind?name=toy")
    assert s == 200 and got["mind"]["version"] == mind["version"] and got["report"]["generation"] == 0
    assert call(url, "/v1/mind?name=nope")[0] == 404
    s, got, _ = call(url, "/v1/reward", {"rewards": [{"who": "u1", "mind": "toy", "variant": 0, "id": mind["ids"][0], "action": "b",
                                                     "reward": 1}, {"who": "u2", "mind": "toy", "variant": 1, "id": 999,
                                                                    "reward": 1}, "junk", {"reward": 3}]})
    assert s == 200 and got["versions"] == {"toy": mind["version"]}
    report = call(url, "/v1/mind?name=toy")[1]["report"]
    assert [v["rewards"] for v in report["variants"]] == [1, 0]
    e = call(url, "/v1/explain", {"name": "toy", "senses": {"d": 2}})[1]
    assert e["action"] == "a"


def test_bad_minds_get_clear_errors(server):
    brain, url = server()
    s, body, _ = call(url, "/v1/mind", {"name": "x", "senses": {"d": 3}, "actions": ACTIONS})
    assert s == 400 and "sense 'd'" in body["error"]
    s, body, _ = call(url, "/v1/mind", {"name": "x", "senses": SENSES})
    assert s == 400 and "actions" in body["error"]
    assert call(url, "/v1/reward", {"rewards": "x"})[0] == 400
    assert call(url, "/v1/think", {"name": "nope", "senses": {}})[1]["action"] is None


def test_world_over_http(server):
    brain, url = server()
    call(url, "/v1/character", {"name": "BAKER", "personality": "baker", "group": "village"})
    call(url, "/v1/character", {"name": "GUARD", "personality": "guard", "group": "guards"})
    assert call(url, "/v1/event", {"text": "the player stole bread", "by": "PLAYER", "seen_by": ["BAKER"], "tag": "theft",
                                   "impact": -0.8})[0] == 200
    assert call(url, "/v1/knows", {"name": "GUARD", "tag": "theft"})[1]["knows"] is False
    shared = call(url, "/v1/meet", {"a": "BAKER", "b": "GUARD"})[1]["shared"]
    assert shared[0]["from"] == "BAKER"
    k = call(url, "/v1/knows", {"name": "GUARD", "tag": "theft"})[1]
    assert k["knows"] is True and k["notes"][0]["source"] == "BAKER"
    assert call(url, "/v1/opinion", {"a": "GUARD", "b": "PLAYER"})[1]["opinion"] == -0.2
    assert call(url, "/v1/opinions", {"name": "BAKER"})[1]["opinions"] == {"PLAYER": -0.8}
    assert call(url, "/v1/feel", {"a": "GUARD", "b": "PLAYER", "change": 0.5})[1]["opinion"] == 0.3
    assert call(url, "/v1/reputation", {"target": "PLAYER", "group": "village"})[1]["reputation"] == -0.8
    assert call(url, "/v1/spread", {})[0] == 200
    assert call(url, "/v1/event", {"text": "x", "seen_by": "BAKER"})[0] == 400
    status = call(url, "/v1/status")[1]
    assert {c["name"]: c["group"] for c in status["characters"]} == {"BAKER": "village", "GUARD": "guards"}


def test_report_over_post_and_action_order(server):
    brain, url = server()
    assert call(url, "/v1/report", {"name": "nope"})[1] == {"missing": True}
    body = {"name": "o", "senses": SENSES, "actions": {"a": {}, "b": {}, "c": {}}, "order": ["c", "a", "zz"]}
    assert call(url, "/v1/mind", body)[1]["mind"]["order"] == ["c", "a", "b"]
    got = call(url, "/v1/report", {"name": "o"})[1]
    assert got["mind"]["order"] == ["c", "a", "b"] and got["report"]["generation"] == 0
    assert call(url, "/v1/think", {"name": "o", "senses": {}})[1]["action"] == "c"
