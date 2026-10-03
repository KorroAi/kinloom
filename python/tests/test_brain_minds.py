"""Minds in the brain: declared, run instantly, written by a model, and learning from rewards (with or without one)."""
import json
import random
import time


from test_brain import Clock, make, model

SENSES = {"d": (0, 10), "armed": True}
ACTIONS = {"a": {}, "b": {"power": (0.0, 1.0)}}


def play(kl, steps, clock, units=20, seed=1, mind="toy"):
    """A toy game: the right action is "a" when d < 5, else "b". Returns the mean reward of each step."""
    rnd = random.Random(seed)
    means = []
    for _ in range(steps):
        total = 0
        for u in range(units):
            d = rnd.uniform(0, 10)
            choice = kl.think(mind, {"d": d, "armed": True}, who="unit-%d" % u)
            r = 1.0 if choice["action"] == ("a" if d < 5 else "b") else 0.0
            kl.reward("unit-%d" % u, r)
            total += r
        means.append(total / units)
        clock.t += 1.0
        kl.wait_idle(5)
    return means


def test_offline_the_rules_are_the_mind():
    kl = make(None)
    kl.mind("toy", "a unit", SENSES, ACTIONS, rules={"a": ["d below 5"], "b": ["d above 5"]})
    assert kl.think("toy", {"d": 2}, who="u1")["action"] == "a"
    assert kl.think("toy", {"d": 8}, who="u1")["action"] == "b"
    assert kl.think("unknown", {"d": 8}) == {"action": None, "args": {}, "variant": 0}
    e = kl.explain("toy", {"d": 8})
    assert e["action"] == "b" and e["scores"]["b"]["rules"] == ["d above 5"]


def test_bad_declarations_are_refused_clearly():
    kl = make(None)
    for senses, actions in [({"d": 3}, ACTIONS), (SENSES, {}), (SENSES, {"bad name": {}}), (None, ACTIONS)]:
        try:
            kl.mind("x", "", senses, actions)
        except ValueError as e:
            assert str(e)
        else:
            raise AssertionError("accepted %r %r" % (senses, actions))


def test_offline_minds_learn_from_rewards_by_mutation():
    clock = Clock()
    kl = make(None, clock=clock)
    kl.mind("toy", "a unit", SENSES, ACTIONS, variants=4, learn=5)
    means = play(kl, 500, clock)
    first, last = sum(means[:30]) / 30, sum(means[-50:]) / 50
    report = kl.mind_report("toy")
    assert first < 0.6                      # always "a": right half the time
    assert last >= 0.85, (last, report["curve"][-10:])
    assert report["generation"] > 10


def test_learning_is_off_without_rewards_and_with_learn_0():
    clock = Clock()
    kl = make(None, clock=clock)
    kl.mind("toy", "a unit", SENSES, ACTIONS, variants=3, learn=0)
    play(kl, 50, clock)
    assert kl.mind_report("toy")["generation"] == 0


def test_the_model_writes_variants_from_the_personality_and_rules():
    variants = {"variants": [{"a": {"score": 1, "when": ["d below 4"]}, "b": {"score": 1, "when": ["d above 4"],
                                                                              "args": {"power": "d high"}}},
                             {"a": {"when": ["d below 6", "armed"]}, "b": {"when": ["d above 6"], "args": {"power": 0.2}}},
                             {"fly": {}}]}
    p = model(minds=variants)
    kl = make(p)
    kl.mind("toy", "a careful unit", SENSES, ACTIONS, rules={"a": ["d below 5"], "b": ["d above 5"]}, variants=3)
    kl.wait_idle(5)
    minds_calls = [c for c in p.calls if c[0] == "minds"]
    assert len(minds_calls) == 1
    system, user = minds_calls[0][1], minds_calls[0][2]
    assert "a careful unit" in system and "d: a number from 0 to 10" in system and "b(power:" in system
    assert "Write 2 different variants" in user and "d below 5" in user
    report = kl.mind_report("toy")
    assert [v["rules"]["a"]["when"] for v in report["variants"]] == [["d below 5"], ["d below 4"], ["d below 6", "armed"]]
    # every unit gets a stable variant; the arguments follow the rules
    seen = {kl.think("toy", {"d": 9, "armed": True}, who="u%d" % i)["variant"] for i in range(40)}
    assert seen == {0, 1, 2}


def test_a_broken_model_is_repaired_once_then_the_rules_stay():
    p = model(minds=["not json", {"variants": [{"a": {"when": ["mana high"]}}]}])
    kl = make(p)
    kl.mind("toy", "", SENSES, ACTIONS, rules={"a": ["d below 5"], "b": ["d above 5"]}, variants=2)
    kl.wait_idle(5)
    calls = [c for c in p.calls if c[0] == "minds"]
    assert len(calls) == 2 and "a mind is an object" in calls[1][2]
    assert kl.think("toy", {"d": 8}, who="x")["action"] == "b"
    assert kl.mind_report("toy")["variants"][1]["rules"]["a"]["when"] == ["d below 5"]


def test_with_a_model_learning_asks_it_to_rewrite_the_worst_variant():
    good = {"a": {"when": ["d below 5"]}, "b": {"when": ["d above 5"]}}
    learned = []

    def learn(system, user):
        learned.append(user)
        return {"variants": [good]}

    p = model(minds=[{"variants": [{"a": {"score": 1}}, {"b": {"score": 1}}]}, learn, learn, learn, learn])
    clock = Clock()
    kl = make(p, clock=clock)
    kl.mind("toy", "a unit", SENSES, ACTIONS, variants=2, learn=5)
    kl.wait_idle(5)
    means = play(kl, 60, clock)
    assert learned and "mean reward" in learned[0] and ("-> a ->" in learned[0] or "-> b ->" in learned[0])
    assert sum(means[-10:]) / 10 > 0.7


def test_rewards_for_a_replaced_variant_are_ignored():
    clock = Clock()
    kl = make(None, clock=clock)
    kl.mind("toy", "", SENSES, ACTIONS, variants=2, learn=5)
    c = kl.brain.mind_compiled("default", "toy")
    assert kl.brain.reward("default", "u", 1.0, mind="toy", variant=0, vid=c["ids"][0], action="a")
    assert not kl.brain.reward("default", "u", 1.0, mind="toy", variant=0, vid=999, action="a")
    assert not kl.reward("nobody", 1.0)
    assert not kl.reward("u", float("nan"))


def test_learned_minds_survive_a_restart(tmp_path):
    path = str(tmp_path / "memory.json")
    clock = Clock()
    kl = make(None, clock=clock, memory_path=path)
    kl.mind("toy", "a unit", SENSES, ACTIONS, variants=4, learn=5)
    play(kl, 200, clock)
    before = kl.mind_report("toy")
    kl.close()
    data = json.load(open(path, encoding="utf-8"))
    assert "default/toy" in data["extra"]["minds"]
    kl2 = make(None, memory_path=path)
    kl2.mind("toy", "a unit", SENSES, ACTIONS, variants=4, learn=5)
    after = kl2.mind_report("toy")
    assert after["generation"] == before["generation"] > 0
    assert [v["rules"] for v in after["variants"]] == [v["rules"] for v in before["variants"]]
    # a changed declaration starts again from its rules
    kl3 = make(None, memory_path=path)
    kl3.mind("toy", "a unit", SENSES, {"a": {}, "b": {}, "c": {}}, variants=4)
    assert kl3.mind_report("toy")["generation"] == 0


def test_redeclaring_the_same_mind_keeps_what_it_learned():
    clock = Clock()
    kl = make(None, clock=clock)
    kl.mind("toy", "a unit", SENSES, ACTIONS, variants=4, learn=5)
    play(kl, 100, clock)
    g = kl.mind_report("toy")["generation"]
    kl.mind("toy", "a unit", SENSES, ACTIONS, variants=4, learn=5)
    assert kl.mind_report("toy")["generation"] == g > 0


def test_think_is_fast_enough_for_crowds():
    kl = make(None)
    kl.mind("raider", "", {"hp": (0, 1), "dist": (0, 40), "ammo": True, "enemy": ["idle", "alert"]},
            {"charge": {"speed": (1, 3)}, "shoot": {"burst": (1, 5)}, "retreat": {}, "wait": {}},
            rules={"retreat": ["hp low"], "shoot": ["ammo", "dist below 20", "enemy is alert"],
                   "charge": {"when": ["hp high", "dist above 10"], "args": {"speed": "dist high"}}, "wait": {"score": 0.2}})
    senses = [{"hp": random.random(), "dist": random.uniform(0, 40), "ammo": True, "enemy": "alert"} for _ in range(1000)]
    start = time.perf_counter()
    for i, s in enumerate(senses):
        kl.think("raider", s, who=i)
    per = (time.perf_counter() - start) / len(senses)
    assert per < 0.0002, "%.1f µs per think" % (per * 1e6)


def test_a_decision_is_credited_with_what_it_set_up():
    """"prep" earns nothing itself, but the strike after it pays: prep's credited return is positive."""
    kl = make(None)
    kl.mind("duel", "", {"ready": True}, {"prep": {}, "strike": {}}, rules={"prep": ["not ready"], "strike": ["ready"]}, learn=0)
    for i in range(30):
        who = "u%d" % i
        kl.think("duel", {"ready": False}, who=who)
        kl.reward(who, 0.0)
        kl.think("duel", {"ready": True}, who=who)
        kl.reward(who, 1.0, done=True)
    state = kl.brain._minds[("default", "duel")]
    prep = [g for s, a, g in state.buffer if a == "prep"]
    assert len(prep) == 30 and all(abs(g - 0.8) < 1e-9 for g in prep)


def test_with_done_minds_judge_whole_episodes():
    clock = Clock()
    kl = make(None, clock=clock)
    kl.mind("toy", "", SENSES, ACTIONS, variants=2, learn=5)
    for step in range(10):
        for u in range(6):
            kl.think("toy", {"d": 3}, who="u%d" % u)
            kl.reward("u%d" % u, 1.0, done=step % 5 == 4)
    report = kl.mind_report("toy")
    assert report["per"] == "episode"
    assert sum(v["episodes"] for v in report["variants"]) == 12
    assert all(v["mean"] == 5.0 for v in report["variants"] if v["episodes"])


def test_the_demo_learns_to_win_without_a_key():
    from kinloom import demo
    r = demo.run(minutes=14, seed=1, report=lambda s: None)
    first = sum(x["win"] for x in r["rows"][:3]) / 3
    last = sum(x["win"] for x in r["rows"][-3:]) / 3
    assert first < 0.2 and last > 0.5, [x["win"] for x in r["rows"]]
    assert r["model_calls"] == 0
