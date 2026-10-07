// Conformance scenario for the C++ client: scenario <port>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include "../../src/kinloom/clients/cpp/kinloom.hpp"

using kinloom::arr;
using kinloom::Json;
using kinloom::obj;

static void sleep_ms(int ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }

/// Native mode (python conformance/native.py): the SDK calls the fake model itself; no kinloom serve.
static std::string native_url() {
    const char* v = std::getenv("KINLOOM_NATIVE");
    return v ? v : "";
}

static kinloom::Kinloom unreachable() { return native_url().empty() ? kinloom::Kinloom("http://127.0.0.1:9") : kinloom::Kinloom::offline(); }

static kinloom::Kinloom make(const std::string& base, int calls, const Json& banned, bool anthropic) {
    kinloom::Options o;
    o.provider_key = "fake-key";
    o.config = obj({{"calls_per_minute", calls}});
    if (!banned.is_null()) o.config.fields_mut()["banned_words"] = banned;
    if (anthropic) {
        o.provider_kind = "anthropic";
        o.provider_url = base.substr(0, base.size() - 3);
        o.provider_model = "claude-test";
    } else {
        o.provider_url = base;
        o.provider_model = "fake-model";
    }
    return kinloom::Kinloom(o);
}

/// The deep native scenario (see conformance/deep.py, the Python reference).
static void deep(const std::string& base) {
    kinloom::Kinloom kl = make(base, 600, arr({"dragon"}), false);
    kl.character("VERA", "", obj({{"soul", "a gruff smith who sold the king's sword"}, {"offline", "Busy."}}));
    Json ready = kl.prepare(10);
    std::cout << "prepare: " << (ready["ready"].boolean() ? "ready" : "waiting") << "\n";
    std::cout << "soul: " << kl.soul("VERA", "player")["card"]["summary"].str() << "\n";
    std::string greet = kl.chat("VERA", "", obj({}), "Ana");
    std::cout << "greet: " << greet << " (" << kl.source("VERA") << ")\n";
    std::cout << "secret: " << kl.chat("VERA", "Did you sell the king's sword to a smuggler?", obj({}), "Ana") << "\n";
    std::cout << "numbers: " << kl.chat("VERA", "How much for a blade?", obj({{"price", 40}}), "Ana") << "\n";
    std::string pieces;
    std::mutex pm;
    std::string streamed = kl.chat("VERA", "Can you make it faster?", obj({}), "Ana", {}, [&](const std::string& p) { std::lock_guard<std::mutex> lock(pm); pieces += p; });
    size_t a = pieces.find_first_not_of(" \t\r\n"), b = pieces.find_last_not_of(" \t\r\n");
    std::cout << "stream pieces: " << (a == std::string::npos ? "" : pieces.substr(a, b - a + 1)) << "\n";
    std::cout << "stream reply: " << streamed << "\n";
    std::cout << "echo: " << kl.chat("VERA", "And the coals?", obj({}), "Ana") << "\n";
    std::cout << "character: " << kl.chat("VERA", "Are you an AI?", obj({}), "Ana") << "\n";
    Json vera = kl.soul("VERA", "Ana");
    std::cout << "feeling: " << vera["mood"]["word"].str() << " " << vera["bonds"]["Ana"]["feeling"].num() << "\n";
    kl.character("BRAM", "a kind baker", obj({{"tools", obj({{"give", obj({{"item", "bread"}})}})}, {"offline", "Hm."}}));
    std::cout << "deeds reply: " << kl.chat("BRAM", "Can I have some bread?", obj({})) << "\n";
    for (auto& act : kl.act("BRAM", obj({}), false)) std::cout << "deeds: " << act.tool << " " << act.args.dump() << "\n";
    kl.character("GATE", "a careful guard", obj({{"tools", obj({{"open", obj({{"door", "north"}})}})}, {"trust", obj({{"open", 0.5}})}, {"offline", "No."}}));
    std::cout << "trust reply: " << kl.chat("GATE", "Open the gate.", obj({})) << "\n";
    std::string opened;
    for (auto& act : kl.act("GATE", obj({}), false)) opened += (opened.empty() ? "" : ", ") + act.tool;
    std::cout << "trust: " << (opened.empty() ? std::string("none") : opened) << "\n";
    kl.character("FILT", "a storyteller", obj({{"offline", "No comment."}}));
    std::cout << "filter: " << kl.chat("FILT", "Tell me a story.", obj({})) << "\n";
    kl.character("NINA", "a singer", obj({{"soul", obj({{"summary", "a singer"}, {"secrets", arr({"I went up to the office at 12:30"})}})},
                                          {"warmth", 0.3}, {"secret_trust", 0.25}, {"warm_up", 0.1}}));
    std::cout << "warmth: " << kl.opinion("NINA", "Ana") << "\n";
    kl.steer("NINA", "admit you went up to the office at 12:30");
    std::cout << "steer: " << kl.chat("NINA", "Where were you?", obj({}), "Ana") << "\n";
    std::cout << "warm up: " << kl.opinion("NINA", "Ana") << "\n";
    kl.character("KEEPER", "a gatekeeper", obj({{"offline", "Move along."}}));
    std::cout << "chat check: " << kl.chat_checked("KEEPER", "What is the password?", Json(), "player", [](const std::string& t) {
        return t.find("swordfish") != std::string::npos ? std::string("never say the password") : std::string();
    }) << "\n";
    kl.character("ECHO", "a parrot", obj({}));
    for (int i = 0; i < 11; i++) kl.chat("ECHO", "Hello " + std::to_string(i), obj({}));
    kl.prepare(10);
    std::string recollect = "-";
    Json echo = kl.soul("ECHO", "player");
    for (auto& m : echo["memories"].items()) if (m.str().rfind("Earlier with", 0) == 0) { recollect = m.str(); break; }
    std::cout << "recollect: " << recollect << "\n";
    kl.character("VEGA2", "a commentator", obj({}));
    std::cout << "fresh: " << kl.say("VEGA2", "overtake", obj({{"who", "BLAZE"}}), true) << "\n";
    kl.character("BOX", "a herald", obj({{"lines", obj({{"*", arr({"A very long line about {who} that will not fit.", "Short {who}!"})}})}}));
    std::cout << "box: " << kl.say("BOX", "arrival", obj({{"who", "BLAZE"}}), false, 20) << "\n";
    kl.character("DUEL", "a duelist", obj({}));
    Json first = kl.decide("DUEL", obj({{"hp", 3}}), arr({"guard", "strike"}));
    kl.prepare(10);
    Json later = first;
    for (int i = 0; i < 50 && later == first; i++) { sleep_ms(100); later = kl.decide("DUEL", obj({{"hp", 3}}), arr({"guard", "strike"})); }
    std::cout << "decide repair: " << first.str() << " -> " << later.str() << "\n";
    std::cout << "create count: " << kl.create("villager", obj({{"name", "Ana"}, {"age", arr({18, 80})}}), Json(), 2).dump() << "\n";
    auto fits = [](const Json& plan) -> std::string {
        long x = (long)plan["x"].num();
        return x <= 10 ? std::string() : "no room at x=" + std::to_string(x) + ", the plot ends at 10";
    };
    std::cout << "create check: " << kl.create_checked("a building", obj({{"build", "tower"}, {"x", arr({0, 20})}}), Json(), fits).dump() << "\n";
    std::cout << "create refused twice: " << kl.create_checked("a building", obj({{"build", "tower"}, {"x", arr({0, 20})}}), Json(), fits,
                                                                obj({{"build", "hut"}, {"x", 1}})).dump() << "\n";
    std::vector<Json> parts;
    std::mutex parts_mu;
    Json town = kl.create("the parts of a town", arr({obj({{"kind", arr({"house", "tower"})}, {"x", arr({0, 20})}})}), Json(), 0, false, {},
                          [](const Json& q) { return q["x"].num() <= 10 ? std::string() : std::string("too far east"); }, Json(),
                          [&](const Json& p) { std::lock_guard<std::mutex> lock(parts_mu); parts.push_back(p); });
    std::cout << "create each: " << town.dump() << " " << Json(parts).dump() << "\n";
    kl.character("BUTLER", "a butler", obj({{"tools", obj({{"open_door", obj({{"door", "kitchen"}})}})}, {"offline", "Sir."}}));
    kl.act("BUTLER", obj({{"bell", 1}}));
    std::vector<kinloom::Action> done;
    for (int i = 0; i < 50 && done.empty(); i++) {
        sleep_ms(100);
        done = kl.act_checked("BUTLER", obj({{"bell", 1}}), true, [](const std::string&, const Json& args) {
            return args["door"].str() == "vault" ? std::string("the vault is locked") : std::string();
        });
    }
    std::string acted;
    for (auto& a : done) acted += (acted.empty() ? "" : ", ") + a.tool + " " + a.args.dump();
    std::cout << "act check: " << acted << "\n";
    sleep_ms(100);
    std::string note = "-";
    Json butler = kl.soul("BUTLER", "player");   // kept: items() of a temporary would dangle
    for (auto& m : butler["memories"].items())
        if (m.type() == Json::String && m.str().rfind("The game did not let me", 0) == 0) { note = m.str(); break; }
    std::cout << "act refused: " << note << "\n";
    std::vector<std::string> picks = kl.suggest_checked("BUTLER", {"Ask about the sword", "Leave"}, "player", Json(), [](const std::string& t) {
        return t.find('!') != std::string::npos ? std::string("no shouting") : std::string();
    });
    std::vector<Json> pick_list;
    for (auto& p : picks) pick_list.push_back(Json(p));
    std::cout << "suggest check: " << Json(pick_list).dump() << "\n";
    std::cout << "remark: " << kl.remark("the builder raised a lighthouse on the north shore", "an old fisherman") << "\n";
    std::cout << "remark offline: " << kl.remark("", "", Json(), {"Look at that!"}) << "\n";
    Json before = kl.create("loot", obj({{"item", "sword"}}), Json(), 0, true);
    kl.prepare(10);
    std::cout << "create instant: " << before.dump() << " -> " << kl.create("loot", obj({{"item", "sword"}}), Json(), 0, true).dump() << "\n";
    kl.character("BAKER2", "a warm baker", obj({}));
    kl.character("GUARD2", "a strict guard", obj({}));
    kl.event_with("the player stole bread", obj({{"by", "PLAYER"}, {"seen_by", arr({"BAKER2", "GUARD2"})}}));
    kl.prepare(10);
    std::cout << "impact: " << kl.opinion("BAKER2", "PLAYER") << " " << kl.opinion("GUARD2", "PLAYER") << "\n";
    kinloom::Kinloom claude = make(base, 600, Json(), true);
    claude.character("CLAUDIA", "a poet", obj({{"offline", "..."}}));
    std::cout << "anthropic chat: " << claude.chat("CLAUDIA", "Hi", obj({})) << "\n";
    std::cout << "anthropic create: " << claude.create("loot", obj({{"item", "sword"}})).dump() << "\n";
    kinloom::Kinloom tight = make(base, 2, Json(), false);
    tight.character("TIGHT", "a busy clerk", obj({{"offline", "Later."}}));
    std::string replies;
    for (int i = 0; i < 3; i++) replies += (i ? " | " : "") + tight.chat("TIGHT", "Hi " + std::to_string(i), obj({}));
    std::cout << "budget: " << replies << "\n";
    kinloom::Options ro;
    ro.provider_key = "fake-key";
    ro.provider_url = base;
    ro.provider_model = "fake-model";
    ro.config = obj({{"calls_per_minute", 600}});
    ro.models = obj({{"background", "fake-cheap"}});
    ro.rating = "teen";
    kinloom::Kinloom rated(ro);
    rated.character("RATED", "a gate guard", obj({{"offline", "Move along."}}));
    std::cout << "rated chat: " << rated.chat("RATED", "Hi", obj({})) << "\n";
    std::cout << "rated create: " << rated.create("loot", obj({{"item", "sword"}})).dump() << "\n";
    kl.close();
    claude.close();
    tight.close();
    rated.close();
    std::cout.flush();
}

int main(int argc, char** argv) {
    if (argc < 2) return 2;
    if (std::string(argv[1]) == "deep") { deep(native_url()); return 0; }
    kinloom::Options native;
    native.provider_url = native_url();
    native.provider_key = "fake-key";
    native.provider_model = "fake-model";
    native.voice_url = native_url();
    native.voice_key = "fake-key";
    native.speak_model = "fake-tts";
    native.listen_model = "fake-stt";
    native.voice_name = "custom";
    native.config = obj({{"calls_per_minute", 600}});
    kinloom::Kinloom kl = native_url().empty() ? kinloom::Kinloom(std::string("http://127.0.0.1:") + argv[1]) : kinloom::Kinloom(native);
    kl.character("VEGA", "commentator", obj({{"lines", obj({{"*", arr({"What a race, {who}!"})}})}, {"events", obj({{"overtake", arr({"who", "whom"})}})}}));
    kl.character("THEO", "engineer", obj({{"offline", "Copy."}}));
    kl.character("BLAZE", "rival", obj({{"tools", obj({{"boost", obj({{"seconds", arr({0.5, 2.5})}})}})}}));
    Json facts = obj({{"who", "BLAZE"}, {"whom", "NOVA"}});
    std::string line;
    for (int i = 0; i < 100; i++) {
        line = kl.say("VEGA", "overtake", facts);
        if (line.find("passes") != std::string::npos) break;
        sleep_ms(50);
    }
    std::cout << "say: " << line << "\n";
    std::cout << "chat: " << kl.chat("THEO", "gap?", obj({{"position", 3}})) << "\n";
    Json choices = obj({{"strategy", arr({"attack", "block"})}, {"aggression", arr({0.0, 1.0})}});
    std::string first = kl.decide("BLAZE", obj({{"lap", 1}}), choices).dump();
    std::cout << "decide first: " << first << "\n";
    std::string later = first;
    for (int i = 0; i < 100; i++) {
        sleep_ms(50);
        later = kl.decide("BLAZE", obj({{"lap", 1}}), choices).dump();
        if (later != first) break;
    }
    std::cout << "decide later: " << later << "\n";
    for (int i = 0; i < 100; i++) {
        auto actions = kl.act("BLAZE", obj({{"lap", 1}}));
        if (!actions.empty()) {
            for (auto& a : actions) std::cout << "act later: " << a.tool << " " << a.args.dump() << "\n";
            break;
        }
        sleep_ms(50);
    }
    Json example = obj({{"challenge", "Win clean"}, {"sky", "#ff7a45"}});
    std::cout << "create: " << kl.create("race", example).dump() << "\n";
    kinloom::Kinloom offline = unreachable();
    offline.character("VEGA", "commentator", obj({{"lines", obj({{"*", arr({"What a race, {who}!"})}})}}));
    offline.character("THEO", "engineer", obj({{"offline", "Copy."}}));
    std::cout << "offline say: " << offline.say("VEGA", "overtake", facts) << "\n";
    std::cout << "offline chat: " << offline.chat("THEO", "gap?", obj({{"position", 3}})) << "\n";
    std::cout << "offline decide: " << offline.decide("BLAZE", obj({{"lap", 1}}), choices).dump() << "\n";
    std::cout << "offline create: " << offline.create("race", example).dump() << "\n";

    // Minds and the world (the depth layer).
    Json senses = obj({{"hp", arr({0, 1})}, {"dist", arr({0, 40})}, {"armed", true}, {"enemy", arr({"idle", "alert"})}});
    Json actions = obj({{"charge", obj({{"speed", arr({0.5, 3.0})}})}, {"shoot", obj({{"burst", arr({1, 5})}})}, {"retreat", obj({})}});
    Json rules = obj({{"retreat", arr({"hp low"})}, {"shoot", arr({"armed", "dist below 20"})},
                      {"charge", obj({{"score", 0.5}, {"args", obj({{"speed", "dist high"}})}})}});
    kl.mind("raider", "a cunning raider", senses, actions, rules, 1);
    kl.mind("scout", "a timid scout", obj({{"noise", arr({0, 1})}}), obj({{"run", obj({})}, {"hide", obj({})}}), Json(), 2);
    for (int i = 0; i < 100 && kl.report("raider").is_null(); i++) sleep_ms(50);
    std::cout << "think retreat: " << kl.think("raider", obj({{"hp", 0.1}, {"dist", 30}, {"armed", true}}), "u1").dump() << "\n";
    std::cout << "think shoot: " << kl.think("raider", obj({{"hp", 0.9}, {"dist", 8}, {"armed", true}, {"enemy", "alert"}}), "u2").dump() << "\n";
    std::cout << "think charge: " << kl.think("raider", obj({{"hp", 0.9}, {"dist", 10}, {"armed", false}}), "u3").dump() << "\n";
    std::cout << "think sticky: " << kl.think("raider", obj({{"hp", 0.52}, {"dist", 30}, {"armed", true}}), "u1").action << "\n";
    std::cout << "think fresh: " << kl.think("raider", obj({{"hp", 0.52}, {"dist", 30}, {"armed", true}}), "u4").dump() << "\n";
    std::string learned;
    for (int i = 0; i < 100; i++) {
        learned = kl.think("scout", obj({{"noise", 0.5}}), "s1").action;
        if (learned == "hide") break;
        sleep_ms(100);
    }
    std::cout << "think learned: " << learned << "\n";
    kl.reward("u1", 1);
    kl.reward("u2", 0.5);
    kl.reward("u3", 0);
    kl.flush();
    long long total = 0;
    Json report = kl.report("raider");  // keep it: a range-for over a temporary's field would dangle
    for (auto& v : report["variants"].items()) total += v["rewards"].integer();
    std::cout << "rewards: " << total << "\n";
    kl.character("BAKER", "a warm baker", obj({{"group", "village"}}));
    kl.character("GUARD", "a strict guard", obj({{"group", "guards"}}));
    std::cout << "knows before: " << (kl.knows("GUARD", "theft") ? "true" : "false") << "\n";
    kl.event_with("the player stole bread", obj({{"by", "PLAYER"}, {"seen_by", arr({"BAKER"})}, {"tag", "theft"}, {"impact", -0.8}}));
    std::vector<Json> shared;
    for (int i = 0; i < 50 && shared.empty(); i++) {
        shared = kl.meet("BAKER", "GUARD");
        if (shared.empty()) sleep_ms(100);
    }
    std::string pairs;
    for (auto& x : shared) pairs += (pairs.empty() ? "" : ", ") + x["from"].str() + " -> " + x["to"].str();
    std::cout << "meet: " << pairs << "\n";
    std::cout << "knows after: " << (kl.knows("GUARD", "theft") ? "true" : "false") << "\n";
    std::cout << "opinion: " << kl.opinion("GUARD", "PLAYER") << "\n";
    std::cout << "reputation: " << kl.reputation("PLAYER", "village") << "\n";
    kl.character("MIRA", "", obj({{"soul", obj({{"summary", "a gruff smith"}, {"mood", "wary"}})}, {"offline", "Hm."},
                                  {"tools", obj({{"give", obj({{"item", "wood"}})}})}}));
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    std::cout << "soul chat: " << kl.chat("MIRA", "Nice toy hammer.", obj({}), "Ana") << "\n";
    Json soul;
    for (int i = 0; i < 50; i++) {
        soul = kl.soul("MIRA", "Ana");
        if (soul.has("card") && soul["card"].has("summary") && soul["bonds"].has("Ana")) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    std::cout << "lore: " << kl.lore({"The village is Brookmere.", "The king died last winter."}) << "\n";
    std::cout << "soul: " << soul["mood"]["word"].str() << " " << (soul["bonds"]["Ana"]["feeling"].num() < 0 ? "dislikes" : "likes")
              << " " << soul["card"]["summary"].str() << "\n";
    std::vector<unsigned char> wav = kl.speak("GUARD", "Halt.");
    std::cout << "speak: " << (wav.size() > 4 && std::string(wav.begin(), wav.begin() + 4) == "RIFF" ? "wav" : "?") << "\n";
    std::cout << "listen: " << kl.listen(wav) << "\n";
    offline.mind("raider", "a cunning raider", senses, actions, rules, 1);
    std::cout << "offline think: " << offline.think("raider", obj({{"hp", 0.1}, {"dist", 30}, {"armed", true}}), "u1").dump() << "\n";
    std::cout << "offline think charge: " << offline.think("raider", obj({{"hp", 0.9}, {"dist", 10}, {"armed", false}}), "u3").dump() << "\n";
    std::cout << "offline knows: " << (offline.knows("GUARD", "theft") ? "true" : "false") << "\n";
    offline.character("MIRA", "", obj({{"soul", obj({{"summary", "a gruff smith"}})}, {"offline", "Hm."}}));
    std::cout << "offline soul chat: " << offline.chat("MIRA", "Nice toy hammer.", obj({}), "Ana") << "\n";
    std::cout << "offline speak: " << (offline.speak("GUARD", "Halt.").empty() ? "none" : "audio") << "\n";
    std::string heard = offline.listen(wav);
    std::cout << "offline listen: " << (heard.empty() ? std::string("-") : heard) << "\n";

    // What came back: where it came from, actions with the reply, events described in words.
    Json challenge = obj({{"challenge", obj({{"when", "challenging someone to a battle"}, {"lines", arr({"{other}, fight!"})}})}});
    kl.character("ANA", "a trainer", obj({{"lines", challenge}}));
    std::string said;
    for (int i = 0; i < 50 && said.empty(); i++) {
        said = kl.say("ANA", "challenge", obj({{"other", "BEN"}}));
        if (said.empty()) sleep_ms(100);
    }
    std::cout << "when say: " << said << "\n";
    kl.say("VEGA", "overtake", obj({{"who", "BLAZE"}, {"whom", "NOVA"}}));
    std::cout << "say source: " << kl.source("VEGA") << "\n";
    std::cout << "chat source: " << kl.source("MIRA") << "\n";
    for (auto& a : kl.act("MIRA", obj({}), false)) std::cout << "chat do: " << a.tool << " " << a.args.dump() << "\n";
    offline.character("ANA", "a trainer", obj({{"lines", challenge}}));
    std::cout << "offline when say: " << offline.say("ANA", "challenge", obj({{"other", "BEN"}})) << "\n";
    std::cout << "offline source: " << offline.source("ANA") << "\n";

    // The game's tools, pictures, ready before play.
    auto png = kinloom::base64_decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGP4z8AARAwQCgAf7gP9i18U1AAAAABJRU5ErkJggg==");
    auto join = [](const std::vector<std::string>& v) {
        std::string out;
        for (size_t i = 0; i < v.size(); i++) out += (i ? ", " : "") + v[i];
        return out;
    };
    std::cout << "tools: " << join(kl.tools(obj({{"open_door", obj({{"door", "north"}})}}))) << "\n";
    kl.character("KEEPER", "a gatekeeper", obj({{"tools", arr({"open_door"})}}));
    sleep_ms(100);
    for (int i = 0; i < 100; i++) {
        auto acts = kl.act("KEEPER", obj({}));
        if (!acts.empty()) {
            for (auto& a : acts) std::cout << "tools act: " << a.tool << " " << a.args.dump() << "\n";
            break;
        }
        sleep_ms(50);
    }
    kl.character("LOOK", "a painter", obj({{"offline", "Blind."}}));
    sleep_ms(100);
    std::cout << "chat image: " << kl.chat("LOOK", "What is this?", obj({}), "player", png) << "\n";
    Json race_image = obj({{"challenge", "Win clean"}, {"sky", "#ff7a45"}});
    std::cout << "create image: " << kl.create("race", race_image, obj({}), 0, false, png).dump() << "\n";
    Json ready = kl.prepare(10);
    std::cout << "prepare: " << (ready["ready"].boolean() ? "ready" : "waiting") << " " << (ready["online"].boolean() ? "online" : "offline") << "\n";
    std::cout << "offline tools: " << join(offline.tools(obj({{"open_door", obj({{"door", "north"}})}}))) << "\n";
    offline.character("LOOK", "a painter", obj({{"offline", "Blind."}}));
    std::cout << "offline chat image: " << offline.chat("LOOK", "What is this?", obj({}), "player", png) << "\n";
    std::cout << "offline create image: " << offline.create("race", race_image, obj({}), 0, false, png).dump() << "\n";
    ready = offline.prepare(1);
    std::cout << "offline prepare: " << (ready["ready"].boolean() ? "ready" : "waiting") << " " << (ready["online"].boolean() ? "online" : "offline") << "\n";
    auto t0 = std::chrono::steady_clock::now();
    kinloom::Kinloom gone = unreachable();
    gone.character("THEO", "engineer", obj({{"offline", "Copy."}}));
    bool fast = gone.chat("THEO", "gap?") == "Copy." && gone.chat("THEO", "gap?") == "Copy." && gone.say("THEO", "x").empty();
    auto took = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - t0).count();
    std::cout << "offline fast: " << (fast && took < 1500 ? std::string("yes") : "no (" + std::to_string(took) + " ms)") << "\n";
    // v1: the player's choices, characters talking together, a snapshot, saves
    std::vector<std::string> reply_choices{"Ask about the sword", "Buy something", "Leave"};
    std::cout << "suggest: " << kinloom::native::py::join(kl.suggest("MIRA", reply_choices, "Ana"), " | ") << "\n";
    std::cout << "offline suggest: " << kinloom::native::py::join(offline.suggest("MIRA", reply_choices, "Ana"), " | ") << "\n";
    std::vector<std::string> talk;
    for (auto& x : kl.converse("MIRA", "BAKER", "the smoke", 4)) talk.push_back(x["who"].str() + ": " + x["text"].str());
    std::cout << "converse: " << kinloom::native::py::join(talk, " | ") << "\n";
    std::cout << "offline converse: " << offline.converse("MIRA", "BAKER", "", 4).size() << "\n";
    Json snap = kl.inspect();
    std::cout << "inspect: MIRA " << snap["characters"]["MIRA"]["mood"]["word"].str() << " " << snap["characters"]["MIRA"]["last_words"].str() << "\n";
    kinloom::Kinloom slot2 = kl.with_session("slot2");
    slot2.load(kl.save());
    std::cout << "load: MIRA " << (slot2.opinion("MIRA", "Ana") < 0 ? "dislikes" : "likes") << " Ana\n";
    if (!native_url().empty()) {
        size_t passed = 0, total = 0;
        std::vector<std::string> failures;
        const char* path = std::getenv("KINLOOM_VECTORS");
        kinloom::native::vectors::run_file(path ? path : "", passed, total, failures);
        std::cout << "vectors: " << passed << "/" << total << "\n";
        for (size_t i = 0; i < failures.size() && i < 12; i++) std::cerr << failures[i] << "\n";
        kl.close();
    }
    std::cout.flush();
    return 0;
}
