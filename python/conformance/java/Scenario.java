// Conformance scenario for the Java client: java Scenario <port>
import static kinloom.Kinloom.list;
import static kinloom.Kinloom.map;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import kinloom.Kinloom;

public class Scenario {
    static String nativeUrl = System.getenv("KINLOOM_NATIVE");

    /** Native mode (python conformance/native.py): the SDK calls the fake model itself; no kinloom serve. */
    static Kinloom unreachable() { return nativeUrl != null ? Kinloom.offline() : new Kinloom("http://127.0.0.1:9", "default", ""); }

    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("deep")) { deep(nativeUrl); return; }
        Kinloom kl;
        if (nativeUrl != null) {
            Kinloom.Options o = new Kinloom.Options();
            o.providerUrl = nativeUrl;
            o.providerKey = "fake-key";
            o.providerModel = "fake-model";
            o.voiceUrl = nativeUrl;
            o.voiceKey = "fake-key";
            o.speakModel = "fake-tts";
            o.listenModel = "fake-stt";
            o.voiceName = "custom";
            o.config = map("calls_per_minute", 600L);
            kl = new Kinloom(o);
        } else kl = new Kinloom("http://127.0.0.1:" + args[0], "default", "");
        kl.character("VEGA", "commentator", map("lines", map("*", list("What a race, {who}!")), "events", map("overtake", list("who", "whom"))));
        kl.character("THEO", "engineer", map("offline", "Copy."));
        kl.character("BLAZE", "rival", map("tools", map("boost", map("seconds", list(0.5, 2.5)))));
        Map<String, Object> facts = map("who", "BLAZE", "whom", "NOVA");
        String line = "";
        for (int i = 0; i < 100; i++) {
            line = kl.say("VEGA", "overtake", facts);
            if (line.contains("passes")) break;
            Thread.sleep(50);
        }
        System.out.println("say: " + line);
        System.out.println("chat: " + kl.chat("THEO", "gap?", map("position", 3)));
        Map<String, Object> choices = map("strategy", list("attack", "block"), "aggression", list(0.0, 1.0));
        String first = Kinloom.toJson(kl.decide("BLAZE", map("lap", 1), choices));
        System.out.println("decide first: " + first);
        String later = first;
        for (int i = 0; i < 100; i++) {
            Thread.sleep(50);
            later = Kinloom.toJson(kl.decide("BLAZE", map("lap", 1), choices));
            if (!later.equals(first)) break;
        }
        System.out.println("decide later: " + later);
        for (int i = 0; i < 100; i++) {
            List<Kinloom.Action> actions = kl.act("BLAZE", map("lap", 1));
            if (!actions.isEmpty()) {
                for (Kinloom.Action a : actions) System.out.println("act later: " + a.tool + " " + Kinloom.toJson(a.args));
                break;
            }
            Thread.sleep(50);
        }
        System.out.println("create: " + Kinloom.toJson(kl.create("race", map("challenge", "Win clean", "sky", "#ff7a45"))));
        Kinloom offline = unreachable();
        offline.character("VEGA", "commentator", map("lines", map("*", list("What a race, {who}!"))));
        offline.character("THEO", "engineer", map("offline", "Copy."));
        System.out.println("offline say: " + offline.say("VEGA", "overtake", facts));
        System.out.println("offline chat: " + offline.chat("THEO", "gap?", map("position", 3)));
        System.out.println("offline decide: " + Kinloom.toJson(offline.decide("BLAZE", map("lap", 1), choices)));
        System.out.println("offline create: " + Kinloom.toJson(offline.create("race", map("challenge", "Win clean", "sky", "#ff7a45"))));

        // Minds and the world (the depth layer).
        Map<String, Object> senses = map("hp", list(0, 1), "dist", list(0, 40), "armed", true, "enemy", list("idle", "alert"));
        Map<String, Object> mindActions = map("charge", map("speed", list(0.5, 3.0)), "shoot", map("burst", list(1, 5)), "retreat", map());
        Map<String, Object> rules = map("retreat", list("hp low"), "shoot", list("armed", "dist below 20"),
                                        "charge", map("score", 0.5, "args", map("speed", "dist high")));
        kl.mind("raider", "a cunning raider", senses, mindActions, rules, 1, 30);
        kl.mind("scout", "a timid scout", map("noise", list(0, 1)), map("run", map(), "hide", map()), null, 2, 30);
        for (int i = 0; i < 100 && kl.report("raider") == null; i++) Thread.sleep(50);
        System.out.println("think retreat: " + kl.think("raider", map("hp", 0.1, "dist", 30, "armed", true), "u1").toJson());
        System.out.println("think shoot: " + kl.think("raider", map("hp", 0.9, "dist", 8, "armed", true, "enemy", "alert"), "u2").toJson());
        System.out.println("think charge: " + kl.think("raider", map("hp", 0.9, "dist", 10, "armed", false), "u3").toJson());
        System.out.println("think sticky: " + kl.think("raider", map("hp", 0.52, "dist", 30, "armed", true), "u1").action);
        System.out.println("think fresh: " + kl.think("raider", map("hp", 0.52, "dist", 30, "armed", true), "u4").toJson());
        String learned = "";
        for (int i = 0; i < 100; i++) {
            learned = kl.think("scout", map("noise", 0.5), "s1").action;
            if ("hide".equals(learned)) break;
            Thread.sleep(100);
        }
        System.out.println("think learned: " + learned);
        kl.reward("u1", 1);
        kl.reward("u2", 0.5);
        kl.reward("u3", 0);
        kl.flush();
        long total = 0;
        for (Object v : (List<Object>) kl.report("raider").get("variants")) total += (long) Kinloom.num(((Map<String, Object>) v).get("rewards"));
        System.out.println("rewards: " + total);
        kl.character("BAKER", "a warm baker", map("group", "village"));
        kl.character("GUARD", "a strict guard", map("group", "guards"));
        System.out.println("knows before: " + kl.knows("GUARD", "theft"));
        kl.event("the player stole bread", map("by", "PLAYER", "seen_by", list("BAKER"), "tag", "theft", "impact", -0.8));
        List<Object> shared = new java.util.ArrayList<>();
        for (int i = 0; i < 50 && shared.isEmpty(); i++) {
            shared = kl.meet("BAKER", "GUARD");
            if (shared.isEmpty()) Thread.sleep(100);
        }
        StringBuilder pairs = new StringBuilder();
        for (Object x : shared) {
            if (pairs.length() > 0) pairs.append(", ");
            pairs.append(((Map<String, Object>) x).get("from")).append(" -> ").append(((Map<String, Object>) x).get("to"));
        }
        System.out.println("meet: " + pairs);
        System.out.println("knows after: " + kl.knows("GUARD", "theft"));
        System.out.println("opinion: " + kl.opinion("GUARD", "PLAYER"));
        System.out.println("reputation: " + kl.reputation("PLAYER", "village"));
        kl.character("MIRA", "", map("soul", map("summary", "a gruff smith", "mood", "wary"), "offline", "Hm.",
                "tools", map("give", map("item", "wood"))));
        Thread.sleep(100);
        System.out.println("soul chat: " + kl.chat("MIRA", "Nice toy hammer.", map(), "Ana"));
        Map<String, Object> soul = null;
        for (int i = 0; i < 50; i++) {
            soul = kl.soul("MIRA", "Ana");
            if (soul != null && soul.get("card") instanceof Map && ((Map<String, Object>) soul.get("bonds")).containsKey("Ana")) break;
            Thread.sleep(100);
        }
        Map<String, Object> bond = (Map<String, Object>) ((Map<String, Object>) soul.get("bonds")).get("Ana");
        System.out.println("lore: " + kl.lore(java.util.Arrays.asList("The village is Brookmere.", "The king died last winter.")));
        System.out.println("soul: " + ((Map<String, Object>) soul.get("mood")).get("word") + " "
                + (((Number) bond.get("feeling")).doubleValue() < 0 ? "dislikes" : "likes") + " "
                + ((Map<String, Object>) soul.get("card")).get("summary"));
        byte[] wav = kl.speak("GUARD", "Halt.");
        System.out.println("speak: " + (wav != null && new String(wav, 0, 4, java.nio.charset.StandardCharsets.US_ASCII).equals("RIFF") ? "wav" : "?"));
        System.out.println("listen: " + kl.listen(wav));
        offline.mind("raider", "a cunning raider", senses, mindActions, rules, 1, 30);
        System.out.println("offline think: " + offline.think("raider", map("hp", 0.1, "dist", 30, "armed", true), "u1").toJson());
        System.out.println("offline think charge: " + offline.think("raider", map("hp", 0.9, "dist", 10, "armed", false), "u3").toJson());
        System.out.println("offline knows: " + offline.knows("GUARD", "theft"));
        offline.character("MIRA", "", map("soul", map("summary", "a gruff smith"), "offline", "Hm."));
        System.out.println("offline soul chat: " + offline.chat("MIRA", "Nice toy hammer.", map(), "Ana"));
        System.out.println("offline speak: " + (offline.speak("GUARD", "Halt.") == null ? "none" : "audio"));
        String heard = offline.listen(wav);
        System.out.println("offline listen: " + (heard.isEmpty() ? "-" : heard));

        // What came back: where it came from, actions with the reply, events described in words.
        Map<String, Object> challenge = map("challenge", map("when", "challenging someone to a battle", "lines", list("{other}, fight!")));
        kl.character("ANA", "a trainer", map("lines", challenge));
        String said = "";
        for (int i = 0; i < 50 && said.isEmpty(); i++) {
            said = kl.say("ANA", "challenge", map("other", "BEN"));
            if (said.isEmpty()) Thread.sleep(100);
        }
        System.out.println("when say: " + said);
        kl.say("VEGA", "overtake", facts);
        System.out.println("say source: " + kl.source("VEGA"));
        System.out.println("chat source: " + kl.source("MIRA"));
        for (Kinloom.Action a : kl.act("MIRA", null, false)) System.out.println("chat do: " + a.tool + " " + Kinloom.toJson(a.args));
        offline.character("ANA", "a trainer", map("lines", challenge));
        System.out.println("offline when say: " + offline.say("ANA", "challenge", map("other", "BEN")));
        System.out.println("offline source: " + offline.source("ANA"));

        // The game's tools, pictures, ready before play.
        byte[] png = java.util.Base64.getDecoder().decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGP4z8AARAwQCgAf7gP9i18U1AAAAABJRU5ErkJggg==");
        System.out.println("tools: " + String.join(", ", kl.tools(map("open_door", map("door", "north")))));
        kl.character("KEEPER", "a gatekeeper", map("tools", list("open_door")));
        Thread.sleep(100);
        for (int i = 0; i < 100; i++) {
            java.util.List<Kinloom.Action> acts = kl.act("KEEPER", null);
            if (!acts.isEmpty()) {
                for (Kinloom.Action a : acts) System.out.println("tools act: " + a.tool + " " + Kinloom.toJson(a.args));
                break;
            }
            Thread.sleep(50);
        }
        kl.character("LOOK", "a painter", map("offline", "Blind."));
        Thread.sleep(100);
        System.out.println("chat image: " + kl.chat("LOOK", "What is this?", map(), "player", png));
        System.out.println("create image: " + Kinloom.toJson(kl.create("race", map("challenge", "Win clean", "sky", "#ff7a45"), null, 0, false, png)));
        Map<String, Object> ready = kl.prepare(10);
        System.out.println("prepare: " + (Boolean.TRUE.equals(ready.get("ready")) ? "ready" : "waiting") + " " + (Boolean.TRUE.equals(ready.get("online")) ? "online" : "offline"));
        System.out.println("offline tools: " + String.join(", ", offline.tools(map("open_door", map("door", "north")))));
        offline.character("LOOK", "a painter", map("offline", "Blind."));
        System.out.println("offline chat image: " + offline.chat("LOOK", "What is this?", map(), "player", png));
        System.out.println("offline create image: " + Kinloom.toJson(offline.create("race", map("challenge", "Win clean", "sky", "#ff7a45"), null, 0, false, png)));
        ready = offline.prepare(1);
        System.out.println("offline prepare: " + (Boolean.TRUE.equals(ready.get("ready")) ? "ready" : "waiting") + " " + (Boolean.TRUE.equals(ready.get("online")) ? "online" : "offline"));
        long t0 = System.currentTimeMillis();
        Kinloom gone = unreachable();
        gone.character("THEO", "engineer", map("offline", "Copy."));
        boolean fast = gone.chat("THEO", "gap?", map()).equals("Copy.") && gone.chat("THEO", "gap?", map()).equals("Copy.")
                && gone.say("THEO", "x", map()).isEmpty();
        long took = System.currentTimeMillis() - t0;
        System.out.println("offline fast: " + (fast && took < 1500 ? "yes" : "no (" + took + " ms)"));
        // v1: the player's choices, characters talking together, a snapshot, saves
        List<String> replyChoices = java.util.Arrays.asList("Ask about the sword", "Buy something", "Leave");
        System.out.println("suggest: " + String.join(" | ", kl.suggest("MIRA", replyChoices, "Ana")));
        System.out.println("offline suggest: " + String.join(" | ", offline.suggest("MIRA", replyChoices, "Ana")));
        List<String> talkLines = new java.util.ArrayList<>();
        for (Map<String, Object> x : kl.converse("MIRA", "BAKER", "the smoke")) talkLines.add(x.get("who") + ": " + x.get("text"));
        System.out.println("converse: " + String.join(" | ", talkLines));
        System.out.println("offline converse: " + offline.converse("MIRA", "BAKER", "").size());
        @SuppressWarnings("unchecked")
        Map<String, Object> snap = (Map<String, Object>) ((Map<String, Object>) kl.inspect().get("characters")).get("MIRA");
        @SuppressWarnings("unchecked")
        Map<String, Object> snapMood = (Map<String, Object>) snap.get("mood");
        System.out.println("inspect: MIRA " + snapMood.get("word") + " " + snap.get("last_words"));
        Kinloom slot2 = kl.withSession("slot2");
        slot2.load(kl.save());
        System.out.println("load: MIRA " + (slot2.opinion("MIRA", "Ana") < 0 ? "dislikes" : "likes") + " Ana");
        if (nativeUrl != null) {
            Object[] v = Kinloom.Vectors.runFile(System.getenv("KINLOOM_VECTORS"));
            System.out.println("vectors: " + v[0] + "/" + v[1]);
            @SuppressWarnings("unchecked")
            List<String> failures = (List<String>) v[2];
            for (String f : failures.subList(0, Math.min(12, failures.size()))) System.err.println(f);
            kl.close();
        }
        System.exit(0);
    }

    static Kinloom make(String base, long calls, List<Object> banned, boolean anthropic) {
        Kinloom.Options o = new Kinloom.Options();
        if (anthropic) {
            o.providerKind = "anthropic";
            o.providerUrl = base.substring(0, base.length() - 3);
            o.providerModel = "claude-test";
        } else {
            o.providerUrl = base;
            o.providerModel = "fake-model";
        }
        o.providerKey = "fake-key";
        o.config = map("calls_per_minute", calls);
        if (banned != null) o.config.put("banned_words", banned);
        return new Kinloom(o);
    }

    static Kinloom make(String base, long calls, List<Object> banned, boolean anthropic, Map<String, Object> models, String rating) {
        Kinloom.Options o = new Kinloom.Options();
        o.providerUrl = base;
        o.providerModel = "fake-model";
        o.providerKey = "fake-key";
        o.config = map("calls_per_minute", calls);
        o.models = models;
        o.rating = rating;
        return new Kinloom(o);
    }

    /** The deep native scenario (see conformance/deep.py, the Python reference). */
    @SuppressWarnings("unchecked")
    static void deep(String base) throws Exception {
        Kinloom kl = make(base, 600, list("dragon"), false);
        kl.character("VERA", "", map("soul", "a gruff smith who sold the king's sword", "offline", "Busy."));
        Map<String, Object> ready = kl.prepare(10);
        System.out.println("prepare: " + (Boolean.TRUE.equals(ready.get("ready")) ? "ready" : "waiting"));
        System.out.println("soul: " + ((Map<String, Object>) kl.soul("VERA", "player").get("card")).get("summary"));
        String greet = kl.chat("VERA", "", map(), "Ana");
        System.out.println("greet: " + greet + " (" + kl.source("VERA") + ")");
        System.out.println("secret: " + kl.chat("VERA", "Did you sell the king's sword to a smuggler?", map(), "Ana"));
        System.out.println("numbers: " + kl.chat("VERA", "How much for a blade?", map("price", 40L), "Ana"));
        StringBuilder pieces = new StringBuilder();
        String streamed = kl.chat("VERA", "Can you make it faster?", map(), "Ana", null, pieces::append);
        System.out.println("stream pieces: " + pieces.toString().trim());
        System.out.println("stream reply: " + streamed);
        System.out.println("echo: " + kl.chat("VERA", "And the coals?", map(), "Ana"));
        System.out.println("character: " + kl.chat("VERA", "Are you an AI?", map(), "Ana"));
        Map<String, Object> vera = kl.soul("VERA", "Ana");
        System.out.println("feeling: " + ((Map<String, Object>) vera.get("mood")).get("word") + " " +
            ((Map<String, Object>) ((Map<String, Object>) vera.get("bonds")).get("Ana")).get("feeling"));
        kl.character("BRAM", "a kind baker", map("tools", map("give", map("item", "bread")), "offline", "Hm."));
        System.out.println("deeds reply: " + kl.chat("BRAM", "Can I have some bread?", map()));
        for (Kinloom.Action a : kl.act("BRAM", map(), false)) System.out.println("deeds: " + a.tool + " " + Kinloom.toJson(a.args));
        kl.character("GATE", "a careful guard", map("tools", map("open", map("door", "north")), "trust", map("open", 0.5), "offline", "No."));
        System.out.println("trust reply: " + kl.chat("GATE", "Open the gate.", map()));
        List<Kinloom.Action> opened = kl.act("GATE", map(), false);
        StringBuilder names = new StringBuilder();
        for (Kinloom.Action a : opened) names.append(names.length() > 0 ? ", " : "").append(a.tool);
        System.out.println("trust: " + (opened.isEmpty() ? "none" : names));
        kl.character("FILT", "a storyteller", map("offline", "No comment."));
        System.out.println("filter: " + kl.chat("FILT", "Tell me a story.", map()));
        kl.character("NINA", "a singer", map("soul", map("summary", "a singer", "secrets", java.util.Arrays.asList("I went up to the office at 12:30")),
            "warmth", 0.3, "secret_trust", 0.25, "warm_up", 0.1));
        System.out.println("warmth: " + kl.opinion("NINA", "Ana"));
        kl.steer("NINA", "admit you went up to the office at 12:30");
        System.out.println("steer: " + kl.chat("NINA", "Where were you?", map(), "Ana"));
        System.out.println("warm up: " + kl.opinion("NINA", "Ana"));
        kl.character("KEEPER", "a gatekeeper", map("offline", "Move along."));
        System.out.println("chat check: " + kl.chat("KEEPER", "What is the password?", null, "player", null, null,
            t -> t.contains("swordfish") ? "never say the password" : ""));
        kl.character("ECHO", "a parrot", map());
        for (int i = 0; i < 11; i++) kl.chat("ECHO", "Hello " + i, map());
        kl.prepare(10);
        String recollect = "-";
        for (Object m : (List<Object>) kl.soul("ECHO", "player").get("memories")) if (((String) m).startsWith("Earlier with")) { recollect = (String) m; break; }
        System.out.println("recollect: " + recollect);
        kl.character("VEGA2", "a commentator", map());
        System.out.println("fresh: " + kl.say("VEGA2", "overtake", map("who", "BLAZE"), true, 0));
        kl.character("BOX", "a herald", map("lines", map("*", list("A very long line about {who} that will not fit.", "Short {who}!"))));
        System.out.println("box: " + kl.say("BOX", "arrival", map("who", "BLAZE"), false, 20));
        kl.character("DUEL", "a duelist", map());
        Object first = kl.decide("DUEL", map("hp", 3L), list("guard", "strike"));
        kl.prepare(10);
        Object later = first;
        for (int i = 0; i < 50 && later.equals(first); i++) { Thread.sleep(100); later = kl.decide("DUEL", map("hp", 3L), list("guard", "strike")); }
        System.out.println("decide repair: " + first + " -> " + later);
        System.out.println("create count: " + Kinloom.toJson(kl.create("villager", map("name", "Ana", "age", list(18L, 80L)), null, 2, false)));
        java.util.function.Function<Object, String> fits = plan -> ((Number) ((Map<?, ?>) plan).get("x")).longValue() <= 10 ? "" : "no room at x=" + ((Map<?, ?>) plan).get("x") + ", the plot ends at 10";
        System.out.println("create check: " + Kinloom.toJson(kl.create("a building", map("build", "tower", "x", list(0L, 20L)), null, fits, null)));
        System.out.println("create refused twice: " + Kinloom.toJson(kl.create("a building", map("build", "tower", "x", list(0L, 20L)), null, fits, map("build", "hut", "x", 1L))));
        List<Object> parts = new ArrayList<>();
        Object town = kl.create("the parts of a town", list(map("kind", list("house", "tower"), "x", list(0L, 20L))), null, 0, false, null,
            q -> ((Number) ((Map<?, ?>) q).get("x")).longValue() <= 10 ? "" : "too far east", null, parts::add);
        System.out.println("create each: " + Kinloom.toJson(town) + " " + Kinloom.toJson(parts));
        kl.character("BUTLER", "a butler", map("tools", map("open_door", map("door", "kitchen")), "offline", "Sir."));
        kl.act("BUTLER", map("bell", 1L));
        List<Kinloom.Action> done = new ArrayList<>();
        for (int i = 0; i < 50 && done.isEmpty(); i++) {
            Thread.sleep(100);
            done = kl.act("BUTLER", map("bell", 1L), true, (tool, args) -> "vault".equals(args.get("door")) ? "the vault is locked" : "");
        }
        List<String> acted = new ArrayList<>();
        for (Kinloom.Action a : done) acted.add(a.tool + " " + Kinloom.toJson(a.args));
        System.out.println("act check: " + String.join(", ", acted));
        Thread.sleep(100);
        String refusedNote = "-";
        for (Object m : (List<Object>) kl.soul("BUTLER", "player").get("memories")) if (((String) m).startsWith("The game did not let me")) { refusedNote = (String) m; break; }
        System.out.println("act refused: " + refusedNote);
        System.out.println("suggest check: " + Kinloom.toJson(kl.suggest("BUTLER", Arrays.asList("Ask about the sword", "Leave"), "player", null,
            t -> t.contains("!") ? "no shouting" : "")));
        System.out.println("remark: " + kl.remark("the builder raised a lighthouse on the north shore", "an old fisherman", null, null, 0));
        System.out.println("remark offline: " + kl.remark("", "", null, Arrays.asList("Look at that!"), 0));
        Object before = kl.create("loot", map("item", "sword"), null, 0, true);
        kl.prepare(10);
        System.out.println("create instant: " + Kinloom.toJson(before) + " -> " + Kinloom.toJson(kl.create("loot", map("item", "sword"), null, 0, true)));
        kl.character("BAKER2", "a warm baker", map());
        kl.character("GUARD2", "a strict guard", map());
        kl.event("the player stole bread", map("by", "PLAYER", "seen_by", list("BAKER2", "GUARD2")));
        kl.prepare(10);
        System.out.println("impact: " + kl.opinion("BAKER2", "PLAYER") + " " + kl.opinion("GUARD2", "PLAYER"));
        Kinloom claude = make(base, 600, null, true);
        claude.character("CLAUDIA", "a poet", map("offline", "..."));
        System.out.println("anthropic chat: " + claude.chat("CLAUDIA", "Hi", map()));
        System.out.println("anthropic create: " + Kinloom.toJson(claude.create("loot", map("item", "sword"))));
        Kinloom tight = make(base, 2, null, false);
        tight.character("TIGHT", "a busy clerk", map("offline", "Later."));
        List<String> replies = new java.util.ArrayList<>();
        for (int i = 0; i < 3; i++) replies.add(tight.chat("TIGHT", "Hi " + i, map()));
        System.out.println("budget: " + String.join(" | ", replies));
        Kinloom rated = make(base, 600, null, false, map("background", "fake-cheap"), "teen");
        rated.character("RATED", "a gate guard", map("offline", "Move along."));
        System.out.println("rated chat: " + rated.chat("RATED", "Hi", map()));
        System.out.println("rated create: " + Kinloom.toJson(rated.create("loot", map("item", "sword"))));
        for (Kinloom k : new Kinloom[] {kl, claude, tight, rated}) k.close();
        System.exit(0);
    }
}
