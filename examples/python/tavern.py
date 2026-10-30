"""A harbor tavern in your terminal: a keeper with a secret, the weather, a rumor, and drinks that cost gold.

    pip install kinloom
    python tavern.py              # a model from your environment (DEEPSEEK_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY...)
    python tavern.py --offline    # no model at all: the examples and the lines answer, and the game still runs

Type to talk to Rosa. Ask for a drink, ask about the ale, ask what people say. An empty line leaves.
"""
import sys

from kinloom import Kinloom

kl = Kinloom(provider=None) if "--offline" in sys.argv else Kinloom()
gold = 6

kl.character(
    "ROSA",
    soul="the keeper of a harbor tavern, warm but worn out, who secretly waters down the ale to pay her debts",
    offline=["Busy night, love. What will it be?", "Ale's two gold, cider three. Coin first."],
    tools={"pour": {"drink": ["ale", "cider", "water"]}},
)

# A choice the game reads every frame: instant, refreshed in the background. The example is the shape and the offline
# answer (the first option, the middle of a range).
sky = kl.decide("WEATHER", {"hour": 22, "season": "autumn"}, {"sky": ["clear", "rain", "storm"], "wind": [0.0, 1.0]})

# Content of any shape: about a second with a model, the example itself without one.
rumor = kl.create("a rumor overheard in a harbor tavern", {"rumor": "The lighthouse keeper sold the lamp oil.", "true": False})

print("The Gull & Anchor. Outside: %s, wind %.1f. You have %d gold." % (sky["sky"], sky["wind"], gold))
print("Someone at the bar whispers: \"%s\"\n" % rumor["rumor"])

PRICES = {"ale": 2, "cider": 3, "water": 0}
greeting = kl.chat("ROSA", "", {"gold": gold, "prices": PRICES}, speaker="Traveler")   # "" = she speaks first
print("Rosa: %s" % greeting)

while True:
    try:
        text = input("> ").strip()
    except EOFError:
        break
    if not text:
        break
    reply = kl.chat("ROSA", text, {"gold": gold, "prices": PRICES}, speaker="Traveler")
    print("Rosa: %s   [%s]" % (reply, reply.source))
    for tool, args in reply.do:                                           # what her reply agreed to do, validated
        drink = args.get("drink", "water")
        if tool == "pour" and gold >= PRICES[drink]:
            gold -= PRICES[drink]
            print("  * Rosa pours you a %s. You have %d gold left." % (drink, gold))
        elif tool == "pour":
            print("  * Rosa looks at your purse and shakes her head.")

print("You step back out into the night.")
