language: JavaScript / TypeScript (browser, Node, Deno, Bun)
Setup: `kinloom init` copied `{client_path}` (typed): import it relative to your file, e.g. from `src/main.ts`:
`import { Kinloom } from "{import_path}"`. While playing, run `kinloom serve` in a terminal, or no server:
`new Kinloom({ provider: "auto" })` (Node, Deno, Bun; in a browser the key would reach players: use a relay).
<!-- brief ends -->
JavaScript projects also get `kinloom-talk.js`, a ready dialogue box (`talkBox(kl, "MIRA").open()`).
`kinloom serve` allows local pages; for a deployed game see `kinloom serve --help`. In a browser, native mode is for
the player's own key only. With a relay token and no `session`, a browser keeps one session id per install
(localStorage), never the shared "default".
---
```ts
import { Kinloom } from "{import_path}";
const kl = new Kinloom();  // { session: "player-2" } for another player's memory

// Characters with a soul: one sentence, a person the player talks to (mood, feelings, memories, secrets, actions)
kl.character("MIRA", "", { soul: "a widowed blacksmith, gruff and proud, who secretly sold the king's sword",
                           offline: "Busy. Come back later.", tools: { give: { item: "sword" } } });
bubble.textContent = "";
await kl.chat("MIRA", playerText, { gold }, "Ana", (piece) => (bubble.textContent += piece));  // "" = she speaks first
for (const a of kl.act("MIRA", {}, false)) if (a.tool === "give") inventory.push(a.args.item); // decided while talking
const soul = await kl.soul("MIRA", "Ana");  // {card, mood: {word, level}, bonds, memories} or null

kl.character("VEGA", "over-excited race commentator, max 10 words", {
  lines: { overtake: ["{who} passes {whom}!"], "*": ["What a race!"] },  // offline lines
  events: { overtake: ["who", "whom", "gap"] },  // prepare these lines now
});
kl.character("THEO", "calm race engineer", { offline: "Copy that." });
kl.character("RAX", "brutal rival", { tools: { ram: { force: [0.0, 1.0] } } });

label.textContent = await kl.say("VEGA", "overtake", { who: "BLAZE", whom: "NOVA", gap: 0.4 });  // instant
radio.textContent = await kl.chat("THEO", playerText, { gapToLeader: 1.8, lap: 3 });  // ~1 s, don't block the loop

function update(dt: number) {  // per frame
  const plan = kl.decide("RAX", { gap, lap }, { strategy: ["attack", "block"], aggression: [0.0, 1.0] }); // instant
  rax.aggression = plan.aggression;
  for (const a of kl.act("RAX", { gap })) if (a.tool === "ram") rax.ram(a.args.force as number);  // instant
}

const challenge = await kl.create("a short race challenge", { title: "Win clean", laps: [2, 5], sky: "#ff7a45" });
const names = await kl.create("rival driver names", "BLAZE", { count: 8 });  // list of 8
kl.event("BLAZE crashed on lap 3", ["BLAZE", "VEGA"]);  // they remember it
kl.state({ lap: 3, leader: "NOVA" });  // facts every call sees

// Minds: utility AI for crowds, run locally every frame (never a model call); rules are the offline mind
kl.mind("raider", "a cunning raider", {
  senses: { hp: [0, 1], dist: [0, 40], armed: true },
  actions: { charge: { speed: [1.0, 3.5] }, shoot: {}, retreat: {} },  // JS: [1, 3] would mean whole numbers
  rules: { retreat: ["hp low"], shoot: ["armed", "dist below 20"], charge: { score: 0.5, args: { speed: "dist high" } } },
});
for (const e of enemies) {  // every frame
  const a = kl.think("raider", { hp: e.hp, dist: e.dist, armed: e.ammo > 0 }, e.id);  // {action, args, variant}
  e.act(a.action, a.args);
}
kl.reward(enemy.id, dealt - taken, enemyDiedOrWon);  // minds learn from how it went

// World: who saw what, rumors, opinions
kl.event("the player stole bread", [], { by: "PLAYER", seenBy: ["BAKER"], tag: "theft", impact: -0.6 });
await kl.meet("BAKER", "GUARD");
if (await kl.knows("GUARD", "theft")) guard.alert();
const standing = await kl.reputation("PLAYER", "village");  // -1..1
```
