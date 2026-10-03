# The fresh-session measurement

The spec's success criterion is a **fresh** coding-agent session that only has the Kinloom kit. It costs tokens, so it is launched by you, not by the session that built Kinloom.

For each game:

1. Get a clean copy (see "Reproduce" in [README.md](README.md)), without applying the patch.
2. Run `kinloom init <game folder>` (or `dotnet run --project src/Kinloom.Cli -- init <game folder>`).
3. Open a new Claude Code session **in the game folder** (it loads the game's `CLAUDE.md` and the `kinloom-integrate` skill that init installed), note the time, and paste the brief:

   - Dodge the Creeps: *"Using Kinloom, add a director that adapts the waves to the player (time between creeps, creep speed) and a sarcastic arena announcer that comments on starts, deaths and records in the HUD. It must still work without an API key. Prove it with kinloom tests."*
   - Platformer 2D: *"Using Kinloom, add a pack mind that steers every robot enemy's speed, and a coach that notices when the player is stuck, shows a hint and places a reward coin. It must still work without an API key. Prove it with kinloom tests."*
   - Truck Town: *"Using Kinloom, add a radio dispatcher I can talk to (time of day, engine power, headlights) and a co-driver in the truck who reacts to crashes. It must still work without an API key. Prove it with kinloom tests."*

4. Optional: add the MCP server so the agent can use `scan_project`, `simulate_role`, `attack_guardrails`: `claude mcp add kinloom -- kinloom mcp` (with the `kinloom` tool installed) or point it at `dotnet <repo>/src/Kinloom.Cli/bin/Debug/net10.0/kinloom.dll mcp`.
5. Stop the clock when `kinloom test` passes and the game runs. Record: wall time, number of times you had to step in, and the session's token use.
