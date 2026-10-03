"""Ember Keep with learning shades: the test game's enemies (../games/keep, made without Kinloom) get a Kinloom mind
and learn, offline, against the game's own autopilot keeper. Same world, same keeper, same spawns; only what each
shade chooses to do changes.

    python proof/depth/keep_minds.py [minutes]      # headless measurement (default 40 simulated minutes)

Shades start with the game's own behavior written as rules (go for the fire, chase the keeper when close) and are
rewarded for what shades want: reaching the fire (+1), hurting the keeper (+0.5), being hit (-0.1), banished (-0.5)."""
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "python", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "games", "keep"))
import keep  # noqa: E402
from kinloom import Kinloom  # noqa: E402

W, H = keep.W, keep.H
SENSES = {"dist_fire": (0.0, 800.0), "dist_keeper": (0.0, 800.0), "keeper_near_fire": True, "keeper_can_swing": True,
          "kind": ["wisp", "crawler", "brute"], "hp": (0.0, 5.0)}
ACTIONS = {"rush": {}, "hunt": {}, "orbit": {}, "sneak": {}}
GAME_RULES = {"rush": {"score": 1.0}, "hunt": {"score": 1.2, "when": ["dist_keeper below 160"]}}   # what keep.py does


class LearningKeep(keep.Game):
    """keep.Game whose shades choose a plan with a mind. step() is the game's own, with one hook: the shade's target."""

    def __init__(self, kl, seed=None):
        self.kl, self.names, self.plans, self.count = kl, {}, {}, 0
        super().__init__(seed)

    def who(self, s):
        if id(s) not in self.names:
            self.count += 1
            self.names[id(s)] = "shade-%d" % self.count
        return self.names[id(s)]

    def senses(self, s):
        return {"dist_fire": math.hypot(s.x - W / 2, s.y - H / 2), "dist_keeper": math.hypot(s.x - self.px, s.y - self.py),
                "keeper_near_fire": math.hypot(self.px - W / 2, self.py - H / 2) < 200, "keeper_can_swing": self.swing_cd == 0,
                "kind": s.kind, "hp": float(s.hp)}

    def target(self, s):
        fx, fy = W / 2, H / 2
        plan = self.plans.get(id(s), "rush")
        if plan == "hunt":
            return self.px, self.py
        a = math.atan2(s.y - fy, s.x - fx)
        if plan == "orbit":                                   # wait at a distance, circling
            return fx + math.cos(a + 0.6) * 230, fy + math.sin(a + 0.6) * 230
        if plan == "sneak":                                   # go round to the side away from the keeper, then in
            away = math.atan2(self.py - fy, self.px - fx) + math.pi
            diff = (away - a + math.pi) % (2 * math.pi) - math.pi
            if abs(diff) > 0.5:
                b = a + math.copysign(0.5, diff)
                return fx + math.cos(b) * 200, fy + math.sin(b) * 200
        return fx, fy                                         # rush (and sneak once on the far side)

    def reward(self, s, value, done=False):
        self.kl.reward(self.who(s), value, done=done)

    def step(self, dt, move=(0.0, 0.0), swing=False, feed=False):
        # ---- keep.Game.step, unchanged except the lines marked KINLOOM ----
        self.time += dt
        if self.over:
            self.over_time += dt
            return
        mx, my = move
        n = math.hypot(mx, my) or 1.0
        self.vx += (mx / n * 1400 - self.vx * 7) * dt
        self.vy += (my / n * 1400 - self.vy * 7) * dt
        self.px = min(W - 12, max(12, self.px + self.vx * dt))
        self.py = min(H - 12, max(12, self.py + self.vy * dt))
        self.swing = max(0.0, self.swing - dt)
        self.swing_cd = max(0.0, self.swing_cd - dt)
        self.invulnerable = max(0.0, self.invulnerable - dt)
        if swing and self.swing_cd == 0:
            self.swing, self.swing_cd = 0.25, 0.45
            for s in self.shades:
                if math.hypot(s.x - self.px, s.y - self.py) < 90:
                    s.hp -= 1
                    s.hurt = 0.2
                    self.reward(s, -0.1)                                                   # KINLOOM
                    dx, dy = s.x - self.px, s.y - self.py
                    d = math.hypot(dx, dy) or 1
                    s.x += dx / d * 40
                    s.y += dy / d * 40
        for w in list(self.wood):
            if self.carrying < 3 and math.hypot(w.x - self.px, w.y - self.py) < 26:
                self.wood.remove(w)
                self.carrying += 1
        near_fire = math.hypot(self.px - W / 2, self.py - H / 2) < 70
        if self.carrying and (feed or near_fire):
            if near_fire:
                self.fire = min(100.0, self.fire + 18 * self.carrying)
                self.stats["wood"] += self.carrying
                self.emit("fed", wood=self.carrying, fire=round(self.fire))
                self.carrying = 0
        while len(self.wood) < 5:
            self.drop_wood()
        self.fire -= dt * (1.1 + 0.15 * self.night)
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_shade()
            self.spawn_timer = max(0.35, 2.2 - 0.25 * self.night)
        decide = int(self.time * 4) != int((self.time - dt) * 4)                               # KINLOOM: 4 decisions a second
        for s in list(self.shades):
            s.wobble += dt * 3
            s.hurt = max(0.0, s.hurt - dt)
            if decide or id(s) not in self.plans:                                               # KINLOOM
                self.plans[id(s)] = self.kl.think("shade", self.senses(s), who=self.who(s))["action"]
            tx, ty = self.target(s)                                                            # KINLOOM (was: fire, or keeper when close)
            dx, dy = tx - s.x, ty - s.y
            d = math.hypot(dx, dy) or 1
            s.x += (dx / d * s.speed + math.cos(s.wobble) * 25) * dt
            s.y += (dy / d * s.speed + math.sin(s.wobble) * 25) * dt
            if s.hp <= 0:
                self.shades.remove(s)
                self.stats["banished"] += 1
                self.emit("banished", kind=s.kind, total=self.stats["banished"])
                self.reward(s, -0.5, True)                                                     # KINLOOM
                continue
            if math.hypot(s.x - W / 2, s.y - H / 2) < 40:
                self.fire -= {"wisp": 6, "crawler": 10, "brute": 22}[s.kind]
                self.shades.remove(s)
                self.emit("fire_hit", kind=s.kind, fire=round(max(self.fire, 0)))
                self.reward(s, 1.0, True)                                                      # KINLOOM
                continue
            if math.hypot(s.x - self.px, s.y - self.py) < 22 and self.invulnerable == 0:
                self.hp -= 1
                self.invulnerable = 1.0
                self.stats["hits"] += 1
                self.emit("hurt", hp=self.hp, kind=s.kind)
                self.reward(s, 0.5)                                                            # KINLOOM
        self.clock += dt
        if self.clock >= self.night_length:
            self.night += 1
            self.clock = 0.0
            self.best_night = max(self.best_night, self.night - 1)
            self.emit("dawn", survived=self.night - 1)
            self.emit("night", night=self.night)
        if self.fire <= 0 or self.hp <= 0:
            self.over = True
            self.best_night = max(self.best_night, self.night - 1)
            for s in self.shades:                                                              # KINLOOM: the round is over
                self.reward(s, 0.0, True)
            self.emit("game_over", night=self.night, reason="fire" if self.fire <= 0 else "keeper",
                      banished=self.stats["banished"])


def measure(minutes, learn, seed=3):
    clock = {"t": 0.0}
    kl = Kinloom(provider=None, memory_path=None, clock=lambda: clock["t"])
    kl.mind("shade", "a shade of the night that wants the fire out", SENSES, ACTIONS, GAME_RULES, variants=4, learn=learn)
    g = LearningKeep(kl, seed=seed)
    counts = {"fire_hit": 0, "banished": 0}
    g.on(lambda kind, data: counts.__setitem__(kind, counts[kind] + 1) if kind in counts else None)
    dt, t, minute, rows, nights = 1 / 30, 0.0, 0, [], []
    while t < minutes * 60:
        move, swing = keep.autopilot(g)
        g.step(dt, move, swing)
        t += dt
        clock["t"] = t
        if g.over and g.over_time > 1:
            nights.append(g.night)
            g.reset()
        if int(t // 60) > minute:
            minute = int(t // 60)
            rows.append((counts["fire_hit"], counts["banished"]))
            counts.update(fire_hit=0, banished=0)
    report = kl.mind_report("shade")
    best = max(report["variants"], key=lambda v: v["mean"] if v["mean"] is not None else -9)
    return rows, nights, report["generation"], best["rules"]


def main():
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 40
    seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    for label, learn in (("game's own behavior", 0), ("learning shades", 10)):
        firsts, lasts, games = [], [], []
        for seed in range(seeds):
            rows, nights, gens, rules = measure(minutes, learn, seed)
            q = max(1, len(rows) // 4)
            share = lambda part: sum(f for f, _ in part) / max(1, sum(f + b for f, b in part))
            firsts.append(share(rows[:q]))
            lasts.append(share(rows[-q:]))
            games.append(statistics.mean(nights) if nights else float("nan"))
        print("%-20s shades that reach the fire (of those that end): first quarter %.0f%%, last quarter %.0f%%; "
              "the keeper's mean night reached: %.2f (%d seeds x %d min)" % (
                  label, 100 * statistics.mean(firsts), 100 * statistics.mean(lasts), statistics.mean(games), seeds, minutes))
        if learn:
            print("    rules of the best variant (last seed): " + "; ".join(
                "%s %.2f when %s" % (a, sp["score"], " and ".join(sp["when"]) or "always") for a, sp in rules.items() if sp["score"] > 0))


if __name__ == "__main__":
    main()
