# Kinloom 1 (legacy)

Kinloom's first design, kept for reference. New games should use the SDK at the [repository root](../README.md).

- **What it is**: a C# runtime (netstandard2.1, C# 9) where the game declares things, roles and instant behaviors in
  JSON and an Arbiter validates every proposal; a CLI; a Godot addon (`adapters/godot`); and the village-simulation demo
  *Asagiri Valley* (`demo/valley`, Godot 4.7 .NET).
- **Why it was replaced**: a measured comparison ([proof/impact](../proof/impact/README.md)) showed it saved coding agents
  no time. The SDK at the root keeps its safety ideas (the model proposes, validation decides) in one file per language.
- **Build and test** from this folder: `dotnet build -warnaserror --no-incremental`, then `dotnet test`.
- **Support**: as is. Fixes go to the SDK at the root.
- **Third-party assets** of the demo keep their own licenses: [demo/valley/CREDITS.md](demo/valley/CREDITS.md).
