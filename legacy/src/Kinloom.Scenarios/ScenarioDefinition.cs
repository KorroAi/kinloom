namespace Kinloom.Scenarios;

public sealed class ScenarioDefinition
{
    public int Seed { get; set; } = 42;
    public int Days { get; set; } = 7;
    public int FrameInterval { get; set; } = 1;
    /// <summary>A few sentences about the setting, for brains.</summary>
    public string? World { get; set; }
    /// <summary>Hour of day 1 the story starts at (0-23).</summary>
    public int StartHour { get; set; }
    /// <summary>Guards who catch the player journal an arrest.</summary>
    public bool Arrests { get; set; }
    /// <summary>Villagers at home sleep (perceive nothing) between 00:00 and 05:00.</summary>
    public bool Sleep { get; set; }
    /// <summary>Authored quests, offered at a given day and hour.</summary>
    public List<QuestDef> Quests { get; set; } = new();
    public List<PlaceDef> Places { get; set; } = new();
    public List<AgentDef> Agents { get; set; } = new();
    public AgentDef? Player { get; set; }
    public List<ItemDef> Items { get; set; } = new();
    public List<CommandDef> Script { get; set; } = new();
}

public sealed class PlaceDef
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public float X { get; set; }
    public float Y { get; set; }
    public float Radius { get; set; } = 4f;
    public List<string> Tags { get; set; } = new();
}

public sealed class AgentDef
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public float X { get; set; }
    public float Y { get; set; }
    public List<string> Tags { get; set; } = new();
    public float Bravery { get; set; } = 0.5f;
    public float Sociability { get; set; } = 0.5f;
    public float Forgiveness { get; set; } = 0.5f;
    public string? Home { get; set; }
    public List<SlotDef> Schedule { get; set; } = new();
    public string? Role { get; set; }
    public string? Bio { get; set; }
    public string? Traits { get; set; }
    public string? Style { get; set; }
    public List<string> Goals { get; set; } = new();
    public List<string> Secrets { get; set; } = new();
    public int Health { get; set; } = 10;
    public int Gold { get; set; }
    /// <summary>Off-stage until an event brings them in (bandits, strangers).</summary>
    public bool Reserve { get; set; }
    /// <summary>Appearance hint for hosts (e.g. a sprite name); ignored by the simulation.</summary>
    public string? Look { get; set; }
    /// <summary>Starting feelings about others: id -> -1..1.</summary>
    public Dictionary<string, float> Opinions { get; set; } = new();
    /// <summary>Story beats that beat any other plan during their window.</summary>
    public List<FixedPlanDef> FixedPlans { get; set; } = new();
}

public sealed class FixedPlanDef
{
    public int Day { get; set; } = 1;
    public string? Until { get; set; }
    public string Intention { get; set; } = "";
    public List<StepDef> Steps { get; set; } = new();
}

public sealed class StepDef
{
    public string Time { get; set; } = "00:00";
    public string Verb { get; set; } = "";
    public string? Target { get; set; }
    public string? Item { get; set; }
    public string? Note { get; set; }
}

public sealed class QuestDef
{
    public string Giver { get; set; } = "";
    public string Kind { get; set; } = "";
    public string Target { get; set; } = "";
    public string? Item { get; set; }
    public int Reward { get; set; }
    public string? RewardItem { get; set; }
    public string Text { get; set; } = "";
    /// <summary>Translations of Text: language code -> text.</summary>
    public Dictionary<string, string> Texts { get; set; } = new();
    public int Day { get; set; } = 1;
    public int? Hour { get; set; }
    public int? DeadlineHours { get; set; }
}

public sealed class SlotDef
{
    public int Hour { get; set; }
    public string Place { get; set; } = "";
}

public sealed class ItemDef
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public string Place { get; set; } = "";
    public float Value { get; set; }
    public string? Owner { get; set; }
    public List<string> Tags { get; set; } = new();
}

public sealed class CommandDef
{
    public int Day { get; set; } = 1;
    public int Hour { get; set; }
    public int Minute { get; set; }
    public string Action { get; set; } = "";
    public string? Place { get; set; }
    public string? Deed { get; set; }
    public string? Target { get; set; }
    public string? Item { get; set; }
    public float Price { get; set; }
}
