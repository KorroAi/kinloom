language: C# (Unity, MonoGame, FNA, Stride, Godot C#, any .NET)
Setup: `kinloom init` copied `{client_path}` (one file, namespace `Kinloom`, no dependencies).
While playing, run `kinloom serve` in a terminal. Or no server (native: the game calls the model itself, the key from the environment): `new KinloomClient(new KinloomOptions
{ ProviderAuto = true })`. Unity: awaited calls continue on the main thread. (WebGL builds cannot
use `HttpClient`: use the web client from JavaScript there.)
Unity, no code: the `KinloomDialogue` component (`Assets/Kinloom/KinloomDialogue.cs`): character name, one-sentence soul,
offline line, tools as JSON, reply choices for gamepads; events onReply, onAction(tool, argsJson), onGesture, onChoices.
Set `KinloomDialogue.Client` from code for native mode or an online relay (never a key in a scene).
---
```csharp
using System.Collections.Generic;
using Kinloom;

var kl = new KinloomClient();                            // one per game; new KinloomClient(session: "player-2") per player
// Characters with a soul: one sentence, a person the player talks to (mood, feelings, memories, secrets, actions)
kl.Character("MIRA", "", new Dictionary<string, object> { ["soul"] = "a gruff blacksmith who secretly sold the king's sword",
    ["offline"] = "Busy.", ["tools"] = new Dictionary<string, object> { ["give"] = new Dictionary<string, object> { ["item"] = "sword" } } });
dialogue.text = await kl.Chat("MIRA", playerText, null, "Ana");        // "" = Ana walks up: she speaks first (~1 s)
foreach (var a in kl.Act("MIRA", null, false)) if (a.Tool == "give") inventory.Add((string)a.Args["item"]);   // decided while talking
var soul = await kl.Soul("MIRA", "Ana");                                 // card, mood, bonds, memories (null offline)

kl.Character("VEGA", "over-excited race commentator, max 10 words", new Dictionary<string, object> {
    ["lines"] = new Dictionary<string, object> { ["overtake"] = new List<object> { "{who} passes {whom}!" } },
    ["events"] = new Dictionary<string, object> { ["overtake"] = new List<object> { "who", "whom", "gap" } } });
kl.Character("THEO", "calm race engineer", new Dictionary<string, object> { ["offline"] = "Copy that." });
kl.Character("RAX", "brutal rival", new Dictionary<string, object> {
    ["tools"] = new Dictionary<string, object> { ["ram"] = new Dictionary<string, object> { ["force"] = new List<object> { 0.0, 1.0 } } } });

label.text = await kl.Say("VEGA", "overtake", new Dictionary<string, object> { ["who"] = "BLAZE", ["whom"] = "NOVA", ["gap"] = 0.4 });
radio.text = await kl.Chat("THEO", playerText, new Dictionary<string, object> { ["gap_to_leader"] = 1.8 });   // ~1 s

// per frame: instant, refreshed in the background
var choices = new Dictionary<string, object> { ["strategy"] = new List<object> { "attack", "block" }, ["aggression"] = new List<object> { 0.0, 1.0 } };
var plan = kl.Decide("RAX", new Dictionary<string, object> { ["gap"] = gap }, choices);
float aggression = System.Convert.ToSingle(plan["aggression"]);
foreach (var a in kl.Act("RAX", new Dictionary<string, object> { ["gap"] = gap }))
    if (a.Tool == "ram") Ram(System.Convert.ToSingle(a.Args["force"]));

var challenge = (Dictionary<string, object>)(await kl.Create("a short race challenge",
    new Dictionary<string, object> { ["title"] = "Win clean", ["laps"] = new List<object> { 2, 5 }, ["sky"] = "#ff7a45" }))!;
kl.Event("BLAZE crashed on lap 3", new[] { "BLAZE", "VEGA" });                       // they remember it
kl.State(new Dictionary<string, object> { ["lap"] = 3, ["leader"] = "NOVA" });       // facts every call sees

// Minds: utility AI for crowds, run locally every frame (never a model call); rules are the offline mind
kl.Mind("raider", "a cunning raider",
    new Dictionary<string, object> { ["hp"] = new List<object> { 0.0, 1.0 }, ["dist"] = new List<object> { 0.0, 40.0 }, ["armed"] = true },
    new Dictionary<string, object> { ["charge"] = new Dictionary<string, object> { ["speed"] = new List<object> { 1.0, 3.0 } },
                                     ["shoot"] = new Dictionary<string, object>(), ["retreat"] = new Dictionary<string, object>() },
    new Dictionary<string, object> { ["retreat"] = new List<object> { "hp low" }, ["shoot"] = new List<object> { "armed", "dist below 20" } });
var t = kl.Think("raider", new Dictionary<string, object> { ["hp"] = hp, ["dist"] = dist, ["armed"] = ammo > 0 }, enemyId);  // every frame
if (t.Action == "shoot") Shoot();
kl.Reward(enemyId, dealt - taken, done: diedOrWon);                                  // minds learn

// World: who saw what, rumors, opinions
await kl.Event("the player stole bread", by: "PLAYER", seenBy: new[] { "BAKER" }, tag: "theft", impact: -0.6);
await kl.Meet("BAKER", "GUARD");
if (await kl.Knows("GUARD", "theft")) guard.Alert();
```
Numbers come back as `long` or `double`: read them with `System.Convert.ToSingle` / `ToInt32`.
