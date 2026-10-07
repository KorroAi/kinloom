"""The calls in kit/calls.md (shown to coding agents in every brief) must build. The quick sections run here; every
language (C#, Java, Rust, C++, GDScript, Lua) is compiled by `python conformance/calls.py`, which skips a toolchain
that is not installed."""
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "conformance"))
import calls  # noqa: E402


def test_every_engine_language_has_a_section():
    assert set(calls.CHECKS) <= set(calls.sections())


def test_the_python_section_parses(tmp_path):
    ok, out = calls.check_python(calls.sections()["python"], str(tmp_path))
    assert ok, out


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_javascript_section_parses(tmp_path):
    ok, out = calls.check_js(calls.sections()["js"], str(tmp_path))
    assert ok, out


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_checker_sees_a_redeclared_name(tmp_path):
    ok, _ = calls.check_js('const line = await kl.say("A", "e");\nconst line = await kl.speak("A", "x");\n', str(tmp_path))
    assert ok is False
