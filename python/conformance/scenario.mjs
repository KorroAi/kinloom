// Conformance scenario for the JavaScript client: node scenario.mjs <port>
import { Kinloom, vector } from "../src/kinloom/clients/web/kinloom.js";
import { reportVectors } from "./vectors.mjs";

const port = process.argv[2];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const j = (v) => JSON.stringify(sortKeys(v));
function sortKeys(v) {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === "object") return Object.fromEntries(Object.keys(v).sort().map((k) => [k, sortKeys(v[k])]));
  return v;
}

// Native mode (python conformance/native.py): the SDK calls the fake model itself; no kinloom serve.
const native = process.env.KINLOOM_NATIVE;
const host = native ? new Kinloom({ provider: { url: native, key: "fake-key", model: "fake-model" }, config: { calls_per_minute: 600 },
  voice: { url: native, key: "fake-key", speakModel: "fake-tts", listenModel: "fake-stt", name: "custom" } }) : null;
const connect = () => (host ? new Kinloom({ brain: host.brain }) : new Kinloom({ url: `http://127.0.0.1:${port}` }));
const unreachable = () => (native ? new Kinloom({ offline: true }) : new Kinloom({ url: "http://127.0.0.1:9" }));
const kl = connect();
kl.character("VEGA", "commentator", { lines: { "*": ["What a race, {who}!"] }, events: { overtake: ["who", "whom"] } });
kl.character("THEO", "engineer", { offline: "Copy." });
kl.character("BLAZE", "rival", { tools: { boost: { seconds: [0.5, 2.5] } } });
const facts = { who: "BLAZE", whom: "NOVA" };
let line = "";
for (let i = 0; i < 100; i++) {
  line = await kl.say("VEGA", "overtake", facts);
  if (line.includes("passes")) break;
  await sleep(50);
}
console.log("say: " + line);
console.log("chat: " + (await kl.chat("THEO", "gap?", { position: 3 })));
const choices = { strategy: ["attack", "block"], aggression: [0.0, 1.0] };
const first = { ...kl.decide("BLAZE", { lap: 1 }, choices) };
console.log("decide first: " + j(first));
let later = first;
for (let i = 0; i < 100; i++) {
  await sleep(50);
  later = kl.decide("BLAZE", { lap: 1 }, choices);
  if (j(later) !== j(first)) break;
}
console.log("decide later: " + j(later));
for (let i = 0; i < 100; i++) {
  const actions = kl.act("BLAZE", { lap: 1 });
  if (actions.length) {
    for (const a of actions) console.log(`act later: ${a.tool} ${j(a.args)}`);
    break;
  }
  await sleep(50);
}
console.log("create: " + j(await kl.create("race", { challenge: "Win clean", sky: "#ff7a45" })));
const offline = unreachable();
offline.character("VEGA", "commentator", { lines: { "*": ["What a race, {who}!"] } });
offline.character("THEO", "engineer", { offline: "Copy." });
console.log("offline say: " + (await offline.say("VEGA", "overtake", facts)));
console.log("offline chat: " + (await offline.chat("THEO", "gap?", { position: 3 })));
console.log("offline decide: " + j(offline.decide("BLAZE", { lap: 1 }, choices)));
console.log("offline create: " + j(await offline.create("race", { challenge: "Win clean", sky: "#ff7a45" })));
// An example with no shape fails at once, with count too (as in Python), never a list of empty answers.
for (const bad of [{}, []]) {
  let threw = false;
  try { await offline.create("an item", bad, { count: 2 }); } catch { threw = true; }
  if (!threw) throw new Error("an example with no shape was accepted with count");
}

// ---------------- minds and the world (the depth layer) ----------------
const RAIDER = {
  senses: { hp: [0, 1], dist: [0, 40], armed: true, enemy: ["idle", "alert"] },
  actions: { charge: { speed: [0.5, 3.0] }, shoot: { burst: [1, 5] }, retreat: {} },
  rules: { retreat: ["hp low"], shoot: ["armed", "dist below 20"], charge: { score: 0.5, args: { speed: "dist high" } } },
  variants: 1,
};
const live = connect();
live.mind("raider", "a cunning raider", RAIDER);
live.mind("scout", "a timid scout", { senses: { noise: [0, 1] }, actions: { run: {}, hide: {} }, variants: 2 });
for (let i = 0; i < 100 && !(await live.report("raider")); i++) await sleep(50);
console.log("think retreat: " + j(live.think("raider", { hp: 0.1, dist: 30, armed: true }, "u1")));
console.log("think shoot: " + j(live.think("raider", { hp: 0.9, dist: 8, armed: true, enemy: "alert" }, "u2")));
console.log("think charge: " + j(live.think("raider", { hp: 0.9, dist: 10, armed: false }, "u3")));
console.log("think sticky: " + live.think("raider", { hp: 0.52, dist: 30, armed: true }, "u1").action);
console.log("think fresh: " + j(live.think("raider", { hp: 0.52, dist: 30, armed: true }, "u4")));
let learned = "";
for (let i = 0; i < 100; i++) {
  learned = live.think("scout", { noise: 0.5 }, "s1").action;
  if (learned === "hide") break;
  await sleep(100);
}
console.log("think learned: " + learned);
live.reward("u1", 1);
live.reward("u2", 0.5);
live.reward("u3", 0);
await live.flush();
const report = await live.report("raider");
console.log("rewards: " + report.variants.reduce((n, v) => n + v.rewards, 0));
live.character("BAKER", "a warm baker", { group: "village" });
live.character("GUARD", "a strict guard", { group: "guards" });
console.log("knows before: " + (await live.knows("GUARD", "theft")));
await live.event("the player stole bread", [], { by: "PLAYER", seenBy: ["BAKER"], tag: "theft", impact: -0.8 });
let shared = [];
for (let i = 0; i < 50 && !shared.length; i++) {
  shared = await live.meet("BAKER", "GUARD");
  if (!shared.length) await sleep(100);
}
console.log("meet: " + shared.map((s) => s.from + " -> " + s.to).join(", "));
console.log("knows after: " + (await live.knows("GUARD", "theft")));
console.log("opinion: " + (await live.opinion("GUARD", "PLAYER")));
console.log("reputation: " + (await live.reputation("PLAYER", "village")));
live.character("MIRA", "", { soul: { summary: "a gruff smith", mood: "wary" }, offline: "Hm.", tools: { give: { item: "wood" } } });
await sleep(100);
console.log("soul chat: " + (await live.chat("MIRA", "Nice toy hammer.", {}, "Ana", () => {})));
let soul = null;
for (let i = 0; i < 50; i++) {
  soul = await live.soul("MIRA", "Ana");
  if (soul && soul.card && soul.bonds.Ana) break;
  await sleep(100);
}
console.log("lore: " + (await live.lore(["The village is Brookmere.", "The king died last winter."])));
console.log("soul: " + soul.mood.word + " " + (soul.bonds.Ana.feeling < 0 ? "dislikes" : "likes") + " " + soul.card.summary);
const spoken = await live.speak("GUARD", "Halt.");
console.log("speak: " + (spoken && atob(spoken.audio).startsWith("RIFF") ? "wav" : "?"));
console.log("listen: " + (await live.listen(Uint8Array.from(atob(spoken.audio), (c) => c.charCodeAt(0)))));
const dead = unreachable();
dead.mind("raider", "a cunning raider", RAIDER);
console.log("offline think: " + j(dead.think("raider", { hp: 0.1, dist: 30, armed: true }, "u1")));
console.log("offline think charge: " + j(dead.think("raider", { hp: 0.9, dist: 10, armed: false }, "u3")));
console.log("offline knows: " + (await dead.knows("GUARD", "theft")));
dead.character("MIRA", "", { soul: { summary: "a gruff smith" }, offline: "Hm." });
console.log("offline soul chat: " + (await dead.chat("MIRA", "Nice toy hammer.", {}, "Ana")));
console.log("offline speak: " + ((await dead.speak("GUARD", "Halt.")) === null ? "none" : "audio"));
console.log("offline listen: " + ((await dead.listen(spoken.audio)) || "-"));

// ---------------- what came back: where it came from, actions with the reply, events described in words ----------------
live.character("ANA", "a trainer", { lines: { challenge: { when: "challenging someone to a battle", lines: ["{other}, fight!"] } } });
let challenge = "";
for (let i = 0; i < 50 && !challenge; i++) {
  challenge = await live.say("ANA", "challenge", { other: "BEN" });
  if (!challenge) await sleep(100);
}
console.log("when say: " + challenge);
await live.say("VEGA", "overtake", facts);
console.log("say source: " + live.source("VEGA"));
console.log("chat source: " + live.source("MIRA"));
for (const a of live.act("MIRA", {}, false)) console.log(`chat do: ${a.tool} ${j(a.args)}`);
dead.character("ANA", "a trainer", { lines: { challenge: { when: "challenging someone to a battle", lines: ["{other}, fight!"] } } });
console.log("offline when say: " + (await dead.say("ANA", "challenge", { other: "BEN" })));
console.log("offline source: " + dead.source("ANA"));

// ---------------- the game's tools, pictures, ready before play ----------------
const PNG = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGP4z8AARAwQCgAf7gP9i18U1AAAAABJRU5ErkJggg==";
console.log("tools: " + (await live.tools({ open_door: { door: "north" } })).join(", "));
live.character("KEEPER", "a gatekeeper", { tools: ["open_door"] });
await sleep(100);
for (let i = 0; i < 100; i++) {
  const acts = live.act("KEEPER", {});
  if (acts.length) {
    for (const a of acts) console.log(`tools act: ${a.tool} ${j(a.args)}`);
    break;
  }
  await sleep(50);
}
live.character("LOOK", "a painter", { offline: "Blind." });
await sleep(100);
console.log("chat image: " + (await live.chat("LOOK", "What is this?", {}, "player", null, PNG)));
console.log("create image: " + j(await live.create("race", { challenge: "Win clean", sky: "#ff7a45" }, { image: PNG })));
live.character("LAMP", "a lamplighter");   // declared just before: prepare must wait for it
let ready = await live.prepare(10);
console.log(`prepare: ${ready.ready ? "ready" : "waiting"} ${ready.online ? "online" : "offline"}`);
console.log("offline tools: " + (await dead.tools({ open_door: { door: "north" } })).join(", "));
dead.character("LOOK", "a painter", { offline: "Blind." });
console.log("offline chat image: " + (await dead.chat("LOOK", "What is this?", {}, "player", null, PNG)));
console.log("offline create image: " + j(await dead.create("race", { challenge: "Win clean", sky: "#ff7a45" }, { image: PNG })));
ready = await dead.prepare(1);
console.log(`offline prepare: ${ready.ready ? "ready" : "waiting"} ${ready.online ? "online" : "offline"}`);
const t0 = Date.now();
const gone = unreachable();
gone.character("THEO", "engineer", { offline: "Copy." });
const fast = (await gone.chat("THEO", "gap?")) === "Copy." && (await gone.chat("THEO", "gap?")) === "Copy." && (await gone.say("THEO", "x")) === "";
console.log("offline fast: " + (fast && Date.now() - t0 < 1500 ? "yes" : `no (${(Date.now() - t0) / 1000} s)`));
// ---------------- v1: the player's choices, characters talking together, a snapshot, saves ----------------
const CHOICES = ["Ask about the sword", "Buy something", "Leave"];
console.log("suggest: " + (await live.suggest("MIRA", CHOICES, "Ana")).join(" | "));
console.log("offline suggest: " + (await dead.suggest("MIRA", CHOICES, "Ana")).join(" | "));
const talk = await live.converse("MIRA", "BAKER", "the smoke");
console.log("converse: " + talk.map((x) => x.who + ": " + x.text).join(" | "));
console.log("offline converse: " + (await dead.converse("MIRA", "BAKER")).length);
const snap = (await live.inspect()).characters.MIRA;
console.log(`inspect: MIRA ${snap.mood.word} ${snap.last_words}`);
const slot2 = live.withSession("slot2");
await slot2.load(await live.save());
console.log(`load: MIRA ${(await slot2.opinion("MIRA", "Ana")) < 0 ? "dislikes" : "likes"} Ana`);
if (native) {
  reportVectors(vector);
  host.close();
  process.exit(0);
}
