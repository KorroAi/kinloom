using System.Numerics;
using Kinloom.Core;
using Raylib_cs;
using static Raylib_cs.Raylib;

namespace Kinloom.Game;

/// <summary>Draws the village, the villagers and the HUD. Pure presentation: all state comes from GameSession.</summary>
public sealed class Renderer
{
    public const int Width = 1280, Height = 800;
    private const int TopBar = 40, MapW = 960, MapH = 576, SideX = 960;
    private const float Scale = MapW / GameSession.MapWidth; // 9.6 px per world unit

    private static readonly Color Grass = new(126, 170, 92, 255);
    private static readonly Color GrassDark = new(116, 160, 84, 255);
    private static readonly Color PathColor = new(214, 196, 150, 255);
    private static readonly Color Ink = new(30, 30, 36, 255);
    private static readonly Color Muted = new(112, 112, 122, 255);
    private static readonly Color Panel = new(246, 244, 239, 255);
    private static readonly Color Line = new(222, 218, 209, 255);
    private static readonly Color Authority = new(58, 98, 200, 255);
    private static readonly Color Trader = new(226, 138, 40, 255);
    private static readonly Color Villager = new(70, 150, 80, 255);
    private static readonly Color PlayerColor = new(200, 40, 40, 255);
    private static readonly Color Good = new(46, 150, 80, 255);
    private static readonly Color Bad = new(200, 50, 50, 255);
    private static readonly Color FleeRing = new(250, 210, 50, 255);
    private static readonly Color ChaseRing = new(220, 40, 40, 255);
    private static readonly Color ReportRing = new(150, 70, 200, 255);

    private readonly GameSession _g;

    public Renderer(GameSession session) { _g = session; }

    public static Vector2 ToScreen(Vec2 p) => new(p.X * Scale, TopBar + p.Y * Scale);

    public static bool InMap(Vector2 s) => s.X >= 0 && s.X < MapW && s.Y >= TopBar && s.Y < TopBar + MapH;

    public void Draw(Agent? selected, string? toast, float toastAlpha, string speedLabel)
    {
        ClearBackground(Panel);
        BeginScissorMode(0, TopBar, MapW, MapH);
        DrawMap(selected);
        DrawNight();
        EndScissorMode();
        DrawHint();
        DrawTopBar(speedLabel);
        DrawSidePanel(selected);
        DrawFeed();
        if (toast != null && toastAlpha > 0) DrawToast(toast, toastAlpha);
    }

    // ---------- map ----------

    private void DrawMap(Agent? selected)
    {
        DrawRectangle(0, TopBar, MapW, MapH, Grass);
        for (int x = 0; x < MapW; x += 48)
            for (int y = TopBar; y < TopBar + MapH; y += 48)
                if (((x + y) / 48) % 2 == 0) DrawRectangle(x, y, 48, 48, GrassDark);

        var square = _g.World.FindPlace("square") ?? _g.World.Places.FirstOrDefault();
        if (square != null)
            foreach (var p in _g.World.Places)
                if (p != square) DrawLineEx(ToScreen(square.Position), ToScreen(p.Position), 16, PathColor);

        foreach (var p in _g.World.Places) DrawPlace(p);
        foreach (var item in _g.World.Items) DrawItem(item);

        var agents = _g.World.Agents.Select(a => (agent: a, pos: ToScreen(_g.DisplayPosition(a)))).OrderBy(t => t.pos.Y).ToList();
        foreach (var (a, pos) in agents) DrawAgent(a, pos, a == selected);
        DrawLabels(agents, selected);
        var bubbles = new List<Rectangle>();
        foreach (var (a, pos) in agents)
        {
            string? bark = a.CurrentBark(_g.World.Tick);
            if (bark != null) DrawBark(pos, bark, bubbles);
        }
    }

    private static void DrawPlace(Place p)
    {
        var c = ToScreen(p.Position);
        float size = Math.Max(34, p.Radius * 2 * Scale);
        var body = new Rectangle(c.X - size / 2, c.Y - size / 2, size, size);
        if (p.Has("market"))
        {
            DrawCircleV(c, size * 0.62f, new Color(198, 192, 178, 255));
            DrawCircleLinesV(c, size * 0.62f, new Color(150, 144, 130, 255));
            DrawCircleV(c, 10, new Color(120, 110, 100, 255));
            DrawCircleV(c, 7, new Color(80, 130, 190, 255));
        }
        else if (p.Has("work"))
        {
            DrawRectangleRec(body, new Color(166, 132, 70, 255));
            for (float y = body.Y + 6; y < body.Y + body.Height - 2; y += 10)
                DrawLineEx(new Vector2(body.X + 4, y), new Vector2(body.X + body.Width - 4, y), 4, new Color(104, 150, 58, 255));
        }
        else
        {
            var (wall, roof) = p.Has("home") ? (new Color(224, 204, 164, 255), new Color(140, 84, 60, 255))
                : p.Has("social") ? (new Color(186, 120, 80, 255), new Color(100, 44, 34, 255))
                : (new Color(234, 216, 178, 255), new Color(176, 72, 50, 255));
            var wallRect = new Rectangle(body.X, body.Y + size * 0.35f, size, size * 0.65f);
            DrawRectangleRec(wallRect, wall);
            DrawRectangleLinesEx(wallRect, 2, new Color(90, 70, 50, 255));
            DrawTriangle(new Vector2(body.X - 5, body.Y + size * 0.38f), new Vector2(body.X + size + 5, body.Y + size * 0.38f), new Vector2(c.X, body.Y), roof);
            DrawRectangle((int)(c.X - 5), (int)(body.Y + size - 15), 10, 15, new Color(80, 52, 36, 255));
        }
        float w = Text.Width(p.Name, 15, true);
        DrawRectangleRounded(new Rectangle(c.X - w / 2 - 6, body.Y - 23, w + 12, 20), 0.5f, 6, new Color(255, 255, 255, 200));
        Text.Draw(p.Name, c.X - w / 2, body.Y - 22, 15, Ink, bold: true);
    }

    private void DrawItem(Item item)
    {
        if (item.OwnerId == _g.Player.Id) return;
        var c = ToScreen(item.Position) + new Vector2(18, 12);
        var color = item.Has("weapon") ? new Color(150, 156, 170, 255) : item.Has("drink") ? new Color(214, 160, 40, 255) : new Color(196, 140, 80, 255);
        var box = new Rectangle(c.X - 9, c.Y - 9, 18, 18);
        DrawRectangleRounded(box, 0.4f, 6, color);
        DrawRectangleRoundedLinesEx(box, 0.4f, 6, 1.5f, Ink);
        string letter = item.Name.Split(' ').Last()[..1];
        Text.Draw(letter, c.X - Text.Width(letter, 14, true) / 2, c.Y - 9, 14, Ink, bold: true);
    }

    private void DrawAgent(Agent a, Vector2 p, bool selected)
    {
        var color = a.IsPlayer ? PlayerColor : a.Has(Tags.Authority) ? Authority : a.Has(Tags.Trader) ? Trader : Villager;
        DrawEllipse((int)p.X, (int)p.Y + 12, 11, 4, new Color(0, 0, 0, 70));
        Color? ring = a.Intent.Kind switch
        {
            IntentKind.Flee => FleeRing,
            IntentKind.Approach => ChaseRing,
            IntentKind.Report => ReportRing,
            _ => null,
        };
        if (selected) DrawCircleV(p, 19, new Color(255, 255, 255, 220));
        if (ring is Color r) DrawCircleV(p, 16, r);
        // body
        var bodyRect = new Rectangle(p.X - 8, p.Y - 2, 16, 14);
        DrawRectangleRounded(bodyRect, 0.6f, 6, color);
        DrawRectangleRoundedLinesEx(bodyRect, 0.6f, 6, 1.5f, Ink);
        // head
        var head = p + new Vector2(0, -7);
        DrawCircleV(head, 7.5f, Ink);
        DrawCircleV(head, 6.2f, new Color(244, 214, 180, 255));
        DrawCircleV(head + new Vector2(-2.3f, -0.5f), 1.2f, Ink);
        DrawCircleV(head + new Vector2(2.3f, -0.5f), 1.2f, Ink);
        if (a.Mind.Emotions.Fear > 0.35f)
        {
            DrawCircleV(p + new Vector2(13, -18), 8, new Color(250, 200, 30, 255));
            Text.Draw("!", p.X + 10.5f, p.Y - 28, 18, Ink, bold: true);
        }
    }

    private static void DrawLabels(List<(Agent agent, Vector2 pos)> agents, Agent? selected)
    {
        int Priority(Agent a) => (a == selected ? 2 : 0) + (a.IsPlayer ? 1 : 0);
        var labels = new List<(Vector2 at, string text, int extra)>();
        foreach (var (a, pos) in agents.OrderByDescending(t => Priority(t.agent)))
        {
            string name = a.IsPlayer ? "You" : Narrator.Short(a.Name);
            var at = pos + new Vector2(0, 16);
            int clash = labels.FindIndex(l => Math.Abs(l.at.X - at.X) < 46 && Math.Abs(l.at.Y - at.Y) < 15);
            if (clash >= 0 && Priority(a) == 0) { labels[clash] = (labels[clash].at, labels[clash].text, labels[clash].extra + 1); continue; }
            while (labels.Any(l => Math.Abs(l.at.X - at.X) < 46 && Math.Abs(l.at.Y - at.Y) < 15)) at.Y += 15;
            labels.Add((at, name, 0));
        }
        foreach (var (at, text, extra) in labels)
        {
            string t = extra > 0 ? $"{text} +{extra}" : text;
            float w = Text.Width(t, 14, true);
            DrawRectangleRounded(new Rectangle(at.X - w / 2 - 4, at.Y, w + 8, 17), 0.5f, 6, new Color(255, 255, 255, 170));
            Text.Draw(t, at.X - w / 2, at.Y, 14, Ink, bold: true);
        }
    }

    private static void DrawBark(Vector2 at, string text, List<Rectangle> taken)
    {
        float w = Text.Width(text, 16, true) + 16;
        var box = new Rectangle(at.X - w / 2f, at.Y - 50, w, 24);
        while (taken.Any(t => CheckCollisionRecs(t, box))) box.Y -= 26;
        taken.Add(box);
        if (box.Y < at.Y - 50) DrawLineEx(new Vector2(at.X, box.Y + 24), new Vector2(at.X, at.Y - 16), 1.5f, Ink);
        else DrawTriangle(new Vector2(at.X - 6, box.Y + 23), new Vector2(at.X, box.Y + 31), new Vector2(at.X + 6, box.Y + 23), Color.White);
        DrawRectangleRounded(box, 0.45f, 6, Color.White);
        DrawRectangleRoundedLinesEx(box, 0.45f, 6, 1.5f, Ink);
        Text.Draw(text, box.X + 8, box.Y + 2, 16, Ink, bold: true);
    }

    private void DrawNight()
    {
        float h = _g.World.Tick % World.TicksPerDay / (float)World.TicksPerHour;
        float dark = h < 5 ? 1f : h < 7 ? (7 - h) / 2 : h < 18 ? 0f : h < 21 ? (h - 18) / 3 : 1f;
        if (dark > 0) DrawRectangle(0, TopBar, MapW, MapH, new Color(20, 24, 60, (int)(dark * 130)));
    }

    private void DrawHint()
    {
        var parts = new List<string>();
        if (_g.NearestStealable() is Item item) parts.Add($"[E] steal {item.Name}");
        if (_g.NearestNpc() is Agent npc) { parts.Add($"[H] help {Narrator.Short(npc.Name)}"); parts.Add($"[P] pay {Narrator.Short(npc.Name)}"); }
        if (_g.NearestNpc(tag: Tags.Trader) is Agent trader) parts.Add($"[B] buy from {Narrator.Short(trader.Name)}");
        parts.Add("[F] draw weapon");
        string text = string.Join("     ", parts);
        float w = Text.Width(text, 17, true) + 24;
        DrawRectangleRounded(new Rectangle(MapW / 2f - w / 2f, TopBar + MapH - 38, w, 30), 0.5f, 6, new Color(0, 0, 0, 170));
        Text.Draw(text, MapW / 2f - w / 2f + 12, TopBar + MapH - 34, 17, Color.White, bold: true);
    }

    // ---------- HUD ----------

    private void DrawTopBar(string speedLabel)
    {
        DrawRectangle(0, 0, Width, TopBar, Ink);
        Text.Draw("KINLOOM", 14, 8, 22, Color.White, bold: true);
        Text.Draw("village prototype", 120, 12, 16, new Color(170, 170, 180, 255));
        string clock = World.Clock(_g.World.Tick).Replace("D", "Day ");
        Text.Draw(clock, 280, 8, 22, new Color(250, 220, 120, 255), bold: true);
        string help = $"ZQSD/WASD move   ·   click a villager to inspect   ·   Space pause   ·   Tab speed {speedLabel}" + (_g.Paused ? "   ·   PAUSED" : "");
        Text.Draw(help, 470, 11, 16, new Color(205, 205, 215, 255));
    }

    private void DrawSidePanel(Agent? selected)
    {
        DrawRectangle(SideX, TopBar, Width - SideX, Height - TopBar, Panel);
        DrawLine(SideX, TopBar, SideX, Height, Line);
        float x = SideX + 16, y = TopBar + 14, w = Width - SideX - 32;
        Header("WHAT THEY THINK OF YOU", x, ref y);
        foreach (var a in _g.World.Agents.Where(a => !a.IsPlayer))
        {
            float o = a.Mind.OpinionOf(_g.Player.Id);
            Text.Draw(Narrator.Short(a.Name), x, y, 16, a == selected ? Authority : Ink, bold: a == selected);
            float barX = x + 70, barW = w - 122, mid = barX + barW / 2;
            DrawRectangleRounded(new Rectangle(barX, y + 5, barW, 11), 0.5f, 4, Line);
            float len = Math.Abs(o) * barW / 2;
            if (len > 0.5f) DrawRectangleRounded(new Rectangle(o >= 0 ? mid : mid - len, y + 5, len, 11), 0.5f, 4, o >= 0 ? Good : Bad);
            DrawLineEx(new Vector2(mid, y + 2), new Vector2(mid, y + 19), 1.5f, Muted);
            Text.Draw(System.FormattableString.Invariant($"{o:+0.00;-0.00;0.00}"), barX + barW + 8, y + 1, 15, Muted);
            y += 24;
        }
        y += 8;
        Legend(x, ref y);
        y += 10;
        int done = _g.Goals.Count(goal => goal.Done);
        if (selected == null)
        {
            Header($"THINGS TO TRY  ({done}/{_g.Goals.Count})", x, ref y);
            foreach (var goal in _g.Goals)
            {
                var box = new Rectangle(x, y + 3, 13, 13);
                if (goal.Done) DrawRectangleRounded(box, 0.3f, 4, Good);
                DrawRectangleRoundedLinesEx(box, 0.3f, 4, 1.5f, goal.Done ? Good : Muted);
                if (goal.Done) Text.Draw("v", x + 3, y - 1, 14, Color.White, bold: true);
                Text.Draw(goal.Text, x + 22, y, 15, goal.Done ? Muted : Ink);
                y += 21;
            }
            y += 10;
        }
        else
        {
            Text.Draw($"THINGS TO TRY  {done}/{_g.Goals.Count} done  ·  right click to see them", x, y, 13, Muted, bold: true);
            y += 26;
        }
        Header("INSPECTOR", x, ref y);
        if (selected == null)
        {
            foreach (var l in Text.Wrap("Click a villager to see what they know about you and why they act.", 16, w)) { Text.Draw(l, x, y, 16, Muted); y += 21; }
            return;
        }
        Text.Draw(selected.Name, x, y, 21, Ink, bold: true); y += 28;
        Text.Draw($"Now: {Doing(selected)}", x, y, 16, Muted); y += 22;
        Bar("Fear", selected.Mind.Emotions.Fear, x, ref y, w, new Color(230, 180, 30, 255));
        Bar("Anger", selected.Mind.Emotions.Anger, x, ref y, w, Bad);
        y += 6;
        Text.Draw("What they know about you", x, y, 16, Ink, bold: true); y += 22;
        var known = selected.Mind.Memories.Where(m => m.ActorId == _g.Player.Id).ToList();
        if (known.Count == 0) { Text.Draw("nothing yet", x + 8, y, 15, Muted); y += 20; }
        foreach (var m in known.TakeLast(4))
        {
            string how = m.Firsthand ? "saw it" : $"heard it from {Narrator.Short(_g.World.NameOf(m.SourceId))}";
            string what = m.Kind switch { "steal" => "you stole", "draw_weapon" => "you drew a weapon", "help" => "you helped someone", "pay" => "you paid", var k => k };
            Text.Draw(System.FormattableString.Invariant($"• {what} — {how} ({m.Confidence * 100:0}% sure)"), x + 4, y, 15, Muted); y += 20;
        }
        y += 8;
        Text.Draw("Why?", x, y, 16, Ink, bold: true); y += 22;
        var story = _g.WhyStory(selected);
        if (story.Count == 0) { Text.Draw("no decision yet", x + 8, y, 15, Muted); return; }
        for (int i = 0; i < story.Count; i++)
        {
            string sentence = i == 0 ? story[i] : "because " + (story[i].StartsWith("You ") ? "you " + story[i][4..] : story[i]);
            foreach (var l in Text.Wrap(sentence, 15, w - 8))
            {
                if (y > Height - 22) return;
                Text.Draw(l, x + (i == 0 ? 0 : 8), y, 15, i == 0 ? Ink : Muted, bold: i == 0); y += 19;
            }
            y += 3;
        }
    }

    private string Doing(Agent a) => a.Intent.Kind switch
    {
        IntentKind.Flee => "running away",
        IntentKind.Approach => a.Intent.TargetId == _g.Player.Id ? "coming after you" : "approaching someone",
        IntentKind.Report => $"going to tell {Narrator.Short(_g.World.NameOf(a.Intent.TargetId))}",
        _ => $"daily routine ({_g.World.FindPlace(a.Schedule?.PlaceAt(_g.World.Hour))?.Name ?? "home"})",
    };

    private static void Legend(float x, ref float y)
    {
        static void Dot(Color c, string label, float row, ref float lx)
        {
            DrawCircleV(new Vector2(lx + 6, row + 9), 6, c);
            Text.Draw(label, lx + 16, row, 14, Muted);
            lx += 22 + Text.Width(label, 14);
        }
        float lx = x;
        Dot(Authority, "guard", y, ref lx); Dot(Trader, "trader", y, ref lx); Dot(Villager, "villager", y, ref lx); Dot(PlayerColor, "you", y, ref lx);
        y += 20; lx = x;
        Dot(FleeRing, "fleeing", y, ref lx); Dot(ChaseRing, "after you", y, ref lx); Dot(ReportRing, "reporting", y, ref lx);
        y += 20;
    }

    private void DrawFeed()
    {
        int y0 = TopBar + MapH;
        DrawRectangle(0, y0, MapW, Height - y0, new Color(250, 249, 246, 255));
        DrawLine(0, y0, MapW, y0, Line);
        float y = y0 + 8;
        Text.Draw("WHAT HAPPENED", 14, y, 14, Muted, bold: true);
        y += 22;
        foreach (var line in _g.Feed.TakeLast(7))
        {
            var color = line.Kind switch
            {
                "consequence" => Bad,
                "deed" => PlayerColor,
                "rumor" or "report" => Authority,
                "warning" or "error" => new Color(180, 120, 0, 255),
                _ => Ink,
            };
            Text.Draw(World.Clock(line.Tick)[3..], 14, y, 16, Muted);
            Text.Draw(line.Text, 70, y, 16, color, bold: line.Kind is "consequence" or "deed");
            y += 20;
        }
    }

    private static void DrawToast(string text, float alpha)
    {
        float w = Text.Width(text, 21, true) + 34;
        var box = new Rectangle(MapW / 2f - w / 2f, TopBar + 12, w, 38);
        DrawRectangleRounded(box, 0.4f, 8, new Color(28, 28, 32, (int)(225 * alpha)));
        Text.Draw(text, box.X + 17, box.Y + 7, 21, new Color(255, 255, 255, (int)(255 * alpha)), bold: true);
    }

    // ---------- helpers ----------

    private static void Header(string text, float x, ref float y)
    {
        Text.Draw(text, x, y, 14, Muted, bold: true);
        y += 24;
    }

    private static void Bar(string label, float value, float x, ref float y, float w, Color color)
    {
        Text.Draw(label, x, y, 15, Muted);
        DrawRectangleRounded(new Rectangle(x + 60, y + 5, w - 60, 10), 0.5f, 4, Line);
        float len = (w - 60) * Math.Clamp(value, 0f, 1f);
        if (len > 0.5f) DrawRectangleRounded(new Rectangle(x + 60, y + 5, len, 10), 0.5f, 4, color);
        y += 21;
    }
}
