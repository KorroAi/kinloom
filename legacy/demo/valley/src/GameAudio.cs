using Godot;

namespace Valley;

/// <summary>Music that follows the mood (day, night, festival, tension, fight) with crossfades, and pooled sound effects.</summary>
public partial class GameAudio : Node
{
    private readonly AudioStreamPlayer _a = new() { Bus = "Master" };
    private readonly AudioStreamPlayer _b = new() { Bus = "Master" };
    private readonly AudioStreamPlayer _ambient = new();
    private readonly List<AudioStreamPlayer> _sfx = new();
    private string _current = "";
    private bool _aActive = true;
    public float MusicDb { get; set; } = -9f;

    public override void _Ready()
    {
        AddChild(_a);
        AddChild(_b);
        AddChild(_ambient);
        for (int i = 0; i < 10; i++)
        {
            var p = new AudioStreamPlayer();
            AddChild(p);
            _sfx.Add(p);
        }
    }

    private static AudioStream Load(string name)
    {
        var s = GD.Load<AudioStream>($"res://assets/audio/{name}");
        if (s is AudioStreamOggVorbis ogg) ogg.Loop = true;
        return s;
    }

    public void Music(string track)
    {
        if (track == _current) return;
        _current = track;
        var fadeIn = _aActive ? _b : _a;
        var fadeOut = _aActive ? _a : _b;
        _aActive = !_aActive;
        fadeIn.Stream = Load($"music_{track}.ogg");
        fadeIn.VolumeDb = -40;
        fadeIn.Play();
        var tw = CreateTween().SetParallel();
        tw.TweenProperty(fadeIn, "volume_db", MusicDb, 2.0f);
        tw.TweenProperty(fadeOut, "volume_db", -40f, 2.0f);
        tw.Chain().TweenCallback(Callable.From(fadeOut.Stop));
    }

    public void Ambient(string? name)
    {
        if (name == null) { _ambient.Stop(); return; }
        var s = GD.Load<AudioStreamWav>($"res://assets/audio/{name}.wav");
        s.LoopMode = AudioStreamWav.LoopModeEnum.Forward;
        s.LoopEnd = (int)(s.GetLength() * s.MixRate);
        if (_ambient.Stream == s && _ambient.Playing) return;
        _ambient.Stream = s;
        _ambient.VolumeDb = -14;
        _ambient.Play();
    }

    public void Sfx(string name, float db = -6f, float pitch = 1f)
    {
        var player = _sfx.FirstOrDefault(p => !p.Playing) ?? _sfx[0];
        player.Stream = GD.Load<AudioStream>($"res://assets/audio/{name}.wav");
        player.VolumeDb = db;
        player.PitchScale = pitch;
        player.Play();
    }

    /// <summary>A little voice blip per character while dialogue types out; each person has their own pitch.</summary>
    public void Voice(string agentId)
    {
        int h = agentId.Sum(c => c); // stable across runs (string.GetHashCode is randomized)
        Sfx($"voice{1 + h % 10}", -16f, 0.85f + (h % 7) * 0.06f);
    }
}
