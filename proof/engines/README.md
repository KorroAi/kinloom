# Kinloom in real engines

Engines run for real, outside the conformance hosts (Node, .NET, the JVM, Cargo, a C++ compiler, lupa):

| Engine | How | Result |
|---|---|---|
| Godot 4.7 | every conformance run (`python/conformance`): the addon installed by `kinloom init`, the scenario and the AI nodes in headless Godot | PASS (relay and native) |
| LÖVE 11.5 (Windows, the official zip) | `love/run.py <lovec.exe>`: a LÖVE game using `kinloom.lua` offline, through `kinloom serve` and calling the model itself, every request through LÖVE's own `love.thread` + LuaSocket transport; the model is the conformance fake | PASS (2026-10-03): offline answers, `chat` answered by the model in relay and native mode, `create`, `decide`, 0 calls left waiting, 0.2 s |
| Unity | `KinloomDialogue.cs` and `Kinloom.cs` compiled against the Unity 6000.3 and 6000.6 assemblies | not run in the editor: no Unity license on the test machine |
| Defold, Bevy, Unreal, MonoGame, libGDX | | not run |

LÖVE 11 has no HTTPS: a LÖVE game reaches a hosted model through a relay (`kinloom serve`) or with LuaSec / LÖVE 12.
