language: C++17 (raylib, SDL, SFML, custom engines; Unreal through a thin wrapper)
Setup: `kinloom init` copied `{client_path}` (one header, no dependencies; Windows links ws2_32). While playing, run
`kinloom serve`. Or no server (native: the game calls the model itself, the key from the environment): `kinloom::Options o; o.provider_auto = true;
kinloom::Kinloom kl(o);`. `say`, `decide` and `act` are fast; use `chat_async` / `create_async` (std::future) from the game loop.
Unreal: include the header from one module's .cpp; convert values to FString with `UTF8_TO_TCHAR(text.c_str())`.
---
```cpp
#include "kinloom.hpp"
using kinloom::arr;
using kinloom::obj;

kinloom::Kinloom kl;                                    // kinloom::Kinloom kl(url, "player-2") per player
// Characters with a soul: one sentence, a person the player talks to (mood, feelings, memories, secrets, actions)
kl.character("MIRA", "", obj({{"soul", "a gruff blacksmith who secretly sold the king's sword"}, {"offline", "Busy."},
                              {"tools", obj({{"give", obj({{"item", "sword"}})}})}}));
std::string reply = kl.chat("MIRA", player_text, obj({}), "Ana");   // "" = Ana walks up: she speaks first (~1 s: off the loop)
for (auto& a : kl.act("MIRA", obj({}), false)) if (a.tool == "give") inventory.push_back(a.args["item"].str());
kinloom::Json soul = kl.soul("MIRA", "Ana");                          // card, mood, bonds, memories (null offline)

kl.character("VEGA", "over-excited race commentator, max 10 words", obj({
    {"lines", obj({{"overtake", arr({"{who} passes {whom}!"})}, {"*", arr({"What a race!"})}})},   // offline lines
    {"events", obj({{"overtake", arr({"who", "whom", "gap"})}})}}));                              // prepare lines now
kl.character("THEO", "calm race engineer", obj({{"offline", "Copy that."}}));
kl.character("RAX", "brutal rival", obj({{"tools", obj({{"ram", obj({{"force", arr({0.0, 1.0})}})}})}}));

std::string line = kl.say("VEGA", "overtake", obj({{"who", "BLAZE"}, {"whom", "NOVA"}, {"gap", 0.4}}));  // fast
auto reply = kl.chat_async("THEO", player_text, obj({{"gap_to_leader", 1.8}}));   // std::future<std::string>

// every frame: instant, refreshed in the background
kinloom::Json plan = kl.decide("RAX", obj({{"gap", gap}}), obj({{"strategy", arr({"attack", "block"})}, {"aggression", arr({0.0, 1.0})}}));
rax.aggression = (float)plan["aggression"].num();
for (auto& a : kl.act("RAX", obj({{"gap", gap}})))
    if (a.tool == "ram") rax.ram(a.args["force"].num());

auto challenge = kl.create_async("a short race challenge", obj({{"title", "Win clean"}, {"laps", arr({2, 5})}, {"sky", "#ff7a45"}}));
kl.event("BLAZE crashed on lap 3", {"BLAZE", "VEGA"});        // they remember it
kl.state(obj({{"lap", 3}, {"leader", "NOVA"}}));               // facts every call sees

// Minds: utility AI for crowds, run locally every frame (never a model call); rules are the offline mind
kl.mind("raider", "a cunning raider", obj({{"hp", arr({0.0, 1.0})}, {"dist", arr({0.0, 40.0})}, {"armed", true}}),
        obj({{"charge", obj({{"speed", arr({1.0, 3.0})}})}, {"shoot", obj({})}, {"retreat", obj({})}}),
        obj({{"retreat", arr({"hp low"})}, {"shoot", arr({"armed", "dist below 20"})}}));
kinloom::Thought t = kl.think("raider", obj({{"hp", hp}, {"dist", dist}, {"armed", ammo > 0}}), enemy_id);   // t.action, t.args
kl.reward(enemy_id, dealt - taken, died_or_won);                                                          // minds learn

// World (blocking with short limits: call from a thread or at a pause)
kl.event_with("the player stole bread", obj({{"by", "PLAYER"}, {"seen_by", arr({"BAKER"})}, {"tag", "theft"}, {"impact", -0.6}}));
kl.meet("BAKER", "GUARD");
bool alert = kl.knows("GUARD", "theft");
```
