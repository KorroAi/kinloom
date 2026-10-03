"""Kinloom: deep AI in any game, any engine, any model, in minutes.

    from kinloom import Kinloom
    kl = Kinloom()
    kl.character("VEGA", "an over-excited race commentator")
    kl.say("VEGA", "overtake", {"who": "BLAZE", "whom": "NOVA", "gap": 0.4})
"""
from .brain import Brain, Kinloom
from .shapes import Shape

__all__ = ["Kinloom", "Brain", "Shape"]
__version__ = "1.0.0"


def __getattr__(name):
    """`from kinloom import character` (a call, not a module name): say how it is written, so the fix is one line."""
    if hasattr(Kinloom, name) and not name.startswith("_"):
        raise ImportError("kinloom.%s is a call on a Kinloom object: kl = Kinloom() once, then kl.%s(...)" % (name, name))
    raise AttributeError("module 'kinloom' has no attribute %r" % name)
