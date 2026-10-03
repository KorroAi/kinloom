"""The measure's checker, without a model: `python -m pytest proof/universal`."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run  # noqa: E402

SRC = run.source(None)


def test_good_code_passes():
    code = ('pack = kl.create("a booster pack", {"name": "Ember", "cost": [1, 10], "effect": "text"}, count=3)\n'
            'print(pack[0]["name"])\n')
    r = run.check(SRC, code, ["create"])
    assert r["pass"] and r["calls"] == ["create"], r


def test_a_new_kinloom_in_the_snippet_is_the_offline_one():
    code = "from kinloom import Kinloom\nkl2 = Kinloom()\nprint(kl2.decide('X', {'a': 1}, ['up', 'down']))\n"
    r = run.check(SRC, code, ["decide"])
    assert r["runs_offline"] and r["runs_hostile"], r


def test_wrong_call_http_and_crashes_fail():
    assert not run.check(SRC, 'kl.say("A", "hello", {})\n', ["create"])["right_call"]
    assert not run.check(SRC, "import requests\nkl.create('x', 'text')\n", ["create"])["clean"]
    assert not run.check(SRC, "import os\nk = os.environ['OPENAI_API_KEY']\n", ["create"])["clean"]
    r = run.check(SRC, "kl.create('x', 'text')\nundefined_thing()\n", ["create"])
    assert not r["runs_offline"] and "NameError" in r["error"]


def test_code_is_taken_from_the_longest_block():
    text = "Here:\n```python\nx = 1\n```\nand\n```python\nkl.create('a', 'b')\ny = 2\n```\n"
    assert run.code_of(text).startswith("kl.create")


def test_the_kit_is_what_init_and_recipe_write():
    agents, recipe = run.kit(SRC, "generate a dungeon room")
    assert "<!-- kinloom:start -->" in agents and "create" in recipe
