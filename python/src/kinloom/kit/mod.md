# Kinloom in a game you do not have the source of (a mod)

Kinloom does not care whose game it is: a mod calls the same verbs as a game's own code. What changes is how you
reach the moment where the game makes a line, a reply, a choice or content. Mods are for your own use unless the game's
terms allow sharing them; respect its license and its online rules (no mods in multiplayer games that forbid them).

## 1. Does the game have a mod API?

Use it first: it is stable across updates and documented.

| The game has | Kinloom client | Example |
|---|---|---|
| Lua mods (The Binding of Isaac, LÖVE games, Garry's Mod, Factorio...) | `kinloom.lua` | an Isaac mod: merchants who talk and haggle, a room carpenter, wishes |
| Java mods (Minecraft Forge / Fabric, any JVM game) | `Kinloom.java` | |
| A script hook (ScriptHookV / RDR2, SKSE) | `kinloom.hpp` (C++) | a ScriptHookRDR2 `.asi` |
| A scripting language of its own | the HTTP API (`kinloom serve`, `GET /v1/openapi.json`) | |

`kinloom init <mod folder> --engine love` (Lua), `java`, `cpp` or `dotnet` (C#) copies the client and writes the
instructions, as for a game.

## 2. No mod API: find where to plug in

**.NET games** (Unity with Mono: `<Game>_Data/Managed/Assembly-CSharp.dll`; MonoGame, FNA, XNA, any .NET game):

```
kinloom hooks "<game folder or .dll>"
```

reads the game's code with **REA** (Reverse Engineer Anything, optional, MIT: `npm install --global rea-agents`, or
`KINLOOM_REA` = the command that runs it) without running the game, and lists the methods that make a line, a reply,
a choice or content, best first, each with the Kinloom call that fits (`say`, `chat`, `decide`, `create`) and a
Harmony patch for the first one. `--json` for scripts and agents. Names can mislead (and obfuscated games have none
worth reading): check a candidate in the game before building on it. ILSpy or dnSpyEx show a method's body. Methods of
generic types (`Box<T>`) are left out: Harmony patches concrete methods; patch the code that uses them.

**Unity IL2CPP** (a `GameAssembly.dll`, no `Managed` folder): the C# became native code. Cpp2IL or Il2CppDumper recover
the names; BepInEx 6 (IL2CPP) or MelonLoader patch them; the C# client works the same.

**Native games** (C++, Unreal, custom engines): REA reads them with Ghidra, IDA or Hopper (`rea function`,
`rea decompile`); hooking native code (a script hook, Detours, a proxy DLL) is the C++ client's job. Coding agents can
call REA directly as an MCP server (`npx rea-agents setup`): ask it where the game builds the text it shows.

**JavaScript / Electron / web games** (RPG Maker MV/MZ, NW.js, Electron): the code is readable; REA's
`analyze-javascript-application` maps a large one. Load `kinloom.js` with the game's plugins.

## 3. Patch, and keep the game's own value when Kinloom has none

A Harmony patch (BepInEx and MelonLoader plugins are Harmony patches; a small launcher of your own can apply them too)
runs Kinloom where the game made its value. When Kinloom has nothing (no model, no server, no line ready yet) the call
returns `""`, and the game's own value stays:

```csharp
using HarmonyLib;
using Kinloom;
using Obj = System.Collections.Generic.Dictionary<string, object>;
using Arr = System.Collections.Generic.List<object>;

static class Mod
{
    public static readonly KinloomClient Kl = new KinloomClient();   // relay to `kinloom serve`
    public static void Start()
    {
        Kl.Character("MARLO", "", new Obj { ["soul"] = "a lamp-oil seller who distrusts the guard",
            ["lines"] = new Obj { ["greet"] = new Obj { ["when"] = "a customer walks into his oil shop",
                                                        ["lines"] = new Arr() } },     // no lines of ours: the game's
            ["events"] = new Obj { ["greet"] = new Arr { "who" } } });
        Kl.Prepare(15).GetAwaiter().GetResult();     // a loading screen: lines written ahead, say is instant
        new Harmony("my.kinloom.mod").PatchAll();
    }
}

[HarmonyPatch]
static class Shopkeeper_Greet
{
    static System.Reflection.MethodBase TargetMethod() => AccessTools.Method("LanternRow.Shopkeeper:Greet");
    static void Postfix(object[] __args, ref string __result)
    {
        var who = AccessTools.Field(__args[0].GetType(), "Name").GetValue(__args[0]) as string ?? "";
        var said = Mod.Kl.Say("MARLO", "greet", new Obj { ["who"] = who }).GetAwaiter().GetResult();
        if (said.Length > 0) __result = said;
    }
}
```

- Facts are the game's values at that moment (`__instance`'s fields, `__args`, read with `AccessTools.Field`), named
  for what they are (`coins_in_purse`, not `coins` when the price is coins too). Do not pass the game's whole line as a
  fact to fill in: facts are cut at 80 characters and the model writes around them.
- `say` and `decide` are instant: safe inside the game's own call. `chat` takes about a second: block only where the
  game waits for an answer anyway; otherwise show the game's line and replace it when the reply comes.
- Unity: create the client and call `Start()` from your plugin's `Awake`; awaited calls continue on the main thread.
- Very small methods can be inlined by the JIT, and a patch on them never runs: patch their caller instead.

## 4. Run it

`kinloom serve` while playing (a model from the environment, or none: everyone answers with the game's own lines).
`kinloom add NAME "who they are"` writes a character into `kinloom.json`. A worked example, end to end with a .NET game
whose source is never used: `proof/mod` in the Kinloom repository.
