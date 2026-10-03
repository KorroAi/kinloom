using Godot;
using Kinloom.Core;

namespace Valley;

public partial class Main
{
    private float _dashTime;
    private float _dashCooldown;
    private float _attackCooldown;
    private float _knockedOut;
    private float _iframes;
    private readonly Dictionary<string, float> _banditCooldown = new();
    private const float PlayerSpeed = 78f;
    private const float TalkRange = 30f;

    private Vector2 MoveInput()
    {
        var v = Vector2.Zero;
        // physical keys: WASD on QWERTY is ZQSD on AZERTY
        if (Input.IsPhysicalKeyPressed(Key.W) || Input.IsKeyPressed(Key.Up)) v.Y -= 1;
        if (Input.IsPhysicalKeyPressed(Key.S) || Input.IsKeyPressed(Key.Down)) v.Y += 1;
        if (Input.IsPhysicalKeyPressed(Key.A) || Input.IsKeyPressed(Key.Left)) v.X -= 1;
        if (Input.IsPhysicalKeyPressed(Key.D) || Input.IsKeyPressed(Key.Right)) v.X += 1;
        return v.LengthSquared() > 0 ? v.Normalized() : v + _autoMove;
    }

    private void UpdatePlayer(float dt)
    {
        _attackCooldown -= dt;
        _dashCooldown -= dt;
        _iframes -= dt;
        _player.Alpha = _iframes > 0 && (int)(_iframes * 12) % 2 == 0 ? 0.45f : 1f; // blink while invulnerable
        var move = MoveInput();
        float speed = PlayerSpeed;
        if (_dashTime > 0) { _dashTime -= dt; speed *= 2.8f; }
        _player.MoveWithCollision(move * speed, dt, _map);
        if (_dashTime > 0 && Engine.GetProcessFrames() % 3 == 0) Afterimage(_player);
    }

    public override void _UnhandledInput(InputEvent e)
    {
        if (e is not InputEventKey { Pressed: true, Echo: false } key) return;
        if (!_started)
        {
            if (key.Keycode is Key.Enter or Key.KpEnter or Key.Space) Begin();
            else if (key.Keycode == Key.L) { L10n.French = !L10n.French; GetTree().ReloadCurrentScene(); }
            return;
        }
        if (_hud.ChroniclePanel.Visible)
        {
            if (key.Keycode is Key.Enter or Key.Escape or Key.Space or Key.C) CloseChronicle();
            return;
        }
        if (_hud.DialoguePanel.Visible)
        {
            if (key.Keycode == Key.Escape) CloseDialogue();
            return;
        }
        switch (key.Keycode) // logical keys for commands (AZERTY-friendly); movement uses physical keys
        {
            case Key.E: TryTalk(); break;
            case Key.R: TryTake(); break;
            case Key.Space: Strike(); break;
            case Key.Shift: Dash(); break;
            case Key.Tab: ToggleMind(); break;
            case Key.Q: ToggleQuests(); break;
            case Key.C: ShowChronicle(); break;
            case Key.T: _speed = (_speed + 1) % Speeds.Length; _hud.Feed(L10n.T("Time flows x{0}", Speeds[_speed]), Assets.Mist, 4); break;
            case Key.Escape: _hud.MindPanel.Visible = _hud.QuestPanel.Visible = false; _mindOf = null; break;
            case Key.F9: EndStory(); break;
            case Key.H: UseHealing(); break;
            case Key.F11:
                DisplayServer.WindowSetMode(DisplayServer.WindowGetMode() == DisplayServer.WindowMode.Fullscreen ? DisplayServer.WindowMode.Maximized : DisplayServer.WindowMode.Fullscreen);
                break;
            case Key.F3: _devView = !_devView; _hud.Feed(_devView ? "Developer view: Kinloom arbiter refusals shown" : "Developer view off", Assets.Mist, 4); break;
        }
        GetViewport().SetInputAsHandled();
    }

    public override void _Input(InputEvent e)
    {
        if (e is InputEventKey { Pressed: true, Echo: false, Keycode: Key.Escape } && _hud.DialoguePanel.Visible)
        {
            CloseDialogue();
            GetViewport().SetInputAsHandled();
            return;
        }
        if (e is InputEventMouseButton { Pressed: true, ButtonIndex: MouseButton.Left } && _started && !_hud.DialoguePanel.Visible)
        {
            var world = GetCanvasTransform().AffineInverse() * GetViewport().GetMousePosition();
            var picked = _actors.Values.Where(a => a.Visible && !a.Agent.IsPlayer && a.GlobalPosition.DistanceTo(world + new Vector2(0, 4)) < 12f)
                .OrderBy(a => a.GlobalPosition.DistanceTo(world)).FirstOrDefault();
            if (picked != null) OpenMind(picked);
        }
    }

    private Actor? NearestNpc(float range, bool includeHostile = false) =>
        _actors.Values.Where(a => !a.Agent.IsPlayer && a.Agent.Active && (includeHostile || !a.Agent.Has(WorldEvents.HostileTag)))
            .Where(a => a.GlobalPosition.DistanceTo(_player.GlobalPosition) <= range)
            .OrderBy(a => a.GlobalPosition.DistanceTo(_player.GlobalPosition)).FirstOrDefault();

    private void TryTalk()
    {
        var npc = NearestNpc(TalkRange);
        if (npc == null) { _hud.Feed(L10n.T("Nobody close enough to talk to."), Assets.Mist, 3); return; }
        OpenDialogue(npc);
    }

    private void Dash()
    {
        if (_dashCooldown > 0) return;
        _dashTime = 0.18f;
        _dashCooldown = 0.7f;
        _audio.Sfx("dash", -10);
    }

    private void Strike()
    {
        if (_attackCooldown > 0) return;
        _attackCooldown = 0.38f;
        _player.PlayAttack();
        _audio.Sfx("slash", -8, (float)GD.RandRange(0.9, 1.1));
        var facing = _player.Facing;
        SlashFx(_player.GlobalPosition + facing * 12f, facing);
        var victim = StrikeTarget();
        if (victim != null) Hit(_player, victim, PlayerDamage);
    }

    /// <summary>One blow, one target: the closest person in front of the player.</summary>
    private Actor? StrikeTarget()
    {
        var facing = _player.Facing;
        return _actors.Values.Where(t => !t.Agent.IsPlayer && t.Agent.Active)
            .Where(t => { var to = t.GlobalPosition - _player.GlobalPosition; return to.Length() <= 22f && to.Normalized().Dot(facing) >= 0.2f; })
            .OrderBy(t => t.GlobalPosition.DistanceTo(_player.GlobalPosition)).FirstOrDefault();
    }

    /// <summary>A blow lands: Core decides what it means (crime, witnesses, death); the game shows it.</summary>
    private void Hit(Actor attacker, Actor target, int damage)
    {
        if (target.Agent.IsPlayer)
        {
            if (_iframes > 0) return; // a moment of grace after each blow
            _iframes = 0.7f;
            damage = Math.Min(damage, target.Agent.Health - 1); // the traveller is knocked out, never killed
            if (damage <= 0) { KnockOut(); return; }
        }
        Combat.Attack(World, attacker.Agent, target.Agent, damage);
        target.Flash();
        target.Nudge((target.GlobalPosition - attacker.GlobalPosition).Normalized() * 6f, _map);
        _audio.Sfx("hit", -6, (float)GD.RandRange(0.9, 1.15));
        Shake(attacker.Agent.IsPlayer || target.Agent.IsPlayer ? 3.5f : 1.5f);
        FloatText(target.GlobalPosition + new Vector2(0, -18), $"-{damage}", Assets.Blood);
        if (target.Agent.IsPlayer && target.Agent.Health <= 1) KnockOut();
    }

    private void BanditBehaviour(Actor bandit, float dt)
    {
        _banditCooldown.TryGetValue(bandit.Agent.Id, out float cd);
        cd -= dt;
        _banditCooldown[bandit.Agent.Id] = cd;
        if (cd > 0 || WorldPaused || !_player.Agent.Active) return;
        if (bandit.GlobalPosition.DistanceTo(_player.GlobalPosition) > 20f) return;
        _banditCooldown[bandit.Agent.Id] = 1.3f;
        bandit.Face(_player.GlobalPosition - bandit.GlobalPosition);
        bandit.PlayAttack();
        SlashFx(bandit.GlobalPosition + bandit.Facing * 10f, bandit.Facing);
        Hit(bandit, _player, 2);
    }

    private void KnockOut()
    {
        if (_knockedOut > 0) return;
        _knockedOut = 3.5f;
        _audio.Sfx("death", -6);
        _hud.Banner(L10n.T("Knocked out"), L10n.T("Everything goes dark…"), Assets.Blood);
        var tw = _hud.Fade.CreateTween();
        tw.TweenProperty(_hud.Fade, "color:a", 1f, 1f);
        tw.TweenInterval(1.5f);
        tw.TweenCallback(Callable.From(() =>
        {
            var hut = World.FindPlace("house_sen")!;
            _player.Position = WorldMap.ToWorld(hut.Position) + new Vector2(0, 16);
            _player.Agent.Position = WorldMap.ToSim(_player.Position);
            _player.Agent.Health = _player.Agent.MaxHealth / 2 + 1;
            _hud.Feed(L10n.T("You wake up in Sen's hut. Someone carried you here."), Assets.Jade, 12);
        }));
        tw.TweenProperty(_hud.Fade, "color:a", 0f, 1f);
    }

    // ------------------------------------------------------------------ items

    private readonly Dictionary<string, Node2D> _itemProps = new();
    private readonly Dictionary<string, string?> _itemHome = new();

    private void PlaceItems()
    {
        int i = 0;
        foreach (var item in World.Items)
        {
            var tex = ResourceLoader.Exists($"res://assets/items/{item.Id}.png") ? Assets.Tex($"items/{item.Id}.png") : Assets.Tex("items/chest.png");
            var pos = WorldMap.ToWorld(item.Position) + new Vector2((i % 3 - 1) * 14, 18 + (i % 2) * 6);
            var holder = new Node2D { Position = WorldMap.CellCenter(_map.NearestFree(WorldMap.Cell(pos))) };
            holder.AddChild(new Sprite2D { Texture = Assets.Tex("chars/shadow.png"), Position = new Vector2(0, 5), Modulate = new Color(1, 1, 1, 0.5f) });
            var sprite = new Sprite2D { Texture = tex, Position = new Vector2(0, -2) };
            holder.AddChild(sprite);
            _map.Entities.AddChild(holder);
            var glint = sprite.CreateTween().SetLoops();
            glint.TweenProperty(sprite, "position:y", sprite.Position.Y - 2, 0.8f).SetTrans(Tween.TransitionType.Sine);
            glint.TweenProperty(sprite, "position:y", sprite.Position.Y, 0.8f).SetTrans(Tween.TransitionType.Sine);
            _itemProps[item.Id] = holder;
            _itemHome[item.Id] = item.OwnerId;
            i++;
        }
    }

    private void UpdateItems()
    {
        foreach (var item in World.Items)
            if (_itemProps.TryGetValue(item.Id, out var s)) s.Visible = item.OwnerId == _itemHome[item.Id] && !item.Has("used");
    }

    private void TryTake()
    {
        // an item lying at its place, or one carried by someone right next to you (pickpocketing: stolen goods can be taken back)
        Vector2 Where(Item i) => _itemProps[i.Id].Visible ? _itemProps[i.Id].GlobalPosition
            : ActorOf(i.OwnerId) is { } carrier && carrier.Agent.Active ? carrier.GlobalPosition : new Vector2(-9999, -9999);
        var loose = World.Items.Where(i => i.OwnerId == null && !i.Has("used") && _itemProps.TryGetValue(i.Id, out var pr) && pr.Visible)
            .OrderBy(i => _itemProps[i.Id].GlobalPosition.DistanceTo(_player.GlobalPosition)).FirstOrDefault();
        if (loose != null && _itemProps[loose.Id].GlobalPosition.DistanceTo(_player.GlobalPosition) <= 22f)
        {
            Actions.PickUp(World, _player.Agent, loose.Id); // nobody's: not a crime
            _audio.Sfx("coin", -6, 1.2f);
            _hud.Feed(L10n.T("You pick up the {0}.", $"[color=#ffc85a]{loose.Name}[/color]"), Assets.Gold, 8);
            return;
        }
        var item = World.Items.Where(i => i.OwnerId != _player.Agent.Id && i.OwnerId != null && !i.Has("used") && _itemProps.ContainsKey(i.Id))
            .OrderBy(i => Where(i).DistanceTo(_player.GlobalPosition)).FirstOrDefault();
        if (item == null || Where(item).DistanceTo(_player.GlobalPosition) > 22f)
        {
            _hud.Feed(L10n.T("Nothing within reach to take."), Assets.Mist, 3);
            return;
        }
        Actions.PerformDeed(World, _player.Agent, "steal", item.OwnerId, item.Id);
        _audio.Sfx("coin", -6, 0.8f);
        int witnesses = World.Journal.Entries.Skip(World.Journal.Entries.Count - 30).Count(e => e.Kind == "witness" && e.Text.Contains(item.Name));
        string who = witnesses == 1 ? L10n.T("1 person") : L10n.T("{0} people", witnesses);
        _hud.Feed(witnesses > 0
            ? L10n.T("You take the {0}… and {1} saw you.", $"[color=#ffc85a]{item.Name}[/color]", $"[color=#ee5a50]{who}[/color]")
            : L10n.T("You take the {0}. Nobody seems to have noticed… this time.", $"[color=#ffc85a]{item.Name}[/color]"), witnesses > 0 ? Assets.Blood : Assets.Gold, 10);
    }
}
