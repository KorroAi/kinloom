"""`kinloom demo`: watch a mind learn, offline, in seconds (no key, no model: learning by mutation).

A skirmish: each unit faces a turret and has 30 seconds (60 steps) to destroy it. The turret fires every step (60 % hit, 20 % behind cover) and reloads for
three steps after five shots. The unit's first rules are what anyone writes first ("shoot when you have ammo,
reload when you don't"): it shoots from too far and never takes cover, so it loses. The game only reports how each
choice went (damage dealt minus damage taken); Kinloom's minds find a better way to fight on their own.
"""
import random
import time

from .brain import Kinloom

SENSES = {"hp": (0.0, 1.0), "dist": (0.0, 40.0), "ammo": (0, 6), "in_cover": True, "enemy_reloading": True, "enemy_hp": (0.0, 1.0)}
ACTIONS = {"shoot": {}, "reload": {}, "advance": {}, "take_cover": {}, "retreat": {}}
NAIVE = {"shoot": ["ammo above 0"], "reload": ["ammo below 1"]}
STEPS = 60


class Skirmish:
    """One unit against one turret. step(action) -> (reward, finished, result)."""

    def __init__(self, rnd):
        self.rnd = rnd
        self.hp, self.enemy_hp = 1.0, 1.0
        self.dist = rnd.uniform(18, 38)
        self.ammo, self.cover, self.shots, self.reloading, self.t = 6, False, 0, 0, 0

    def senses(self):
        return {"hp": self.hp, "dist": self.dist, "ammo": self.ammo, "in_cover": self.cover,
                "enemy_reloading": self.reloading > 0, "enemy_hp": self.enemy_hp}

    def step(self, action):
        dealt = taken = 0.0
        if action == "shoot" and self.ammo > 0:
            self.ammo -= 1
            if self.rnd.random() < max(0.05, min(0.95, 1.0 - self.dist / 30.0)):
                dealt = 0.15
        elif action == "reload":
            self.ammo = 6
        elif action == "advance":
            self.dist, self.cover = max(0.0, self.dist - 3.0), False
        elif action == "retreat":
            self.dist, self.cover = min(40.0, self.dist + 3.0), False
        elif action == "take_cover":
            self.cover = True
        if self.reloading:
            self.reloading -= 1
        elif self.rnd.random() < (0.2 if self.cover else 0.6):
            taken = 0.12
            self.shots += 1
        else:
            self.shots += 1
        if self.shots >= 5 and not self.reloading:
            self.shots, self.reloading = 0, 3
        self.enemy_hp -= dealt
        self.hp -= taken
        self.t += 1
        reward = dealt - taken
        if self.enemy_hp <= 1e-9:
            return reward + 1.0, True, "win"
        if self.hp <= 1e-9:
            return reward - 1.0, True, "loss"
        if self.t >= STEPS:                       # out of time: the round is lost
            return reward - 1.0, True, "timeout"
        return reward, False, None


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def run(minutes=30.0, units=40, seed=7, provider=None, report=print, learn=5.0):
    """Simulates `minutes` of play (0.5 s per step, `units` fights at once). Returns the win rate per stretch."""
    clock = _Clock()
    kl = Kinloom(provider=provider, memory_path=None, clock=clock)
    kl.mind("fighter", "a soldier who wants to win the fight and stay alive", SENSES, ACTIONS, rules=NAIVE, variants=4, learn=learn)
    rnd = random.Random(seed)
    fights = [Skirmish(rnd) for _ in range(units)]
    results, stretch, rows = [], [], []
    steps = int(minutes * 60 / 0.5)
    started = time.perf_counter()
    thinks = 0
    for step in range(steps):
        for i, fight in enumerate(fights):
            who = "unit-%d" % i
            choice = kl.think("fighter", fight.senses(), who=who)
            thinks += 1
            reward, done, result = fight.step(choice["action"])
            kl.reward(who, reward, done=done)
            if done:
                results.append(result)
                stretch.append(result)
                fights[i] = Skirmish(rnd)
        clock.t += 0.5
        kl.wait_idle(30)
        if (step + 1) % int(60 / 0.5) == 0:
            wins = stretch.count("win") / max(1, len(stretch))
            losses = stretch.count("loss") / max(1, len(stretch))
            gen = kl.mind_report("fighter")["generation"]
            rows.append({"minute": (step + 1) * 0.5 / 60, "fights": len(stretch), "win": wins, "loss": losses, "generation": gen})
            report("minute %2d  fights %4d  won %3.0f%%  lost %3.0f%%  generation %3d" % (
                rows[-1]["minute"], len(stretch), 100 * wins, 100 * losses, gen))
            stretch = []
    elapsed = time.perf_counter() - started
    best = max(kl.mind_report("fighter")["variants"], key=lambda v: v["mean"] if v["mean"] is not None else -9)
    stats = kl.stats()
    kl.close()
    return {"rows": rows, "best_rules": best["rules"], "thinks": thinks, "seconds": elapsed, "model_calls": stats["calls"]}
