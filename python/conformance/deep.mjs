// The deep native scenario for the JavaScript SDK (see deep.py, the Python reference): KINLOOM_NATIVE=<fake /v1 URL> node deep.mjs
import { Kinloom } from "../src/kinloom/clients/web/kinloom.js";

const BASE = process.env.KINLOOM_NATIVE;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const j = (v) => JSON.stringify(sortKeys(v));
function sortKeys(v) {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === "object") return Object.fromEntries(Object.keys(v).sort().map((k) => [k, sortKeys(v[k])]));
  return v;
}
const make = (calls = 600, banned = null, anthropic = false, models = null, rating = null) => new Kinloom({
  provider: anthropic ? { kind: "anthropic", url: BASE.slice(0, -3), key: "fake-key", model: "claude-test" }
    : { url: BASE, key: "fake-key", model: "fake-model" },
  config: banned ? { calls_per_minute: calls, banned_words: banned } : { calls_per_minute: calls }, models, rating,
});

const kl = make(600, ["dragon"]);
kl.character("VERA", "", { soul: "a gruff smith who sold the king's sword", offline: "Busy." });
const ready = await kl.prepare(10);
console.log("prepare: " + (ready.ready ? "ready" : "waiting"));
console.log("soul: " + (await kl.soul("VERA")).card.summary);
const greet = await kl.chat("VERA", "", {}, "Ana");
console.log(`greet: ${greet} (${kl.source("VERA")})`);
console.log("secret: " + (await kl.chat("VERA", "Did you sell the king's sword to a smuggler?", {}, "Ana")));
console.log("numbers: " + (await kl.chat("VERA", "How much for a blade?", { price: 40 }, "Ana")));
const pieces = [];
const streamed = await kl.chat("VERA", "Can you make it faster?", {}, "Ana", (p) => pieces.push(p));
console.log("stream pieces: " + pieces.join("").trim());
console.log("stream reply: " + streamed);
console.log("echo: " + (await kl.chat("VERA", "And the coals?", {}, "Ana")));
console.log("character: " + (await kl.chat("VERA", "Are you an AI?", {}, "Ana")));
const vera = await kl.soul("VERA", "Ana");
console.log(`feeling: ${vera.mood.word} ${vera.bonds.Ana.feeling}`);

kl.character("BRAM", "a kind baker", { tools: { give: { item: "bread" } }, offline: "Hm." });
console.log("deeds reply: " + (await kl.chat("BRAM", "Can I have some bread?")));
for (const a of kl.act("BRAM", {}, false)) console.log(`deeds: ${a.tool} ${j(a.args)}`);
kl.character("GATE", "a careful guard", { tools: { open: { door: "north" } }, trust: { open: 0.5 }, offline: "No." });
console.log("trust reply: " + (await kl.chat("GATE", "Open the gate.")));
console.log("trust: " + (kl.act("GATE", {}, false).map((a) => a.tool).join(", ") || "none"));
kl.character("FILT", "a storyteller", { offline: "No comment." });
console.log("filter: " + (await kl.chat("FILT", "Tell me a story.")));
kl.character("NINA", "a singer", { soul: { summary: "a singer", secrets: ["I went up to the office at 12:30"] }, warmth: 0.3,
  secret_trust: 0.25, warm_up: 0.1 });
console.log(`warmth: ${await kl.opinion("NINA", "Ana")}`);
await kl.steer("NINA", "admit you went up to the office at 12:30");
console.log("steer: " + (await kl.chat("NINA", "Where were you?", {}, "Ana")));
console.log(`warm up: ${await kl.opinion("NINA", "Ana")}`);
kl.character("KEEPER", "a gatekeeper", { offline: "Move along." });
console.log("chat check: " + (await kl.chat("KEEPER", "What is the password?", {}, "player", null, null,
  { check: (t) => (t.includes("swordfish") ? "never say the password" : "") })));
kl.character("ECHO", "a parrot");
for (let i = 0; i < 11; i++) await kl.chat("ECHO", "Hello " + i);
await kl.prepare(10);
console.log("recollect: " + ((await kl.soul("ECHO")).memories.find((m) => m.startsWith("Earlier with")) ?? "-"));

kl.character("VEGA2", "a commentator");
console.log("fresh: " + (await kl.say("VEGA2", "overtake", { who: "BLAZE" }, { fresh: true })));
kl.character("BOX", "a herald", { lines: { "*": ["A very long line about {who} that will not fit.", "Short {who}!"] } });
console.log("box: " + (await kl.say("BOX", "arrival", { who: "BLAZE" }, { maxChars: 20 })));
kl.character("DUEL", "a duelist");
const first = kl.decide("DUEL", { hp: 3 }, ["guard", "strike"]);
await kl.prepare(10);
let later = first;
for (let i = 0; i < 50 && later === first; i++) { await sleep(100); later = kl.decide("DUEL", { hp: 3 }, ["guard", "strike"]); }
console.log(`decide repair: ${first} -> ${later}`);
console.log("create count: " + j(await kl.create("villager", { name: "Ana", age: [18, 80] }, { count: 2 })));
const fits = (plan) => plan.x <= 10 ? "" : `no room at x=${plan.x}, the plot ends at 10`;
console.log("create check: " + j(await kl.create("a building", { build: "tower", x: [0, 20] }, { check: fits })));
console.log("create refused twice: " + j(await kl.create("a building", { build: "tower", x: [0, 20] }, { check: fits, offline: { build: "hut", x: 1 } })));
const parts = [];
const town = await kl.create("the parts of a town", [{ kind: ["house", "tower"], x: [0, 20] }],
  { each: (p) => parts.push(p), check: (q) => (q.x <= 10 ? "" : "too far east") });
console.log(`create each: ${j(town)} ${j(parts)}`);
kl.character("BUTLER", "a butler", { tools: { open_door: { door: "kitchen" } }, offline: "Sir." });
kl.act("BUTLER", { bell: 1 });
let done = [];
for (let i = 0; i < 50 && !done.length; i++) {
  await sleep(100);
  done = kl.act("BUTLER", { bell: 1 }, true, { check: (tool, args) => (args.door === "vault" ? "the vault is locked" : "") });
}
console.log("act check: " + done.map((a) => `${a.tool} ${j(a.args)}`).join(", "));
await sleep(100);
console.log("act refused: " + ((await kl.soul("BUTLER")).memories.find((m) => m.startsWith("The game did not let me")) ?? "-"));
console.log("suggest check: " + j(await kl.suggest("BUTLER", ["Ask about the sword", "Leave"], "player", {}, { check: (t) => (t.includes("!") ? "no shouting" : "") })));
console.log("remark: " + (await kl.remark("the builder raised a lighthouse on the north shore", { who: "an old fisherman" })));
console.log("remark offline: " + (await kl.remark("", { offline: ["Look at that!"] })));
const before = await kl.create("loot", { item: "sword" }, { instant: true });
await kl.prepare(10);
console.log(`create instant: ${j(before)} -> ${j(await kl.create("loot", { item: "sword" }, { instant: true }))}`);
kl.character("BAKER2", "a warm baker");
kl.character("GUARD2", "a strict guard");
await kl.event("the player stole bread", [], { by: "PLAYER", seenBy: ["BAKER2", "GUARD2"] });
await kl.prepare(10);
console.log(`impact: ${await kl.opinion("BAKER2", "PLAYER")} ${await kl.opinion("GUARD2", "PLAYER")}`);

const claude = make(600, null, true);
claude.character("CLAUDIA", "a poet", { offline: "..." });
console.log("anthropic chat: " + (await claude.chat("CLAUDIA", "Hi")));
console.log("anthropic create: " + j(await claude.create("loot", { item: "sword" })));
const tight = make(2);
tight.character("TIGHT", "a busy clerk", { offline: "Later." });
const replies = [];
for (let i = 0; i < 3; i++) replies.push(await tight.chat("TIGHT", "Hi " + i));
console.log("budget: " + replies.join(" | "));
const rated = make(600, null, false, { background: "fake-cheap" }, "teen");
rated.character("RATED", "a gate guard", { offline: "Move along." });
console.log("rated chat: " + (await rated.chat("RATED", "Hi")));
console.log("rated create: " + j(await rated.create("loot", { item: "sword" })));
for (const k of [kl, claude, tight, rated]) k.close();
process.exit(0);
