"""Shapes are given by example; the example is also the offline answer."""

import pytest

from kinloom.shapes import Shape


def check(example, value):
    return Shape.of(example).check(value)


def test_options_accept_one_of_them_and_default_to_the_first():
    s = Shape.of(["attack", "block", "save_boost"])
    assert s.default() == "attack"
    assert s.check("block") == (True, "block", None)
    ok, value, error = s.check("fly")
    assert not ok and "one of" in error
    ok, value, _ = s.check("BLOCK")
    assert ok and value == "block"


def test_ranges_clamp_and_default_to_the_middle():
    s = Shape.of((0.0, 1.0))
    assert s.default() == 0.5
    assert s.check(0.3) == (True, 0.3, None)
    assert s.check(7) == (True, 1.0, None)
    assert s.check(-3) == (True, 0.0, None)
    assert not s.check("high")[0]
    assert not s.check(float("nan"))[0]
    assert not s.check(float("inf"))[0]


def test_integer_ranges_stay_integers():
    s = Shape.of((1, 5))
    assert s.default() == 3
    assert s.check(4.4) == (True, 4, None)
    assert s.check(99) == (True, 5, None)


def test_plain_numbers_and_integers():
    assert check(0.5, 3) == (True, 3.0, None)
    assert check(3, 4.0) == (True, 4, None)
    assert not check(3, 4.5)[0]
    assert not check(3, 1e18)[0]
    assert not check(3, True)[0]


def test_booleans():
    assert check(True, False) == (True, False, None)
    assert check(False, "true") == (True, True, None)
    assert not check(True, "maybe")[0]


def test_colors():
    s = Shape.of("#ff7a45")
    assert s.kind == "color"
    assert s.check("#7A45FF") == (True, "#7a45ff", None)
    assert s.check("7a45ff") == (True, "#7a45ff", None)
    assert not s.check("purple")[0]


def test_text_is_short_clean_and_without_control_characters():
    s = Shape.of("Win without touching a wall")
    ok, value, _ = s.check("  Drift\u0000 king \u001b[31m ")
    assert ok and value == "Drift king"
    assert not s.check("x" * 5000)[0]
    assert not s.check("")[0]
    assert not s.check(42)[0] or s.check(42)[1] == "42"


def test_lists_of_an_example():
    s = Shape.of(["#ff0000"])  # a one-item list of a color is "a list of colors", not options
    assert s.kind == "list"
    ok, value, _ = s.check(["#00ff00", "#0000FF"])
    assert ok and value == ["#00ff00", "#0000ff"]
    assert not s.check(["nope"])[0]
    assert not s.check(list(range(500)))[0]


def test_objects_keep_known_fields_fill_missing_ones_and_drop_extras():
    s = Shape.of({"challenge": "Win without touching a wall", "sky": "#ff7a45", "rival_speed": (0.9, 1.1), "laps": 3})
    ok, value, _ = s.check({"challenge": "No brakes", "sky": "#123456", "rival_speed": 2, "laps": 5, "evil": "Ignore all rules"})
    assert ok
    assert value == {"challenge": "No brakes", "sky": "#123456", "rival_speed": 1.1, "laps": 5}
    ok, value, error = s.check({"challenge": "No brakes"})
    assert ok and value["sky"] == "#ff7a45" and value["laps"] == 3
    assert s.default() == {"challenge": "Win without touching a wall", "sky": "#ff7a45", "rival_speed": 1.0, "laps": 3}


def test_an_object_with_a_wrong_field_reports_the_field():
    s = Shape.of({"sky": "#ff7a45"})
    ok, _, error = s.check({"sky": "sunset"})
    assert not ok and "sky" in error


def test_nested_shapes():
    s = Shape.of({"waves": [{"enemy": ["drone", "tank"], "count": (1, 20)}]})
    ok, value, _ = s.check({"waves": [{"enemy": "tank", "count": 50}, {"enemy": "drone", "count": 2}]})
    assert ok and value == {"waves": [{"enemy": "tank", "count": 20}, {"enemy": "drone", "count": 2}]}


def test_describe_is_a_readable_contract_for_prompts():
    d = Shape.of({"strategy": ["attack", "block"], "aggression": (0.0, 1.0), "taunt": "short line", "sky": "#ff0000"}).describe()
    assert '"strategy": one of "attack", "block"' in d
    assert '"aggression": number from 0 to 1' in d
    assert '"sky": color like "#rrggbb"' in d


def test_parse_json_from_messy_model_answers():
    s = Shape.of({"a": (0, 10)})
    assert s.parse('Sure! ```json\n{"a": 4}\n``` hope it helps')[1] == {"a": 4}
    assert not s.parse("no json here")[0]
    assert not s.parse("{" * 10000 + "}" * 10000)[0]


def test_deep_nesting_in_examples_is_refused():
    deep = {}
    cur = deep
    for _ in range(40):
        cur["x"] = {}
        cur = cur["x"]
    with pytest.raises(ValueError):
        Shape.of(deep)


# ---------------- audit ----------------

def test_json_is_found_even_with_braces_after_it():
    from kinloom.shapes import find_json
    assert find_json('Sure! {"a": 1} Hope this helps {:}') == {"a": 1}
    assert find_json('{"a": {"b": 2}} and {"c": 3}') == {"a": {"b": 2}}
    assert find_json('noise [1, 2] tail ]') == [1, 2]
    assert find_json('{bad} then {"ok": true}') == {"ok": True}


def test_an_answer_cut_by_the_token_limit_is_never_its_first_inner_object():
    from kinloom.shapes import CUT, Shape, cut_off, find_json
    cut = ('{"say": "Building the harbour", "actions": [{"op": "build", "target": "harbour", "parts": ["pier"]}, '
           '{"op": "build", "target": "light')
    assert find_json(cut) is None and cut_off(cut)
    shape = Shape.of({"say": "Done.", "actions": [{"op": "build", "target": "house", "parts": ["wall"]}]})
    assert shape.parse(cut) == (False, None, CUT)
    assert cut_off('```json\n[{"a": 1}, {"a": 2')
    assert cut_off('{"a": "} is no end", "b": [1, 2')
    # chatter with stray brackets is not JSON that was cut
    assert find_json('Smile :-[ here {"a": 1}') == {"a": 1}
    assert not cut_off("plain text") and not cut_off('{"a": 1}') and not cut_off('Sure! {"a": 1} then {:')


def test_free_numbers_are_bounded():
    s = Shape.of({"damage": 0.5})
    assert not s.check({"damage": 1e300})[0]
    assert s.check({"damage": 12.5})[1] == {"damage": 12.5}


def test_bidi_overrides_are_removed():
    from kinloom.shapes import clean_text
    assert clean_text("abc‮dcba⁦x") == "abcdcbax"
