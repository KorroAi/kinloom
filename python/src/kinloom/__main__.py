"""`python -m kinloom ...`: the same as the `kinloom` command (when pip's scripts folder is not on PATH).

Inside a Python game, `python -m` finds the game's own copy first (kinloom/ next to the game, written by `kinloom
init`): the installed Kinloom is used instead when there is one, so `python -m kinloom init` updates that copy."""
import os
import sys

_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.normcase(_here) == os.path.normcase(os.getcwd()) and os.path.exists(os.path.join(_here, "kinloom", "brain.py")):
    _kept = sys.path[:]
    sys.path[:] = [p for p in sys.path if os.path.normcase(os.path.abspath(p or ".")) != os.path.normcase(_here)]
    _local = {m: sys.modules.pop(m) for m in list(sys.modules) if m == "kinloom" or m.startswith("kinloom.")}
    try:
        from kinloom.cli import main          # the installed one
    except ImportError:                        # only the game's copy exists: use it
        sys.path[:] = _kept
        sys.modules.update(_local)
        from kinloom.cli import main
else:
    from .cli import main

raise SystemExit(main())
