using System.Numerics;
using Raylib_cs;
using static Raylib_cs.Raylib;

namespace Kinloom.Game;

/// <summary>Anti-aliased text with Segoe UI when available (falls back to raylib's default font).</summary>
public static class Text
{
    private static Font _regular, _bold;
    private static bool _custom;

    public static void Load()
    {
        string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "Fonts");
        string regular = Path.Combine(dir, "segoeui.ttf"), bold = Path.Combine(dir, "segoeuib.ttf");
        if (File.Exists(regular) && File.Exists(bold))
        {
            // ASCII + the few typographic characters the UI uses (·, —, •, é, è, à)
            int[] glyphs = Enumerable.Range(32, 95).Concat(new[] { 0xB7, 0x2014, 0x2022, 0xE9, 0xE8, 0xE0 }).ToArray();
            _regular = LoadFontEx(regular, 48, glyphs, glyphs.Length);
            _bold = LoadFontEx(bold, 48, glyphs, glyphs.Length);
            SetTextureFilter(_regular.Texture, TextureFilter.Bilinear);
            SetTextureFilter(_bold.Texture, TextureFilter.Bilinear);
            _custom = IsFontValid(_regular) && IsFontValid(_bold);
        }
        if (!_custom) _regular = _bold = GetFontDefault();
    }

    public static void Unload()
    {
        if (!_custom) return;
        UnloadFont(_regular);
        UnloadFont(_bold);
    }

    public static void Draw(string text, float x, float y, float size, Color color, bool bold = false) =>
        DrawTextEx(bold ? _bold : _regular, text, new Vector2(x, y), size, 0.5f, color);

    public static float Width(string text, float size, bool bold = false) =>
        MeasureTextEx(bold ? _bold : _regular, text, size, 0.5f).X;

    public static List<string> Wrap(string text, float size, float maxWidth)
    {
        var lines = new List<string>();
        string current = "";
        foreach (var word in text.Split(' '))
        {
            string candidate = current.Length == 0 ? word : current + " " + word;
            if (Width(candidate, size) > maxWidth && current.Length > 0) { lines.Add(current); current = word; }
            else current = candidate;
        }
        if (current.Length > 0) lines.Add(current);
        return lines;
    }
}
