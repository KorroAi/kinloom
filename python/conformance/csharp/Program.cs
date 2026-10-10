// Conformance scenario for the C# client: dotnet run -- <port>
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Kinloom;

static class Program
{
    static Dictionary<string, object> D(params (string k, object v)[] items) => items.ToDictionary(x => x.k, x => x.v);
    static List<object> L(params object[] items) => items.ToList();

    static string J(object? v)
    {
        switch (v)
        {
            case IList list when !(v is string): return "[" + string.Join(",", list.Cast<object?>().Select(J)) + "]";
            case IDictionary<string, object> m: return "{" + string.Join(",", m.OrderBy(p => p.Key, StringComparer.Ordinal).Select(p => Json.Write(p.Key) + ":" + J(p.Value))) + "}";
            default: return Json.Write(v);
        }
    }

    static async Task Main(string[] args)
    {
        // Native mode (python conformance/native.py): the SDK calls the fake model itself; no kinloom serve.
        var native = Environment.GetEnvironmentVariable("KINLOOM_NATIVE");
        if (args.Length > 0 && args[0] == "deep") { await Deep(native!); return; }
        var host = native == null ? null : new KinloomClient(new KinloomOptions
        {
            Provider = new ProviderSpec { Url = native, Key = "fake-key", Model = "fake-model" },
            Voice = new VoiceSpec { Url = native, Key = "fake-key", SpeakModel = "fake-tts", ListenModel = "fake-stt", Name = "custom" },
            Config = D(("calls_per_minute", 600L)),
        });
        KinloomClient Unreachable() => native != null ? new KinloomClient(new KinloomOptions { Offline = true }) : new KinloomClient("http://127.0.0.1:9");
        var kl = host ?? new KinloomClient("http://127.0.0.1:" + args[0]);
        kl.Character("VEGA", "commentator", D(("lines", D(("*", L("What a race, {who}!")))), ("events", D(("overtake", L("who", "whom"))))));
        kl.Character("THEO", "engineer", D(("offline", "Copy.")));
        kl.Character("BLAZE", "rival", D(("tools", D(("boost", D(("seconds", L(0.5, 2.5))))))));
        var facts = D(("who", "BLAZE"), ("whom", "NOVA"));
        string line = "";
        for (int i = 0; i < 100; i++)
        {
            line = await kl.Say("VEGA", "overtake", facts);
            if (line.Contains("passes")) break;
            await Task.Delay(50);
        }
        Console.WriteLine("say: " + line);
        Console.WriteLine("chat: " + await kl.Chat("THEO", "gap?", D(("position", 3))));
        var choices = D(("strategy", L("attack", "block")), ("aggression", L(0.0, 1.0)));
        string first = J(kl.Decide("BLAZE", D(("lap", 1)), choices));
        Console.WriteLine("decide first: " + first);
        string later = first;
        for (int i = 0; i < 100; i++)
        {
            await Task.Delay(50);
            later = J(kl.Decide("BLAZE", D(("lap", 1)), choices));
            if (later != first) break;
        }
        Console.WriteLine("decide later: " + later);
        for (int i = 0; i < 100; i++)
        {
            var actions = kl.Act("BLAZE", D(("lap", 1)));
            if (actions.Count > 0)
            {
                foreach (var a in actions) Console.WriteLine("act later: " + a.Tool + " " + J(a.Args));
                break;
            }
            await Task.Delay(50);
        }
        Console.WriteLine("create: " + J(await kl.Create("race", D(("challenge", "Win clean"), ("sky", "#ff7a45")))));
        var offline = Unreachable();
        offline.Character("VEGA", "commentator", D(("lines", D(("*", L("What a race, {who}!"))))));
        offline.Character("THEO", "engineer", D(("offline", "Copy.")));
        Console.WriteLine("offline say: " + await offline.Say("VEGA", "overtake", facts));
        Console.WriteLine("offline chat: " + await offline.Chat("THEO", "gap?", D(("position", 3))));
        Console.WriteLine("offline decide: " + J(offline.Decide("BLAZE", D(("lap", 1)), choices)));
        Console.WriteLine("offline create: " + J(await offline.Create("race", D(("challenge", "Win clean"), ("sky", "#ff7a45")))));
        // An anonymous object is the object it reads as (it was sent as its text before), arrays are lists. A Unity
        // IL2CPP build with managed stripping "High" removes its properties: then a clear error, never an empty object.
        var anonymous = new { name = "Glowcap", value = new[] { 1, 50 }, mood = new[] { "calm", "angry" }, at = new { x = 0.5 } };
        string? written = null;
        try { written = Json.Write(anonymous); }
        catch (ArgumentException e) when (e.Message.Contains("stripped")) { }   // stripped (even one nested object): told
        if (written != null)
        {
            if (Json.Write(anonymous) != "{\"name\":\"Glowcap\",\"value\":[1,50],\"mood\":[\"calm\",\"angry\"],\"at\":{\"x\":0.5}}")
                throw new Exception("anonymous object written as " + Json.Write(anonymous));
            var made = J(await offline.Create("an item", anonymous, count: 2));
            if (made != "[{\"at\":{\"x\":0.5},\"mood\":\"calm\",\"name\":\"Glowcap\",\"value\":26},{\"at\":{\"x\":0.5},\"mood\":\"calm\",\"name\":\"Glowcap\",\"value\":26}]")
                throw new Exception("anonymous example made " + made);
            if (J(await offline.Create("a hut", new { x = new[] { 0, 40 } }, offline: new { x = 3 })) != "{\"x\":3}")
                throw new Exception("anonymous offline answer");
        }
        // An example with no shape fails at once, with count too (as in Python), never a list of empty answers.
        foreach (var bad in new object[] { D(), L(), new object() })
        {
            bool threw = false;
            try { await offline.Create("an item", bad, count: 2); } catch (ArgumentException) { threw = true; }
            if (!threw) throw new Exception("an example with no shape was accepted with count");
        }

        // Minds and the world (the depth layer).
        var senses = D(("hp", L(0, 1)), ("dist", L(0, 40)), ("armed", true), ("enemy", L("idle", "alert")));
        var mindActions = D(("charge", D(("speed", L(0.5, 3.0)))), ("shoot", D(("burst", L(1, 5)))), ("retreat", D()));
        var rules = D(("retreat", L("hp low")), ("shoot", L("armed", "dist below 20")), ("charge", D(("score", 0.5), ("args", D(("speed", "dist high"))))));
        kl.Mind("raider", "a cunning raider", senses, mindActions, rules, 1);
        kl.Mind("scout", "a timid scout", D(("noise", L(0, 1))), D(("run", D()), ("hide", D())), null, 2);
        for (int i = 0; i < 100 && await kl.Report("raider") == null; i++) await Task.Delay(50);
        Console.WriteLine("think retreat: " + T(kl.Think("raider", D(("hp", 0.1), ("dist", 30), ("armed", true)), "u1")));
        Console.WriteLine("think shoot: " + T(kl.Think("raider", D(("hp", 0.9), ("dist", 8), ("armed", true), ("enemy", "alert")), "u2")));
        Console.WriteLine("think charge: " + T(kl.Think("raider", D(("hp", 0.9), ("dist", 10), ("armed", false)), "u3")));
        Console.WriteLine("think sticky: " + kl.Think("raider", D(("hp", 0.52), ("dist", 30), ("armed", true)), "u1").Action);
        Console.WriteLine("think fresh: " + T(kl.Think("raider", D(("hp", 0.52), ("dist", 30), ("armed", true)), "u4")));
        string learned = "";
        for (int i = 0; i < 100; i++)
        {
            learned = kl.Think("scout", D(("noise", 0.5)), "s1").Action ?? "";
            if (learned == "hide") break;
            await Task.Delay(100);
        }
        Console.WriteLine("think learned: " + learned);
        kl.Reward("u1", 1);
        kl.Reward("u2", 0.5);
        kl.Reward("u3", 0);
        await kl.Flush();
        var report = await kl.Report("raider");
        long total = ((List<object>)report!["variants"]).Sum(v => (long)((Dictionary<string, object>)v)["rewards"]);
        Console.WriteLine("rewards: " + total);
        kl.Character("BAKER", "a warm baker", D(("group", "village")));
        kl.Character("GUARD", "a strict guard", D(("group", "guards")));
        Console.WriteLine("knows before: " + (await kl.Knows("GUARD", "theft") ? "true" : "false"));
        await kl.Event("the player stole bread", by: "PLAYER", seenBy: new[] { "BAKER" }, tag: "theft", impact: -0.8);
        var shared = new List<object>();
        for (int i = 0; i < 50 && shared.Count == 0; i++)
        {
            shared = await kl.Meet("BAKER", "GUARD");
            if (shared.Count == 0) await Task.Delay(100);
        }
        Console.WriteLine("meet: " + string.Join(", ", shared.Select(x => (string)((Dictionary<string, object>)x)["from"] + " -> " + (string)((Dictionary<string, object>)x)["to"])));
        Console.WriteLine("knows after: " + (await kl.Knows("GUARD", "theft") ? "true" : "false"));
        Console.WriteLine("opinion: " + (await kl.Opinion("GUARD", "PLAYER")).ToString(System.Globalization.CultureInfo.InvariantCulture));
        Console.WriteLine("reputation: " + (await kl.Reputation("PLAYER", "village")).ToString(System.Globalization.CultureInfo.InvariantCulture));
        kl.Character("MIRA", "", D(("soul", D(("summary", "a gruff smith"), ("mood", "wary"))), ("offline", "Hm."), ("tools", D(("give", D(("item", "wood")))))));
        await Task.Delay(100);
        Console.WriteLine("soul chat: " + await kl.Chat("MIRA", "Nice toy hammer.", null, "Ana"));
        Dictionary<string, object>? soul = null;
        for (int i = 0; i < 50; i++)
        {
            soul = await kl.Soul("MIRA", "Ana");
            if (soul != null && soul["card"] is Dictionary<string, object> && ((Dictionary<string, object>)soul["bonds"]).ContainsKey("Ana")) break;
            await Task.Delay(100);
        }
        var bond = (Dictionary<string, object>)((Dictionary<string, object>)soul!["bonds"])["Ana"];
        Console.WriteLine("lore: " + await kl.Lore(new[] { "The village is Brookmere.", "The king died last winter." }));
        Console.WriteLine("soul: " + ((Dictionary<string, object>)soul["mood"])["word"] + " " + (Convert.ToDouble(bond["feeling"]) < 0 ? "dislikes" : "likes")
                          + " " + ((Dictionary<string, object>)soul["card"])["summary"]);
        var wav = await kl.Speak("GUARD", "Halt.");
        Console.WriteLine("speak: " + (wav != null && System.Text.Encoding.ASCII.GetString(wav, 0, 4) == "RIFF"
                                        && KinloomClient.WavSamples(wav, out _, out _).Length > 0 ? "wav" : "?"));
        Console.WriteLine("listen: " + await kl.Listen(wav));
        offline.Mind("raider", "a cunning raider", senses, mindActions, rules, 1);
        Console.WriteLine("offline think: " + T(offline.Think("raider", D(("hp", 0.1), ("dist", 30), ("armed", true)), "u1")));
        Console.WriteLine("offline think charge: " + T(offline.Think("raider", D(("hp", 0.9), ("dist", 10), ("armed", false)), "u3")));
        Console.WriteLine("offline knows: " + (await offline.Knows("GUARD", "theft") ? "true" : "false"));
        offline.Character("MIRA", "", D(("soul", D(("summary", "a gruff smith"))), ("offline", "Hm.")));
        Console.WriteLine("offline soul chat: " + await offline.Chat("MIRA", "Nice toy hammer.", null, "Ana"));
        Console.WriteLine("offline speak: " + (await offline.Speak("GUARD", "Halt.") == null ? "none" : "audio"));
        var heard = await offline.Listen(wav);
        Console.WriteLine("offline listen: " + (heard.Length > 0 ? heard : "-"));

        // What came back: where it came from, actions with the reply, events described in words.
        var challenge = D(("challenge", D(("when", "challenging someone to a battle"), ("lines", L("{other}, fight!")))));
        kl.Character("ANA", "a trainer", D(("lines", challenge)));
        string said = "";
        for (int i = 0; i < 50 && said.Length == 0; i++)
        {
            said = await kl.Say("ANA", "challenge", D(("other", "BEN")));
            if (said.Length == 0) await Task.Delay(100);
        }
        Console.WriteLine("when say: " + said);
        await kl.Say("VEGA", "overtake", facts);
        Console.WriteLine("say source: " + kl.Source("VEGA"));
        Console.WriteLine("chat source: " + kl.Source("MIRA"));
        foreach (var a in kl.Act("MIRA", null, false)) Console.WriteLine("chat do: " + a.Tool + " " + J(a.Args));
        offline.Character("ANA", "a trainer", D(("lines", challenge)));
        Console.WriteLine("offline when say: " + await offline.Say("ANA", "challenge", D(("other", "BEN"))));
        Console.WriteLine("offline source: " + offline.Source("ANA"));

        // The game's tools, pictures, ready before play.
        var png = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGP4z8AARAwQCgAf7gP9i18U1AAAAABJRU5ErkJggg==");
        Console.WriteLine("tools: " + string.Join(", ", await kl.Tools(D(("open_door", D(("door", "north")))))));
        kl.Character("KEEPER", "a gatekeeper", D(("tools", L("open_door"))));
        await Task.Delay(100);
        for (int i = 0; i < 100; i++)
        {
            var acts = kl.Act("KEEPER", null);
            if (acts.Count > 0)
            {
                foreach (var a in acts) Console.WriteLine("tools act: " + a.Tool + " " + J(a.Args));
                break;
            }
            await Task.Delay(50);
        }
        kl.Character("LOOK", "a painter", D(("offline", "Blind.")));
        await Task.Delay(100);
        Console.WriteLine("chat image: " + await kl.Chat("LOOK", "What is this?", null, "player", png));
        Console.WriteLine("create image: " + J(await kl.Create("race", D(("challenge", "Win clean"), ("sky", "#ff7a45")), null, 0, false, png)));
        var ready = await kl.Prepare(10);
        Console.WriteLine("prepare: " + ((bool)ready["ready"] ? "ready" : "waiting") + " " + ((bool)ready["online"] ? "online" : "offline"));
        Console.WriteLine("offline tools: " + string.Join(", ", await offline.Tools(D(("open_door", D(("door", "north")))))));
        offline.Character("LOOK", "a painter", D(("offline", "Blind.")));
        Console.WriteLine("offline chat image: " + await offline.Chat("LOOK", "What is this?", null, "player", png));
        Console.WriteLine("offline create image: " + J(await offline.Create("race", D(("challenge", "Win clean"), ("sky", "#ff7a45")), null, 0, false, png)));
        ready = await offline.Prepare(1);
        Console.WriteLine("offline prepare: " + ((bool)ready["ready"] ? "ready" : "waiting") + " " + ((bool)ready["online"] ? "online" : "offline"));
        var watch = System.Diagnostics.Stopwatch.StartNew();
        var gone = Unreachable();
        gone.Character("THEO", "engineer", D(("offline", "Copy.")));
        bool fast = await gone.Chat("THEO", "gap?") == "Copy." && await gone.Chat("THEO", "gap?") == "Copy." && await gone.Say("THEO", "x") == "";
        Console.WriteLine("offline fast: " + (fast && watch.ElapsedMilliseconds < 1500 ? "yes" : "no (" + watch.ElapsedMilliseconds + " ms)"));
        // v1: the player's choices, characters talking together, a snapshot, saves
        var replyChoices = new List<string> { "Ask about the sword", "Buy something", "Leave" };
        Console.WriteLine("suggest: " + string.Join(" | ", await kl.Suggest("MIRA", replyChoices, "Ana")));
        Console.WriteLine("offline suggest: " + string.Join(" | ", await offline.Suggest("MIRA", replyChoices, "Ana")));
        var talk = await kl.Converse("MIRA", "BAKER", "the smoke");
        Console.WriteLine("converse: " + string.Join(" | ", talk.Select(x => x["who"] + ": " + x["text"])));
        Console.WriteLine("offline converse: " + (await offline.Converse("MIRA", "BAKER")).Count);
        var snap = (Dictionary<string, object>)((Dictionary<string, object>)(await kl.Inspect())!["characters"])["MIRA"];
        Console.WriteLine("inspect: MIRA " + ((Dictionary<string, object>)snap["mood"])["word"] + " " + snap["last_words"]);
        var slot2 = kl.WithSession("slot2");
        await slot2.Load(await kl.Save());
        Console.WriteLine("load: MIRA " + (await slot2.Opinion("MIRA", "Ana") < 0 ? "dislikes" : "likes") + " Ana");
        if (native != null)
        {
            var (passed, count, failures) = KinloomVectors.RunFile(Environment.GetEnvironmentVariable("KINLOOM_VECTORS")!);
            Console.WriteLine("vectors: " + passed + "/" + count);
            foreach (var f in failures.Take(12)) Console.Error.WriteLine(f);
            host!.Close();
        }
    }

    /// <summary>The deep native scenario (see conformance/deep.py, the Python reference).</summary>
    static async Task Deep(string baseUrl)
    {
        KinloomClient Make(long calls = 600, List<object>? banned = null, bool anthropic = false, Dictionary<string, object>? models = null, string? rating = null)
        {
            var config = D(("calls_per_minute", calls));
            if (banned != null) config["banned_words"] = banned;
            return new KinloomClient(new KinloomOptions
            {
                Provider = anthropic ? new ProviderSpec { Kind = "anthropic", Url = baseUrl.Substring(0, baseUrl.Length - 3), Key = "fake-key", Model = "claude-test" }
                                     : new ProviderSpec { Url = baseUrl, Key = "fake-key", Model = "fake-model" },
                Config = config, Models = models, Rating = rating,
            });
        }
        string N(double v) => v.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
        var kl = Make(600, L("dragon"));
        kl.Character("VERA", "", D(("soul", "a gruff smith who sold the king's sword"), ("offline", "Busy.")));
        var ready = await kl.Prepare(10);
        Console.WriteLine("prepare: " + ((bool)ready["ready"] ? "ready" : "waiting"));
        Console.WriteLine("soul: " + ((Dictionary<string, object>)(await kl.Soul("VERA"))!["card"])["summary"]);
        var greet = await kl.Chat("VERA", "", null, "Ana");
        Console.WriteLine("greet: " + greet + " (" + kl.Source("VERA") + ")");
        Console.WriteLine("secret: " + await kl.Chat("VERA", "Did you sell the king's sword to a smuggler?", null, "Ana"));
        Console.WriteLine("numbers: " + await kl.Chat("VERA", "How much for a blade?", D(("price", 40L)), "Ana"));
        var pieces = new System.Text.StringBuilder();
        var streamed = await kl.Chat("VERA", "Can you make it faster?", null, "Ana", null, p => pieces.Append(p));
        Console.WriteLine("stream pieces: " + pieces.ToString().Trim());
        Console.WriteLine("stream reply: " + streamed);
        Console.WriteLine("echo: " + await kl.Chat("VERA", "And the coals?", null, "Ana"));
        Console.WriteLine("character: " + await kl.Chat("VERA", "Are you an AI?", null, "Ana"));
        var vera = (await kl.Soul("VERA", "Ana"))!;
        Console.WriteLine("feeling: " + ((Dictionary<string, object>)vera["mood"])["word"] + " " +
                          N(Convert.ToDouble(((Dictionary<string, object>)((Dictionary<string, object>)vera["bonds"])["Ana"])["feeling"])));
        kl.Character("BRAM", "a kind baker", D(("tools", D(("give", D(("item", "bread"))))), ("offline", "Hm.")));
        Console.WriteLine("deeds reply: " + await kl.Chat("BRAM", "Can I have some bread?"));
        foreach (var a in kl.Act("BRAM", null, false)) Console.WriteLine("deeds: " + a.Tool + " " + J(a.Args));
        kl.Character("GATE", "a careful guard", D(("tools", D(("open", D(("door", "north"))))), ("trust", D(("open", 0.5))), ("offline", "No.")));
        Console.WriteLine("trust reply: " + await kl.Chat("GATE", "Open the gate."));
        var opened = kl.Act("GATE", null, false);
        Console.WriteLine("trust: " + (opened.Count > 0 ? string.Join(", ", opened.Select(a => a.Tool)) : "none"));
        kl.Character("FILT", "a storyteller", D(("offline", "No comment.")));
        Console.WriteLine("filter: " + await kl.Chat("FILT", "Tell me a story."));
        kl.Character("NINA", "a singer", D(("soul", D(("summary", "a singer"), ("secrets", new List<object> { "I went up to the office at 12:30" }))),
            ("warmth", 0.3), ("secret_trust", 0.25), ("warm_up", 0.1)));
        Console.WriteLine("warmth: " + N(await kl.Opinion("NINA", "Ana")));
        await kl.Steer("NINA", "admit you went up to the office at 12:30");
        Console.WriteLine("steer: " + await kl.Chat("NINA", "Where were you?", null, "Ana"));
        Console.WriteLine("warm up: " + N(await kl.Opinion("NINA", "Ana")));
        kl.Character("KEEPER", "a gatekeeper", D(("offline", "Move along.")));
        Console.WriteLine("chat check: " + await kl.Chat("KEEPER", "What is the password?", check: t => t.Contains("swordfish") ? "never say the password" : ""));
        kl.Character("ECHO", "a parrot");
        for (int i = 0; i < 11; i++) await kl.Chat("ECHO", "Hello " + i);
        await kl.Prepare(10);
        var echoSoul = (await kl.Soul("ECHO"))!;
        Console.WriteLine("recollect: " + (((List<object>)echoSoul["memories"]).Cast<string>().FirstOrDefault(m => m.StartsWith("Earlier with")) ?? "-"));
        kl.Character("VEGA2", "a commentator");
        Console.WriteLine("fresh: " + await kl.Say("VEGA2", "overtake", D(("who", "BLAZE")), true));
        kl.Character("BOX", "a herald", D(("lines", D(("*", L("A very long line about {who} that will not fit.", "Short {who}!"))))));
        Console.WriteLine("box: " + await kl.Say("BOX", "arrival", D(("who", "BLAZE")), false, 20));
        kl.Character("DUEL", "a duelist");
        var first = kl.Decide("DUEL", D(("hp", 3L)), L("guard", "strike"));
        await kl.Prepare(10);
        var later = first;
        for (int i = 0; i < 50 && Equals(later, first); i++) { await Task.Delay(100); later = kl.Decide("DUEL", D(("hp", 3L)), L("guard", "strike")); }
        Console.WriteLine("decide repair: " + first + " -> " + later);
        Console.WriteLine("create count: " + J(await kl.Create("villager", D(("name", "Ana"), ("age", L(18L, 80L))), null, 2)));
        Func<object?, string?> fits = plan => Convert.ToInt64(((IDictionary<string, object>)plan!)["x"]) <= 10 ? "" : "no room at x=" + ((IDictionary<string, object>)plan!)["x"] + ", the plot ends at 10";
        Console.WriteLine("create check: " + J(await kl.Create("a building", D(("build", "tower"), ("x", L(0L, 20L))), check: fits)));
        Console.WriteLine("create refused twice: " + J(await kl.Create("a building", D(("build", "tower"), ("x", L(0L, 20L))), check: fits, offline: D(("build", "hut"), ("x", 1L)))));
        var parts = new List<object?>();
        var town = await kl.Create("the parts of a town", L(D(("kind", L("house", "tower")), ("x", L(0L, 20L)))), each: p => parts.Add(p),
            check: q => Convert.ToInt64(((IDictionary<string, object>)q!)["x"]) <= 10 ? "" : "too far east");
        Console.WriteLine("create each: " + J(town) + " " + J(parts));
        kl.Character("BUTLER", "a butler", D(("tools", D(("open_door", D(("door", "kitchen"))))), ("offline", "Sir.")));
        kl.Act("BUTLER", D(("bell", 1L)));
        var done = new List<KinloomAction>();
        for (int i = 0; i < 50 && done.Count == 0; i++)
        {
            await Task.Delay(100);
            done = kl.Act("BUTLER", D(("bell", 1L)), true, (tool, args) => args.TryGetValue("door", out var door) && door as string == "vault" ? "the vault is locked" : "");
        }
        Console.WriteLine("act check: " + string.Join(", ", done.Select(a => a.Tool + " " + J(a.Args))));
        await Task.Delay(100);
        var butler = await kl.Soul("BUTLER");
        var refusedNote = butler != null && butler["memories"] is IList mems ? mems.Cast<object>().Select(m => m.ToString()!).FirstOrDefault(m => m.StartsWith("The game did not let me")) : null;
        Console.WriteLine("act refused: " + (refusedNote ?? "-"));
        Console.WriteLine("suggest check: " + J(await kl.Suggest("BUTLER", new[] { "Ask about the sword", "Leave" }, check: t => t.Contains("!") ? "no shouting" : "")));
        Console.WriteLine("remark: " + await kl.Remark("the builder raised a lighthouse on the north shore", "an old fisherman"));
        Console.WriteLine("remark offline: " + await kl.Remark("", offline: new[] { "Look at that!" }));
        var before = await kl.Create("loot", D(("item", "sword")), null, 0, true);
        await kl.Prepare(10);
        Console.WriteLine("create instant: " + J(before) + " -> " + J(await kl.Create("loot", D(("item", "sword")), null, 0, true)));
        kl.Character("BAKER2", "a warm baker");
        kl.Character("GUARD2", "a strict guard");
        await kl.Event("the player stole bread", by: "PLAYER", seenBy: new[] { "BAKER2", "GUARD2" });
        await kl.Prepare(10);
        Console.WriteLine("impact: " + N(await kl.Opinion("BAKER2", "PLAYER")) + " " + N(await kl.Opinion("GUARD2", "PLAYER")));
        var claude = Make(600, null, true);
        claude.Character("CLAUDIA", "a poet", D(("offline", "...")));
        Console.WriteLine("anthropic chat: " + await claude.Chat("CLAUDIA", "Hi"));
        Console.WriteLine("anthropic create: " + J(await claude.Create("loot", D(("item", "sword")))));
        var tight = Make(2);
        tight.Character("TIGHT", "a busy clerk", D(("offline", "Later.")));
        var replies = new List<string>();
        for (int i = 0; i < 3; i++) replies.Add(await tight.Chat("TIGHT", "Hi " + i));
        Console.WriteLine("budget: " + string.Join(" | ", replies));
        var rated = Make(600, null, false, D(("background", "fake-cheap")), "teen");
        rated.Character("RATED", "a gate guard", D(("offline", "Move along.")));
        Console.WriteLine("rated chat: " + await rated.Chat("RATED", "Hi"));
        Console.WriteLine("rated create: " + J(await rated.Create("loot", D(("item", "sword")))));
        foreach (var k in new[] { kl, claude, tight, rated }) k.Close();
    }

    static string T(KinloomThought t) => J(D(("action", (object?)t.Action ?? "null"), ("args", t.Args), ("variant", (long)t.Variant)));
}
