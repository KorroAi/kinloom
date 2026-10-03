using Godot;
using Kinloom.Core;

namespace Valley;

/// <summary>The body of one agent: animated sprite, shadow, emote, hit flash, death. It walks where the simulation
/// wants the agent to be (NPCs) or where the input says (player), and writes its position back into Core.</summary>
public partial class Actor : Node2D
{
    public const float WalkSpeed = 44f;   // px/s
    public const float RunSpeed = 72f;

    private static readonly string[] Dirs = { "down", "up", "left", "right" };

    public Agent Agent { get; private set; } = null!;
    public string Look { get; private set; } = "Villager";
    public AnimatedSprite2D Body { get; } = new();
    private readonly Sprite2D _shadow = new();
    private readonly Sprite2D _emote = new() { Visible = false };
    private float _emoteTime;
    private bool _emoteSticky;
    private float _flash;
    private int _dir;
    private List<Vector2> _path = new();
    private Vector2I _pathGoal = new(-1, -1);
    private float _repath;
    private float _attackAnim;
    private bool _deadShown;
    private float _walkHold;
    private Vector2 _lastStep;
    /// <summary>Motion diagnostics: facing changes and abrupt about-turns (used by --motioncheck).</summary>
    public int DirChanges { get; private set; }
    public int Reversals { get; private set; }

    private void Track(Vector2 step)
    {
        if (step.LengthSquared() < 0.0001f) return;
        if (_lastStep.LengthSquared() > 0.0001f && step.Dot(_lastStep) < -0.5f * step.Length() * _lastStep.Length()) Reversals++;
        _lastStep = step;
    }
    public Vector2 Facing => _dir switch { 0 => Vector2.Down, 1 => Vector2.Up, 2 => Vector2.Left, _ => Vector2.Right };
    public bool Moving { get; private set; }
    public float Alpha { get; set; } = 1f;
    /// <summary>Always show the health bar (enemies); others show it only when hurt.</summary>
    public bool ShowHealth { get; set; }

    public override void _Draw()
    {
        if (Agent == null || !Agent.IsAlive || !Visible) return;
        if (!ShowHealth && Agent.Health >= Agent.MaxHealth) return;
        float w = 14f, f = Math.Clamp((float)Agent.Health / Math.Max(1, Agent.MaxHealth), 0f, 1f);
        var color = f > 0.5f ? new Color(0.45f, 0.9f, 0.55f) : f > 0.25f ? new Color(1f, 0.8f, 0.3f) : new Color(0.95f, 0.3f, 0.3f);
        DrawRect(new Rect2(-w / 2 - 0.5f, -15.5f, w + 1, 3.5f), new Color(0, 0, 0, 0.7f * Alpha));
        DrawRect(new Rect2(-w / 2, -15f, w * f, 2.5f), new Color(color, Alpha));
    }

    public void Setup(Agent agent, string look)
    {
        Agent = agent;
        Look = look;
        Name = agent.Id;
        Position = WorldMap.ToWorld(agent.Position);
        _shadow.Texture = Assets.Tex("chars/shadow.png");
        _shadow.Position = new Vector2(0, 6);
        _shadow.Modulate = new Color(1, 1, 1, 0.55f);
        AddChild(_shadow);
        Body.SpriteFrames = Frames(look);
        Body.Position = new Vector2(0, -2);
        AddChild(Body);
        _emote.Position = new Vector2(0, -20);
        _emote.ZIndex = 20;
        AddChild(_emote);
        Body.Play("idle_down");
    }

    private static readonly Dictionary<string, SpriteFrames> FrameCache = new();

    /// <summary>Ninja Adventure sheets: 4 columns (down, up, left, right) × rows: 0-3 walk, 4 attack.</summary>
    private static SpriteFrames Frames(string look)
    {
        if (FrameCache.TryGetValue(look, out var cached)) return cached;
        var tex = Assets.Tex($"chars/{look}/SpriteSheet.png");
        var frames = new SpriteFrames();
        frames.RemoveAnimation("default");
        for (int d = 0; d < 4; d++)
        {
            string walk = "walk_" + Dirs[d], idle = "idle_" + Dirs[d], attack = "attack_" + Dirs[d];
            frames.AddAnimation(walk);
            frames.SetAnimationSpeed(walk, 8);
            for (int row = 0; row < 4; row++) frames.AddFrame(walk, new AtlasTexture { Atlas = tex, Region = new Rect2(d * 16, row * 16, 16, 16) });
            frames.AddAnimation(idle);
            frames.AddFrame(idle, new AtlasTexture { Atlas = tex, Region = new Rect2(d * 16, 0, 16, 16) });
            frames.AddAnimation(attack);
            frames.SetAnimationLoopMode(attack, SpriteFrames.LoopMode.None);
            frames.AddFrame(attack, new AtlasTexture { Atlas = tex, Region = new Rect2(d * 16, tex.GetHeight() >= 80 ? 64 : 0, 16, 16) });
        }
        FrameCache[look] = frames;
        return frames;
    }

    public void ShowEmote(int index, float seconds = 3f, bool sticky = false)
    {
        _emote.Texture = Assets.Emote(index);
        _emote.Visible = true;
        _emoteTime = seconds;
        _emoteSticky = sticky;
    }

    public void ClearStickyEmote()
    {
        if (_emoteSticky) { _emoteSticky = false; _emote.Visible = false; }
    }

    public void Flash() => _flash = 0.18f;

    public void PlayAttack()
    {
        _attackAnim = 0.25f;
        Body.Play("attack_" + Dirs[_dir]);
    }

    public void Face(Vector2 v)
    {
        if (v.LengthSquared() < 0.0001f) return;
        bool horizontal = _dir >= 2;
        // hysteresis: near diagonals keep the current axis instead of flipping every frame
        if (horizontal ? Mathf.Abs(v.Y) > Mathf.Abs(v.X) * 1.4f : Mathf.Abs(v.X) > Mathf.Abs(v.Y) * 1.4f) horizontal = !horizontal;
        int dir = horizontal ? (v.X < 0 ? 2 : 3) : (v.Y < 0 ? 1 : 0);
        if (dir != _dir) DirChanges++;
        _dir = dir;
    }

    /// <summary>Push without going through walls (knockback, crowd separation).</summary>
    public void Nudge(Vector2 offset, WorldMap map)
    {
        var next = Position + offset;
        if (!map.IsBlocked(WorldMap.Cell(next + new Vector2(0, 4)))) Position = next;
        Agent.Position = WorldMap.ToSim(Position);
    }

    /// <summary>Moves by a velocity with collision against the map grid (player).</summary>
    public void MoveWithCollision(Vector2 velocity, float dt, WorldMap map)
    {
        Moving = velocity.LengthSquared() > 1f;
        if (Moving) Face(velocity);
        var step = velocity * dt;
        var next = Position + new Vector2(step.X, 0);
        if (!Collides(next, map)) Position = next;
        next = Position + new Vector2(0, step.Y);
        if (!Collides(next, map)) Position = next;
        Agent.Position = WorldMap.ToSim(Position);
    }

    private static bool Collides(Vector2 p, WorldMap map)
    {
        foreach (var o in new[] { new Vector2(-5, 2), new Vector2(5, 2), new Vector2(-5, 7), new Vector2(5, 7) })
            if (map.IsBlocked(WorldMap.Cell(p + o))) return true;
        return false;
    }

    /// <summary>NPC movement: follow an A* path towards the simulation's destination.</summary>
    public void FollowDestination(Vec2? destination, float dt, WorldMap map, float speed)
    {
        Moving = false;
        if (destination == null) return;
        var goalWorld = WorldMap.ToWorld(destination.Value);
        var goalCell = map.NearestFree(WorldMap.Cell(goalWorld));
        _repath -= dt;
        if (_path.Count == 0 && Position.DistanceTo(goalWorld) < 14f) return; // arrived: stand still, no re-pathing in place
        bool goalMoved = goalCell != _pathGoal && (_path.Count == 0 || _pathGoal.DistanceTo(goalCell) > 1.5f || _repath <= 0);
        if (goalMoved || (_path.Count == 0 && _repath <= 0))
        {
            _pathGoal = goalCell;
            _path = map.Path(Position, WorldMap.CellCenter(goalCell));
            // never walk back to a node we have already passed (happens when the goal moves)
            while (_path.Count > 1 && Position.DistanceTo(_path[1]) <= _path[0].DistanceTo(_path[1])) _path.RemoveAt(0);
            _repath = 0.6f;
        }
        if (_path.Count == 0) return;
        var target = _path[0];
        var delta = target - Position;
        float d = delta.Length();
        float move = speed * dt;
        var before = Position;
        if (d <= move)
        {
            Position = target;
            _path.RemoveAt(0);
        }
        else Position += delta / d * move;
        Track(Position - before);
        Moving = true;
        Face(delta);
        Agent.Position = WorldMap.ToSim(Position);
    }

    public override void _Process(double delta)
    {
        float dt = (float)delta;
        QueueRedraw();
        if (!Agent.IsAlive)
        {
            if (!_deadShown)
            {
                _deadShown = true;
                Body.Stop();
                Body.RotationDegrees = 90;
                Body.Modulate = new Color(0.7f, 0.7f, 0.75f);
                _emote.Visible = false;
            }
            return;
        }
        if (Moving) _walkHold = 0.15f; else _walkHold -= dt; // no walk/idle flicker on arrival
        if (_attackAnim > 0) _attackAnim -= dt;
        else Body.Play((_walkHold > 0 ? "walk_" : "idle_") + Dirs[_dir]);

        if (_emote.Visible && !_emoteSticky)
        {
            _emoteTime -= dt;
            if (_emoteTime <= 0) _emote.Visible = false;
        }
        _emote.Position = new Vector2(0, -20 + Mathf.Sin(Time.GetTicksMsec() / 180f) * 1.5f);

        if (_flash > 0)
        {
            _flash -= dt;
            Body.Modulate = new Color(3f, 3f, 3f, Alpha);
        }
        else Body.Modulate = new Color(1, 1, 1, Alpha);
        _shadow.Modulate = new Color(1, 1, 1, 0.55f * Alpha);
    }
}
