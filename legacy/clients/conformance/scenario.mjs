// Conformance scenario for the JavaScript client: node scenario.mjs <port>. Prints the transcript compared with expected.txt.
import { readFileSync } from "node:fs";
import { Kinloom } from "../javascript/kinloom.js";

const port = process.argv[2];
const log = [];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const kl = await Kinloom.connect(`ws://localhost:${port}/ws`);

const effects = [];
let said = null;
kl.handle("set", (e) => { effects.push(e); });
kl.handle("say", (e) => { said = e; });

const manifest = JSON.parse(readFileSync(new URL("./manifest.json", import.meta.url), "utf8"));
log.push("declare errors: " + (await kl.declare(manifest)).length);
log.push("bad declare errors: " + ((await kl.declare({ things: [{ id: "x", type: "Ghost" }] })).length > 0));
kl.update("player", { idle_seconds: 2 });
kl.event("overtake", { who: "player" });
for (let i = 0; i < 300 && effects.length === 0; i++) { await kl.tick(1); await sleep(10); }
for (const e of effects) log.push(`effect ${e.kind} ${e.thing}.${e.member} ${JSON.stringify(e.args.value)} from ${e.source}`);

const reply = await kl.ask("rex", "Nice truck.", "player");
for (let i = 0; i < 100 && !said; i++) await sleep(10);
log.push(`said by ${said?.thing}: ${said?.text}`);
log.push("reply: " + reply.reply);

const g = await kl.generate("name", { style: "loud" });
log.push(`generated: ${g.ok} ${g.value?.name}`);
const state = await kl.save();
log.push("saved: " + state.includes('"version":1'));
await kl.load(state);
log.push("loaded");
log.push("remove missing: " + (await kl.remove("nobody")));
try { await kl._request("fly", {}); log.push("unknown method error: none"); }
catch (e) { log.push("unknown method error: " + e.code); }
kl.close();
console.log(log.join("\n"));
