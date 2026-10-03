using System.Text.Json;
using Kinloom.Core;

namespace Kinloom.Scenarios;

public static class ScenarioLoader
{
    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true,
        UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow, // a typo in a key must not be silently ignored
    };

    public static PackDefinition LoadPack(string path)
    {
        var pack = Deserialize<PackDefinition>(path);
        ValidatePack(pack, path);
        return pack;
    }

    private static void ValidatePack(PackDefinition pack, string path)
    {
        var seen = new HashSet<string>();
        foreach (var d in pack.Deeds)
        {
            string where = $"Pack {path}, deed '{d.Kind}'";
            if (string.IsNullOrWhiteSpace(d.Kind)) throw new ScenarioException($"Pack {path}: a deed has an empty kind");
            if (!seen.Add(d.Kind)) throw new ScenarioException($"Pack {path}: deed '{d.Kind}' is defined twice");
            if (d.Valence is < -1f or > 1f) throw new ScenarioException($"{where}: valence must be between -1 and 1 (got {d.Valence.ToString(System.Globalization.CultureInfo.InvariantCulture)})");
            if (d.Threat is < 0f or > 1f) throw new ScenarioException($"{where}: threat must be between 0 and 1 (got {d.Threat.ToString(System.Globalization.CultureInfo.InvariantCulture)})");
            if (d.Radius < 0f) throw new ScenarioException($"{where}: radius must be 0 or more (got {d.Radius.ToString(System.Globalization.CultureInfo.InvariantCulture)})");
        }
    }

    public static ScenarioDefinition LoadScenario(string path) => Deserialize<ScenarioDefinition>(path);

    private static T Deserialize<T>(string path)
    {
        if (!File.Exists(path)) throw new ScenarioException($"File not found: {path}");
        try
        {
            return JsonSerializer.Deserialize<T>(File.ReadAllText(path), Options)
                ?? throw new ScenarioException($"Empty file: {path}");
        }
        catch (JsonException e)
        {
            throw new ScenarioException($"Invalid JSON in {path}: {e.Message}");
        }
    }

    /// <param name="language">Optional language code ("fr"): authored texts use their translation when the scenario has one.</param>
    public static Simulation Build(ScenarioDefinition s, PackDefinition pack, string? language = null)
    {
        if (s.Days < 1) throw new ScenarioException($"Scenario 'days' must be at least 1 (got {s.Days})");
        if (s.StartHour is < 0 or > 23) throw new ScenarioException($"Scenario 'startHour' must be 0-23 (got {s.StartHour})");
        if (s.FrameInterval < 1) throw new ScenarioException($"Scenario 'frameInterval' must be at least 1 (got {s.FrameInterval})");
        var world = new World(pack, s.Seed);
        if (s.StartHour > 0) world.StartAt(s.StartHour * World.TicksPerHour);
        world.Tuning.Arrests = s.Arrests;
        world.Tuning.Sleep = s.Sleep;
        try
        {
            foreach (var p in s.Places) world.Add(new Place(p.Id, p.Name, new Vec2(p.X, p.Y), p.Radius, p.Tags));
            foreach (var a in s.Agents) world.Add(BuildAgent(world, a, false));
            if (s.Player != null) world.Add(BuildAgent(world, s.Player, true));
            foreach (var i in s.Items)
            {
                var place = world.FindPlace(i.Place) ?? throw new ScenarioException($"Item '{i.Id}': unknown place '{i.Place}'");
                if (i.Owner != null && world.FindAgent(i.Owner) == null) throw new ScenarioException($"Item '{i.Id}': unknown owner '{i.Owner}'");
                world.Add(new Item(i.Id, i.Name, place.Position, i.Value, i.Owner, i.Tags));
            }
        }
        catch (ArgumentException e)
        {
            throw new ScenarioException(e.Message);
        }

        foreach (var a in s.Agents)
            foreach (var kv in a.Opinions)
            {
                if (world.FindAgent(kv.Key) == null) throw new ScenarioException($"Agent '{a.Id}': opinion about unknown '{kv.Key}'");
                if (kv.Value is < -1f or > 1f) throw new ScenarioException($"Agent '{a.Id}': opinion about '{kv.Key}' must be between -1 and 1");
                world.GetAgent(a.Id).Mind.ShiftOpinion(kv.Key, kv.Value);
            }

        foreach (var a in s.Agents)
            foreach (var fp in a.FixedPlans)
                world.GetAgent(a.Id).FixedPlans.Add(BuildFixedPlan(world, a.Id, fp));
        foreach (var q in s.Quests) ScheduleQuest(world, s, q, language);

        if (s.Script.Count > 0 && s.Player == null) throw new ScenarioException("Scenario has a script but no player");
        var commands = s.Script.Select((c, n) => ToCommand(world, pack, c, n)).ToList();
        return new Simulation(world, commands) { FrameInterval = s.FrameInterval };
    }

    private static Agent BuildAgent(World world, AgentDef d, bool isPlayer)
    {
        var agent = new Agent(d.Id, d.Name, new Vec2(d.X, d.Y), new Personality(d.Bravery, d.Sociability, d.Forgiveness), isPlayer, d.Tags);
        if (d.Health < 1) throw new ScenarioException($"Agent '{d.Id}': health must be at least 1");
        if (d.Gold < 0) throw new ScenarioException($"Agent '{d.Id}': gold cannot be negative");
        agent.MaxHealth = agent.Health = d.Health;
        agent.Gold = d.Gold;
        agent.Present = !d.Reserve;
        agent.Profile = new Profile
        {
            Role = d.Role ?? "",
            Bio = d.Bio ?? "",
            Traits = d.Traits ?? "",
            Style = d.Style ?? "",
            Goals = d.Goals,
            Secrets = d.Secrets,
        };
        if (d.Home != null)
        {
            if (world.FindPlace(d.Home) == null) throw new ScenarioException($"Agent '{d.Id}': unknown home place '{d.Home}'");
            agent.HomePlaceId = d.Home;
        }
        if (d.Schedule.Count > 0)
        {
            var schedule = new Schedule();
            foreach (var slot in d.Schedule)
            {
                if (slot.Hour < 0 || slot.Hour > 23) throw new ScenarioException($"Agent '{d.Id}': schedule hour {slot.Hour} must be 0-23");
                if (world.FindPlace(slot.Place) == null) throw new ScenarioException($"Agent '{d.Id}': unknown place '{slot.Place}' in schedule");
                schedule.Add(slot.Hour, slot.Place);
            }
            agent.Schedule = schedule;
        }
        return agent;
    }

    private static int Minute(string? time, string where)
    {
        var parts = (time ?? "").Split(':');
        if (parts.Length == 2 && int.TryParse(parts[0], out int h) && int.TryParse(parts[1], out int m) && h is >= 0 and <= 24 && m is >= 0 and <= 59)
            return h * 60 + m;
        throw new ScenarioException($"{where}: time '{time}' must be HH:MM");
    }

    private static Plan BuildFixedPlan(World world, string agentId, FixedPlanDef d)
    {
        string where = $"Agent '{agentId}', fixed plan of day {d.Day}";
        if (d.Day < 1) throw new ScenarioException($"{where}: day must be at least 1");
        if (d.Steps.Count == 0) throw new ScenarioException($"{where}: no steps");
        var steps = new List<PlanStep>();
        foreach (var st in d.Steps)
        {
            if (!Verbs.IsKnown(st.Verb)) throw new ScenarioException($"{where}: unknown verb '{st.Verb}' (use {string.Join(", ", Verbs.All)})");
            bool place = Verbs.TargetsPlace(st.Verb);
            if (place && world.FindPlace(st.Target) == null) throw new ScenarioException($"{where}: unknown place '{st.Target}'");
            if (!place && st.Verb != Verbs.Steal && world.FindAgent(st.Target) == null) throw new ScenarioException($"{where}: unknown person '{st.Target}'");
            if (st.Item != null && world.FindItem(st.Item) == null) throw new ScenarioException($"{where}: unknown item '{st.Item}'");
            int minute = Minute(st.Time, where);
            steps.Add(new PlanStep(minute / 60, minute % 60, st.Verb, st.Target, st.Item, st.Note));
        }
        return new Plan(d.Intention, d.Day, steps, null, d.Until != null ? Minute(d.Until, where) : (int?)null);
    }

    private static void ScheduleQuest(World world, ScenarioDefinition s, QuestDef q, string? language)
    {
        string where = $"Quest '{q.Text}'";
        if (world.FindAgent(q.Giver) == null) throw new ScenarioException($"{where}: unknown giver '{q.Giver}'");
        if (!QuestKinds.IsKnown(q.Kind)) throw new ScenarioException($"{where}: unknown kind '{q.Kind}' (use {string.Join(", ", QuestKinds.All)})");
        if (world.FindAgent(q.Target) == null) throw new ScenarioException($"{where}: unknown target '{q.Target}'");
        if (q.Item != null && world.FindItem(q.Item) == null) throw new ScenarioException($"{where}: unknown item '{q.Item}'");
        if (q.RewardItem != null && world.FindItem(q.RewardItem) == null) throw new ScenarioException($"{where}: unknown reward item '{q.RewardItem}'");
        int hour = q.Hour ?? s.StartHour;
        int tick = (q.Day - 1) * World.TicksPerDay + hour * World.TicksPerHour;
        string text = language != null && q.Texts.TryGetValue(language, out var translated) ? translated : q.Text;
        world.Quests.ScheduleOffer(tick, q.Giver, q.Kind, q.Target, q.Item, q.Reward, text, q.DeadlineHours, q.RewardItem);
    }

    private static PlayerCommand ToCommand(World world, PackDefinition pack, CommandDef c, int index)
    {
        string where = $"Script step {index + 1} ({c.Action})";
        if (c.Day < 1 || c.Hour is < 0 or > 23 || c.Minute is < 0 or > 59)
            throw new ScenarioException($"{where}: invalid time (day {c.Day}, {c.Hour}:{c.Minute})");
        int tick = (c.Day - 1) * World.TicksPerDay + c.Hour * World.TicksPerHour + c.Minute / (60 / World.TicksPerHour);

        switch (c.Action)
        {
            case "goto":
                if (world.FindPlace(c.Place) == null) throw new ScenarioException($"{where}: unknown place '{c.Place}'");
                break;
            case "deed":
                if (!pack.HasDeed(c.Deed)) throw new ScenarioException($"{where}: deed '{c.Deed}' is not in pack '{pack.Name}'");
                if (c.Target != null && world.FindAgent(c.Target) == null) throw new ScenarioException($"{where}: unknown target '{c.Target}'");
                if (c.Item != null && world.FindItem(c.Item) == null) throw new ScenarioException($"{where}: unknown item '{c.Item}'");
                break;
            case "buy":
                var trader = world.FindAgent(c.Target);
                if (trader == null || !trader.Has(Tags.Trader)) throw new ScenarioException($"{where}: '{c.Target}' is not a trader");
                if (c.Price <= 0) throw new ScenarioException($"{where}: price must be greater than 0");
                break;
            default:
                throw new ScenarioException($"{where}: unknown action '{c.Action}' (use goto, deed or buy)");
        }
        return new PlayerCommand(tick, c.Action, c.Place, c.Deed, c.Target, c.Item, c.Price);
    }
}
