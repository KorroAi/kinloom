// The Lantern Row mod: the three patches `kinloom hooks` proposed, filled in. Usage: LanternRowKinloom <LanternRow.dll> [url]
// Offline (no server, no model, no line ready yet) every patch leaves the game's own text as it was.
using System;
using System.Reflection;
using HarmonyLib;
using Kinloom;
using Obj = System.Collections.Generic.Dictionary<string, object>;
using Arr = System.Collections.Generic.List<object>;

static class Mod
{
    public static KinloomClient Kl = null!;

    static int Main(string[] args)
    {
        Kl = new KinloomClient(args.Length > 1 ? args[1] : "http://127.0.0.1:7717");
        Kl.Character("MARLO", "", new Obj {
            ["soul"] = "Marlo, a lamp-oil seller on Lantern Row who distrusts the night guard",
            ["lines"] = new Obj { ["greet"] = new Obj { ["when"] = "a customer walks into his oil shop (3 coins a flask)",
                                                        ["lines"] = new Arr() } },
            ["events"] = new Obj { ["greet"] = new Arr { "who", "coins_in_purse" } } });
        Kl.Character("GUARD", "the night guard of Lantern Row, curt and tired", new Obj {
            ["lines"] = new Obj {
                ["round"] = new Obj { ["when"] = "he walks his round past the shops", ["lines"] = new Arr() },
                ["curfew"] = new Obj { ["when"] = "nine o'clock: curfew, everyone must go inside", ["lines"] = new Arr() } },
            ["events"] = new Obj { ["round"] = new Arr(), ["curfew"] = new Arr() } });
        Kl.Prepare(15).GetAwaiter().GetResult();     // lines written ahead: say is instant in the game
        var game = Assembly.LoadFrom(args[0]);
        new Harmony("kinloom.proof.lanternrow").PatchAll(typeof(Mod).Assembly);
        game.EntryPoint!.Invoke(null, new object[] { Array.Empty<string>() });
        Console.WriteLine("sources: MARLO " + Kl.Source("MARLO") + ", GUARD " + Kl.Source("GUARD"));
        return 0;
    }

    public static string Who(object player) => AccessTools.Field(player.GetType(), "Name").GetValue(player) as string ?? "";
    public static int Coins(object player) => (int)AccessTools.Field(player.GetType(), "Coins").GetValue(player)!;
}

[HarmonyPatch]
static class Guard_Shout
{
    static MethodBase TargetMethod() => AccessTools.Method("LanternRow.Guard:Shout");
    static void Prefix(object[] __args)
    {
        var text = __args[0] as string ?? "";
        var said = Mod.Kl.Say("GUARD", text.StartsWith("Curfew") ? "curfew" : "round").GetAwaiter().GetResult();
        if (said.Length > 0) __args[0] = said;
    }
}

[HarmonyPatch]
static class Shopkeeper_Answer
{
    static MethodBase TargetMethod() => AccessTools.Method("LanternRow.Shopkeeper:Answer");
    static void Postfix(object[] __args, ref string __result)
    {
        var reply = Mod.Kl.Chat("MARLO", (string)__args[1], new Obj { ["usual"] = __result, ["coins_in_purse"] = Mod.Coins(__args[0]) },
                                Mod.Who(__args[0])).GetAwaiter().GetResult();
        if (reply.Length > 0) __result = reply;
    }
}

[HarmonyPatch]
static class Shopkeeper_Greet
{
    static MethodBase TargetMethod() => AccessTools.Method("LanternRow.Shopkeeper:Greet");
    static void Postfix(object[] __args, ref string __result)
    {
        var said = Mod.Kl.Say("MARLO", "greet", new Obj { ["who"] = Mod.Who(__args[0]), ["coins_in_purse"] = Mod.Coins(__args[0]) })
            .GetAwaiter().GetResult();
        if (said.Length > 0) __result = said;
    }
}
