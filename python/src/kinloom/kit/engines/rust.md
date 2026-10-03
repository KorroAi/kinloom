language: Rust (Bevy, macroquad, ggez, Fyrox, any Rust game)
Setup: `kinloom init` copied `{client_path}` (no crates needed): add `mod kinloom;` to `main.rs` (or `lib.rs`; other modules: `use crate::obj;`). While
playing, run `kinloom serve`. Or no server (native: the game calls the model itself, the key from the environment): `kinloom::Kinloom::native(
kinloom::Options { provider_auto: true, ..Default::default() })`. `Kinloom` is `Clone + Send + Sync`; Bevy: `#[derive(Resource)] struct Ai(kinloom::Kinloom);`. `obj!` builds JSON objects.
---
```rust
mod kinloom;
use kinloom::Kinloom;

let kl = Kinloom::new();                               // Kinloom::with(url, "player-2", "") per player
// Characters with a soul: one sentence, a person the player talks to (mood, feelings, memories, secrets, actions)
kl.character("MIRA", "", obj! { "soul" => "a gruff blacksmith who secretly sold the king's sword", "offline" => "Busy.",
                                "tools" => obj! { "give" => obj! { "item" => "sword" } } });
let reply = kl.chat_as("MIRA", &player_text, obj! {}, "Ana");     // "" = Ana walks up: she speaks first (~1 s: use a thread)
for a in kl.act_with("MIRA", obj! {}, false) { if a.tool == "give" { inventory.push(a.args.get("item").as_str().to_string()); } }
let soul = kl.soul("MIRA", "Ana");                                // Option<Json>: card, mood, bonds, memories

kl.character("VEGA", "over-excited race commentator, max 10 words", obj! {
    "lines" => obj! { "overtake" => vec!["{who} passes {whom}!"], "*" => vec!["What a race!"] },   // offline lines
    "events" => obj! { "overtake" => vec!["who", "whom", "gap"] } });                                // prepare lines now
kl.character("THEO", "calm race engineer", obj! { "offline" => "Copy that." });
kl.character("RAX", "brutal rival", obj! { "tools" => obj! { "ram" => obj! { "force" => vec![0.0, 1.0] } } });

let line = kl.say("VEGA", "overtake", obj! { "who" => "BLAZE", "whom" => "NOVA", "gap" => 0.4 });  // fast
let reply = kl.chat_async("THEO", &player_text, obj! { "gap_to_leader" => 1.8 });  // Receiver: reply.try_recv() each frame

// every frame: instant, refreshed in the background
let plan = kl.decide("RAX", obj! { "gap" => gap }, obj! { "strategy" => vec!["attack", "block"], "aggression" => vec![0.0, 1.0] });
rax.aggression = plan.get("aggression").as_f64() as f32;
for a in kl.act("RAX", obj! { "gap" => gap }) {
    if a.tool == "ram" { rax.ram(a.args.get("force").as_f64()); }
}

let challenge = kl.create("a short race challenge",
    obj! { "title" => "Win clean", "laps" => vec![2, 5], "sky" => "#ff7a45" }, obj! {}, 0, false);   // create_async: off-frame
kl.event("BLAZE crashed on lap 3", &["BLAZE", "VEGA"]);   // they remember it
kl.state(obj! { "lap" => 3, "leader" => "NOVA" });         // facts every call sees

// Minds: utility AI for crowds, run locally every frame (never a model call); rules are the offline mind
kl.mind("raider", "a cunning raider", obj! { "hp" => vec![0.0, 1.0], "dist" => vec![0.0, 40.0], "armed" => true },
        obj! { "charge" => obj! { "speed" => vec![1.0, 3.0] }, "shoot" => obj! {}, "retreat" => obj! {} },
        obj! { "retreat" => vec!["hp low"], "shoot" => vec!["armed", "dist below 20"] }, 3, 30.0);
let t = kl.think("raider", &obj! { "hp" => hp, "dist" => dist, "armed" => ammo > 0 }, &enemy_id);   // every frame
kl.reward_done(&enemy_id, dealt - taken, died_or_won);                                             // minds learn

// World (blocking with short limits: call from a thread or at a pause)
kl.event_with("the player stole bread", obj! { "by" => "PLAYER", "seen_by" => vec!["BAKER"], "tag" => "theft", "impact" => -0.6 });
kl.meet("BAKER", "GUARD");
let alert = kl.knows("GUARD", "theft");
```
