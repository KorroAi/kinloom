using Godot;

namespace Valley;

/// <summary>Cached textures, fonts and the UI theme. Everything comes from res://assets (Ninja Adventure, CC0; DotGothic16, OFL).</summary>
public static class Assets
{
    private static readonly Dictionary<string, Texture2D> Cache = new();

    public static Texture2D Tex(string path)
    {
        if (!Cache.TryGetValue(path, out var t))
        {
            t = GD.Load<Texture2D>("res://assets/" + path);
            Cache[path] = t;
        }
        return t;
    }

    public static AtlasTexture Region(string path, Rect2 region) => new() { Atlas = Tex(path), Region = region };

    /// <summary>A rectangle of 16 px tiles in a tileset.</summary>
    public static AtlasTexture Tiles(string path, int x, int y, int w = 1, int h = 1) => Region(path, new Rect2(x * 16, y * 16, w * 16, h * 16));

    public static Texture2D Emote(int n) => Tex($"ui/emote/emote{n}.png");

    public static Texture2D Face(string look) => Tex($"chars/{look}/Faceset.png");

    private static FontFile? _font;
    public static FontFile Font => _font ??= GD.Load<FontFile>("res://assets/ui/DotGothic16-Regular.ttf");

    public static readonly Color Ink = new(0.13f, 0.09f, 0.08f);
    public static readonly Color Paper = new(0.98f, 0.94f, 0.86f);
    public static readonly Color Gold = new(1f, 0.78f, 0.35f);
    public static readonly Color Jade = new(0.45f, 0.85f, 0.65f);
    public static readonly Color Blood = new(0.93f, 0.33f, 0.3f);
    public static readonly Color Mist = new(0.72f, 0.78f, 0.9f);
    public static readonly Color Night = new(0.05f, 0.06f, 0.1f, 0.88f);

    /// <summary>Wooden 9-slice panels from the pack's "Theme Wood", with the pixel font.</summary>
    public static Theme BuildTheme()
    {
        var theme = new Theme { DefaultFont = Font, DefaultFontSize = 24 };
        theme.SetStylebox("panel", "PanelContainer", Panel());
        theme.SetStylebox("panel", "Panel", Panel());
        theme.SetStylebox("normal", "Button", NinePatch("ui/theme/button_normal.png", 6));
        theme.SetStylebox("hover", "Button", NinePatch("ui/theme/button_hover.png", 6));
        theme.SetStylebox("pressed", "Button", NinePatch("ui/theme/button_pressed.png", 6));
        theme.SetStylebox("focus", "Button", new StyleBoxEmpty());
        theme.SetColor("font_color", "Button", Ink);
        theme.SetColor("font_hover_color", "Button", Ink);
        theme.SetColor("font_pressed_color", "Button", Ink);
        theme.SetFontSize("font_size", "Button", 22);
        theme.SetStylebox("normal", "LineEdit", Flat(new Color(0.99f, 0.96f, 0.9f), Ink, 3, 10));
        theme.SetStylebox("focus", "LineEdit", Flat(new Color(1f, 0.98f, 0.93f), Gold, 3, 10));
        theme.SetColor("font_color", "LineEdit", Ink);
        theme.SetColor("font_placeholder_color", "LineEdit", new Color(Ink, 0.45f));
        theme.SetColor("caret_color", "LineEdit", Ink);
        theme.SetColor("font_color", "Label", Paper);
        theme.SetColor("default_color", "RichTextLabel", Paper);
        theme.SetFont("normal_font", "RichTextLabel", Font);
        theme.SetFont("bold_font", "RichTextLabel", Font);
        theme.SetFont("italics_font", "RichTextLabel", Font);
        return theme;
    }

    public static StyleBox Panel() => NinePatch("ui/theme/nine_path_panel.png", 6, 14);

    public static StyleBox NinePatch(string path, int margin, int content = 8)
    {
        var box = new StyleBoxTexture
        {
            Texture = Tex(path),
            TextureMarginLeft = margin, TextureMarginRight = margin, TextureMarginTop = margin, TextureMarginBottom = margin,
            ContentMarginLeft = content, ContentMarginRight = content, ContentMarginTop = content, ContentMarginBottom = content,
            AxisStretchHorizontal = StyleBoxTexture.AxisStretchMode.Stretch,
            AxisStretchVertical = StyleBoxTexture.AxisStretchMode.Stretch,
        };
        return box;
    }

    public static StyleBoxFlat Flat(Color bg, Color border, int borderWidth = 2, int padding = 12, int radius = 4) => new()
    {
        BgColor = bg,
        BorderColor = border,
        BorderWidthLeft = borderWidth, BorderWidthRight = borderWidth, BorderWidthTop = borderWidth, BorderWidthBottom = borderWidth,
        CornerRadiusTopLeft = radius, CornerRadiusTopRight = radius, CornerRadiusBottomLeft = radius, CornerRadiusBottomRight = radius,
        ContentMarginLeft = padding, ContentMarginRight = padding, ContentMarginTop = padding * 0.7f, ContentMarginBottom = padding * 0.7f,
    };

    public static Label Text(string text, int size, Color color, bool outline = true)
    {
        var l = new Label { Text = text };
        l.AddThemeFontOverride("font", Font);
        l.AddThemeFontSizeOverride("font_size", size);
        l.AddThemeColorOverride("font_color", color);
        if (outline)
        {
            l.AddThemeColorOverride("font_outline_color", new Color(0, 0, 0, 0.85f));
            l.AddThemeConstantOverride("outline_size", Math.Max(4, size / 4));
        }
        return l;
    }

    /// <summary>Emote index for an emotion word coming from a brain.</summary>
    public static int EmoteFor(string? emotion) => emotion switch
    {
        "happy" => 11,
        "angry" => 9,
        "afraid" => 19,
        "sad" => 17,
        "surprised" => 16,
        "love" => 27,
        "worried" => 12,
        "thinking" => 20,
        "quest" => 22,
        "alert" => 21,
        "secret" => 28,
        "question" => 25,
        _ => 14,
    };
}
