language: Java (Minecraft mods, libGDX, jMonkeyEngine, LWJGL, Android, any JVM 8+)
Setup: `kinloom init` copied `{client_path}` (package `kinloom`, no dependencies). While playing, run `kinloom serve`.
Or no server (native: the game calls the model itself, the key from the environment): `Kinloom.Options o = new Kinloom.Options(); o.providerAuto = true;
Kinloom kl = new Kinloom(o);`. Use `chatAsync` / `createAsync` from the game thread; `say`, `decide` and `act` are fast.
---
```java
import static kinloom.Kinloom.list;
import static kinloom.Kinloom.map;
import kinloom.Kinloom;

Kinloom kl = new Kinloom();                            // new Kinloom(url, "player-2", "") per player
// Characters with a soul: one sentence, a person the player talks to (mood, feelings, memories, secrets, actions)
kl.character("MIRA", "", map("soul", "a gruff blacksmith who secretly sold the king's sword", "offline", "Busy.",
    "tools", map("give", map("item", "sword"))));
String reply = kl.chat("MIRA", playerText, map(), "Ana");       // "" = Ana walks up: she speaks first (~1 s: off the game thread)
for (Kinloom.Action a : kl.act("MIRA", map(), false)) if (a.tool.equals("give")) inventory.add((String) a.args.get("item"));
Map<String, Object> soul = kl.soul("MIRA", "Ana");              // card, mood, bonds, memories (null offline)

kl.character("VEGA", "over-excited race commentator, max 10 words", map(
    "lines", map("overtake", list("{who} passes {whom}!"), "*", list("What a race!")),   // offline lines
    "events", map("overtake", list("who", "whom", "gap"))));                              // prepare these lines now
kl.character("THEO", "calm race engineer", map("offline", "Copy that."));
kl.character("RAX", "brutal rival", map("tools", map("ram", map("force", list(0.0, 1.0)))));

String line = kl.say("VEGA", "overtake", map("who", "BLAZE", "whom", "NOVA", "gap", 0.4));   // fast
kl.chatAsync("THEO", playerText, map("gap_to_leader", 1.8)).thenAccept(reply -> radio = reply);  // ~1 s

// every tick: instant, refreshed in the background
Map<String, Object> plan = kl.decide("RAX", map("gap", gap), map("strategy", list("attack", "block"), "aggression", list(0.0, 1.0)));
rax.aggression = (float) Kinloom.num(plan.get("aggression"));
for (Kinloom.Action a : kl.act("RAX", map("gap", gap)))
    if (a.tool.equals("ram")) rax.ram(Kinloom.num(a.args.get("force")));

kl.createAsync("a short race challenge", map("title", "Win clean", "laps", list(2, 5), "sky", "#ff7a45"), map(), 0)
  .thenAccept(challenge -> start((Map<String, Object>) challenge));
kl.event("BLAZE crashed on lap 3", "BLAZE", "VEGA");          // they remember it
kl.state(map("lap", 3, "leader", "NOVA"));                     // facts every call sees

// Minds: utility AI for crowds, run locally every tick (never a model call); rules are the offline mind
kl.mind("raider", "a cunning raider", Kinloom.map("hp", Kinloom.list(0.0, 1.0), "dist", Kinloom.list(0.0, 40.0), "armed", true),
        Kinloom.map("charge", Kinloom.map("speed", Kinloom.list(1.0, 3.0)), "shoot", Kinloom.map(), "retreat", Kinloom.map()),
        Kinloom.map("retreat", Kinloom.list("hp low"), "shoot", Kinloom.list("armed", "dist below 20")), 3, 30);
Kinloom.Thought t = kl.think("raider", Kinloom.map("hp", hp, "dist", dist, "armed", ammo > 0), enemyId);   // t.action, t.args
kl.reward(enemyId, dealt - taken, diedOrWon);                                                             // minds learn

// World (blocking with short limits: call off the game thread)
kl.event("the player stole bread", Kinloom.map("by", "PLAYER", "seen_by", Kinloom.list("BAKER"), "tag", "theft", "impact", -0.6));
kl.meet("BAKER", "GUARD");
boolean alert = kl.knows("GUARD", "theft");
```
