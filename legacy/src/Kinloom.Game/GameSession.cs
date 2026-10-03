using Kinloom.Core;

namespace Kinloom.Game;

public sealed record FeedLine(int Tick, string Kind, string Text);

/// <summary>A "thing to try" that ticks off when the player first triggers that system.</summary>
public sealed class Goal
{
    public Goal(string id, string text) { Id = id; Text = text; }
    public string Id { get; }
    public string Text { get; }
    public bool Done { get; internal set; }
}

/// <summary>Real-time game layer over the Kinloom simulation: player movement, player actions, event feed, interpolation.
/// No rendering here, so it is fully testable.</summary>
public sealed class GameSession
{
    public const float PlayerSpeed = 10f;   // world units per second
    public const float InteractRange = 4f;  // how close the player must be to act on someone or something
    public const float MapWidth = 100f, MapHeight = 60f;

    private static readonly Dictionary<string, float> BasePrices = new() { ["baker"] = 2f, ["smith"] = 10f, ["innkeeper"] = 3f };
    private static readonly HashSet<string> FeedKinds = new() { "deed", "reaction", "rumor", "report", "consequence", "restock", "warning", "error" };
    public const int RestockHour = 6;

    private readonly Dictionary<string, Vec2> _previous = new();
    private readonly Dictionary<string, string> _originalOwner = new(); // item id -> trader who restocks it
    private int _restocks;
    private readonly List<FeedLine> _feed = new();
    private float _accumulator;
    private int _journalRead;

    public GameSession(Simulation sim)
    {
        Sim = sim;
        Sim.CaptureFrames = false; // a live game needs no replay buffer
        Player = sim.Player ?? throw new ArgumentException("The scenario needs a player");
        foreach (var a in World.Agents) _previous[a.Id] = a.Position;
        foreach (var i in World.Items) if (i.OwnerId != null) _originalOwner[i.Id] = i.OwnerId;
        Goals = new List<Goal>
        {
            new("steal", "Steal something"),
            new("flee", "Make villagers run away"),
            new("confronted", "Get confronted by the guard"),
            new("rumor", "Hear a rumor about you spread"),
            new("overcharged", "Get overcharged by a trader"),
            new("refused", "Get refused service"),
            new("forgiven", "Win someone back after a bad deed"),
        };
    }

    public IReadOnlyList<Goal> Goals { get; }

    public Simulation Sim { get; }
    public World World => Sim.World;
    public Agent Player { get; }
    public float SecondsPerTick { get; set; } = 0.4f;
    public bool Paused { get; set; }
    public IReadOnlyList<FeedLine> Feed => _feed;

    /// <summary>0..1: how far real time is between the previous tick and the next one.</summary>
    public float TickProgress => SecondsPerTick <= 0 ? 1f : Math.Clamp(_accumulator / SecondsPerTick, 0f, 1f);

    public void WarmUp(int ticks)
    {
        for (int i = 0; i < ticks; i++) Tick();
        CollectFeed();
    }

    public void Update(float dt, Vec2 moveInput)
    {
        if (Paused) return;
        MovePlayer(dt, moveInput);
        _accumulator += dt;
        while (_accumulator >= SecondsPerTick)
        {
            _accumulator -= SecondsPerTick;
            Tick();
        }
        CollectFeed();
    }

    private void Tick()
    {
        foreach (var a in World.Agents) _previous[a.Id] = a.Position;
        var held = Player.Position;
        Sim.Step();
        Player.Position = held; // the player is driven by input, not by the simulation
        if (World.Tick % World.TicksPerDay == RestockHour * World.TicksPerHour) Restock();
    }

    /// <summary>Each morning, traders replace what the player stole from them.</summary>
    private void Restock()
    {
        foreach (var stolen in World.Items.Where(i => i.OwnerId == Player.Id && _originalOwner.ContainsKey(i.Id)).ToList())
        {
            string owner = _originalOwner[stolen.Id];
            _originalOwner.Remove(stolen.Id); // the stolen one is the player's now; the new one takes over
            var fresh = World.Add(new Item($"{stolen.Id}-restock{++_restocks}", stolen.Name, stolen.Position, stolen.Value, owner, stolen.Tags));
            _originalOwner[fresh.Id] = owner;
            World.Journal.Add(World.Tick, "restock", owner, $"{Narrator.Short(World.NameOf(owner))} restocks: a new {fresh.Name}.");
        }
    }

    private void MovePlayer(float dt, Vec2 input)
    {
        float len = MathF.Sqrt(input.X * input.X + input.Y * input.Y);
        if (len < 0.001f) return;
        float step = PlayerSpeed * dt / len;
        float x = Math.Clamp(Player.Position.X + input.X * step, 0f, MapWidth);
        float y = Math.Clamp(Player.Position.Y + input.Y * step, 0f, MapHeight);
        Player.Position = new Vec2(x, y);
        _previous[Player.Id] = Player.Position;
    }

    public Vec2 PreviousPosition(Agent a) => _previous.TryGetValue(a.Id, out var p) ? p : a.Position;

    /// <summary>Smoothly interpolated position for drawing (the simulation itself moves in 5-minute steps).</summary>
    public Vec2 DisplayPosition(Agent a)
    {
        if (a.IsPlayer) return a.Position;
        var from = PreviousPosition(a);
        float t = TickProgress;
        return new Vec2(from.X + (a.Position.X - from.X) * t, from.Y + (a.Position.Y - from.Y) * t);
    }

    public Agent? NearestNpc(float range = InteractRange, string? tag = null) =>
        World.Agents.Where(a => !a.IsPlayer && (tag == null || a.Has(tag)) && a.Position.DistanceTo(Player.Position) <= range)
            .OrderBy(a => a.Position.DistanceTo(Player.Position)).FirstOrDefault();

    public Item? NearestStealable(float range = InteractRange) =>
        World.Items.Where(i => i.OwnerId != Player.Id && i.Position.DistanceTo(Player.Position) <= range)
            .OrderBy(i => i.Position.DistanceTo(Player.Position)).FirstOrDefault();

    public string Steal()
    {
        var item = NearestStealable();
        if (item == null) return "Nothing to steal here.";
        string? owner = item.OwnerId;
        Actions.PerformDeed(World, Player, "steal", owner, item.Id);
        CollectFeed();
        return owner == null ? $"You take the {item.Name}." : $"You steal the {item.Name} from {World.NameOf(owner)}.";
    }

    public string DrawWeapon()
    {
        Actions.PerformDeed(World, Player, "draw_weapon", null, null);
        CollectFeed();
        return "You draw your weapon.";
    }

    public string Help()
    {
        var npc = NearestNpc();
        if (npc == null) return "Nobody close enough to help.";
        Actions.PerformDeed(World, Player, "help", npc.Id, null);
        CollectFeed();
        return $"You help {npc.Name}.";
    }

    public string Pay()
    {
        var npc = NearestNpc();
        if (npc == null) return "Nobody close enough to pay.";
        Actions.PerformDeed(World, Player, "pay", npc.Id, null);
        CollectFeed();
        return $"You pay {npc.Name}.";
    }

    public string Buy()
    {
        var trader = NearestNpc(tag: Tags.Trader);
        if (trader == null) return "No trader close enough.";
        float basePrice = BasePrices.TryGetValue(trader.Id, out var p) ? p : 5f;
        var result = Commerce.Trade(World, Player, trader, basePrice);
        Sim.Trades.Add(new TradeLog(World.Tick, trader.Id, Player.Id, result));
        if (!result.Refused && result.Price > basePrice + 0.05f) MarkGoal("overcharged");
        CollectFeed();
        return result.Refused
            ? $"{trader.Name} refuses to serve you."
            : System.FormattableString.Invariant($"{trader.Name} sells to you for {result.Price:0.0} (usual price {basePrice:0.0}).");
    }

    /// <summary>The cause chain of this character's latest decision (reaction, consequence or report).</summary>
    public List<JournalEntry> Why(Agent a)
    {
        var last = World.Journal.Entries.LastOrDefault(e => e.AgentId == a.Id && (e.Kind == "reaction" || e.Kind == "consequence" || e.Kind == "report"));
        return last == null ? new List<JournalEntry>() : World.Journal.Why(last.Id);
    }

    /// <summary>Why(), told as a story: latest decision first, the original deed last.</summary>
    public List<string> WhyStory(Agent a) => Why(a).Select(e => Narrator.Narrate(e, World, Player)).ToList();

    private void CollectFeed()
    {
        var entries = World.Journal.Entries;
        for (; _journalRead < entries.Count; _journalRead++)
        {
            var e = entries[_journalRead];
            if (FeedKinds.Contains(e.Kind)) _feed.Add(new FeedLine(e.Tick, e.Kind, Narrator.Narrate(e, World, Player)));
            CheckGoals(e);
        }
    }

    private void MarkGoal(string goalId)
    {
        var goal = Goals.FirstOrDefault(g => g.Id == goalId);
        if (goal != null) goal.Done = true;
    }

    private void CheckGoals(JournalEntry e)
    {
        string me = Player.Name;
        switch (e.Kind)
        {
            case "deed" when e.AgentId == Player.Id && e.Text.StartsWith(me + " steal"): MarkGoal("steal"); break;
            case "reaction" when e.Text.Contains(" decides to flee ") && e.Text.Contains($"opinion of {me} "): MarkGoal("flee"); break;
            case "consequence" when e.Text.Contains($" confronts {me} "): MarkGoal("confronted"); break;
            case "consequence" when e.Text.Contains($" refuses to serve {me} "): MarkGoal("refused"); break;
            case "rumor" when e.Text.Contains($": {me} "): MarkGoal("rumor"); break;
            case "opinion" when e.Text.Contains($"'s opinion of {me}: -"):
                var parts = e.Text.Split(": ").Last().Split(" -> ");
                if (parts.Length == 2 && float.TryParse(parts[1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float after)
                    && float.TryParse(parts[0], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float before)
                    && after > before) MarkGoal("forgiven");
                break;
        }
    }
}
