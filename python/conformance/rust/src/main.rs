// Conformance scenario for the Rust client: cargo run -- <port>
#[path = "../../../src/kinloom/clients/rust/kinloom.rs"]
mod kinloom;

use kinloom::{Json, Kinloom, Options};
use std::sync::{Arc, Mutex};
use std::thread::sleep;
use std::time::Duration;

/// Native mode (python conformance/native.py): the SDK calls the fake model itself; no kinloom serve.
fn native() -> Option<String> {
    std::env::var("KINLOOM_NATIVE").ok().filter(|v| !v.is_empty())
}

fn unreachable_kl() -> Kinloom {
    if native().is_some() {
        Kinloom::offline()
    } else {
        Kinloom::with("http://127.0.0.1:9", "default", "")
    }
}

fn main() {
    let port = std::env::args().nth(1).expect("port");
    if port == "deep" {
        deep(&native().expect("KINLOOM_NATIVE"));
        return;
    }
    let kl = match native() {
        Some(url) => Kinloom::native(Options {
            provider_url: Some(url.clone()),
            provider_key: Some("fake-key".into()),
            provider_model: Some("fake-model".into()),
            voice_url: Some(url),
            voice_key: Some("fake-key".into()),
            speak_model: Some("fake-tts".into()),
            listen_model: Some("fake-stt".into()),
            voice_name: Some("custom".into()),
            config: Some(obj! { "calls_per_minute" => 600 }),
            ..Default::default()
        }),
        None => Kinloom::with(&format!("http://127.0.0.1:{}", port), "default", ""),
    };
    kl.character("VEGA", "commentator", obj! { "lines" => obj! { "*" => vec!["What a race, {who}!"] }, "events" => obj! { "overtake" => vec!["who", "whom"] } });
    kl.character("THEO", "engineer", obj! { "offline" => "Copy." });
    kl.character("BLAZE", "rival", obj! { "tools" => obj! { "boost" => obj! { "seconds" => vec![0.5, 2.5] } } });
    let facts = obj! { "who" => "BLAZE", "whom" => "NOVA" };
    let mut line = String::new();
    for _ in 0..100 {
        line = kl.say("VEGA", "overtake", facts.clone());
        if line.contains("passes") {
            break;
        }
        sleep(Duration::from_millis(50));
    }
    println!("say: {}", line);
    println!("chat: {}", kl.chat("THEO", "gap?", obj! { "position" => 3 }));
    let choices = obj! { "strategy" => vec!["attack", "block"], "aggression" => vec![0.0, 1.0] };
    let first = kl.decide("BLAZE", obj! { "lap" => 1 }, choices.clone()).to_json();
    println!("decide first: {}", first);
    let mut later = first.clone();
    for _ in 0..100 {
        sleep(Duration::from_millis(50));
        later = kl.decide("BLAZE", obj! { "lap" => 1 }, choices.clone()).to_json();
        if later != first {
            break;
        }
    }
    println!("decide later: {}", later);
    for _ in 0..100 {
        let actions = kl.act("BLAZE", obj! { "lap" => 1 });
        if !actions.is_empty() {
            for a in actions {
                println!("act later: {} {}", a.tool, a.args.to_json());
            }
            break;
        }
        sleep(Duration::from_millis(50));
    }
    let example = obj! { "challenge" => "Win clean", "sky" => "#ff7a45" };
    println!("create: {}", kl.create("race", example.clone(), obj! {}, 0, false).to_json());
    let offline = unreachable_kl();
    offline.character("VEGA", "commentator", obj! { "lines" => obj! { "*" => vec!["What a race, {who}!"] } });
    offline.character("THEO", "engineer", obj! { "offline" => "Copy." });
    println!("offline say: {}", offline.say("VEGA", "overtake", facts));
    println!("offline chat: {}", offline.chat("THEO", "gap?", obj! { "position" => 3 }));
    println!("offline decide: {}", offline.decide("BLAZE", obj! { "lap" => 1 }, choices).to_json());
    println!("offline create: {}", offline.create("race", example, Json::Null, 0, false).to_json());

    // Minds and the world (the depth layer).
    let senses = obj! { "hp" => vec![0, 1], "dist" => vec![0, 40], "armed" => true, "enemy" => vec!["idle", "alert"] };
    let actions = obj! { "charge" => obj! { "speed" => vec![0.5, 3.0] }, "shoot" => obj! { "burst" => vec![1, 5] }, "retreat" => obj! {} };
    let rules = obj! { "retreat" => vec!["hp low"], "shoot" => vec!["armed", "dist below 20"],
                       "charge" => obj! { "score" => 0.5, "args" => obj! { "speed" => "dist high" } } };
    kl.mind("raider", "a cunning raider", senses.clone(), actions.clone(), rules.clone(), 1, 30.0);
    kl.mind("scout", "a timid scout", obj! { "noise" => vec![0, 1] }, obj! { "run" => obj! {}, "hide" => obj! {} }, Json::Null, 2, 30.0);
    for _ in 0..100 {
        if kl.report("raider").is_some() {
            break;
        }
        sleep(Duration::from_millis(50));
    }
    println!("think retreat: {}", kl.think("raider", &obj! { "hp" => 0.1, "dist" => 30, "armed" => true }, "u1").to_json());
    println!("think shoot: {}", kl.think("raider", &obj! { "hp" => 0.9, "dist" => 8, "armed" => true, "enemy" => "alert" }, "u2").to_json());
    println!("think charge: {}", kl.think("raider", &obj! { "hp" => 0.9, "dist" => 10, "armed" => false }, "u3").to_json());
    println!("think sticky: {}", kl.think("raider", &obj! { "hp" => 0.52, "dist" => 30, "armed" => true }, "u1").action.unwrap_or_default());
    println!("think fresh: {}", kl.think("raider", &obj! { "hp" => 0.52, "dist" => 30, "armed" => true }, "u4").to_json());
    let mut learned = String::new();
    for _ in 0..100 {
        learned = kl.think("scout", &obj! { "noise" => 0.5 }, "s1").action.unwrap_or_default();
        if learned == "hide" {
            break;
        }
        sleep(Duration::from_millis(100));
    }
    println!("think learned: {}", learned);
    kl.reward("u1", 1.0);
    kl.reward("u2", 0.5);
    kl.reward("u3", 0.0);
    kl.flush();
    let report = kl.report("raider").expect("report");
    let total: i64 = report.get("variants").as_array().iter().map(|v| v.get("rewards").as_i64()).sum();
    println!("rewards: {}", total);
    kl.character("BAKER", "a warm baker", obj! { "group" => "village" });
    kl.character("GUARD", "a strict guard", obj! { "group" => "guards" });
    println!("knows before: {}", kl.knows("GUARD", "theft"));
    kl.event_with("the player stole bread", obj! { "by" => "PLAYER", "seen_by" => vec!["BAKER"], "tag" => "theft", "impact" => -0.8 });
    let mut shared = Vec::new();
    for _ in 0..50 {
        shared = kl.meet("BAKER", "GUARD");
        if !shared.is_empty() {
            break;
        }
        sleep(Duration::from_millis(100));
    }
    let pairs: Vec<String> = shared.iter().map(|s| format!("{} -> {}", s.get("from").as_str(), s.get("to").as_str())).collect();
    println!("meet: {}", pairs.join(", "));
    println!("knows after: {}", kl.knows("GUARD", "theft"));
    println!("opinion: {}", kl.opinion("GUARD", "PLAYER"));
    println!("reputation: {}", kl.reputation("PLAYER", "village"));
    kl.character("MIRA", "", obj! { "soul" => obj! { "summary" => "a gruff smith", "mood" => "wary" }, "offline" => "Hm.",
                                   "tools" => obj! { "give" => obj! { "item" => "wood" } } });
    sleep(Duration::from_millis(100));
    println!("soul chat: {}", kl.chat_as("MIRA", "Nice toy hammer.", obj! {}, "Ana"));
    let mut soul = Json::Null;
    for _ in 0..50 {
        if let Some(s) = kl.soul("MIRA", "Ana") {
            soul = s;
            if soul.get("card").get("summary").as_str() != "" && *soul.get("bonds").get("Ana") != Json::Null {
                break;
            }
        }
        sleep(Duration::from_millis(100));
    }
    let feels = if soul.get("bonds").get("Ana").get("feeling").as_f64() < 0.0 { "dislikes" } else { "likes" };
    println!("lore: {}", kl.lore(&["The village is Brookmere.", "The king died last winter."]));
    println!("soul: {} {} {}", soul.get("mood").get("word").as_str(), feels, soul.get("card").get("summary").as_str());
    let wav = kl.speak("GUARD", "Halt.");
    println!("speak: {}", if wav.starts_with(b"RIFF") { "wav" } else { "?" });
    println!("listen: {}", kl.listen(&wav, ""));
    offline.mind("raider", "a cunning raider", senses, actions, rules, 1, 30.0);
    println!("offline think: {}", offline.think("raider", &obj! { "hp" => 0.1, "dist" => 30, "armed" => true }, "u1").to_json());
    println!("offline think charge: {}", offline.think("raider", &obj! { "hp" => 0.9, "dist" => 10, "armed" => false }, "u3").to_json());
    println!("offline knows: {}", offline.knows("GUARD", "theft"));
    offline.character("MIRA", "", obj! { "soul" => obj! { "summary" => "a gruff smith" }, "offline" => "Hm." });
    println!("offline soul chat: {}", offline.chat_as("MIRA", "Nice toy hammer.", obj! {}, "Ana"));
    println!("offline speak: {}", if offline.speak("GUARD", "Halt.").is_empty() { "none" } else { "audio" });
    let heard = offline.listen(&wav, "");
    println!("offline listen: {}", if heard.is_empty() { "-" } else { heard.as_str() });

    // What came back: where it came from, actions with the reply, events described in words.
    let challenge = || obj! { "challenge" => obj! { "when" => "challenging someone to a battle", "lines" => vec!["{other}, fight!"] } };
    kl.character("ANA", "a trainer", obj! { "lines" => challenge() });
    let mut said = String::new();
    for _ in 0..50 {
        said = kl.say("ANA", "challenge", obj! { "other" => "BEN" });
        if !said.is_empty() {
            break;
        }
        sleep(Duration::from_millis(100));
    }
    println!("when say: {}", said);
    kl.say("VEGA", "overtake", obj! { "who" => "BLAZE", "whom" => "NOVA" });
    println!("say source: {}", kl.source("VEGA"));
    println!("chat source: {}", kl.source("MIRA"));
    for a in kl.act_with("MIRA", obj! {}, false) {
        println!("chat do: {} {}", a.tool, a.args.to_json());
    }
    offline.character("ANA", "a trainer", obj! { "lines" => challenge() });
    println!("offline when say: {}", offline.say("ANA", "challenge", obj! { "other" => "BEN" }));
    println!("offline source: {}", offline.source("ANA"));

    // The game's tools, pictures, ready before play.
    let png = kinloom::base64_decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGP4z8AARAwQCgAf7gP9i18U1AAAAABJRU5ErkJggg==");
    println!("tools: {}", kl.tools(obj! { "open_door" => obj! { "door" => "north" } }).join(", "));
    kl.character("KEEPER", "a gatekeeper", obj! { "tools" => vec!["open_door"] });
    sleep(Duration::from_millis(100));
    for _ in 0..100 {
        let acts = kl.act("KEEPER", obj! {});
        if !acts.is_empty() {
            for a in acts {
                println!("tools act: {} {}", a.tool, a.args.to_json());
            }
            break;
        }
        sleep(Duration::from_millis(50));
    }
    kl.character("LOOK", "a painter", obj! { "offline" => "Blind." });
    sleep(Duration::from_millis(100));
    println!("chat image: {}", kl.chat_image("LOOK", "What is this?", obj! {}, "player", &png));
    let example = || obj! { "challenge" => "Win clean", "sky" => "#ff7a45" };
    println!("create image: {}", kl.create_image("race", example(), obj! {}, 0, false, &png).to_json());
    let ready = kl.prepare(10.0);
    println!("prepare: {} {}", if ready.get("ready").as_bool() { "ready" } else { "waiting" }, if ready.get("online").as_bool() { "online" } else { "offline" });
    println!("offline tools: {}", offline.tools(obj! { "open_door" => obj! { "door" => "north" } }).join(", "));
    offline.character("LOOK", "a painter", obj! { "offline" => "Blind." });
    println!("offline chat image: {}", offline.chat_image("LOOK", "What is this?", obj! {}, "player", &png));
    println!("offline create image: {}", offline.create_image("race", example(), obj! {}, 0, false, &png).to_json());
    let ready = offline.prepare(1.0);
    println!("offline prepare: {} {}", if ready.get("ready").as_bool() { "ready" } else { "waiting" }, if ready.get("online").as_bool() { "online" } else { "offline" });
    let t0 = std::time::Instant::now();
    let gone = unreachable_kl();
    gone.character("THEO", "engineer", obj! { "offline" => "Copy." });
    let fast = gone.chat("THEO", "gap?", obj! {}) == "Copy." && gone.chat("THEO", "gap?", obj! {}) == "Copy." && gone.say("THEO", "x", obj! {}).is_empty();
    let took = t0.elapsed().as_millis();
    if fast && took < 1500 {
        println!("offline fast: yes");
    } else {
        println!("offline fast: no ({} ms)", took);
    }
    // v1: the player's choices, characters talking together, a snapshot, saves
    let reply_choices = ["Ask about the sword", "Buy something", "Leave"];
    println!("suggest: {}", kl.suggest("MIRA", &reply_choices, "Ana", Json::Null).join(" | "));
    println!("offline suggest: {}", offline.suggest("MIRA", &reply_choices, "Ana", Json::Null).join(" | "));
    let talk: Vec<String> = kl.converse("MIRA", "BAKER", "the smoke", 4).iter().map(|x| format!("{}: {}", x.get("who").as_str(), x.get("text").as_str())).collect();
    println!("converse: {}", talk.join(" | "));
    println!("offline converse: {}", offline.converse("MIRA", "BAKER", "", 4).len());
    let snap = kl.inspect().unwrap_or(Json::Null);
    let mira = snap.get("characters").get("MIRA");
    println!("inspect: MIRA {} {}", mira.get("mood").get("word").as_str(), mira.get("last_words").as_str());
    let slot2 = kl.with_session("slot2");
    slot2.load(&kl.save());
    println!("load: MIRA {} Ana", if slot2.opinion("MIRA", "Ana") < 0.0 { "dislikes" } else { "likes" });
    if native().is_some() {
        let (passed, total, failures) = kinloom::vectors::run_file(&std::env::var("KINLOOM_VECTORS").unwrap_or_default());
        println!("vectors: {}/{}", passed, total);
        for f in failures.iter().take(12) {
            eprintln!("{}", f);
        }
        kl.close();
    }
}

fn make(base: &str, calls: i64, banned: Option<Vec<&str>>, anthropic: bool) -> Kinloom {
    let mut config = obj! { "calls_per_minute" => calls };
    if let (Json::Obj(m), Some(words)) = (&mut config, banned) {
        m.insert("banned_words".into(), Json::from(words));
    }
    let mut o = Options { provider_key: Some("fake-key".into()), config: Some(config), ..Default::default() };
    if anthropic {
        o.provider_kind = Some("anthropic".into());
        o.provider_url = Some(base[..base.len() - 3].to_string());
        o.provider_model = Some("claude-test".into());
    } else {
        o.provider_url = Some(base.to_string());
        o.provider_model = Some("fake-model".into());
    }
    Kinloom::native(o)
}

fn make_rated(base: &str) -> Kinloom {
    Kinloom::native(Options { provider_key: Some("fake-key".into()), provider_url: Some(base.to_string()), provider_model: Some("fake-model".into()),
                              config: Some(obj! { "calls_per_minute" => 600i64 }), models: Some(obj! { "background" => "fake-cheap" }),
                              rating: Some("teen".into()), ..Default::default() })
}

/// The deep native scenario (see conformance/deep.py, the Python reference).
fn deep(base: &str) {
    let kl = make(base, 600, Some(vec!["dragon"]), false);
    kl.character("VERA", "", obj! { "soul" => "a gruff smith who sold the king's sword", "offline" => "Busy." });
    let ready = kl.prepare(10.0);
    println!("prepare: {}", if ready.get("ready").as_bool() { "ready" } else { "waiting" });
    println!("soul: {}", kl.soul("VERA", "player").unwrap_or(Json::Null).get("card").get("summary").as_str());
    let greet = kl.chat_as("VERA", "", obj! {}, "Ana");
    println!("greet: {} ({})", greet, kl.source("VERA"));
    println!("secret: {}", kl.chat_as("VERA", "Did you sell the king's sword to a smuggler?", obj! {}, "Ana"));
    println!("numbers: {}", kl.chat_as("VERA", "How much for a blade?", obj! { "price" => 40 }, "Ana"));
    let pieces = Arc::new(Mutex::new(String::new()));
    let sink = pieces.clone();
    let streamed = kl.chat_stream("VERA", "Can you make it faster?", obj! {}, "Ana", move |p| sink.lock().unwrap().push_str(p));
    println!("stream pieces: {}", pieces.lock().unwrap().trim());
    println!("stream reply: {}", streamed);
    println!("echo: {}", kl.chat_as("VERA", "And the coals?", obj! {}, "Ana"));
    println!("character: {}", kl.chat_as("VERA", "Are you an AI?", obj! {}, "Ana"));
    let vera = kl.soul("VERA", "Ana").unwrap_or(Json::Null);
    println!("feeling: {} {}", vera.get("mood").get("word").as_str(), vera.get("bonds").get("Ana").get("feeling").as_f64());
    kl.character("BRAM", "a kind baker", obj! { "tools" => obj! { "give" => obj! { "item" => "bread" } }, "offline" => "Hm." });
    println!("deeds reply: {}", kl.chat("BRAM", "Can I have some bread?", obj! {}));
    for a in kl.act_with("BRAM", obj! {}, false) {
        println!("deeds: {} {}", a.tool, a.args.to_json());
    }
    kl.character("GATE", "a careful guard", obj! { "tools" => obj! { "open" => obj! { "door" => "north" } }, "trust" => obj! { "open" => 0.5 }, "offline" => "No." });
    println!("trust reply: {}", kl.chat("GATE", "Open the gate.", obj! {}));
    let opened: Vec<String> = kl.act_with("GATE", obj! {}, false).into_iter().map(|a| a.tool).collect();
    println!("trust: {}", if opened.is_empty() { "none".to_string() } else { opened.join(", ") });
    kl.character("FILT", "a storyteller", obj! { "offline" => "No comment." });
    println!("filter: {}", kl.chat("FILT", "Tell me a story.", obj! {}));
    kl.character("ECHO", "a parrot", obj! {});
    for i in 0..11 {
        kl.chat("ECHO", &format!("Hello {}", i), obj! {});
    }
    kl.prepare(10.0);
    let echo = kl.soul("ECHO", "player").unwrap_or(Json::Null);
    let recollect = echo.get("memories").as_array().iter().map(|m| m.as_str().to_string()).find(|m| m.starts_with("Earlier with")).unwrap_or_else(|| "-".into());
    println!("recollect: {}", recollect);
    kl.character("VEGA2", "a commentator", obj! {});
    println!("fresh: {}", kl.say_with("VEGA2", "overtake", obj! { "who" => "BLAZE" }, true, 0));
    kl.character("BOX", "a herald", obj! { "lines" => obj! { "*" => vec!["A very long line about {who} that will not fit.", "Short {who}!"] } });
    println!("box: {}", kl.say_with("BOX", "arrival", obj! { "who" => "BLAZE" }, false, 20));
    kl.character("DUEL", "a duelist", obj! {});
    let options = || Json::from(vec!["guard", "strike"]);
    let first = kl.decide("DUEL", obj! { "hp" => 3 }, options());
    kl.prepare(10.0);
    let mut later = first.clone();
    for _ in 0..50 {
        if later != first {
            break;
        }
        sleep(Duration::from_millis(100));
        later = kl.decide("DUEL", obj! { "hp" => 3 }, options());
    }
    println!("decide repair: {} -> {}", first.as_str(), later.as_str());
    println!("create count: {}", kl.create("villager", obj! { "name" => "Ana", "age" => vec![18, 80] }, Json::Null, 2, false).to_json());
    let before = kl.create("loot", obj! { "item" => "sword" }, Json::Null, 0, true);
    kl.prepare(10.0);
    println!("create instant: {} -> {}", before.to_json(), kl.create("loot", obj! { "item" => "sword" }, Json::Null, 0, true).to_json());
    kl.character("BAKER2", "a warm baker", obj! {});
    kl.character("GUARD2", "a strict guard", obj! {});
    kl.event_with("the player stole bread", obj! { "by" => "PLAYER", "seen_by" => vec!["BAKER2", "GUARD2"] });
    kl.prepare(10.0);
    println!("impact: {} {}", kl.opinion("BAKER2", "PLAYER"), kl.opinion("GUARD2", "PLAYER"));
    let claude = make(base, 600, None, true);
    claude.character("CLAUDIA", "a poet", obj! { "offline" => "..." });
    println!("anthropic chat: {}", claude.chat("CLAUDIA", "Hi", obj! {}));
    println!("anthropic create: {}", claude.create("loot", obj! { "item" => "sword" }, Json::Null, 0, false).to_json());
    let tight = make(base, 2, None, false);
    tight.character("TIGHT", "a busy clerk", obj! { "offline" => "Later." });
    let replies: Vec<String> = (0..3).map(|i| tight.chat("TIGHT", &format!("Hi {}", i), obj! {})).collect();
    println!("budget: {}", replies.join(" | "));
    let rated = make_rated(base);
    rated.character("RATED", "a gate guard", obj! { "offline" => "Move along." });
    println!("rated chat: {}", rated.chat("RATED", "Hi", obj! {}));
    println!("rated create: {}", rated.create("loot", obj! { "item" => "sword" }, Json::Null, 0, false).to_json());
    for k in [&kl, &claude, &tight, &rated] {
        k.close();
    }
}
