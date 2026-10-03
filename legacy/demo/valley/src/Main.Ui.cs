using System.Text;
using Godot;
using Kinloom.Brain;
using Kinloom.Core;

namespace Valley;

public partial class Main
{
    private Actor? _talkingTo;
    private int _waitingTicket = -1;
    private bool _endAfterReply;
    private float _closeAt = -1;
    private Actor? _mindOf;
    private float _mindRefresh;
    private static readonly Dictionary<string, float> BasePrices = new() { ["mira"] = 2f, ["goro"] = 8f, ["yuki"] = 3f, ["daichi"] = 10f };

    private void SetupUi()
    {
        _hud.DialogueInput.TextSubmitted += text => { if (!string.IsNullOrWhiteSpace(text)) SayToNpc(text.Trim()); };
        PlaceItems();
    }

    private void OpenDialogue(Actor npc)
    {
        _talkingTo = npc;
        _endAfterReply = false;
        _closeAt = -1;
        npc.Face(_player.GlobalPosition - npc.GlobalPosition);
        _player.Face(npc.GlobalPosition - _player.GlobalPosition);
        var a = npc.Agent;
        _hud.DialogueFace.Texture = Assets.Face(npc.Look);
        _hud.DialogueName.Text = a.Name;
        _hud.DialogueRole.Text = L10n.T(a.Profile.Role);
        float o = a.Mind.OpinionOf(_player.Agent.Id);
        string mood = L10n.Opinion(o);
        _hud.TypeText($"[color=#9a9ab0]{L10n.T("{0} looks at you. ({1} towards you.)", a.Name, char.ToUpper(mood[0]) + mood[1..])}[/color]");
        _hud.SkipTyping();
        _hud.DialoguePanel.Visible = true;
        _hud.DialogueInput.Text = "";
        _hud.DialogueInput.Editable = true;
        _hud.DialogueInput.GrabFocus();
        RefreshDialogueActions();
        _audio.Sfx("menu", -10);
    }

    private void RefreshDialogueActions()
    {
        foreach (var c in _hud.DialogueActions.GetChildren()) c.QueueFree();
        if (_talkingTo == null) return;
        var a = _talkingTo.Agent;
        foreach (var line in new[] { L10n.T("What's the news?"), L10n.T("Can I help you?"), L10n.T("Tell me about yourself.") })
            _hud.ActionButton(line, () => SayToNpc(line));
        var offered = World.Quests.All.FirstOrDefault(q => q.GiverId == a.Id && q.Status == QuestStatus.Offered);
        if (offered != null) _hud.ActionButton(L10n.T("Accept request"), () => AcceptQuest(offered));
        if (BasePrices.TryGetValue(a.Id, out float price))
        {
            bool refuses = !Commerce.WillTrade(a, _player.Agent);
            float p = Commerce.PriceFor(a, _player.Agent, price);
            _hud.ActionButton(refuses ? L10n.T("Buy (refused)") : L10n.T("Buy ({0} g)", p.ToString("0")), Buy);
        }
        _hud.ActionButton(L10n.T("Give 5 g"), GiveGold);
        foreach (var item in World.Items.Where(i => i.OwnerId == _player.Agent.Id).Take(2))
            _hud.ActionButton(L10n.T("Give {0}", item.Name), () => GiveItem(item));
    }

    private void SayToNpc(string text)
    {
        if (_talkingTo == null || _waitingTicket >= 0) return;
        _hud.DialogueInput.Text = "";
        _hud.DialogueInput.Editable = false;
        _hud.TypeText($"[color=#9fe0c0]{L10n.T("You:")}[/color] {text}\n[color=#9a9ab0]…[/color]");
        _hud.SkipTyping();
        _talkingTo.ShowEmote(20, 30f);
        _waitingTicket = _brain.Talk(_talkingTo.Agent.Id, text);
        _audio.Sfx("menu", -12, 1.2f);
    }

    private void OnReply(BrainEvent e)
    {
        if (e.Ticket != _waitingTicket) return;
        _waitingTicket = -1;
        if (_talkingTo == null) return;
        _talkingTo.ShowEmote(Assets.EmoteFor(e.Emotion), 3f);
        _hud.TypeText(e.Text);
        _hud.DialogueInput.Editable = true;
        _hud.DialogueInput.GrabFocus();
        RefreshDialogueActions();
        if (_endAfterReply) { _endAfterReply = false; _closeAt = _clock + 3.5f; }
    }

    private void CloseDialogue()
    {
        _hud.DialoguePanel.Visible = false;
        _hud.DialogueInput.ReleaseFocus();
        _talkingTo = null;
        _waitingTicket = -1;
        _closeAt = -1;
        _audio.Sfx("cancel", -12);
    }

    private void AcceptQuest(Quest q)
    {
        if (World.Quests.Accept(World, q.Id, _player.Agent.Id))
        {
            _talkingTo?.ClearStickyEmote();
            _audio.Sfx("accept", -6);
            _hud.Feed($"[color=#9fe0c0]{L10n.T("Request accepted")}[/color] — {q.Reason}", Assets.Jade, 25);
        }
        RefreshDialogueActions();
    }

    private void Buy()
    {
        if (_talkingTo == null) return;
        var a = _talkingTo.Agent;
        var result = Commerce.Trade(World, _player.Agent, a, BasePrices[a.Id]);
        if (result.Refused) { _hud.TypeText($"[color=#ee5a50]{a.CurrentBark(World.Tick) ?? "…"}[/color] {L10n.T("({0} refuses to serve you.)", a.Name)}"); _audio.Sfx("cancel", -6); return; }
        int price = (int)Math.Ceiling(result.Price);
        if (_player.Agent.Gold < price) { _hud.TypeText(L10n.T("You can't afford it ({0} g).", price)); return; }
        _player.Agent.Gold -= price;
        a.Gold += price;
        _player.Agent.Health = Math.Min(_player.Agent.MaxHealth, _player.Agent.Health + 3);
        _audio.Sfx("coin", -6);
        _hud.TypeText($"{a.CurrentBark(World.Tick) ?? "…"} [color=#9a9ab0]{L10n.T("(you pay {0} g{1} and feel better)", price, result.Price > BasePrices[a.Id] + 0.01f ? L10n.T(", more than the usual price") : "")}[/color]");
        RefreshDialogueActions();
    }

    private void GiveGold()
    {
        if (_talkingTo == null || _player.Agent.Gold < 5) return;
        _player.Agent.Gold -= 5;
        _talkingTo.Agent.Gold += 5;
        Actions.PerformDeed(World, _player.Agent, "pay", _talkingTo.Agent.Id, null);
        _audio.Sfx("coin", -6);
        _hud.TypeText($"[color=#9a9ab0]{L10n.T("You give 5 gold to {0}.", _talkingTo.Agent.Name)}[/color]");
        RefreshDialogueActions();
    }

    private void GiveItem(Item item)
    {
        if (_talkingTo == null) return;
        Actions.Give(World, _player.Agent, _talkingTo.Agent, item.Id);
        _audio.Sfx("accept", -6);
        _hud.TypeText($"[color=#9a9ab0]{L10n.T("You hand the {0} to {1}.", item.Name, _talkingTo.Agent.Name)}[/color]");
        RefreshDialogueActions();
    }

    // ------------------------------------------------------------------ mind panel

    private void ToggleMind()
    {
        if (_hud.MindPanel.Visible) { _hud.MindPanel.Visible = false; _mindOf = null; return; }
        var npc = NearestNpc(160f, includeHostile: true);
        if (npc != null) OpenMind(npc);
    }

    private void OpenMind(Actor npc)
    {
        _mindOf = npc;
        _hud.MindPanel.Visible = true;
        _hud.MindFace.Texture = Assets.Face(npc.Look);
        _mindRefresh = 0;
    }

    private void RefreshMind()
    {
        if (_mindOf == null) return;
        var a = _mindOf.Agent;
        var s = _brain.StateOf(a.Id);
        var sb = new StringBuilder();
        string gold = Hex(Assets.Gold), jade = Hex(Assets.Jade), mist = Hex(Assets.Mist), blood = Hex(Assets.Blood);
        sb.Append($"[font_size=30][color=#{gold}]{a.Name}[/color][/font_size]  [color=#{mist}]{L10n.T(a.Profile.Role)}[/color]\n");
        if (!a.IsAlive) sb.Append($"[color=#{blood}]{L10n.T("Dead.")}[/color]\n");
        if (a.Plan != null) sb.Append($"\n[color=#{jade}]{L10n.T("INTENTION")}[/color]  {a.Plan.Intention}\n");
        var step = a.Plan?.ActiveStep(World.MinuteOfDay);
        sb.Append($"[color=#{jade}]{L10n.T("NOW")}[/color]  {(a.Intent.Kind != IntentKind.Routine ? $"{a.Intent} {L10n.T("(reflex)")}" : step?.ToString().Replace(" — ", " · ") ?? L10n.T("following the usual routine"))}\n");
        if (s.Goal != null) sb.Append($"[color=#{jade}]{L10n.T("WANTS")}[/color]  {s.Goal}\n");
        if (s.Beliefs.Count > 0)
        {
            sb.Append($"\n[color=#{jade}]{L10n.T("THOUGHTS")}[/color]\n");
            foreach (var b in s.Beliefs.TakeLast(4)) sb.Append($"· [i]{b}[/i]\n");
        }
        var memories = a.Mind.Memories.OrderByDescending(m => m.Salience).ThenByDescending(m => m.DeedTick).Take(5).ToList();
        if (memories.Count > 0)
        {
            sb.Append($"\n[color=#{jade}]{L10n.T("KNOWS")}[/color]\n");
            foreach (var m in memories)
                sb.Append($"· {L10n.Describe(World, m)} [color=#{mist}]({(m.Firsthand ? L10n.T("saw it") : L10n.T("heard from {0}", World.NameOf(m.SourceId)))})[/color]{(m.IsLie ? $" [color=#{blood}]{L10n.T("← a lie")}[/color]" : "")}\n");
        }
        sb.Append($"\n[color=#{jade}]{L10n.T("FEELINGS")}[/color]\n");
        var people = World.Agents.Where(o => o.Id != a.Id && o.Present && Math.Abs(a.Mind.OpinionOf(o.Id)) > 0.05f)
            .OrderByDescending(o => o.IsPlayer ? 10 : Math.Abs(a.Mind.OpinionOf(o.Id))).Take(6);
        foreach (var o in people)
        {
            float v = a.Mind.OpinionOf(o.Id);
            int bars = (int)Math.Round(Math.Abs(v) * 10);
            string color = v >= 0 ? jade : blood;
            sb.Append($"{(o.IsPlayer ? L10n.T("You") : o.Name),-8} [color=#{color}]{new string('■', bars)}[/color][color=#333344]{new string('■', 10 - bars)}[/color] {L10n.Opinion(v)}\n");
        }
        var lastThought = World.Journal.Entries.LastOrDefault(e => e.AgentId == a.Id && (e.Kind == "thought" || e.Kind == "plan" || e.Kind == "reaction"));
        if (lastThought != null)
        {
            sb.Append($"\n[color=#{jade}]{L10n.T("WHY?")}[/color] [color=#{mist}]{L10n.T("(causal chain of the latest decision)")}[/color]\n");
            foreach (var link in World.Journal.Why(lastThought.Id).Take(4))
                sb.Append($"← [color=#{mist}]{World.Clock(link.Tick)}[/color] {L10n.Journal(link.Text)}\n");
        }
        _hud.MindText.Text = sb.ToString();
    }

    private void ToggleQuests()
    {
        _hud.QuestPanel.Visible = !_hud.QuestPanel.Visible;
        if (!_hud.QuestPanel.Visible) return;
        var sb = new StringBuilder($"[font_size=34][color=#{Hex(Assets.Gold)}]{L10n.T("Requests")}[/color][/font_size]\n\n");
        if (World.Quests.All.Count == 0) sb.Append(L10n.T("Nobody has asked you for anything yet. Talk to people; their troubles are real.") + "\n");
        foreach (var q in World.Quests.All.OrderBy(q => q.Status))
        {
            string color = q.Status switch { QuestStatus.Completed => Hex(Assets.Jade), QuestStatus.Failed => Hex(Assets.Blood), QuestStatus.Active => Hex(Assets.Gold), _ => Hex(Assets.Mist) };
            sb.Append($"[color=#{color}]{L10n.Status(q.Status)}[/color]  {World.NameOf(q.GiverId)}: \"{q.Reason}\"\n");
            sb.Append($"      [color=#{Hex(Assets.Mist)}]{L10n.QuestKind(q.Kind)} · {World.NameOf(q.TargetId)}{(q.ItemId != null ? " · " + World.NameOf(q.ItemId) : "")} · {L10n.T("reward {0} g", q.Reward)}[/color]\n\n");
        }
        _hud.QuestText.Text = sb.ToString();
    }

    private void ShowChronicle()
    {
        if (_lastChronicle == null) { _hud.Feed(L10n.T("No chronicle yet: the storyteller writes one each night."), Assets.Mist, 4); return; }
        var parts = _lastChronicle.Split("\n\n", 2);
        _hud.ChronicleText.Text = $"[center][font_size=20][color=#8a5a30]{L10n.T("THE CHRONICLE OF ASAGIRI")}[/color][/font_size]\n[font_size=40]{parts[0]}[/font_size][/center]\n\n{(parts.Length > 1 ? parts[1] : "")}\n\n[center][color=#8a5a30][font_size=18]{L10n.T("Enter to continue")}[/font_size][/color][/center]";
        _hud.ChroniclePanel.Visible = true;
        _audio.Sfx("quest_new", -8);
    }

    private void CloseChronicle()
    {
        if (_ended) { GetTree().ReloadCurrentScene(); return; }
        _hud.ChroniclePanel.Visible = false;
    }

    // ------------------------------------------------------------------ the end

    private bool _ending, _ended;

    private void EndStory()
    {
        if (_ending) return;
        _ending = true;
        _hud.Banner(L10n.T("The last night"), L10n.T("Your time in Asagiri is over. The valley decides how it will remember you…"), Assets.Gold);
        _audio.Music("sad");
        _brain.RequestEpilogue();
    }

    private void ShowEpilogue(string text)
    {
        _ended = true;
        var lines = text.Split('\n');
        string title = lines[0], epithet = lines.Length > 1 ? lines[1] : "";
        string body = string.Join("\n", lines.Skip(2)).Trim();
        string pid = _player.Agent.Id;
        var villagers = World.Agents.Where(a => !a.IsPlayer && !a.Has(WorldEvents.HostileTag) && a.Present).ToList();
        var trust = villagers.Where(a => a.Mind.OpinionOf(pid) > 0.2f).Select(a => a.Name).ToList();
        var hate = villagers.Where(a => a.Mind.OpinionOf(pid) < -0.2f).Select(a => a.Name).ToList();
        int done = World.Quests.All.Count(q => q.HeroId == pid && q.Status == QuestStatus.Completed);
        int crimes = villagers.Sum(a => a.Mind.Memories.Count(m => m.ActorId == pid && m.IsCrime));
        string stats = $"[color=#3a6a4a]{L10n.T("Trusted by:")}[/color] {(trust.Count > 0 ? string.Join(", ", trust) : L10n.T("no one"))}\n"
            + $"[color=#8a3030]{L10n.T("Resented by:")}[/color] {(hate.Count > 0 ? string.Join(", ", hate) : L10n.T("no one"))}\n"
            + L10n.T("Requests fulfilled: {0}   ·   Crimes remembered by villagers: {1}", done, crimes);
        _hud.ChronicleText.Text = $"[center][font_size=20][color=#8a5a30]{L10n.T("THE LEGEND OF THE TRAVELLER")}[/color][/font_size]\n[font_size=40]{title}[/font_size]\n"
            + $"[font_size=26][color=#8a5a30]{epithet}[/color][/font_size][/center]\n\n{body}\n\n{stats}\n\n"
            + $"[center][color=#8a5a30][font_size=18]{L10n.T("Enter to live another story")}[/font_size][/color][/center]";
        _hud.ChroniclePanel.Visible = true;
        _audio.Sfx("quest_done", -4);
    }

    // ------------------------------------------------------------------ hud

    private void UpdateHud(float dt)
    {
        _clock += dt;
        int minute = World.MinuteOfDay;
        _hud.Clock.Text = $"{L10n.T("Day {0}", World.Day)} · {minute / 60:00}:{minute % 60:00}";
        var active = World.Events.Active.Select(e => L10n.EventName(e.Kind)).ToList();
        string brain = _brain.InFlight > 0 ? L10n.T("{0} mind(s) thinking…", _brain.InFlight) : "";
        if (_brain.Stats.Cost is double cost) brain += (brain.Length > 0 ? "  ·  " : "") + (L10n.French ? $"IA ≈ {cost:0.000} $" : $"AI ≈ ${cost:0.000}");
        _hud.Status.Text = string.Join("  ·  ", new[] { active.Count > 0 ? string.Join(", ", active) : "", brain, _speed > 0 ? L10n.T("time x{0}", Speeds[_speed]) : "" }.Where(x => x.Length > 0));
        _hud.SetHearts(_player.Agent.Health, _player.Agent.MaxHealth);
        _hud.GoldLabel.Text = _player.Agent.Gold.ToString();
        var carried = World.Items.Where(i => i.OwnerId == _player.Agent.Id).Select(i => i.Name).ToList();
        _hud.Inventory.Text = carried.Count > 0 ? L10n.T("Carrying: {0}", string.Join(", ", carried)) : "";
        _hud.Inventory.Visible = carried.Count > 0;
        _hud.UpdateBubbles(dt, p => GetCanvasTransform() * p);
        UpdateObjectives();
        _hud.UpdateNameplates(_started ? _actors.Values.Where(a => a.Visible && !a.Agent.IsPlayer && a.Agent.IsAlive && a.GlobalPosition.DistanceTo(_player.GlobalPosition) < 120f) : Enumerable.Empty<Actor>(), p => GetCanvasTransform() * p);
        if (_started && !_ending && World.Day >= _scenario.Days && World.Hour >= 22) EndStory();
        ShowPendingLines();
        FlushBanner();
        UpdateItems();
        if (_closeAt > 0 && _clock >= _closeAt) CloseDialogue();
        if (_knockedOut > 0) _knockedOut -= dt;
        _mindRefresh -= dt;
        if (_hud.MindPanel.Visible && _mindRefresh <= 0) { _mindRefresh = 0.5f; RefreshMind(); }
    }
}
