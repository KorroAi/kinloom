language: C# (Unity, MonoGame, FNA, Stride, Godot C#, any .NET)
Setup: `kinloom init` copied `{client_path}`. While playing, run `kinloom serve`, or no server:
`new KinloomClient(new KinloomOptions { ProviderAuto = true })` (the key from the environment). Unity: awaited calls
continue on the main thread; no code: `KinloomDialogue`; WebGL, shipping: KINLOOM.md.
<!-- brief ends -->
Values may also be anonymous objects (`new { name = "Glowcap" }`), except in Unity IL2CPP builds with managed
stripping "High", which removes what they are read with (a clear error then): `Obj` works in every build.
Unity: awaited calls, and the pieces a streamed `Chat(..., onPiece: ...)` gives, continue on the thread that called
(the main thread); warnings go to `KinloomClient.Warn` (the Unity console once `KinloomDialogue` is in the project).
WebGL: `HttpClient` cannot run there: pass `KinloomOptions { Http = <your UnityWebRequest wrapper> }` (relay calls go
through it too), or use the web client from JavaScript.
Shipped game: one session per player (`new KinloomClient(url, playerId, token)`); `KinloomDialogue` with a Relay Token
makes one per install (PlayerPrefs) by itself.
Unity, no code: the `KinloomDialogue` component (`Assets/Kinloom/KinloomDialogue.cs`): character name, one-sentence soul,
offline line, tools as JSON, reply choices for gamepads; events onReply, onAction(tool, argsJson), onGesture, onChoices.
Set `KinloomDialogue.Client` from code for native mode or an online relay (never a key in a scene).
---
```csharp
using Kinloom;
using Obj = System.Collections.Generic.Dictionary<string, object>;  // shorthands
using Arr = System.Collections.Generic.List<object>;

var kl = new KinloomClient();  // one per game; new KinloomClient(session: "player-2") per player
// Characters with a soul: one sentence, a person the player talks to (mood, feelings, memories, secrets, actions)
kl.Character("MIRA", "", new Obj { ["soul"] = "a gruff blacksmith who secretly sold the king's sword",
    ["offline"] = "Busy.", ["tools"] = new Obj { ["give"] = new Obj { ["item"] = "sword" } } });
dialogue.text = await kl.Chat("MIRA", playerText, null, "Ana");  // "" = Ana walks up: she speaks first (~1 s)
foreach (var a in kl.Act("MIRA", null, false)) if (a.Tool == "give") inventory.Add((string)a.Args["item"]);  // decided while talking
var soul = await kl.Soul("MIRA", "Ana");  // card, mood, bonds, memories (null offline)

kl.Character("VEGA", "over-excited race commentator, max 10 words", new Obj {
    ["lines"] = new Obj { ["overtake"] = new Arr { "{who} passes {whom}!" } },
    ["events"] = new Obj { ["overtake"] = new Arr { "who", "whom", "gap" } } });
kl.Character("THEO", "calm race engineer", new Obj { ["offline"] = "Copy that." });
kl.Character("RAX", "brutal rival", new Obj {
    ["tools"] = new Obj { ["ram"] = new Obj { ["force"] = new Arr { 0.0, 1.0 } } } });

label.text = await kl.Say("VEGA", "overtake", new Obj { ["who"] = "BLAZE", ["whom"] = "NOVA", ["gap"] = 0.4 });
radio.text = await kl.Chat("THEO", playerText, new Obj { ["gap_to_leader"] = 1.8 });  // ~1 s

// per frame: instant, refreshed in the background
var choices = new Obj { ["strategy"] = new Arr { "attack", "block" }, ["aggression"] = new Arr { 0.0, 1.0 } };
var plan = kl.Decide("RAX", new Obj { ["gap"] = gap }, choices);
float aggression = System.Convert.ToSingle(plan["aggression"]);
foreach (var a in kl.Act("RAX", new Obj { ["gap"] = gap }))
    if (a.Tool == "ram") Ram(System.Convert.ToSingle(a.Args["force"]));

var challenge = (Dictionary<string, object>)(await kl.Create("a short race challenge",
    new Obj { ["title"] = "Win clean", ["laps"] = new Arr { 2, 5 }, ["sky"] = "#ff7a45" }))!;
kl.Event("BLAZE crashed on lap 3", new[] { "BLAZE", "VEGA" });  // they remember it
kl.State(new Obj { ["lap"] = 3, ["leader"] = "NOVA" });  // facts every call sees

// Minds: utility AI for crowds, run locally every frame (never a model call); rules are the offline mind
kl.Mind("raider", "a cunning raider",
    new Obj { ["hp"] = new Arr { 0.0, 1.0 }, ["dist"] = new Arr { 0.0, 40.0 }, ["armed"] = true },
    new Obj { ["charge"] = new Obj { ["speed"] = new Arr { 1.0, 3.0 } },
                                     ["shoot"] = new Obj(), ["retreat"] = new Obj() },
    new Obj { ["retreat"] = new Arr { "hp low" }, ["shoot"] = new Arr { "armed", "dist below 20" } });
var t = kl.Think("raider", new Obj { ["hp"] = hp, ["dist"] = dist, ["armed"] = ammo > 0 }, enemyId);  // every frame
if (t.Action == "shoot") Shoot();
kl.Reward(enemyId, dealt - taken, done: diedOrWon);  // minds learn

// World: who saw what, rumors, opinions
await kl.Event("the player stole bread", by: "PLAYER", seenBy: new[] { "BAKER" }, tag: "theft", impact: -0.6);
await kl.Meet("BAKER", "GUARD");
if (await kl.Knows("GUARD", "theft")) guard.Alert();
```
Numbers come back as `long` or `double`: read them with `System.Convert.ToSingle` / `ToInt32`.
