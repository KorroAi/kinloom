using System.Numerics;
using Kinloom.Core;
using Raylib_cs;
using static Raylib_cs.Raylib;

namespace Kinloom.Game;

/// <summary>Window, input and the main loop. With an autoplay directory, plays a fixed sequence and saves screenshots.</summary>
public sealed class GameApp
{
    private static readonly (string Label, float SecondsPerTick)[] Speeds = { ("x1", 0.4f), ("x3", 0.4f / 3), ("x10", 0.04f) };

    private readonly GameSession _g;
    private readonly Renderer _renderer;
    private readonly string? _autoplayDir;
    private Agent? _selected;
    private string? _toast;
    private float _toastTime;
    private int _speed;

    public GameApp(GameSession session, string? autoplayDir)
    {
        _g = session;
        _renderer = new Renderer(session);
        _autoplayDir = autoplayDir;
        _g.SecondsPerTick = Speeds[0].SecondsPerTick;
    }

    public void Run()
    {
        SetConfigFlags(ConfigFlags.Msaa4xHint | ConfigFlags.VSyncHint);
        InitWindow(Renderer.Width, Renderer.Height, "Kinloom - village prototype");
        SetTargetFPS(60);
        Text.Load();
        var script = _autoplayDir != null ? Autoplay().GetEnumerator() : null;
        int waitFrames = 0;

        while (!WindowShouldClose())
        {
            float dt = script != null ? 1f / 60f : GetFrameTime();
            if (script == null) HandleInput();
            _g.Update(dt, script == null ? ReadMove() : new Vec2(0, 0));
            if (_toastTime > 0) _toastTime -= dt;

            BeginDrawing();
            _renderer.Draw(_selected, _toast, Math.Clamp(_toastTime, 0f, 1f), Speeds[_speed].Label);
            EndDrawing();

            if (script != null)
            {
                if (waitFrames > 0) { waitFrames--; continue; }
                if (!script.MoveNext()) break;
                waitFrames = script.Current;
            }
        }
        Text.Unload();
        CloseWindow();
    }

    private void Toast(string message)
    {
        _toast = message;
        _toastTime = 3.5f;
    }

    private void HandleInput()
    {
        if (IsKeyPressed(KeyboardKey.Space)) _g.Paused = !_g.Paused;
        if (IsKeyPressed(KeyboardKey.Tab)) { _speed = (_speed + 1) % Speeds.Length; _g.SecondsPerTick = Speeds[_speed].SecondsPerTick; }
        if (_g.Paused) return;
        if (IsKeyPressed(KeyboardKey.E)) Toast(_g.Steal());
        if (IsKeyPressed(KeyboardKey.F)) Toast(_g.DrawWeapon());
        if (IsKeyPressed(KeyboardKey.H)) Toast(_g.Help());
        if (IsKeyPressed(KeyboardKey.P)) Toast(_g.Pay());
        if (IsKeyPressed(KeyboardKey.B)) Toast(_g.Buy());
        if (IsMouseButtonPressed(MouseButton.Right)) _selected = null;
        if (IsMouseButtonPressed(MouseButton.Left)) Select(GetMousePosition());
    }

    private void Select(Vector2 mouse)
    {
        if (!Renderer.InMap(mouse)) return;
        _selected = _g.World.Agents.Where(a => !a.IsPlayer)
            .Select(a => (a, d: Vector2.Distance(Renderer.ToScreen(_g.DisplayPosition(a)), mouse)))
            .Where(t => t.d < 20).OrderBy(t => t.d).Select(t => t.a).FirstOrDefault();
    }

    private static Vec2 ReadMove()
    {
        float x = 0, y = 0;
        if (IsKeyDown(KeyboardKey.A) || IsKeyDown(KeyboardKey.Left)) x -= 1;
        if (IsKeyDown(KeyboardKey.D) || IsKeyDown(KeyboardKey.Right)) x += 1;
        if (IsKeyDown(KeyboardKey.W) || IsKeyDown(KeyboardKey.Up)) y -= 1;
        if (IsKeyDown(KeyboardKey.S) || IsKeyDown(KeyboardKey.Down)) y += 1;
        return new Vec2(x, y);
    }

    // ---------- autoplay: a fixed play-through that saves screenshots, used to check the rendering ----------

    private IEnumerable<int> Autoplay()
    {
        Directory.CreateDirectory(_autoplayDir!);
        int shot = 0;
        IEnumerable<int> Shot(string name)
        {
            yield return 2; // let two frames render first
            var image = LoadImageFromScreen();
            ExportImage(image, Path.Combine(_autoplayDir!, $"{++shot:00}-{name}.png"));
            UnloadImage(image);
            yield return 0;
        }
        void GoTo(string place) => _g.Player.Position = _g.World.FindPlace(place)!.Position.Offset(-2, 2);
        void FastForwardTo(int day, int hour, int minute = 0)
        {
            int target = (day - 1) * World.TicksPerDay + hour * World.TicksPerHour + minute / 5;
            if (target > _g.World.Tick) _g.WarmUp(target - _g.World.Tick);
            _toastTime = 0; // a skipped stretch of time makes the last message stale
        }

        FastForwardTo(1, 9, 45);
        GoTo("bakery");
        yield return 30;
        foreach (var f in Shot("morning-bakery")) yield return f;

        Toast(_g.Steal());
        yield return 40;
        foreach (var f in Shot("theft-seen")) yield return f;

        _g.SecondsPerTick = 0.05f;
        yield return 25;
        foreach (var f in Shot("baker-reports")) yield return f;

        GoTo("square");
        for (int i = 0; i < 400 && !_g.Feed.Any(l => l.Text.Contains("confronts")); i++) yield return 1;
        _selected = _g.World.GetAgent("guard");
        _g.SecondsPerTick = 0.4f;
        yield return 20;
        foreach (var f in Shot("guard-confronts")) yield return f;

        FastForwardTo(1, 19, 30);
        GoTo("tavern");
        _selected = _g.World.GetAgent("smith");
        yield return 40;
        foreach (var f in Shot("tavern-rumors")) yield return f;

        FastForwardTo(2, 10, 50);
        GoTo("forge");
        yield return 10;
        Toast(_g.Buy());
        yield return 20;
        foreach (var f in Shot("smith-overcharges")) yield return f;

        FastForwardTo(2, 12, 20);
        GoTo("square");
        _selected = _g.World.GetAgent("farmer");
        yield return 20;
        Toast(_g.DrawWeapon());
        yield return 50;
        foreach (var f in Shot("weapon-panic")) yield return f;
    }
}
