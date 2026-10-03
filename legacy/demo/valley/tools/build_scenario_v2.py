"""One-off migration of scenarios/asagiri.json to gameplay v2: shift the village east (room for the forest),
add forest places, the bandit camp, monsters, loose items, authored quests and the Jade Fox night theft."""
import json
import re
from pathlib import Path

OX = 36
path = Path(__file__).resolve().parents[3] / "scenarios" / "asagiri.json"
text = path.read_text(encoding="utf-8")
data = json.loads(re.sub(r"^\s*//.*$", "", text, flags=re.M))

for p in data["places"]:
    p["x"] += OX
for a in data["agents"]:
    a["x"] += OX
data["player"]["x"] += OX
data["player"]["gold"] = 25
data["arrests"] = True
data["sleep"] = True
data["days"] = 3
data["world"] = data["world"].replace("and a dark forest to the west where bandits hide.",
    "and a dark forest to the west: an old trail, a mushroom glade, a spirit grove where spiders nest, and the camp of Crow's bandit gang.")

forest = next(p for p in data["places"] if p["id"] == "forest")
forest["name"] = "Forest Edge"
data["places"] += [
    {"id": "trail", "name": "Old Forest Trail", "x": 24, "y": 22, "radius": 4, "tags": ["wild"]},
    {"id": "bandit_camp", "name": "Bandit Camp", "x": 9, "y": 10, "radius": 5, "tags": ["wild", "hostile"]},
    {"id": "glade", "name": "Mushroom Glade", "x": 14, "y": 34, "radius": 4, "tags": ["wild"]},
    {"id": "grove", "name": "Spirit Grove", "x": 32, "y": 7, "radius": 4, "tags": ["wild"]},
]

agents = {a["id"]: a for a in data["agents"]}
# Crow's gang lives at the camp from the start (fightable); two raiders stay in reserve for the director's raids.
for bid, hp in (("crow", 24), ("viper", 10), ("boar", 12)):
    b = agents[bid]
    b.pop("reserve", None)
    b["home"] = "bandit_camp"
    b["health"] = hp
    b["schedule"] = [{"hour": 0, "place": "bandit_camp"}]
agents["crow"].update(x=9, y=10, gold=40, role="bandit leader")
agents["viper"].update(x=7, y=12)
agents["boar"].update(x=11, y=12)
data["agents"] += [
    {"id": "jackal", "name": "Jackal", "look": "NinjaGray", "x": 41, "y": 21, "reserve": True, "tags": ["hostile"], "bravery": 0.8, "sociability": 0.2, "forgiveness": 0.1, "gold": 8, "health": 8, "role": "bandit"},
    {"id": "rat", "name": "Rat", "look": "NinjaRed", "x": 41, "y": 23, "reserve": True, "tags": ["hostile"], "bravery": 0.7, "sociability": 0.2, "forgiveness": 0.1, "gold": 6, "health": 7, "role": "bandit"},
]
monsters = [
    ("slime1", "Blue Slime", "Slime", 12, 33, "glade", 5), ("slime2", "Blue Slime", "Slime", 17, 36, "glade", 5),
    ("slime3", "Blue Slime", "Slime", 20, 24, "trail", 5), ("mushroom1", "Angry Mushroom", "Mushroom", 11, 37, "glade", 4),
    ("spider1", "Red Spider", "SpiderRed", 30, 6, "grove", 6), ("spider2", "Red Spider", "SpiderRed", 34, 9, "grove", 6),
    ("beast1", "Forest Beast", "Beast", 26, 16, "trail", 12), ("skull1", "Wandering Skull", "Skull", 22, 28, "trail", 7),
]
for mid, name, look, x, y, home, hp in monsters:
    data["agents"].append({"id": mid, "name": name, "look": look, "x": x, "y": y, "home": home, "tags": ["hostile", "monster"],
                           "bravery": 1.0, "sociability": 0.0, "forgiveness": 0.0, "gold": 3, "health": hp, "role": "beast",
                           "schedule": [{"hour": 0, "place": home}]})

riku = agents["riku"]
riku["secrets"] = ["is a scout for the bandits and owes Crow a large debt", "has a copy of the shrine key made by Goro",
                   "stole a sack of flour from Mira's storeroom last week", "has promised Crow the Jade Fox Relic tonight"]
riku["fixedPlans"] = [{"day": 2, "until": "03:30", "intention": "Pay the debt to Crow with the relic",
                       "steps": [{"time": "00:30", "verb": "goto", "target": "shrine", "note": "sneak in with the copied key"},
                                 {"time": "01:00", "verb": "steal", "target": "jun", "item": "relic"},
                                 {"time": "01:20", "verb": "goto", "target": "bandit_camp"},
                                 {"time": "02:30", "verb": "give", "target": "crow", "item": "relic"},
                                 {"time": "03:00", "verb": "goto", "target": "riverside"}]}]
agents["yuki"]["secrets"].append("knows that Riku owes Crow's gang money")
agents["hana"]["secrets"] = ["saw Riku sneaking near the shrine at night, twice", "saw Riku carrying a flour sack by the river last week"]
agents["goro"]["secrets"] = ["made a copy of the shrine key for Riku without asking why"]

data["items"] += [
    {"id": "ore", "name": "Iron Ore", "place": "grove", "value": 5},
    {"id": "moon_herb", "name": "Moon Herb", "place": "glade", "value": 5},
]
data["quests"] = [
    {"giver": "mira", "kind": "accuse", "target": "riku", "reward": 10, "text": "Someone stole a sack of flour from my storeroom last week. Find out who — ask around."},
    {"giver": "goro", "kind": "retrieve_item", "target": "goro", "item": "ore", "reward": 5, "rewardItem": "katana",
     "text": "Bring me iron ore from the Spirit Grove in the forest. Spiders nest there. Do it, and the masterwork katana is yours."},
    {"giver": "sen", "kind": "retrieve_item", "target": "sen", "item": "moon_herb", "reward": 5, "rewardItem": "herbs",
     "text": "Bring me a Moon Herb from the Mushroom Glade, west of the river. Mind the slimes."},
    {"giver": "emi", "kind": "retrieve_item", "target": "emi", "item": "ledger", "reward": 12,
     "text": "Haru cheats on the rice tax, I know it. Get me Haru's ledger — however you must."},
    {"giver": "kaito", "kind": "slay", "target": "boar", "reward": 10,
     "text": "Boar, one of Crow's bandits, beat me in the forest last month. Help me bring Boar down."},
    {"giver": "jun", "kind": "retrieve_item", "target": "jun", "item": "relic", "reward": 30, "day": 2, "hour": 6,
     "text": "The Jade Fox Relic is gone! Someone opened the shrine in the night. Bring it back before the festival."},
    {"giver": "ren", "kind": "accuse", "target": "riku", "reward": 15, "day": 2, "hour": 7,
     "text": "The relic was taken in the night. Find out who did it and tell me — and be sure of it."},
]

out = json.dumps(data, indent=2, ensure_ascii=False)
path.write_text("// Asagiri Valley — the Kinloom Brain showcase (gameplay v2). Coordinates are map tiles (16 px); the forest is west of the river.\n" + out + "\n", encoding="utf-8")
print(f"{path}: {len(data['agents'])} agents, {len(data['places'])} places, {len(data['items'])} items, {len(data['quests'])} quests")
