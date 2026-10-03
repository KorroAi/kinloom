using Godot;
using Kinloom.Brain;
using Kinloom.Llm;
using Kinloom.Core;
using Kinloom.Scenarios;

namespace Valley;

/// <summary>Asagiri Valley: Godot owns the bodies, Kinloom owns the minds.
/// Core ticks at a fixed rate, the Brain thinks asynchronously, and this node turns both into a living, reacting village.</summary>
public partial class Main : Node2D
{
    public const float SecondsPerTick = 0.75f;
    private static readonly float[] Speeds = { 1f, 3f, 8f };

    private Simulation _sim = null!;
    private Brain _brain = null!;
    private ScenarioDefinition _scenario = null!;
    private WorldMap _map = null!;
    private Hud _hud = null!;
    private GameAudio _audio = null!;
    private Camera2D _camera = null!;
    private readonly Dictionary<string, Actor> _actors = new();
    private Actor _player = null!;
    private float _tickTimer;
    private int _speed;
    private bool _started;
    private int _journalRead;

    private World World => _sim.World;
    private static bool _languageChosen; // survives scene reloads (language toggle, new story)

    public override void _Ready()
    {
        var args = OS.GetCmdlineUserArgs();
        if (!_languageChosen) { L10n.French = args.Contains("--en") ? false : args.Contains("--fr") || L10n.DefaultFrench(); _languageChosen = true; }
        LoadWorld();
        _map = new WorldMap { Name = "Map" };
        AddChild(_map);
        _map.Build(World);

        foreach (var agent in World.Agents)
        {
            var actor = new Actor();
            actor.Setup(agent, _scenario.Agents.Concat(new[] { _scenario.Player! }).First(a => a.Id == agent.Id).Look ?? "Villager");
            actor.Visible = agent.Present;
            _map.Entities.AddChild(actor);
            _actors[agent.Id] = actor;
        }
        _player = _actors[_sim.Player!.Id];

        _camera = new Camera2D { Zoom = new Vector2(3, 3), PositionSmoothingEnabled = true, PositionSmoothingSpeed = 6f };
        _camera.LimitLeft = 0; _camera.LimitTop = 0; _camera.LimitRight = WorldMap.W * WorldMap.T; _camera.LimitBottom = WorldMap.H * WorldMap.T;
        _player.AddChild(_camera);

        _audio = new GameAudio { Name = "Audio" };
        AddChild(_audio);
        _hud = new Hud { Name = "Hud" };
        AddChild(_hud);
        _hud.TypeTick += () => { if (_talkingTo != null) _audio.Voice(_talkingTo.Agent.Id); };
        SetupFx();
        SetupUi();
        SetupAdventure();

        string model = _brain.Client?.Name ?? "no model — rules only";
        _hud.ModelLabel.Text = _brain.Enabled ? L10n.T("mind: {0}", model) : L10n.T("mind: rules only (set DEEPSEEK_API_KEY)");
        _hud.TitleStatus.Text = _brain.Enabled ? L10n.T("Minds powered by {0} through Kinloom Brain", model) : L10n.T("No API key found: villagers run on Kinloom rules only");
        _journalRead = World.Journal.Entries.Count;
        _audio.Music("title");

        int auto = Array.IndexOf(args, "--autoplay");
        if (auto >= 0) StartAutoplay(auto + 1 < args.Length ? args[auto + 1] : "out/valley");
        if (args.Contains("--film")) _ = RunFilm();
        if (args.Contains("--clip")) _ = RunClip();
        if (args.Contains("--motioncheck")) _ = RunMotionCheck();
        int ic = Array.IndexOf(args, "--intentcheck");
        if (ic >= 0) _ = RunIntentCheck(ic + 1 < args.Length ? args[ic + 1] : "out/intent");
        int qa = Array.IndexOf(args, "--qa");
        if (qa >= 0) _ = RunQa(qa + 1 < args.Length ? args[qa + 1] : "out/qa");
        int fx = Array.IndexOf(args, "--fxcheck");
        if (fx >= 0) _ = RunFxCheck(fx + 1 < args.Length ? args[fx + 1] : "out/fx");
    }

    private void LoadWorld()
    {
        string data = ProjectSettings.GlobalizePath("res://data");
        var pack = ScenarioLoader.LoadPack(System.IO.Path.Combine(data, "asagiri.pack.json"));
        _scenario = ScenarioLoader.LoadScenario(System.IO.Path.Combine(data, "asagiri.json"));
        if (L10n.French) pack.UseLanguage("fr");
        _sim = ScenarioLoader.Build(_scenario, pack, L10n.French ? "fr" : null);
        _sim.CaptureFrames = false;
        _sim.ExternalMovement = true;
        var client = LlmConfig.FromEnvironment();
        _brain = new Brain(_sim, client, new BrainOptions
        {
            WorldDescription = _scenario.World ?? "",
            MaxConcurrent = 5,
            AmbientTalkChance = 0.025f,
            DirectorEveryHours = 5,
            PlayerName = "Traveller",
            Language = L10n.BrainLanguage,
            Prices = LlmConfig.PricesFromEnvironment(),
        });
    }

    public void Begin()
    {
        if (_started) return;
        _started = true;
        var tw = _hud.TitleScreen.CreateTween();
        tw.TweenProperty(_hud.TitleScreen, "modulate:a", 0f, 1.2f);
        tw.TweenCallback(Callable.From(() => _hud.TitleScreen.Visible = false));
        _audio.Music("morning");
        _hud.Banner(L10n.T("Day {0}", 1), L10n.T("Autumn in Asagiri. The rice tax is due, and the lantern festival is near."), Assets.Gold);
        _hud.Feed($"[color=#9fe0c0]{L10n.T("You arrive in Asagiri by the forest road. The villagers don't know you yet — but they will notice everything you do.")}[/color]", Assets.Jade, 20);
    }

    private bool WorldPaused => !_started || _hud.DialoguePanel.Visible || _hud.ChroniclePanel.Visible || _hud.ArrestPanel.Visible || _knockedOut > 0;

    public override void _Process(double delta)
    {
        float dt = (float)delta;
        if (!WorldPaused)
        {
            _tickTimer += dt * Speeds[_speed];
            while (_tickTimer >= SecondsPerTick)
            {
                _tickTimer -= SecondsPerTick;
                _sim.Step();
            }
        }
        _brain.Update();

        if (_started && !WorldPaused) UpdatePlayer(dt);
        UpdateNpcs(dt);
        ReadJournal();
        foreach (var e in _brain.DrainEvents()) OnBrainEvent(e);
        UpdateHud(dt);
        UpdateFx(dt);
        UpdateAutoplay(dt);
    }

    private void UpdateNpcs(float dt)
    {
        foreach (var (id, actor) in _actors)
        {
            var a = actor.Agent;
            if (a.IsPlayer) continue;
            if (a.IsAlive && a.Present != actor.Visible) Appear(actor, a.Present); // the fallen stay hidden
            if (!a.Active || WorldPaused && _talkingTo == actor) { if (a.Active) actor.FollowDestination(null, dt, _map, 0); continue; }
            float scale = WorldPaused ? 0f : Math.Min(Speeds[_speed], 3f);
            if (!WorldPaused && DriveHostile(actor, dt, scale)) continue;
            if (!WorldPaused && DriveAlly(actor, dt, scale)) continue;
            float speed = (a.Intent.Kind == IntentKind.Flee || a.Intent.Kind == IntentKind.Approach ? Actor.RunSpeed : Actor.WalkSpeed) * scale;
            actor.FollowDestination(_sim.DestinationOf(a), dt, _map, speed);
            if (a.Has(WorldEvents.HostileTag)) BanditBehaviour(actor, dt);
            if (!actor.Moving) Separate(actor, dt);
        }
    }

    private void Appear(Actor actor, bool present)
    {
        if (present)
        {
            actor.Position = WorldMap.ToWorld(actor.Agent.Position);
            actor.Visible = true;
            actor.Alpha = 0;
            var tw = actor.CreateTween();
            tw.TweenMethod(Callable.From<float>(v => actor.Alpha = v), 0f, 1f, 0.8f);
            Smoke(actor.Position);
        }
        else
        {
            Smoke(actor.Position);
            actor.Visible = false;
        }
    }

    /// <summary>People standing still do not pile up on the same spot.</summary>
    private void Separate(Actor actor, float dt)
    {
        foreach (var other in _actors.Values)
        {
            if (other == actor || !other.Visible || !other.Agent.IsAlive) continue;
            var d = actor.GlobalPosition - other.GlobalPosition;
            float len = d.Length();
            if (len >= 9f) continue;
            if (len < 0.01f) d = new Vector2(actor.Agent.Id.Sum(c => c) % 2 == 0 ? 1 : -1, 0.3f);
            actor.Nudge(d.Normalized() * 18f * dt, _map);
        }
    }

    public Actor? ActorOf(string? id) => id != null && _actors.TryGetValue(id, out var a) ? a : null;

    public string NameOf(string? id) => id == null ? "?" : World.NameOf(id);

    public override void _Notification(int what)
    {
        if (what == NotificationWMCloseRequest) GetTree().Quit();
    }
}
