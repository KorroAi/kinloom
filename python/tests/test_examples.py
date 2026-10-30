"""The examples in examples/ stay runnable: played offline, the way someone with no key first meets them."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "python", "src")


def test_the_tavern_plays_offline():
    env = dict(os.environ, PYTHONPATH=SRC, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, os.path.join(ROOT, "examples", "python", "tavern.py"), "--offline"],
                       input="A cider please\nIs the ale watered down?\n\n", capture_output=True, text=True,
                       encoding="utf-8", env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    assert "The Gull & Anchor" in p.stdout and "You have 6 gold" in p.stdout
    assert p.stdout.count("Rosa: ") == 3 and p.stdout.count("[offline]") == 2
    assert "You step back out into the night." in p.stdout


def test_the_web_example_loads_the_clients_it_names():
    page = open(os.path.join(ROOT, "examples", "web", "index.html"), encoding="utf-8").read()
    for client in ("kinloom.js", "kinloom-talk.js"):
        rel = "../../python/src/kinloom/clients/web/" + client
        assert rel in page
        assert os.path.exists(os.path.normpath(os.path.join(ROOT, "examples", "web", rel)))
