namespace Kinloom.Runtime.Tests;

/// <summary>A small, deliberately unusual game used across tests: trucks, a HUD and a spawner.</summary>
internal static class TestData
{
    public const string Trucks = """
    {
      "types": {
        "Truck": {
          "description": "An AI-driven rival truck on the track.",
          "properties": { "speed": { "type": "number", "unit": "km/h" }, "lap": "integer", "position": "vec3" },
          "params":     { "aggression": { "type": "number", "min": 0, "max": 1, "default": 0.5 },
                          "mood": { "type": "enum", "options": ["calm", "angry"], "default": "calm" } },
          "functions":  { "boost": { "description": "Short burst of speed.", "args": { "seconds": { "type": "number", "min": 0, "max": 3 } }, "cooldown": 10 },
                          "honk": {} },
          "creatable":  { "args": { "position": "vec3" }, "max": 3 }
        },
        "Hud": {
          "description": "The on-screen interface.",
          "functions": { "say": { "args": { "text": { "type": "string", "max": 200 } } } }
        },
        "Player": { "properties": { "idle_seconds": "number", "health": "number" } }
      },
      "things": [
        { "id": "truck_2", "type": "Truck", "name": "Rex", "tags": ["rival"] },
        { "id": "truck_3", "type": "Truck", "name": "Mo", "tags": ["rival"] },
        { "id": "hud", "type": "Hud" },
        { "id": "player", "type": "Player", "name": "The player" }
      ],
      "events": {
        "overtake": { "description": "Someone overtook someone.", "importance": 0.6 },
        "crash": { "description": "A crash.", "importance": 0.9 }
      },
      "roles": [
        {
          "id": "rex",
          "mission": "You drive Rex. You hate losing to the player.",
          "inhabits": "truck_2",
          "sees": ["thing:self", "thing:player", "type:Truck", "event:overtake", "event:crash"],
          "can": ["set:self.aggression", "invoke:self.boost", "invoke:hud.say", "say", "behavior:self", "remember"],
          "wake": [ { "on": "event:overtake" }, { "every": 20 } ],
          "tier": "fast",
          "memory": { "scope": "role", "persist": true, "max": 50 },
          "budget": { "callsPerMinute": 4 },
          "fallback": { "say": ["Grr."] }
        }
      ]
    }
    """;
}
