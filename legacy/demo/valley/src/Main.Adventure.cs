using Godot;
using Kinloom.Core;

namespace Valley;

/// <summary>The adventure layer: beasts and bandits that hunt, allies that fight, loot, healing, the katana,
/// arrests with real choices, reputation, and an objective tracker with an arrow.</summary>
public partial class Main
{
    private readonly Dictionary<string, (Vector2 Target, float Until)> _wander = new();
    private readonly Dictionary<string, float> _allyCooldown = new();
    private readonly RandomNumberGenerator _advRng = new() { Seed = 11 };
    private int _lootCount;
    private Node2D _arrow = null!;
    private Label _arrowLabel = null!;

    private bool IsNight => World.Hour >= 21 || World.Hour < 5;

    private static bool IsMonster(Agent a) => a.Has("monster");

    private int PlayerDamage => World.Items.Any(i => i.Id == "katana" && i.OwnerId == _player.Agent.Id) ? 5 : 3;

    private void SetupAdventure()
    {
        _arrow = new Node2D { ZIndex = 40, Visible = false };
        var tri = new Polygon2D { Polygon = new[] { new Vector2(7, 0), new Vector2(-4, -5), new Vector2(-4, 5) }, Color = new Color(Assets.Gold, 0.9f) };
        _arrow.AddChild(tri);
        _player.AddChild(_arrow);
        _arrowLabel = new Label { Scale = new Vector2(0.33f, 0.33f), ZIndex = 41, Visible = false };
        _arrowLabel.AddThemeFontOverride("font", Assets.Font);
        _arrowLabel.AddThemeFontSizeOverride("font_size", 26);
        _arrowLabel.AddThemeColorOverride("font_color", Assets.Gold);
        _arrowLabel.AddThemeColorOverride("font_outline_color", Colors.Black);
        _arrowLabel.AddThemeConstantOverride("outline_size", 8);
        _player.AddChild(_arrowLabel);
        foreach (var a in _actors.Values)
            if (a.Agent.Has(WorldEvents.HostileTag)) a.ShowHealth = true;
    }

    // ------------------------------------------------------------------ enemies

    /// <summary>Beasts wander around their den and hunt the traveller on sight (farther at night). Bandits guard their camp.</summary>
    private bool DriveHostile(Actor actor, float dt, float speedScale)
    {
        var a = actor.Agent;
        if (!a.Has(WorldEvents.HostileTag) || a.Intent.Kind != IntentKind.Routine) return false;
        bool raider = !IsMonster(a) && a.Plan != null; // raiders follow their raid plan (Core)
        if (raider) return false;
        float sight = IsMonster(a) ? (IsNight ? 150f : 90f) : 110f;
        float dist = actor.GlobalPosition.DistanceTo(_player.GlobalPosition);
        var home = World.FindPlace(a.HomePlaceId);
        bool leashed = home != null && WorldMap.ToWorld(home.Position).DistanceTo(_player.GlobalPosition) > (IsMonster(a) ? 260f : 200f);
        if (_player.Agent.Active && _knockedOut <= 0 && dist < sight && !leashed)
        {
            float angle = a.Id.Sum(c => c) * 2.39996f; // each foe takes its own side
            var spot = _player.GlobalPosition + new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * 12f;
            if (dist > 14f) actor.FollowDestination(WorldMap.ToSim(spot), dt, _map, Actor.RunSpeed * 0.85f * speedScale);
            else actor.Face(_player.GlobalPosition - actor.GlobalPosition);
            EnemyStrike(actor, dt);
            return true;
        }
        if (!_wander.TryGetValue(a.Id, out var w) || _clock > w.Until || actor.GlobalPosition.DistanceTo(w.Target) < 8f)
        {
            var center = home != null ? WorldMap.ToWorld(home.Position) : actor.GlobalPosition;
            var r = (home?.Radius ?? 3f) * WorldMap.T;
            // wander forward-ish (no sharp about-turns), and drift back toward the den when too far
            float heading = actor.Facing.Angle() + _advRng.RandfRange(-1.2f, 1.2f);
            var next = actor.GlobalPosition + Vector2.FromAngle(heading) * _advRng.RandfRange(24f, 48f);
            if (next.DistanceTo(center) > r) next = center + (next - center).LimitLength(r * 0.6f);
            w = (next, _clock + _advRng.RandfRange(3f, 7f));
            _wander[a.Id] = w;
        }
        actor.FollowDestination(WorldMap.ToSim(w.Target), dt, _map, Actor.WalkSpeed * 0.6f * speedScale);
        return true;
    }

    private readonly Dictionary<string, float> _windup = new();

    /// <summary>Enemies telegraph: a short flash, then the blow lands only if the traveller is still in reach (dash to dodge).</summary>
    private void EnemyStrike(Actor enemy, float dt)
    {
        string id = enemy.Agent.Id;
        if (_windup.TryGetValue(id, out float w))
        {
            w -= dt;
            if (w > 0) { _windup[id] = w; return; }
            _windup.Remove(id);
            enemy.PlayAttack();
            if (!IsMonster(enemy.Agent)) SlashFx(enemy.GlobalPosition + enemy.Facing * 10f, enemy.Facing);
            if (enemy.GlobalPosition.DistanceTo(_player.GlobalPosition) > 21f || _dashTime > 0) { FloatText(_player.GlobalPosition + new Vector2(0, -20), L10n.T("dodged"), Assets.Mist); return; }
            int damage = id == "crow" ? 3 : IsMonster(enemy.Agent) ? (enemy.Look == "Beast" ? 2 : 1) : 2;
            Hit(enemy, _player, damage);
            return;
        }
        _banditCooldown.TryGetValue(id, out float cd);
        cd -= dt;
        _banditCooldown[id] = cd;
        if (cd > 0 || WorldPaused || enemy.GlobalPosition.DistanceTo(_player.GlobalPosition) > 18f) return;
        _banditCooldown[id] = id == "crow" ? 1.3f : 1.8f;
        _windup[id] = 0.4f;
        enemy.Flash();
    }

    /// <summary>Companions and guards fight any hostile close to them.</summary>
    private bool DriveAlly(Actor actor, float dt, float speedScale)
    {
        var a = actor.Agent;
        bool companion = a.FollowId == _player.Agent.Id;
        if (!companion && !a.Has(Tags.Authority)) return false;
        var foe = _actors.Values.Where(e => e.Agent.Active && e.Agent.Has(WorldEvents.HostileTag) && e.Visible)
            .OrderBy(e => e.GlobalPosition.DistanceTo(actor.GlobalPosition)).FirstOrDefault();
        if (foe == null || foe.GlobalPosition.DistanceTo(actor.GlobalPosition) > (companion ? 110f : 90f)) return false;
        if (foe.GlobalPosition.DistanceTo(actor.GlobalPosition) > 16f)
            actor.FollowDestination(WorldMap.ToSim(foe.GlobalPosition), dt, _map, Actor.RunSpeed * speedScale);
        _allyCooldown.TryGetValue(a.Id, out float cd);
        cd -= dt;
        if (cd <= 0 && foe.GlobalPosition.DistanceTo(actor.GlobalPosition) <= 18f)
        {
            cd = 1.1f;
            actor.Face(foe.GlobalPosition - actor.GlobalPosition);
            actor.PlayAttack();
            SlashFx(foe.GlobalPosition, actor.Facing);
            Hit(actor, foe, 2);
        }
        _allyCooldown[a.Id] = cd;
        return true;
    }

    /// <summary>A beast's or bandit's fall: gold, what they carried, sometimes a potion.</summary>
    private void DropLoot(Actor fallen)
    {
        if (!IsMonster(fallen.Agent) || _advRng.Randf() > 0.35f) return;
        var potion = World.Add(new Item($"potion{++_lootCount}", L10n.French ? "Potion de soin" : "Healing Potion", WorldMap.ToSim(fallen.GlobalPosition), 3f, _player.Agent.Id, new[] { "consumable", "potion" }));
        _hud.Feed(L10n.T("You find a {0}.", $"[color=#ffc85a]{potion.Name}[/color]"), Assets.Gold, 10);
    }

    // ------------------------------------------------------------------ healing and loose items

    private void UseHealing()
    {
        var pick = World.Items.FirstOrDefault(i => i.OwnerId == _player.Agent.Id && (i.Has("potion") || i.Id == "herbs" || i.Id == "buns"));
        if (pick == null) { _hud.Feed(L10n.T("Nothing to heal with. Buy food, or ask Sen the healer."), Assets.Mist, 4); return; }
        int heal = pick.Has("potion") ? 6 : pick.Id == "herbs" ? 8 : 3;
        var p = _player.Agent;
        p.Health = Math.Min(p.MaxHealth, p.Health + heal);
        pick.OwnerId = null;
        pick.Tags.Add("used");
        _audio.Sfx("thought", -6, 1.3f);
        FloatText(_player.GlobalPosition + new Vector2(0, -20), $"+{heal}", Assets.Jade);
        _hud.Feed(L10n.T("You use the {0} (+{1} health).", pick.Name, heal), Assets.Jade, 6);
    }

    // ------------------------------------------------------------------ justice

    private Agent? _arrestingGuard;

    private void OnArrest(JournalEntry e)
    {
        if (e.TargetId != _player.Agent.Id || _knockedOut > 0) return;
        _arrestingGuard = World.FindAgent(e.AgentId);
        if (_arrestingGuard == null) return;
        int fine = Fine();
        CloseDialogue();
        _hud.ShowArrest(L10n.T("{0} seizes your arm: \"You are under arrest.\"", _arrestingGuard.Name),
            new (string, Action)[]
            {
                (L10n.T("Pay the fine ({0} g)", fine), () => PayFine(fine)),
                (L10n.T("Go to jail (6 hours)"), GoToJail),
                (L10n.T("Resist"), Resist),
            });
        _audio.Sfx("alert", -4);
    }

    private int Fine() => 15;

    private void PayFine(int fine)
    {
        var p = _player.Agent;
        if (p.Gold < fine) { _hud.Feed(L10n.T("Not enough gold for the fine."), Assets.Blood, 4); return; }
        p.Gold -= fine;
        if (_arrestingGuard != null) _arrestingGuard.Gold += fine;
        World.Journal.Add(World.Tick, "consequence", p.Id, $"{p.Name} pays a fine of {fine} to {_arrestingGuard?.Name}", null, _arrestingGuard?.Id);
        _hud.HideArrest();
        _audio.Sfx("coin", -6);
        _hud.Feed(L10n.T("You pay the fine. The village will remember, but you walk free."), Assets.Gold, 10);
    }

    private void GoToJail()
    {
        _hud.HideArrest();
        var post = World.FindPlace("dojo")!;
        _player.Position = WorldMap.ToWorld(post.Position) + new Vector2(0, 20);
        _player.Agent.Position = WorldMap.ToSim(_player.Position);
        World.Journal.Add(World.Tick, "consequence", _player.Agent.Id, $"{_player.Agent.Name} spends six hours in a cell at the Guard Post", null, _arrestingGuard?.Id);
        var tw = _hud.Fade.CreateTween();
        tw.TweenProperty(_hud.Fade, "color:a", 1f, 0.6f);
        tw.TweenCallback(Callable.From(() => { for (int i = 0; i < 6 * World.TicksPerHour; i++) _sim.Step(); }));
        tw.TweenProperty(_hud.Fade, "color:a", 0f, 0.8f);
        _hud.Banner(L10n.T("Six hours later…"), L10n.T("The cell door creaks open. The village has had time to talk."), Assets.Mist);
    }

    private void Resist()
    {
        _hud.HideArrest();
        if (_arrestingGuard == null) return;
        Actions.PerformDeed(World, _player.Agent, "draw_weapon", _arrestingGuard.Id, null);
        _hud.Feed(L10n.T("You pull free and draw steel. Everyone saw."), Assets.Blood, 10);
        _shake = 3f;
    }

    // ------------------------------------------------------------------ reputation and objectives

    private (float Value, string Label, Color Color) Reputation()
    {
        var villagers = World.Agents.Where(a => !a.IsPlayer && a.Present && a.IsAlive && !a.Has(WorldEvents.HostileTag)).ToList();
        float v = villagers.Count == 0 ? 0 : villagers.Average(a => a.Mind.OpinionOf(_player.Agent.Id));
        return v >= 0.3f ? (v, L10n.T("Hero of the valley"), Assets.Jade)
            : v >= 0.1f ? (v, L10n.T("Well liked"), Assets.Jade)
            : v > -0.1f ? (v, L10n.T("A stranger"), Assets.Mist)
            : v > -0.3f ? (v, L10n.T("Suspect"), new Color(1f, 0.7f, 0.4f))
            : (v, L10n.T("Outcast"), Assets.Blood);
    }

    /// <summary>What the player should do next, for each open request, and where to go for the first one.</summary>
    private void UpdateObjectives()
    {
        string pid = _player.Agent.Id;
        var active = World.Quests.All.Where(q => q.HeroId == pid && q.Status == QuestStatus.Active).ToList();
        int offered = World.Quests.All.Count(q => q.Status == QuestStatus.Offered && World.FindAgent(q.GiverId)?.IsAlive == true);
        var rep = Reputation();
        var sb = new System.Text.StringBuilder();
        sb.Append($"[color=#{Hex(rep.Color)}]{L10n.T("Reputation")}: {rep.Label}[/color]\n");
        if (active.Count == 0)
            sb.Append($"[color=#b8c6e6]{(offered > 0 ? L10n.T("{0} people need help — look for the red ! and talk to them (E).", offered) : L10n.T("Explore, talk, and see what the valley needs."))}[/color]");
        foreach (var q in active.Take(3))
            sb.Append($"[color=#ffc85a]▸[/color] {ObjectiveText(q)}\n");
        _hud.Objectives.Text = sb.ToString();

        var target = active.Count > 0 ? ObjectiveTarget(active[0]) : null;
        _arrow.Visible = _arrowLabel.Visible = target.HasValue && _started && target.Value.DistanceTo(_player.GlobalPosition) > 40f;
        if (_arrow.Visible)
        {
            var dir = (target!.Value - _player.GlobalPosition).Normalized();
            _arrow.Position = dir * 20f + new Vector2(0, -4);
            _arrow.Rotation = dir.Angle();
            _arrowLabel.Position = dir * 30f + new Vector2(-6, -8);
            _arrowLabel.Text = $"{(int)(target.Value.DistanceTo(_player.GlobalPosition) / WorldMap.T)}m";
        }
    }

    private string ObjectiveText(Quest q)
    {
        string giver = World.NameOf(q.GiverId), target = World.NameOf(q.TargetId), item = q.ItemId != null ? World.NameOf(q.ItemId) : "";
        var it = World.FindItem(q.ItemId);
        bool carrying = it?.OwnerId == _player.Agent.Id;
        return q.Kind switch
        {
            QuestKinds.RetrieveItem when carrying => L10n.T("Bring the {0} to {1} (talk, then Give).", item, giver),
            QuestKinds.RetrieveItem => L10n.T("Find the {0} for {1}.", item, giver),
            QuestKinds.DeliverItem => L10n.T("Deliver the {0} to {1}.", item, target),
            QuestKinds.Slay => L10n.T("Defeat {0} ({1}'s request).", target, giver),
            QuestKinds.Accuse => L10n.T("Find out who did it, then tell {0} (write it).", giver),
            QuestKinds.Persuade => L10n.T("Win {0} back for {1}.", target, giver),
            QuestKinds.Protect => L10n.T("Keep {0} alive ({1}).", target, giver),
            QuestKinds.Punish => L10n.T("Teach {0} a lesson ({1}).", target, giver),
            _ => q.Reason,
        };
    }

    private Vector2? ObjectiveTarget(Quest q)
    {
        var it = World.FindItem(q.ItemId);
        Vector2? At(string? id) => ActorOf(id) is { } a && a.Visible && a.Agent.IsAlive ? a.GlobalPosition : null;
        switch (q.Kind)
        {
            case QuestKinds.RetrieveItem:
                if (it == null) return At(q.GiverId);
                if (it.OwnerId == _player.Agent.Id) return At(q.GiverId);
                if (it.OwnerId == null && _itemProps.TryGetValue(it.Id, out var prop) && prop.Visible) return prop.GlobalPosition;
                return null; // someone has it: find out who
            case QuestKinds.Slay:
                return At(q.TargetId);
            case QuestKinds.DeliverItem:
                return At(q.TargetId);
            case QuestKinds.Accuse:
                return null; // an investigation: ask around
            default:
                return At(q.TargetId);
        }
    }
}
