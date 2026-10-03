using Godot;
using Kinloom.Core;

namespace Valley;

public partial class Main
{
    private CanvasModulate _tint = null!;
    private readonly List<PointLight2D> _lights = new();
    private PointLight2D _playerLight = null!;
    private CpuParticles2D _rain = null!;
    private CpuParticles2D _leaves = null!;
    private float _shake;
    private float _sadUntil = -1;
    private static Texture2D? _glow;

    private static Texture2D Glow()
    {
        if (_glow != null) return _glow;
        var g = new Gradient();
        g.SetColor(0, new Color(1, 1, 1, 1));
        g.SetColor(1, new Color(1, 1, 1, 0));
        _glow = new GradientTexture2D { Gradient = g, Width = 128, Height = 128, Fill = GradientTexture2D.FillEnum.Radial, FillFrom = new Vector2(0.5f, 0.5f), FillTo = new Vector2(1f, 0.5f) };
        return _glow;
    }

    private void SetupFx()
    {
        _tint = new CanvasModulate { Color = Colors.White };
        AddChild(_tint);
        foreach (var p in _map.Lanterns)
        {
            var l = new PointLight2D { Texture = Glow(), Position = p, Color = new Color(1f, 0.7f, 0.42f), Energy = 0f, TextureScale = 0.6f };
            AddChild(l);
            _lights.Add(l);
        }
        _playerLight = new PointLight2D { Texture = Glow(), Color = new Color(1f, 0.85f, 0.65f), Energy = 0f, TextureScale = 0.9f };
        _player.AddChild(_playerLight);

        _rain = new CpuParticles2D
        {
            Amount = 700, Lifetime = 0.7f, Emitting = false, Texture = Assets.Region("fx/rain.png", new Rect2(0, 0, 8, 8)),
            EmissionShape = CpuParticles2D.EmissionShapeEnum.Rectangle, EmissionRectExtents = new Vector2(420, 10),
            Direction = new Vector2(-0.25f, 1), Spread = 3, Gravity = Vector2.Zero, InitialVelocityMin = 420, InitialVelocityMax = 520,
            Position = new Vector2(0, -200), Modulate = new Color(0.75f, 0.85f, 1f, 0.75f), ZIndex = 50,
        };
        _player.AddChild(_rain);
        _leaves = new CpuParticles2D
        {
            Amount = 26, Lifetime = 7f, Texture = Assets.Region("fx/leaf.png", new Rect2(0, 0, 6, 7)),
            EmissionShape = CpuParticles2D.EmissionShapeEnum.Rectangle, EmissionRectExtents = new Vector2(420, 10),
            Direction = new Vector2(0.4f, 1), Spread = 25, Gravity = new Vector2(6, 12), InitialVelocityMin = 10, InitialVelocityMax = 25,
            AngularVelocityMin = -90, AngularVelocityMax = 90, Position = new Vector2(0, -220), ZIndex = 49,
        };
        _player.AddChild(_leaves);
        // no mist sprite: it read as clouds following the player (user feedback); dawn is carried by the light alone
    }

    /// <summary>Tint for the hour: dawn mist, warm noon, golden dusk, blue night.</summary>
    private static Color SkyColor(float hour)
    {
        (float h, Color c)[] keys =
        {
            (0, new Color(0.2f, 0.24f, 0.44f)), (4.5f, new Color(0.24f, 0.27f, 0.48f)), (6.5f, new Color(0.95f, 0.8f, 0.78f)),
            (9, new Color(1, 1, 1)), (16.5f, new Color(1, 0.98f, 0.94f)), (18.5f, new Color(1f, 0.78f, 0.6f)),
            (20.5f, new Color(0.3f, 0.32f, 0.54f)), (24, new Color(0.2f, 0.24f, 0.44f)),
        };
        for (int i = 0; i < keys.Length - 1; i++)
            if (hour >= keys[i].h && hour <= keys[i + 1].h)
                return keys[i].c.Lerp(keys[i + 1].c, (hour - keys[i].h) / (keys[i + 1].h - keys[i].h));
        return Colors.White;
    }

    private void UpdateFx(float dt)
    {
        float hour = World.MinuteOfDay / 60f + _tickTimer / SecondsPerTick / World.TicksPerHour;
        bool storm = World.Events.Active.Any(e => e.Kind == WorldEvents.Storm);
        bool festival = World.Events.Active.Any(e => e.Kind == WorldEvents.Festival);
        bool raid = World.Events.Active.Any(e => e.Kind == WorldEvents.BanditRaid);
        var sky = SkyColor(hour);
        if (storm) sky = sky.Lerp(new Color(0.45f, 0.5f, 0.62f), 0.55f);
        _tint.Color = _tint.Color.Lerp(sky, Math.Min(1f, dt * 2f));
        float darkness = 1f - sky.V;
        foreach (var l in _lights) l.Energy = Mathf.Lerp(l.Energy, darkness > 0.25f || festival ? (festival ? 0.95f : 0.7f) : 0f, dt * 2f);
        _playerLight.Energy = Mathf.Lerp(_playerLight.Energy, darkness > 0.3f ? 0.35f : 0f, dt * 2f);
        _rain.Emitting = storm;
        _leaves.Emitting = !storm;

        if (_shake > 0)
        {
            _shake = Math.Max(0, _shake - dt * 12f);
            _camera.Offset = new Vector2((float)GD.RandRange(-_shake, _shake), (float)GD.RandRange(-_shake, _shake));
        }
        else _camera.Offset = Vector2.Zero;

        if (!_started) return;
        bool fighting = _actors.Values.Any(a => a.Agent.Active && a.Agent.Has(WorldEvents.HostileTag) && a.GlobalPosition.DistanceTo(_player.GlobalPosition) < 160f);
        string track = fighting ? "fight" : raid ? "tension" : _clock < _sadUntil ? "sad" : festival ? "festival" : hour >= 20.5f || hour < 5f ? "night" : hour < 9f ? "morning" : "day";
        _audio.Music(track);
        _audio.Ambient(storm ? "rain" : null);
    }

    private void Shake(float amount) => _shake = Math.Max(_shake, amount);

    private void FloatText(Vector2 at, string text, Color color)
    {
        var l = new Label { Text = text, Position = at + new Vector2(-40, 0), Size = new Vector2(80, 20), HorizontalAlignment = HorizontalAlignment.Center, ZIndex = 60, Scale = new Vector2(0.33f, 0.33f), PivotOffset = new Vector2(40, 10) };
        l.AddThemeFontOverride("font", Assets.Font);
        l.AddThemeFontSizeOverride("font_size", 32);
        l.AddThemeColorOverride("font_color", color);
        l.AddThemeColorOverride("font_outline_color", Colors.Black);
        l.AddThemeConstantOverride("outline_size", 8);
        AddChild(l);
        var tw = l.CreateTween().SetParallel();
        tw.TweenProperty(l, "position:y", at.Y - 22, 1.1f).SetEase(Tween.EaseType.Out).SetTrans(Tween.TransitionType.Cubic);
        tw.TweenProperty(l, "modulate:a", 0f, 1.1f).SetDelay(0.4f);
        tw.Chain().TweenCallback(Callable.From(l.QueueFree));
    }

    private void SlashFx(Vector2 at, Vector2 dir)
    {
        var frames = new SpriteFrames();
        frames.AddAnimation("slash");
        frames.SetAnimationLoopMode("slash", SpriteFrames.LoopMode.None);
        frames.SetAnimationSpeed("slash", 18);
        for (int i = 0; i < 4; i++) frames.AddFrame("slash", Assets.Region("fx/slash.png", new Rect2(i * 32, 0, 32, 32)));
        var fx = new AnimatedSprite2D { SpriteFrames = frames, Position = at, Rotation = dir.Angle(), ZIndex = 30, Scale = new Vector2(0.8f, 0.8f) };
        AddChild(fx);
        fx.Play("slash");
        fx.AnimationFinished += fx.QueueFree;
    }

    private void Smoke(Vector2 at)
    {
        var frames = new SpriteFrames();
        frames.AddAnimation("puff");
        frames.SetAnimationLoopMode("puff", SpriteFrames.LoopMode.None);
        frames.SetAnimationSpeed("puff", 14);
        for (int i = 0; i < 6; i++) frames.AddFrame("puff", Assets.Region("fx/smoke.png", new Rect2(i * 32, 0, 32, 32)));
        var fx = new AnimatedSprite2D { SpriteFrames = frames, Position = at, ZIndex = 30 };
        AddChild(fx);
        fx.Play("puff");
        fx.AnimationFinished += fx.QueueFree;
    }

    private void Afterimage(Actor actor)
    {
        var ghost = new Sprite2D { Texture = actor.Body.SpriteFrames.GetFrameTexture(actor.Body.Animation, actor.Body.Frame), Position = actor.Position + actor.Body.Position, Modulate = new Color(0.6f, 0.85f, 1f, 0.5f) };
        _map.Entities.AddChild(ghost);
        var tw = ghost.CreateTween();
        tw.TweenProperty(ghost, "modulate:a", 0f, 0.25f);
        tw.TweenCallback(Callable.From(ghost.QueueFree));
    }
}
