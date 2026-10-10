# Kinloom in real engines

Engines run for real, outside the conformance hosts (Node, .NET, the JVM, Cargo, a C++ compiler, lupa):

| Engine | How | Result |
|---|---|---|
| Godot 4.7 | every conformance run (`python/conformance`): the addon installed by `kinloom init`, the scenario and the AI nodes in headless Godot | PASS (relay and native) |
| LÖVE 11.5 (Windows, the official zip) | `love/run.py <lovec.exe>`: a LÖVE game using `kinloom.lua` offline, through `kinloom serve` and calling the model itself, every request through LÖVE's own `love.thread` + LuaSocket transport; the model is the conformance fake | PASS (2026-10-03): offline answers, `chat` answered by the model in relay and native mode, `create`, `decide`, 0 calls left waiting, 0.2 s |
| Unity 6000.3.25f1 and 6000.6.3f1 (editor, batch mode) | `unity/run.py <Unity.exe>`: a new project set up by `kinloom init`; the C# conformance scenario run by the editor through a relay and in native mode (transcript, the shared vectors, every request equal to Python's, the deep scenario), then `KinloomDialogue` in play mode through a relay with a scripted model; `player`: a Windows player built with IL2CPP (managed stripping Low, and High with `player-high`) runs the scenario in both modes (6000.6: the 6000.3 install has no IL2CPP module) | PASS (2026-10-10), both versions: awaited calls continue on Unity's main thread (`UnitySynchronizationContext`); in play mode she speaks first, her action, gesture and mood arrive, the reply choices come, a pick gets her answer, the box closes. 0 compiler warnings. It found two bugs: Unity's Mono refused numbers past a double (`1e400`), so a model answer holding one was unreadable (fixed); IL2CPP with High stripping removed anonymous objects' properties, which went out empty (now a clear error; the docs use dictionaries) |
| Defold, Bevy, Unreal, MonoGame, libGDX | | not run |

Unity runs with the editor's own license (Unity Hub signed in). Players were built for Windows only; no mobile, console or WebGL build.

LÖVE 11 has no HTTPS: a LÖVE game reaches a hosted model through a relay (`kinloom serve`) or with LuaSec / LÖVE 12.
