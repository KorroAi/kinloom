using Godot;

namespace Valley;

/// <summary>All screen-space UI. Built in code with the pack's wooden panels and the DotGothic16 font.</summary>
public partial class Hud : CanvasLayer
{
    public Label Clock { get; private set; } = null!;
    public Label Status { get; private set; } = null!;
    public HBoxContainer Hearts { get; private set; } = null!;
    public Label GoldLabel { get; private set; } = null!;
    public Label ModelLabel { get; private set; } = null!;
    public Label Inventory { get; private set; } = null!;
    private VBoxContainer _feed = null!;
    private Label _feedTitle = null!;
    private VBoxContainer _titleBox = null!;
    private Vector2 _laidOut;
    private PanelContainer _statsPanel = null!;
    private Label _banner = null!;
    private Label _bannerSub = null!;
    private Control _bubbleLayer = null!;
    public Label Hint { get; private set; } = null!;
    public RichTextLabel Objectives { get; private set; } = null!;

    // dialogue
    public PanelContainer DialoguePanel { get; private set; } = null!;
    public TextureRect DialogueFace { get; private set; } = null!;
    public Label DialogueName { get; private set; } = null!;
    public Label DialogueRole { get; private set; } = null!;
    public RichTextLabel DialogueText { get; private set; } = null!;
    public LineEdit DialogueInput { get; private set; } = null!;
    public HBoxContainer DialogueActions { get; private set; } = null!;
    private string _typeTarget = "";
    private float _typed;
    public bool Typing => _typed < _typeTarget.Length;
    public event Action? TypeTick;

    // panels
    public PanelContainer MindPanel { get; private set; } = null!;
    public RichTextLabel MindText { get; private set; } = null!;
    public TextureRect MindFace { get; private set; } = null!;
    public PanelContainer QuestPanel { get; private set; } = null!;
    public RichTextLabel QuestText { get; private set; } = null!;
    public PanelContainer ChroniclePanel { get; private set; } = null!;
    public RichTextLabel ChronicleText { get; private set; } = null!;
    public Control TitleScreen { get; private set; } = null!;
    public Label TitleStatus { get; private set; } = null!;
    public ColorRect Fade { get; private set; } = null!;
    public PanelContainer ArrestPanel { get; private set; } = null!;
    private RichTextLabel _arrestText = null!;
    private HBoxContainer _arrestButtons = null!;

    public override void _Ready()
    {
        Layer = 10;
        var root = new Control { Theme = Assets.BuildTheme(), MouseFilter = Control.MouseFilterEnum.Ignore };
        root.SetAnchorsPreset(Control.LayoutPreset.FullRect);
        AddChild(root);

        _bubbleLayer = new Control { MouseFilter = Control.MouseFilterEnum.Ignore };
        _bubbleLayer.SetAnchorsPreset(Control.LayoutPreset.FullRect);
        root.AddChild(_bubbleLayer);

        BuildTopLeft(root);
        BuildFeed(root);
        BuildBanner(root);
        BuildDialogue(root);
        BuildMind(root);
        BuildQuests(root);
        BuildChronicle(root);
        BuildArrest(root);

        Hint = Assets.Text(L10n.T("WASD/ZQSD move · E talk · R take · Space strike · Shift dash · H heal · Tab minds · Q quests · C chronicle · T time · F11 window"), 20, new Color(Assets.Paper, 0.8f));
        Hint.Position = new Vector2(24, 1040);
        root.AddChild(Hint);

        Objectives = new RichTextLabel { BbcodeEnabled = true, FitContent = true, ScrollActive = false, CustomMinimumSize = new Vector2(430, 0), MouseFilter = Control.MouseFilterEnum.Ignore };
        Objectives.AddThemeFontSizeOverride("normal_font_size", 19);
        Objectives.AddThemeColorOverride("font_outline_color", new Color(0, 0, 0, 0.9f));
        Objectives.AddThemeConstantOverride("outline_size", 6);
        root.AddChild(Objectives);

        Fade = new ColorRect { Color = new Color(0, 0, 0, 0), MouseFilter = Control.MouseFilterEnum.Ignore };
        Fade.SetAnchorsPreset(Control.LayoutPreset.FullRect);
        root.AddChild(Fade);
        BuildTitle(root);
    }

    // ------------------------------------------------------------------ top left

    private void BuildTopLeft(Control root)
    {
        var panel = _statsPanel = new PanelContainer();
        panel.AddThemeStyleboxOverride("panel", Assets.Flat(new Color(0.06f, 0.05f, 0.08f, 0.78f), new Color(Assets.Gold, 0.55f), 2, 14, 8));
        panel.Position = new Vector2(20, 18);
        root.AddChild(panel);
        var box = new VBoxContainer();
        box.AddThemeConstantOverride("separation", 4);
        panel.AddChild(box);
        Clock = Assets.Text("Day 1 · 07:00", 32, Assets.Paper);
        box.AddChild(Clock);
        Status = Assets.Text("", 20, Assets.Mist);
        box.AddChild(Status);
        var row = new HBoxContainer();
        row.AddThemeConstantOverride("separation", 4);
        Hearts = new HBoxContainer();
        Hearts.AddThemeConstantOverride("separation", 2);
        row.AddChild(Hearts);
        row.AddChild(new Control { CustomMinimumSize = new Vector2(16, 0) });
        row.AddChild(new TextureRect { Texture = Assets.Tex("items/coin.png"), CustomMinimumSize = new Vector2(28, 28), StretchMode = TextureRect.StretchModeEnum.KeepAspectCentered, ExpandMode = TextureRect.ExpandModeEnum.IgnoreSize });
        GoldLabel = Assets.Text("20", 24, Assets.Gold);
        row.AddChild(GoldLabel);
        box.AddChild(row);
        Inventory = Assets.Text("", 18, Assets.Gold);
        Inventory.AutowrapMode = TextServer.AutowrapMode.WordSmart;
        Inventory.CustomMinimumSize = new Vector2(300, 0);
        box.AddChild(Inventory);
        ModelLabel = Assets.Text("", 16, new Color(Assets.Jade, 0.85f));
        box.AddChild(ModelLabel);
    }

    private (int, int) _heartsShown = (-1, -1);

    public void SetHearts(int health, int max)
    {
        if (_heartsShown == (health, max)) return;
        _heartsShown = (health, max);
        foreach (var c in Hearts.GetChildren()) c.QueueFree();
        int hearts = (max + 1) / 2;
        for (int i = 0; i < hearts; i++)
        {
            int value = health - i * 2;
            int frame = value >= 2 ? 4 : value == 1 ? 2 : 0; // the strip goes empty -> full
            var t = new TextureRect
            {
                Texture = Assets.Region("ui/heart.png", new Rect2(frame * 16, 0, 16, 16)),
                CustomMinimumSize = new Vector2(32, 32),
                StretchMode = TextureRect.StretchModeEnum.KeepAspectCentered,
                ExpandMode = TextureRect.ExpandModeEnum.IgnoreSize,
            };
            Hearts.AddChild(t);
        }
    }

    // ------------------------------------------------------------------ feed

    private void BuildFeed(Control root)
    {
        _feedTitle = Assets.Text(L10n.T("THE VALLEY"), 20, new Color(Assets.Gold, 0.9f));
        root.AddChild(_feedTitle);
        _feed = new VBoxContainer { Position = new Vector2(1920 - 500, 50), CustomMinimumSize = new Vector2(480, 0) };
        _feed.AddThemeConstantOverride("separation", 6);
        root.AddChild(_feed);
    }

    public void Feed(string bbcode, Color accent, float life = 30f)
    {
        var card = new PanelContainer { MouseFilter = Control.MouseFilterEnum.Ignore };
        var style = Assets.Flat(new Color(0.05f, 0.05f, 0.08f, 0.72f), new Color(0, 0, 0, 0), 0, 12, 6);
        style.BorderWidthLeft = 5;
        style.BorderColor = accent;
        card.AddThemeStyleboxOverride("panel", style);
        var text = new RichTextLabel { BbcodeEnabled = true, FitContent = true, ScrollActive = false, Text = bbcode, CustomMinimumSize = new Vector2(450, 0), MouseFilter = Control.MouseFilterEnum.Ignore };
        text.AddThemeFontSizeOverride("normal_font_size", 18);
        text.AddThemeConstantOverride("outline_size", 0);
        card.AddChild(text);
        _feed.AddChild(card);
        card.Modulate = new Color(1, 1, 1, 0);
        var tw = card.CreateTween();
        tw.TweenProperty(card, "modulate:a", 1f, 0.35f);
        tw.TweenInterval(life);
        tw.TweenProperty(card, "modulate:a", 0f, 1.2f);
        tw.TweenCallback(Callable.From(card.QueueFree));
        while (_feed.GetChildCount() > 7) _feed.GetChild(0).Free();
    }

    // ------------------------------------------------------------------ banner

    private void BuildBanner(Control root)
    {
        _banner = Assets.Text("", 56, Assets.Gold);
        _banner.HorizontalAlignment = HorizontalAlignment.Center;
        _banner.Position = new Vector2(0, 150);
        _banner.Size = new Vector2(1920, 80);
        _banner.Modulate = new Color(1, 1, 1, 0);
        root.AddChild(_banner);
        _bannerSub = Assets.Text("", 28, Assets.Paper);
        _bannerSub.HorizontalAlignment = HorizontalAlignment.Center;
        _bannerSub.AutowrapMode = TextServer.AutowrapMode.WordSmart;
        _bannerSub.Position = new Vector2(360, 230);
        _bannerSub.Size = new Vector2(1200, 80);
        _bannerSub.Modulate = new Color(1, 1, 1, 0);
        root.AddChild(_bannerSub);
    }

    public void Banner(string title, string subtitle, Color color)
    {
        _banner.Text = title;
        _banner.AddThemeColorOverride("font_color", color);
        _bannerSub.Text = subtitle;
        foreach (var l in new[] { _banner, _bannerSub })
        {
            var tw = l.CreateTween();
            tw.TweenProperty(l, "modulate:a", 1f, 0.5f);
            tw.TweenInterval(4.5f);
            tw.TweenProperty(l, "modulate:a", 0f, 1f);
        }
    }

    // ------------------------------------------------------------------ bubbles

    public sealed class Bubble
    {
        public Actor Actor = null!;
        public PanelContainer Panel = null!;
        public float Life;
    }

    private readonly List<Bubble> _bubbles = new();
    private readonly Dictionary<Actor, Label> _plates = new();

    /// <summary>Names over the heads of nearby people (so a viewer always knows who is who).</summary>
    public void UpdateNameplates(IEnumerable<Actor> near, Func<Vector2, Vector2> toScreen)
    {
        var keep = new HashSet<Actor>(near);
        foreach (var (actor, label) in _plates.ToList())
            if (!keep.Contains(actor) || !IsInstanceValid(actor)) { label.QueueFree(); _plates.Remove(actor); }
        var placed = new List<Rect2>();
        foreach (var actor in keep.OrderBy(a => a.GlobalPosition.Y))
        {
            if (!_plates.TryGetValue(actor, out var label))
            {
                var hostile = actor.Agent.Has(Kinloom.Core.WorldEvents.HostileTag);
                label = Assets.Text(actor.Agent.Name, 18, hostile ? Assets.Blood : new Color(1, 1, 1, 0.9f));
                label.HorizontalAlignment = HorizontalAlignment.Center;
                label.Size = new Vector2(160, 24);
                _bubbleLayer.AddChild(label);
                _plates[actor] = label;
            }
            var pos = (toScreen(actor.GlobalPosition + new Vector2(0, 10)) - new Vector2(80, 0)).Round();
            foreach (var r in placed)
                if (r.Intersects(new Rect2(pos + new Vector2(40, 0), new Vector2(80, 22)))) pos.Y = r.End.Y + 1; // no piles of names in a crowd
            placed.Add(new Rect2(pos + new Vector2(40, 0), new Vector2(80, 22)));
            label.Position = pos;
        }
    }

    public void Say(Actor actor, string text, bool thought, float life)
    {
        foreach (var old in _bubbles.Where(b => b.Actor == actor).ToList()) { old.Panel.QueueFree(); _bubbles.Remove(old); }
        while (_bubbles.Count >= 5) { _bubbles[0].Panel.QueueFree(); _bubbles.RemoveAt(0); }
        var panel = new PanelContainer { MouseFilter = Control.MouseFilterEnum.Ignore };
        var bg = thought ? new Color(0.86f, 0.9f, 1f, 0.95f) : new Color(1f, 0.98f, 0.93f, 0.97f);
        panel.AddThemeStyleboxOverride("panel", Assets.Flat(bg, thought ? new Color(0.35f, 0.42f, 0.62f) : Assets.Ink, 3, 12, thought ? 16 : 6));
        var label = new Label { Text = thought ? $"({text})" : text, AutowrapMode = TextServer.AutowrapMode.WordSmart, CustomMinimumSize = new Vector2(Math.Min(360, 40 + text.Length * 11), 0) };
        label.AddThemeFontOverride("font", Assets.Font);
        label.AddThemeFontSizeOverride("font_size", 20);
        label.AddThemeColorOverride("font_color", thought ? new Color(0.2f, 0.25f, 0.42f) : Assets.Ink);
        panel.AddChild(label);
        _bubbleLayer.AddChild(panel);
        _bubbles.Add(new Bubble { Actor = actor, Panel = panel, Life = life });
    }

    public void UpdateBubbles(float dt, Func<Vector2, Vector2> toScreen)
    {
        for (int i = _bubbles.Count - 1; i >= 0; i--)
        {
            var b = _bubbles[i];
            b.Life -= dt;
            if (b.Life <= 0 || !IsInstanceValid(b.Actor))
            {
                b.Panel.QueueFree();
                _bubbles.RemoveAt(i);
                continue;
            }
            var screen = toScreen(b.Actor.GlobalPosition + new Vector2(0, -26));
            var size = b.Panel.Size;
            var pos = (screen - new Vector2(size.X / 2, size.Y)).Round();
            // stack upwards instead of overlapping bubbles already placed this frame
            for (int j = _bubbles.Count - 1; j > i; j--)
            {
                var other = new Rect2(_bubbles[j].Panel.Position, _bubbles[j].Panel.Size);
                if (other.Intersects(new Rect2(pos, size))) pos.Y = other.Position.Y - size.Y - 4;
            }
            b.Panel.Position = pos;
            b.Panel.Modulate = new Color(1, 1, 1, Mathf.Clamp(b.Life * 2f, 0, 1));
            bool underFeed = screen.X + size.X / 2 > 1400;
            bool underClock = screen.X - size.X / 2 < 420 && screen.Y - size.Y < 200;
            b.Panel.Visible = screen.X > 0 && screen.Y > 60 && screen.Y < 1080 && !underFeed && !underClock;
        }
    }

    // ------------------------------------------------------------------ dialogue

    private void BuildDialogue(Control root)
    {
        DialoguePanel = new PanelContainer { Visible = false, Position = new Vector2(330, 700), CustomMinimumSize = new Vector2(1260, 330) };
        DialoguePanel.AddThemeStyleboxOverride("panel", Assets.Flat(new Color(0.07f, 0.06f, 0.09f, 0.94f), Assets.Gold, 3, 22, 10));
        root.AddChild(DialoguePanel);
        var h = new HBoxContainer();
        h.AddThemeConstantOverride("separation", 22);
        DialoguePanel.AddChild(h);
        var faceFrame = new PanelContainer { CustomMinimumSize = new Vector2(176, 176), SizeFlagsVertical = Control.SizeFlags.ShrinkBegin };
        faceFrame.AddThemeStyleboxOverride("panel", Assets.NinePatch("ui/faceset_box.png", 4, 8));
        DialogueFace = new TextureRect { ExpandMode = TextureRect.ExpandModeEnum.IgnoreSize, StretchMode = TextureRect.StretchModeEnum.KeepAspectCentered, CustomMinimumSize = new Vector2(152, 152) };
        faceFrame.AddChild(DialogueFace);
        h.AddChild(faceFrame);
        var v = new VBoxContainer { SizeFlagsHorizontal = Control.SizeFlags.ExpandFill };
        v.AddThemeConstantOverride("separation", 10);
        h.AddChild(v);
        var names = new HBoxContainer();
        names.AddThemeConstantOverride("separation", 16);
        DialogueName = Assets.Text("", 34, Assets.Gold);
        DialogueRole = Assets.Text("", 22, Assets.Mist);
        DialogueRole.SizeFlagsVertical = Control.SizeFlags.ShrinkEnd;
        names.AddChild(DialogueName);
        names.AddChild(DialogueRole);
        v.AddChild(names);
        DialogueText = new RichTextLabel { BbcodeEnabled = true, CustomMinimumSize = new Vector2(0, 110), ScrollActive = false, SizeFlagsVertical = Control.SizeFlags.ExpandFill };
        DialogueText.AddThemeFontSizeOverride("normal_font_size", 26);
        v.AddChild(DialogueText);
        DialogueActions = new HBoxContainer();
        DialogueActions.AddThemeConstantOverride("separation", 10);
        v.AddChild(DialogueActions);
        var inputRow = new HBoxContainer();
        inputRow.AddThemeConstantOverride("separation", 10);
        DialogueInput = new LineEdit { PlaceholderText = L10n.T("Say anything… (Enter to speak, Esc to leave)"), SizeFlagsHorizontal = Control.SizeFlags.ExpandFill, CustomMinimumSize = new Vector2(0, 48) };
        DialogueInput.AddThemeFontSizeOverride("font_size", 24);
        inputRow.AddChild(DialogueInput);
        v.AddChild(inputRow);
    }

    public void TypeText(string bbcodeFree)
    {
        _typeTarget = bbcodeFree;
        _typed = 0;
        DialogueText.Text = bbcodeFree;
        DialogueText.VisibleCharacters = 0;
    }

    public void SkipTyping()
    {
        _typed = _typeTarget.Length;
        DialogueText.VisibleCharacters = -1;
    }

    /// <summary>Places every panel for the real screen size (16:9, 16:10, windowed…): nothing is positioned for one resolution only.</summary>
    private void Layout(Vector2 s)
    {
        _laidOut = s;
        _feedTitle.Position = new Vector2(s.X - 500, 18);
        _feed.Position = new Vector2(s.X - 500, 50);
        _banner.Position = new Vector2(0, s.Y * 0.14f);
        _banner.Size = new Vector2(s.X, 80);
        _bannerSub.Position = new Vector2((s.X - 1200) / 2, s.Y * 0.14f + 80);
        Hint.Position = new Vector2(24, s.Y - 40);
        DialoguePanel.CustomMinimumSize = new Vector2(Math.Min(1400, s.X - 560), 330); // leaves the feed column free
        DialoguePanel.Size = new Vector2(DialoguePanel.CustomMinimumSize.X, DialoguePanel.Size.Y);
        DialoguePanel.Position = new Vector2(20, s.Y - DialoguePanel.Size.Y - 56);
        MindPanel.Position = new Vector2(20, 200);
        QuestPanel.Position = new Vector2((s.X - QuestPanel.Size.X) / 2, Math.Max(40, (s.Y - QuestPanel.Size.Y) / 2));
        ChroniclePanel.Position = new Vector2((s.X - ChroniclePanel.Size.X) / 2, Math.Max(30, (s.Y - ChroniclePanel.Size.Y) / 2));
        _titleBox.Position = new Vector2(0, s.Y * 0.2f);
        _titleBox.Size = new Vector2(s.X, s.Y * 0.7f);
        Objectives.Position = new Vector2(20, _statsPanel.Position.Y + _statsPanel.Size.Y + 12);
        ArrestPanel.Position = new Vector2((s.X - 900) / 2, s.Y * 0.32f);
    }

    public override void _Process(double delta)
    {
        var size = GetViewport().GetVisibleRect().Size;
        if (size != _laidOut || Engine.GetProcessFrames() % 30 == 0) Layout(size);
        if (_typed < _typeTarget.Length)
        {
            int before = (int)_typed;
            _typed += (float)delta * 55f;
            DialogueText.VisibleCharacters = (int)_typed;
            if ((int)_typed / 4 != before / 4) TypeTick?.Invoke();
            if (_typed >= _typeTarget.Length) DialogueText.VisibleCharacters = -1;
        }
    }

    public Button ActionButton(string text, Action onPress)
    {
        var b = new Button { Text = text, FocusMode = Control.FocusModeEnum.None, CustomMinimumSize = new Vector2(0, 44) };
        b.Pressed += onPress;
        DialogueActions.AddChild(b);
        return b;
    }

    // ------------------------------------------------------------------ mind, quests, chronicle

    private PanelContainer SidePanel(Control root, Vector2 pos, Vector2 size)
    {
        var p = new PanelContainer { Visible = false, Position = pos, CustomMinimumSize = size };
        p.AddThemeStyleboxOverride("panel", Assets.Flat(new Color(0.06f, 0.06f, 0.1f, 0.93f), new Color(Assets.Jade, 0.8f), 3, 22, 10));
        root.AddChild(p);
        return p;
    }

    private void BuildMind(Control root)
    {
        MindPanel = SidePanel(root, new Vector2(20, 190), new Vector2(620, 820));
        var v = new VBoxContainer();
        v.AddThemeConstantOverride("separation", 10);
        MindPanel.AddChild(v);
        var head = new HBoxContainer();
        head.AddThemeConstantOverride("separation", 16);
        MindFace = new TextureRect { ExpandMode = TextureRect.ExpandModeEnum.IgnoreSize, StretchMode = TextureRect.StretchModeEnum.KeepAspectCentered, CustomMinimumSize = new Vector2(96, 96) };
        head.AddChild(MindFace);
        var t = Assets.Text(L10n.T("MIND"), 22, Assets.Jade);
        t.SizeFlagsVertical = Control.SizeFlags.ShrinkCenter;
        head.AddChild(t);
        v.AddChild(head);
        MindText = new RichTextLabel { BbcodeEnabled = true, CustomMinimumSize = new Vector2(576, 680), ScrollActive = false };
        MindText.AddThemeFontSizeOverride("normal_font_size", 19);
        v.AddChild(MindText);
    }

    private void BuildQuests(Control root)
    {
        QuestPanel = SidePanel(root, new Vector2(560, 160), new Vector2(800, 600));
        QuestText = new RichTextLabel { BbcodeEnabled = true, CustomMinimumSize = new Vector2(756, 556), ScrollActive = false };
        QuestText.AddThemeFontSizeOverride("normal_font_size", 22);
        QuestPanel.AddChild(QuestText);
    }

    private void BuildChronicle(Control root)
    {
        ChroniclePanel = new PanelContainer { Visible = false, Position = new Vector2(460, 120), CustomMinimumSize = new Vector2(1000, 820) };
        ChroniclePanel.AddThemeStyleboxOverride("panel", Assets.Flat(Assets.Paper, new Color(0.45f, 0.28f, 0.16f), 6, 48, 6));
        root.AddChild(ChroniclePanel);
        ChronicleText = new RichTextLabel { BbcodeEnabled = true, CustomMinimumSize = new Vector2(900, 720), ScrollActive = true, ScrollFollowing = false };
        ChronicleText.AddThemeColorOverride("default_color", Assets.Ink);
        ChronicleText.AddThemeFontSizeOverride("normal_font_size", 23);
        ChroniclePanel.AddChild(ChronicleText);
    }

    private void BuildArrest(Control root)
    {
        ArrestPanel = new PanelContainer { Visible = false, CustomMinimumSize = new Vector2(900, 0) };
        ArrestPanel.AddThemeStyleboxOverride("panel", Assets.Flat(new Color(0.12f, 0.05f, 0.05f, 0.96f), Assets.Blood, 4, 28, 8));
        root.AddChild(ArrestPanel);
        var v = new VBoxContainer();
        v.AddThemeConstantOverride("separation", 18);
        ArrestPanel.AddChild(v);
        _arrestText = new RichTextLabel { BbcodeEnabled = true, FitContent = true, ScrollActive = false, CustomMinimumSize = new Vector2(840, 0) };
        _arrestText.AddThemeFontSizeOverride("normal_font_size", 28);
        v.AddChild(_arrestText);
        _arrestButtons = new HBoxContainer();
        _arrestButtons.AddThemeConstantOverride("separation", 14);
        v.AddChild(_arrestButtons);
    }

    public void ShowArrest(string text, (string Label, Action Do)[] options)
    {
        _arrestText.Text = text;
        foreach (var c in _arrestButtons.GetChildren()) c.QueueFree();
        foreach (var (label, act) in options)
        {
            var b = new Button { Text = label, FocusMode = Control.FocusModeEnum.None, CustomMinimumSize = new Vector2(0, 52) };
            b.Pressed += act;
            _arrestButtons.AddChild(b);
        }
        ArrestPanel.Visible = true;
    }

    public void HideArrest() => ArrestPanel.Visible = false;

    private void BuildTitle(Control root)
    {
        TitleScreen = new ColorRect { Color = new Color(0.03f, 0.03f, 0.06f, 0.82f) };
        TitleScreen.SetAnchorsPreset(Control.LayoutPreset.FullRect);
        root.AddChild(TitleScreen);
        var v = _titleBox = new VBoxContainer();
        v.AddThemeConstantOverride("separation", 18);
        TitleScreen.AddChild(v);
        var kicker = Assets.Text(L10n.T("A KINLOOM BRAIN DEMO"), 26, Assets.Jade);
        kicker.HorizontalAlignment = HorizontalAlignment.Center;
        v.AddChild(kicker);
        var title = Assets.Text(L10n.T("ASAGIRI VALLEY"), 110, Assets.Gold);
        title.HorizontalAlignment = HorizontalAlignment.Center;
        v.AddChild(title);
        var tag = Assets.Text(L10n.T("Its people think, talk, scheme and remember. What will they say about you?"), 30, Assets.Paper);
        tag.HorizontalAlignment = HorizontalAlignment.Center;
        v.AddChild(tag);
        v.AddChild(new Control { CustomMinimumSize = new Vector2(0, 50) });
        TitleStatus = Assets.Text("", 22, Assets.Mist);
        TitleStatus.HorizontalAlignment = HorizontalAlignment.Center;
        v.AddChild(TitleStatus);
        var goal = Assets.Text(L10n.T("Three days in the valley. Talk, help, steal, fight: every villager will remember, and tell the others."), 24, Assets.Mist);
        goal.HorizontalAlignment = HorizontalAlignment.Center;
        v.AddChild(goal);
        var press = Assets.Text(L10n.T("Press Enter to begin"), 30, Assets.Paper);
        press.HorizontalAlignment = HorizontalAlignment.Center;
        v.AddChild(press);
        var lang = Assets.Text(L10n.T("L: language — English"), 20, new Color(Assets.Mist, 0.8f));
        lang.HorizontalAlignment = HorizontalAlignment.Center;
        v.AddChild(lang);
        var tw = press.CreateTween().SetLoops();
        tw.TweenProperty(press, "modulate:a", 0.25f, 0.9f);
        tw.TweenProperty(press, "modulate:a", 1f, 0.9f);
    }
}
