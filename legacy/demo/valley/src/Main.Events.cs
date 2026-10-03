using System.Globalization;
using System.Text.RegularExpressions;
using Godot;
using Kinloom.Brain;
using Kinloom.Core;

namespace Valley;

public partial class Main
{
    private readonly List<(float At, string Speaker, string? Listener, string Text)> _pendingLines = new();
    private float _clock;
    private float _lastRejectShown = -100f;
    private bool _devView;
    private string? _lastChronicle;
    private static readonly Regex OpinionShift = new(@"([+-]\d\.\d\d) -> ([+-]?\d\.\d\d)", RegexOptions.Compiled);

    private static string Hex(Color c) => c.ToHtml(false);
    private string Who(string? id) => $"[color=#{Hex(Assets.Gold)}]{NameOf(id)}[/color]";

    /// <summary>Rule-level happenings (Core journal): witnesses, reactions, deaths, rumours about the player, quests.</summary>
    private void ReadJournal()
    {
        var entries = World.Journal.Entries;
        string playerId = _player.Agent.Id;
        for (; _journalRead < entries.Count; _journalRead++)
        {
            var e = entries[_journalRead];
            var actor = ActorOf(e.AgentId);
            switch (e.Kind)
            {
                case "witness":
                    actor?.ShowEmote(21, 2f);
                    break;
                case "reaction":
                    if (actor == null) break;
                    if (e.Text.Contains("flee")) actor.ShowEmote(19, 3f);
                    else if (e.Text.Contains("confront") || e.Text.Contains("recognizes")) actor.ShowEmote(9, 3f);
                    else if (e.Text.Contains("report")) actor.ShowEmote(22, 3f);
                    else if (e.Text.Contains("grateful")) actor.ShowEmote(27, 3f);
                    if (actor.Agent.CurrentBark(World.Tick) is { } bark) _hud.Say(actor, bark, false, 2.5f);
                    break;
                case "deed":
                    OnDeed(e, actor);
                    break;
                case "opinion":
                    if (e.TargetId == playerId && actor != null && OpinionShift.Match(e.Text) is { Success: true } m)
                    {
                        float before = float.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture), after = float.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture);
                        if (Math.Abs(after - before) >= 0.02f)
                            FloatText(actor.GlobalPosition + new Vector2(0, -30), after > before ? L10n.T("♥ trust") : L10n.T("✖ trust"), after > before ? Assets.Jade : Assets.Blood);
                    }
                    break;
                case "tell":
                case "rumor":
                case "lie":
                    if (e.Text.Contains(_player.Agent.Name) && !e.Text.StartsWith(_player.Agent.Name))
                        _hud.Feed($"[color=#b8c6e6]{L10n.T("Word spreads")}[/color] — {L10n.Journal(e.Text).Replace(_player.Agent.Name, $"[color=#ffc85a]{L10n.T("you")}[/color]")}" + (e.Kind == "lie" ? $" [color=#ee5a50]{L10n.T("(a lie)")}[/color]" : ""), Assets.Mist, 18);
                    else if (e.Kind == "lie")
                        _hud.Feed($"[color=#ee5a50]{L10n.T("A lie is told.")}[/color] {L10n.Journal(e.Text)}", Assets.Blood, 14);
                    break;
                case "death":
                    if (actor != null && actor.Agent.Has(WorldEvents.HostileTag))
                    {
                        Smoke(actor.GlobalPosition);
                        var gone = actor;
                        GetTree().CreateTimer(0.25f).Timeout += () => gone.Visible = false; // beasts and bandits vanish in smoke
                        if (e.TargetId == _player.Agent.Id)
                        {
                            int loot = Math.Max(5, actor.Agent.Gold);
                            actor.Agent.Gold = 0;
                            _player.Agent.Gold += loot;
                            _audio.Sfx("coin", -4);
                            FloatText(actor.GlobalPosition + new Vector2(0, -20), $"+{loot} g", Assets.Gold);
                            _hud.Feed(L10n.T("You defeat {0} and recover {1} gold.", $"[color=#ee5a50]{actor.Agent.Name}[/color]", $"[color=#ffc85a]{loot}[/color]"), Assets.Gold, 15);
                        DropLoot(actor);
                            foreach (var stolen in World.Items.Where(i => i.OwnerId == actor.Agent.Id))
                            {
                                stolen.OwnerId = _player.Agent.Id; // recovered loot: give it back to its owner (E, then "Give")
                                _hud.Feed(L10n.T("You recover the {0}. Its owner will want it back.", $"[color=#ffc85a]{stolen.Name}[/color]"), Assets.Gold, 20);
                            }
                        }
                        break;
                    }
                    _audio.Sfx("death", -4);
                    _hud.Feed($"[color=#ee5a50]{L10n.Journal(e.Text)}[/color]", Assets.Blood, 30);
                    _sadUntil = _clock + 25f;
                    break;
                case "quest" when e.Text.Contains(" offers a quest ("):
                    actor?.ShowEmote(22, 999f, sticky: true);
                    _audio.Sfx("quest_new", -8);
                    string reason = e.Text[(e.Text.IndexOf("): ", StringComparison.Ordinal) + 3)..];
                    _hud.Feed($"{Who(e.AgentId)} [color=#ee5a50]{L10n.T("needs your help:")}[/color] \"{reason}\"  [color=#8a8a9a]{L10n.T("(talk to them)")}[/color]", Assets.Blood, 30);
                    break;
                case "quest":
                    if (e.Text.Contains(" accepts ")) { if (!World.Quests.All.Any(q => q.GiverId == e.TargetId && q.Status == QuestStatus.Offered)) ActorOf(e.TargetId)?.ClearStickyEmote(); }
                    else if (e.Text.StartsWith("Quest done")) { _audio.Sfx("quest_done", -4); _hud.Banner(L10n.T("Request fulfilled"), L10n.Journal(e.Text).Replace("Requête accomplie : ", "").Replace("Quest done: ", ""), Assets.Jade); ActorOf(e.AgentId)?.ClearStickyEmote(); }
                    else if (e.Text.StartsWith("Quest failed")) { _audio.Sfx("cancel", -4); _hud.Feed($"[color=#ee5a50]{L10n.Journal(e.Text)}[/color]", Assets.Blood, 20); }
                    break;
                case "arrest":
                    OnArrest(e);
                    break;
                case "arrival":
                    if (actor != null && actor.Agent.Has(WorldEvents.HostileTag)) _hud.Feed(L10n.T("{0} emerges from the forest.", $"[color=#ee5a50]{actor.Agent.Name}[/color]"), Assets.Blood, 15);
                    else if (actor != null) _hud.Feed(L10n.T("A stranger arrives: {0}.", Who(e.AgentId)), Assets.Gold, 15);
                    break;
                case "event":
                    OnWorldEvent(e);
                    break;
                case "talk":
                    string talk = L10n.Journal(e.Text).Replace(_player.Agent.Name, L10n.T("you"));
                    int colon = talk.IndexOf(": ", StringComparison.Ordinal);
                    if (colon < 0) colon = talk.IndexOf(" : ", StringComparison.Ordinal);
                    _hud.Feed($"[color=#e8c890]{(colon > 0 ? talk[..colon].TrimEnd() : "")}[/color] [color=#c8c0b0]{(colon > 0 ? talk[(colon + 2)..].TrimStart(':', ' ') : talk)}[/color]", new Color(0.8f, 0.7f, 0.45f), 16);
                    break;
                case "consequence":
                    if (e.Text.Contains(_player.Agent.Name)) _hud.Feed(L10n.Journal(e.Text).Replace(_player.Agent.Name, $"[color=#ffc85a]{L10n.T("you")}[/color]"), Assets.Blood, 15);
                    break;
            }
        }
    }

    private void OnDeed(JournalEntry e, Actor? actor)
    {
        if (actor == null) return;
        var target = ActorOf(e.TargetId);
        if (e.Text.Contains(" attack") && !actor.Agent.IsPlayer)
        {
            if (target != null) actor.Face(target.GlobalPosition - actor.GlobalPosition);
            actor.PlayAttack();
            if (target != null) { target.Flash(); SlashFx(target.GlobalPosition, actor.Facing); _audio.Sfx("hit", -9); }
        }
        if (e.Text.Contains(" steal") && !actor.Agent.IsPlayer)
            _hud.Feed($"{Who(e.AgentId)} [color=#ee5a50]{L10n.T("steals")}[/color] {e.Text[(e.Text.IndexOf('(') + 1)..].TrimEnd(')')}" + (target != null ? $" {L10n.T("from")} {Who(e.TargetId)}" : "") + ".", Assets.Blood, 20);
        if (e.Text.Contains(" give") || e.Text.Contains(" pay")) _audio.Sfx("coin", -10);
    }

    private readonly HashSet<int> _announcedEvents = new();

    private void OnWorldEvent(JournalEntry e)
    {
        bool over = e.Text.StartsWith("Event over");
        foreach (var d in _map.FestivalDecor) d.Visible = World.Events.Active.Any(a => a.Kind == WorldEvents.Festival);
        if (over) { _hud.Feed($"[color=#b8c6e6]{L10n.T("Event over: {0}", L10n.EventName(e.Text.Replace("Event over: ", "")))}[/color]", Assets.Mist, 8); return; }
        // the director's announcement (brain event) usually arrives right after; give it a moment
        _pendingBanner = (_clock + 0.6f, e);
    }

    private (float At, JournalEntry Entry)? _pendingBanner;

    private void FlushBanner()
    {
        if (_pendingBanner is not { } p || _clock < p.At) return;
        _pendingBanner = null;
        if (_announcedEvents.Contains(p.Entry.Id)) return;
        var ev = World.Events.History.FirstOrDefault(x => x.EntryId == p.Entry.Id);
        if (ev != null) AnnounceEvent(ev, null);
    }

    private void AnnounceEvent(WorldEvent ev, string? announcement)
    {
        if (L10n.French && announcement != null && announcement.StartsWith("A ") && announcement.EndsWith(" begins."))
            announcement = $"{char.ToUpper(L10n.EventName(ev.Kind)[0])}{L10n.EventName(ev.Kind)[1..]} : ça commence."; // the rule director speaks English
        if (!_announcedEvents.Add(ev.EntryId)) return;
        string title = ev.Kind switch
        {
            WorldEvents.Festival => L10n.T("Lantern Festival"),
            WorldEvents.Storm => L10n.T("A Storm Rolls In"),
            WorldEvents.BanditRaid => L10n.T("Bandit Raid!"),
            WorldEvents.StrangerArrives => L10n.T("A Stranger Arrives"),
            WorldEvents.Illness => L10n.T("Sickness"),
            _ => ev.Kind,
        };
        var color = ev.Kind is WorldEvents.BanditRaid or WorldEvents.Illness ? Assets.Blood : ev.Kind == WorldEvents.Storm ? Assets.Mist : Assets.Gold;
        _hud.Banner(title, announcement ?? ev.Reason, color);
        _audio.Sfx(ev.Kind == WorldEvents.BanditRaid ? "alert" : "event", -4);
        _hud.Feed($"[color=#{Hex(color)}]{title}[/color] — {announcement ?? ev.Reason}", color, 30);
    }

    /// <summary>Mind-level happenings (Brain): thinking, thoughts, conversations, plans, quests, director, chronicle.</summary>
    private void OnBrainEvent(BrainEvent e)
    {
        var actor = ActorOf(e.AgentId);
        switch (e.Kind)
        {
            case "thinking":
                if (actor != null && actor.Visible && e.Text != "converse") actor.ShowEmote(20, 2.5f);
                break;
            case "thought":
                if (actor == null) break;
                actor.ShowEmote(Assets.EmoteFor(e.Emotion ?? "thinking"), 3f);
                if (OnScreen(actor) && actor.GlobalPosition.DistanceTo(_player.GlobalPosition) < 260f) _hud.Say(actor, e.Text, true, 5f);
                break;
            case "say":
                _pendingLines.Add((_clock + e.Order * 3.2f, e.AgentId!, e.TargetId, e.Text));
                break;
            case "plan":
                break; // visible in the Mind panel; too chatty for the feed
            case "quest":
                break; // the journal's "offers a quest" entry drives the marker and the feed
            case "event":
                var ev = World.Events.History.FirstOrDefault(x => x.EntryId == e.EntryId);
                if (ev != null) AnnounceEvent(ev, e.Text);
                break;
            case "chronicle":
                _lastChronicle = e.Text;
                if (!_ending) ShowChronicle(); // the legend takes over at the end
                break;
            case "reply":
                OnReply(e);
                break;
            case "epilogue":
                ShowEpilogue(e.Text);
                break;
            case "end":
                _endAfterReply = true;
                break;
            case "rejected":
                if (!_devView || _clock - _lastRejectShown < 5f) break; // F3: developer view
                _lastRejectShown = _clock;
                _hud.Feed($"[color=#6f7a8a]{L10n.T("Kinloom arbiter blocked {0}: {1}", NameOf(e.AgentId), e.Text)}[/color]", new Color(0.3f, 0.35f, 0.45f), 8);
                break;
            case "error":
                GD.PrintErr($"[brain] {e.Text}");
                break;
        }
    }

    private void ShowPendingLines()
    {
        for (int i = _pendingLines.Count - 1; i >= 0; i--)
        {
            var l = _pendingLines[i];
            if (_clock < l.At) continue;
            _pendingLines.RemoveAt(i);
            var speaker = ActorOf(l.Speaker);
            if (speaker == null) continue;
            var listener = ActorOf(l.Listener);
            if (listener != null) { speaker.Face(listener.GlobalPosition - speaker.GlobalPosition); listener.Face(speaker.GlobalPosition - listener.GlobalPosition); }
            if (OnScreen(speaker)) { _hud.Say(speaker, l.Text, false, 3.4f); _audio.Voice(l.Speaker); }
        }
    }

    private bool OnScreen(Actor a)
    {
        var p = GetCanvasTransform() * a.GlobalPosition;
        return a.Visible && p.X > -50 && p.X < 1970 && p.Y > -50 && p.Y < 1130;
    }
}
