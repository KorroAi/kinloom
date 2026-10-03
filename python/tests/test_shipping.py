"""Shipping: a Python game carries Kinloom inside it (nothing to install for players or for uv/venv setups), and the
status says plainly when there is no AI yet or a key cannot be used."""
import os
import subprocess
import sys

from kinloom import init
from kinloom.cli import _describe
from test_brain import make


def test_a_python_game_gets_the_package_next_to_it(tmp_path):
    (tmp_path / "game.py").write_text("import kinloom\nprint(kinloom.__file__)\n")
    written, path = init.install_client(str(tmp_path), "python")
    assert path == "kinloom" and (tmp_path / "kinloom" / "brain.py").exists() and (tmp_path / "kinloom" / "talk.py").exists()
    assert not (tmp_path / "kinloom" / "clients").exists()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    out = subprocess.run([sys.executable, "-E", "-s", "game.py"], cwd=tmp_path, capture_output=True, text=True, env=env)
    assert out.returncode == 0 and os.path.dirname(out.stdout.strip()) == str(tmp_path / "kinloom")
    init.install_client(str(tmp_path), "python")            # again: replaced, still one copy
    assert (tmp_path / "kinloom" / "brain.py").exists()


def test_a_game_package_called_kinloom_is_left_alone(tmp_path):
    (tmp_path / "kinloom").mkdir()
    (tmp_path / "kinloom" / "__init__.py").write_text("MINE = 1\n")
    assert init.install_client(str(tmp_path), "python") == ([], None)
    assert (tmp_path / "kinloom" / "__init__.py").read_text() == "MINE = 1\n"


def test_offline_status_says_there_is_no_ai_yet(monkeypatch):
    for var in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY", "KINLOOM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    kl = make(None)
    said = _describe(kl.brain)          # the two ways the developer chose between (2026-10-01): a key, or their agent's plan
    assert "no AI yet" in said and "API key" in said and "kinloom use claude-code" in said
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert "GEMINI_API_KEY is set but no model is named" in _describe(kl.brain)


def test_importing_a_call_explains_how_to_write_it():
    import pytest
    with pytest.raises(ImportError, match=r"kl = Kinloom\(\) once, then kl.character"):
        from kinloom import character  # noqa: F401
    import kinloom
    with pytest.raises(AttributeError):
        kinloom.nothing_like_this
