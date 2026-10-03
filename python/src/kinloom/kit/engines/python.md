language: Python
Setup: `kinloom init` copied the package into `kinloom/` next to the game (standard library only: it ships with the
game, nothing to install, works with python, uv run or a frozen build). Use it directly, no server needed:
`from kinloom import Kinloom`. The model is found from the environment (see the rules); no key means offline answers.
Shipped to players with your key kept on your server (`kinloom deploy`): `Kinloom(url=..., token=...)` or
`KINLOOM_URL` / `KINLOOM_TOKEN`; the rest of the code does not change.
---
```python
from kinloom import Kinloom
kl = Kinloom()                                   # one per game; kl.session("player-2") for another player's memory

# Characters with a soul: one sentence, a person the player talks to (mood, feelings, memories, secrets, actions)
def give(item: str = "sword"):
    """hand an item to the player"""
kl.character("MIRA", soul="a widowed blacksmith, gruff and proud, who secretly sold the king's sword",
             offline="Busy. Come back later.", tools=[give])
opening = kl.chat("MIRA", "", speaker="Ana")                                # "" = Ana walks up: she speaks first
reply = kl.chat("MIRA", "Can you forge me a blade?", {"gold": 3}, speaker="Ana", stream=print)   # streamed pieces
kl.act("MIRA", think=False)                     # what she decided while talking (give() already ran, validated)
soul = kl.soul("MIRA", speaker="Ana")           # {card, mood: {word, level}, bonds: {"Ana": {talks, feeling}}, memories}

# In a game loop, never block on chat. Pygame / pygame-ce: a ready dialogue box (needs pygame, not Kinloom):
#   from kinloom.talk import PygameTalkBox
#   box = PygameTalkBox(kl, "MIRA", speaker="Ana", facts=lambda: {"gold": gold},
#                       on_action=lambda tool, args: give_item(args["item"]))
#   T pressed: box.open()   every event: if box.handle(e): continue   every frame: box.update(); box.draw(screen)
from kinloom.talk import Talk
talk = Talk(kl, "MIRA", speaker="Ana")          # any other engine: talk.send(text); every frame talk.update(), then
talk.send("Good evening.")                      # draw talk.lines [(who, text)] and talk.current (the reply being written)

kl.character("VEGA", "over-excited race commentator, max 10 words",
             lines={"overtake": ["{who} passes {whom}!"], "*": ["What a race!"]},   # offline lines
             events={"overtake": ["who", "whom", "gap"]})                            # prepare these lines now
label_text = kl.say("VEGA", "overtake", {"who": "BLAZE", "whom": "NOVA", "gap": 0.4})    # instant string

kl.character("THEO", "calm race engineer", offline="Copy that.")
reply = kl.chat("THEO", "how far is the leader?", {"gap_to_leader": 1.8, "lap": 3})       # ~1 s: run it off the frame loop
future = kl.chat_async("THEO", "any rain coming?")                                          # or: future.result() later

plan = kl.decide("BLAZE", {"gap": 1.2, "lap": 3},                                        # instant dict, refreshed in background
                 {"strategy": ["attack", "block", "save tyres"], "aggression": [0.0, 1.0]})

def boost(seconds: float = 1.0):
    """Short burst of speed."""
kl.character("NOVA", "cunning rival driver", tools=[boost])          # functions: called for you with validated args
kl.character("RAX", "brutal rival", tools={"ram": {"force": [0.0, 1.0]}})   # or examples: you apply them
for tool, args in kl.act("RAX", {"gap": 0.8, "player_speed": 212}):         # instant: validated calls since last time
    print(tool, args)

challenge = kl.create("a short race challenge", {"title": "Win clean", "laps": [2, 5], "sky": "#ff7a45"})   # waits ~1-2 s
names = kl.create("rival driver names", "BLAZE", count=8)                     # a list of 8
quick = kl.create("a pit radio tip", "Push now!", instant=True)              # instant, from a pool refilled in the background

kl.event("BLAZE crashed on lap 3", about=["BLAZE", "VEGA"])   # they remember it
kl.remember("THEO", "the player hates rain")
kl.state({"lap": 3, "leader": "NOVA", "weather": "dry"})       # facts every call sees

# Minds: utility AI for crowds, run locally every frame (never a model call); rules are the offline mind
kl.mind("raider", "a cunning raider", senses={"hp": [0.0, 1.0], "dist": [0.0, 40.0], "armed": True},
        actions={"charge": {"speed": [1.0, 3.0]}, "shoot": {}, "retreat": {}},
        rules={"retreat": ["hp low"], "shoot": ["armed", "dist below 20"], "charge": {"score": 0.5, "args": {"speed": "dist high"}}})
a = kl.think("raider", {"hp": 0.8, "dist": 12.0, "armed": True}, who="raider-17")   # {"action", "args", "variant"}
kl.reward("raider-17", 0.3)                    # how it went; done=True when the unit's fight ends: minds learn

# World: who saw what, rumors, opinions
kl.character("BAKER", "a warm baker", group="village")
kl.event("the player stole bread", by="PLAYER", seen_by=["BAKER"], tag="theft", impact=-0.6)
kl.meet("BAKER", "GUARD")                      # they share what they know
if kl.knows("GUARD", "theft") and kl.reputation("PLAYER", "village") < 0:
    pass                                       # prices up, doors closed, guards alert...
```
