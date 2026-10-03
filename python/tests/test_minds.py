"""Minds: readable rules compiled to utility AI, run locally, validated, mutated."""
import random

import pytest

from kinloom import minds

SENSES = {"hp": (0.0, 1.0), "enemy_dist": (0, 40), "has_ammo": True, "enemy": ["idle", "alert", "fleeing"]}
ACTIONS = {"charge": {"speed": (1.0, 3.0)}, "shoot": {"burst": (1, 5)}, "retreat": {}, "wait": {}}


def decl(rules=None, variants=1):
    return minds.Declaration("raider", "a cunning raider", SENSES, ACTIONS, rules, variants)


# ---------- rules ----------

@pytest.mark.parametrize("text,op,p1", [
    ("hp low", "low", 0.0), ("hp high", "high", 0.0), ("enemy_dist below 12", "below", 12.0),
    ("enemy_dist above 5", "above", 5.0), ("enemy_dist around 10", "around", 10.0), ("enemy_dist < 12", "below", 12.0),
    ("enemy_dist >= 5", "above", 5.0), ("enemy_dist ~ 10", "around", 10.0), ("has_ammo", "flag", 0),
    ("not has_ammo", "not", 0), ("!has_ammo", "not", 0), ("enemy is fleeing", "is", "fleeing"), ("enemy = alert", "is", "alert"),
    ("  HP   LOW ", "low", 0.0), ("Enemy IS Fleeing", "is", "fleeing"),
])
def test_rules_parse(text, op, p1):
    senses = minds.senses_of(SENSES)
    rule, error = minds.parse_rule(text, senses)
    assert error is None, error
    assert rule[1] == op
    assert rule[2] == p1


@pytest.mark.parametrize("text", ["mana low", "hp sideways", "hp above", "hp above lots", "has_ammo high", "enemy is dead",
                                  "enemy below 3", "", "hp low; drop table", 42])
def test_bad_rules_are_refused_with_a_reason(text):
    rule, error = minds.parse_rule(text, minds.senses_of(SENSES))
    assert rule is None and error


def test_thresholds_are_clamped_into_the_sense_range():
    rule, _ = minds.parse_rule("enemy_dist below 900", minds.senses_of(SENSES))
    assert rule[2] == 40.0


def test_senses_must_be_ranges_flags_or_options():
    with pytest.raises(ValueError):
        minds.senses_of({"hp": 0.5})
    with pytest.raises(ValueError):
        minds.senses_of({"x": "text"})


# ---------- running ----------

def test_offline_mind_is_the_rules():
    m = minds.Mind(decl({"retreat": ["hp low"], "shoot": ["has_ammo", "enemy_dist below 20"], "charge": {"score": 0.3}}))
    assert m.think({"hp": 0.1, "enemy_dist": 30, "has_ammo": True}, "a")["action"] == "retreat"
    assert m.think({"hp": 0.9, "enemy_dist": 8, "has_ammo": True}, "b")["action"] == "shoot"
    assert m.think({"hp": 0.9, "enemy_dist": 8, "has_ammo": False}, "c")["action"] == "charge"


def test_without_rules_the_first_action_wins():
    m = minds.Mind(decl())
    assert m.think({"hp": 0.5}, "x")["action"] == "charge"


def test_rule_arguments_map_into_the_argument_range():
    m = minds.Mind(decl({"charge": {"when": ["hp high"], "args": {"speed": "enemy_dist high"}}}))
    far = m.think({"hp": 1.0, "enemy_dist": 40}, "a")
    near = m.think({"hp": 1.0, "enemy_dist": 0}, "b")
    assert far["action"] == "charge" and far["args"]["speed"] == pytest.approx(3.0)
    assert near["args"]["speed"] == pytest.approx(1.0)


def test_constant_arguments_are_validated_and_missing_ones_get_the_default():
    m = minds.Mind(decl({"shoot": {"score": 2, "args": {"burst": 99}}, "charge": {"score": 1}}))
    assert m.think({}, "a") == {"action": "shoot", "args": {"burst": 5}, "variant": 0}
    m = minds.Mind(decl({"charge": {"score": 2}}))
    assert m.think({}, "a")["args"] == {"speed": 2.0}


def test_missing_or_wrong_senses_are_neutral_not_errors():
    m = minds.Mind(decl({"retreat": ["hp low"], "wait": {"score": 0.4}}))
    assert m.think({"hp": "lots"}, "a")["action"] == "retreat"   # 0.5 > 0.4
    assert m.think({"hp": float("nan")}, "b")["action"] == "retreat"
    assert m.think(None, "c")["action"] == "retreat"


def test_a_unit_keeps_its_action_unless_another_is_clearly_better():
    m = minds.Mind(decl({"retreat": ["hp low"], "charge": ["hp high"]}))
    assert m.think({"hp": 0.45}, "u")["action"] == "retreat"
    assert m.think({"hp": 0.52}, "u")["action"] == "retreat"      # sticky
    assert m.think({"hp": 0.7}, "u")["action"] == "charge"
    assert m.think({"hp": 0.52}, "fresh")["action"] == "charge"   # a new unit has no history


def test_explain_gives_every_score_and_its_rules():
    m = minds.Mind(decl({"retreat": ["hp low"], "shoot": ["has_ammo", "enemy_dist below 20"]}))
    e = m.explain({"hp": 0.2, "enemy_dist": 30, "has_ammo": True})
    assert e["action"] == "retreat"
    assert set(e["scores"]) == set(ACTIONS)
    assert e["scores"]["retreat"]["score"] == pytest.approx(0.8)
    assert "hp low" in e["scores"]["retreat"]["rules"]


def test_curves():
    s = minds.senses_of(SENSES)
    val = lambda text, v: minds.rule_value(minds.parse_rule(text, s)[0], {"hp": v, "enemy_dist": v, "has_ammo": v, "enemy": v})
    assert val("enemy_dist below 10", 0) > 0.99 and val("enemy_dist below 10", 20) < 0.01
    assert val("enemy_dist below 10", 10) == pytest.approx(0.5)
    assert val("enemy_dist around 10", 10) == pytest.approx(1.0) and val("enemy_dist around 10", 30) < 0.01
    assert val("has_ammo", True) == 1.0 and val("has_ammo", False) == 0.0 and val("not has_ammo", False) == 1.0
    assert val("enemy is alert", "alert") == 1.0 and val("enemy is alert", "idle") == 0.0
    assert val("hp high", 2.0) == 1.0 and val("hp low", -1) == 1.0


def test_variants_are_stable_per_unit():
    assert minds.fnv1a("a") == 0xE40C292C
    assert minds.fnv1a("") == 0x811C9DC5
    assert minds.fnv1a("é") == minds.fnv1a("é")


# ---------- validating what a model writes ----------

def test_model_programs_are_validated():
    d = decl()
    prog, errors = minds.validate({"retreat": {"score": 9, "when": ["hp low"]}, "wait": {"when": ["hp low", "mana high"]},
                                   "fly": {"score": 1},
                                   "shoot": {"when": "has_ammo", "args": {"burst": "enemy_dist low", "extra": 1}}}, d)
    assert prog["retreat"]["score"] == 3.0
    assert prog["retreat"]["when"] == ["hp low"]
    assert prog["wait"]["score"] == 0          # an action with a broken rule is dropped whole, never widened
    assert "fly" not in prog
    assert prog["shoot"]["when"] == ["has_ammo"]
    assert prog["shoot"]["args"] == {"burst": "enemy_dist low"}
    assert any("mana" in e for e in errors) and any("fly" in e for e in errors)


@pytest.mark.parametrize("bad", [None, "x", [], {}, {"fly": {}}, {"retreat": "hp low; rm"}, {"charge": {"args": {"speed": "hp is x"}}}])
def test_garbage_programs_fall_back(bad):
    prog, errors = minds.validate(bad, decl())
    if prog is not None:
        assert set(prog) <= set(ACTIONS)
        assert minds.Mind(decl(), [prog]).think({"hp": 0.5}, "x")["action"] in ACTIONS


def test_program_text_and_limits_cannot_grow():
    prog, _ = minds.validate({"retreat": {"when": ["hp low"] * 50}}, decl())
    assert len(prog["retreat"]["when"]) <= minds.MAX_RULES


# ---------- mutation ----------

def test_mutation_is_valid_different_and_seeded():
    d = decl({"retreat": ["hp low"], "shoot": ["has_ammo", "enemy_dist below 20"]})
    base = minds.validate(d.rules, d)[0]
    seen = set()
    for seed in range(40):
        child = minds.mutate(base, d, random.Random(seed))
        again = minds.mutate(base, d, random.Random(seed))
        assert child == again
        assert minds.validate(child, d)[0] == child
        seen.add(repr(sorted(child.items())))
    assert len(seen) > 20


# ---------- compiled form (what the clients run) ----------

def test_compiled_form_is_plain_numbers_and_strings():
    m = minds.Mind(decl({"retreat": ["hp low"], "charge": {"when": ["enemy_dist around 10"], "args": {"speed": "hp high"}}}))
    c = m.compiled()
    assert c["order"] == list(ACTIONS)
    assert c["variants"][0]["retreat"]["when"] == [["hp", "low", 0.0, 1.0]]
    assert c["variants"][0]["charge"]["args"]["speed"] == ["hp", "high", 0.0, 1.0, 1.0, 3.0, False]
    assert c["stick"] == minds.STICK
    assert minds.run_compiled(c, {"hp": 0.1}, "u", {})["action"] == "retreat"


def test_an_action_argument_that_is_a_list_is_given_as_it_is():
    # a list argument is not a sense-mapped one ([sense, op, p1, p2, lo, hi, whole]): think used to crash on it
    d = minds.Declaration("m", "", {"hp": (0, 1)}, {"drop": {"items": ["sword"], "count": (1, 3)}, "wait": {}},
                          {"drop": {"when": ["hp low"], "args": {"count": "hp low"}}}, 1)
    m = minds.Mind(d)
    t = minds.run_compiled(m.compiled(), {"hp": 0.0}, "u", {})
    assert t["action"] == "drop" and t["args"]["count"] == 3
    assert t["args"]["items"] == m.compiled()["variants"][0]["drop"]["args"]["items"]
    assert isinstance(t["args"]["items"], list)


def test_a_sense_whose_name_starts_with_not_is_not_negated():
    senses = minds.senses_of({"nothing": True, "note": (0, 1)})
    assert minds.parse_rule("nothing", senses)[0] == ["nothing", "flag", 0, 0]
    assert minds.parse_rule("not nothing", senses)[0] == ["nothing", "not", 0, 0]
    assert minds.parse_rule("note high", senses)[0][:2] == ["note", "high"]


# ---------------- credit: evidence and proposals ----------------

def toy_samples(n=400, seed=3):
    """"a" pays when d < 5 and costs otherwise; "b" is neutral."""
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        d = rnd.uniform(0, 10)
        action = rnd.choice(["a", "b"])
        g = (1.0 if d < 5 else -1.0) if action == "a" else 0.0
        out.append(({"d": d}, action, g + rnd.gauss(0, 0.2)))
    return out


def toy_decl(rules=None):
    return minds.Declaration("toy", "", {"d": (0, 10)}, {"a": {}, "b": {}, "c": {}}, rules, 2)


def test_evidence_finds_where_an_action_does_better_or_worse():
    found = minds.evidence(toy_decl(), toy_samples())
    assert all(abs(z) > 4 for z, *_ in found[:4])
    assert any(a == "a" and adv > 0 and "below" in rule for z, a, rule, adv, n in found)
    assert any(a == "a" and adv < 0 and "above" in rule for z, a, rule, adv, n in found)
    assert minds.evidence(toy_decl(), toy_samples()[:20]) == []


def test_a_proposal_makes_the_action_win_where_it_pays():
    decl = minds.Declaration("toy", "", {"d": (0, 10)}, {"a": {}, "b": {}}, {"b": {"score": 1}}, 2)
    base = decl.offline
    wins = 0
    for seed in range(10):
        child = minds.propose(base, decl, toy_samples(), random.Random(seed), min_z=2)
        if child is None:
            continue
        m = minds.Mind(decl, [child])
        if m.think({"d": 1}, None)["action"] == "a" and m.think({"d": 9}, None)["action"] == "b":
            wins += 1
    assert wins >= 8


def test_untried_actions_get_explored_and_nothing_is_proposed_without_data():
    decl = toy_decl({"b": {"score": 1}})
    seen = set()
    for seed in range(30):
        child = minds.propose(decl.offline, decl, toy_samples(), random.Random(seed))
        if child is not None and child["c"]["score"] > 0:
            seen.add(tuple(child["c"]["when"]))
    assert seen                                    # "c" was never played: some proposals try it somewhere
    assert minds.propose(decl.offline, decl, [], random.Random(1)) is None
