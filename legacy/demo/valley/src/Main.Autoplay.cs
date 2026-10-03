using Godot;
using Kinloom.Core;

namespace Valley;

/// <summary>--autoplay &lt;dir&gt;: plays a short scripted session and saves screenshots (rendering checks and demo stills).</summary>
public partial class Main
{
    private Vector2 _autoMove;
    private string? _autoDir;
    private int _shot;

    private void StartAutoplay(string dir)
    {
        _autoDir = System.IO.Path.GetFullPath(dir);
        System.IO.Directory.CreateDirectory(_autoDir);
        _ = RunAutoplay();
    }

    private void UpdateAutoplay(float dt) { }

    private void TeleportTo(Vec2 sim)
    {
        _player.Position = WorldMap.CellCenter(_map.NearestFree(WorldMap.Cell(WorldMap.ToWorld(sim))));
        _player.Agent.Position = WorldMap.ToSim(_player.Position);
        _camera.ResetSmoothing();
    }

    /// <summary>--qa &lt;dir&gt;: tours the adventure content (forest, beasts, camp, loot, night, arrest) for screenshots.</summary>
    private async Task RunQa(string dir)
    {
        _autoDir = System.IO.Path.GetFullPath(dir);
        System.IO.Directory.CreateDirectory(_autoDir);
        await Wait(0.8f);
        await Shot("title");
        Begin();
        await Wait(2f);
        await Shot("village_objectives");
        TeleportTo(new Vec2(24, 22));
        await Wait(1.5f);
        await Shot("forest_trail");
        var slime = _actors["slime1"];
        TeleportTo(WorldMap.ToSim(slime.GlobalPosition + new Vector2(30, 0)));
        await Wait(1.5f);
        await Shot("slime_hunts");
        for (int i = 0; i < 4; i++)
        {
            var near = _actors.Values.Where(a => a.Agent.Active && a.Agent.Has("monster")).OrderBy(a => a.GlobalPosition.DistanceTo(_player.GlobalPosition)).First();
            _player.Face(near.GlobalPosition - _player.GlobalPosition);
            _attackCooldown = 0;
            Strike();
            await Wait(0.35f);
        }
        await Shot("forest_fight");
        var herb = _itemProps["moon_herb"];
        TeleportTo(WorldMap.ToSim(herb.GlobalPosition + new Vector2(10, 0)));
        await Wait(0.5f);
        TryTake();
        await Wait(1f);
        await Shot("herb_picked");
        TeleportTo(new Vec2(12, 16));
        await Wait(2.5f);
        await Shot("bandit_camp");
        // a theft in front of the guards, to see the arrest
        _player.Agent.Health = _player.Agent.MaxHealth;
        _speed = 2;
        await Until(() => World.Hour >= 10, 60f);
        _speed = 0;
        TeleportTo(WorldMap.ToSim(_itemProps["silk"].GlobalPosition + new Vector2(10, 0)));
        await Wait(0.6f);
        TryTake();
        await Wait(1f);
        await Shot("theft");
        _speed = 1;
        await Until(() => _hud.ArrestPanel.Visible, 40f);
        _speed = 0;
        await Wait(0.5f);
        await Shot("arrest");
        if (_hud.ArrestPanel.Visible) PayFine(Fine());
        await Wait(1f);
        _speed = 2;
        await Until(() => World.Hour >= 21, 90f);
        _speed = 0;
        TeleportTo(new Vec2(36 + WorldMap.OX, 23));
        await Wait(2.5f);
        await Shot("village_night");
        TeleportTo(new Vec2(40, 21));
        await Wait(1.5f);
        await Shot("forest_edge_night");
        GetTree().Quit();
    }

    /// <summary>--intentcheck &lt;dir&gt;: words that are acts (pay, bluff, accuse, recruit), with the real model.</summary>
    private async Task RunIntentCheck(string dir)
    {
        _autoDir = System.IO.Path.GetFullPath(dir);
        System.IO.Directory.CreateDirectory(_autoDir);
        await Wait(0.5f);
        Begin();
        await Wait(1f);
        async Task Say(Actor npc, string line, string shot)
        {
            TeleportNear(npc, new Vector2(16, 4));
            await Wait(0.3f);
            if (!_hud.DialoguePanel.Visible || _talkingTo != npc) OpenDialogue(npc);
            int before = _player.Agent.Gold, npcBefore = npc.Agent.Gold;
            SayToNpc(line);
            await Until(() => _waitingTicket < 0, 45f);
            await Until(() => !_hud.Typing, 20f);
            await Wait(0.5f);
            GD.Print($"[intent] \"{line}\" -> player gold {before} -> {_player.Agent.Gold}, {npc.Agent.Name} gold {npcBefore} -> {npc.Agent.Gold} | reply: {_hud.DialogueText.GetParsedText()}");
            await Shot(shot);
        }
        var mira = _actors["mira"];
        await Say(mira, "Tiens, je te donne 5 pièces pour ta peine.", "pay");
        await Say(mira, "Et voilà 100 pièces d'or, rien que pour toi !", "bluff");
        var q = World.Quests.All.FirstOrDefault(x => x.GiverId == "mira" && x.Status == QuestStatus.Offered);
        if (q != null) AcceptQuest(q);
        await Say(mira, "Je sais qui a volé ta farine : c'est Riku.", "accuse");
        CloseDialogue();
        var kaito = _actors["kaito"];
        await Say(kaito, "Viens avec moi dans la forêt, j'ai besoin d'un bon sabre à mes côtés.", "follow");
        GD.Print($"[intent] kaito follows: {kaito.Agent.FollowId ?? "no"} | mira quest: {q?.Status.ToString() ?? "none"}");
        GD.Print($"[intent] brain: {_brain.Stats}");
        GetTree().Quit();
    }

    /// <summary>--motioncheck: 25 s of village life, then who turned around or flipped facing too often.</summary>
    private async Task RunMotionCheck()
    {
        await Wait(0.5f);
        Begin();
        TeleportTo(new Vec2(36 + WorldMap.OX, 22));
        await Wait(25f);
        foreach (var a in _actors.Values.Where(a => !a.Agent.IsPlayer && a.Visible).OrderByDescending(a => a.Reversals * 3 + a.DirChanges).Take(8))
            GD.Print($"[motion] {a.Agent.Id,-9} reversals {a.Reversals,3}  facing changes {a.DirChanges,3}  intent {a.Agent.Intent}");
        GetTree().Quit();
    }

    /// <summary>--clip: the first seconds of a game, walking into the village (record with --write-movie to check motion).</summary>
    private async Task RunClip()
    {
        await Wait(0.5f);
        Begin();
        await Wait(1.5f);
        await WalkTo(WorldMap.ToWorld(new Vec2(30 + WorldMap.OX, 21)), 12f);
        await WalkTo(WorldMap.ToWorld(new Vec2(36 + WorldMap.OX, 16)), 8f);
        await Wait(4f);
        GetTree().Quit();
    }

    /// <summary>--fxcheck &lt;dir&gt;: lantern festival at night, then a storm (rendering check, few LLM calls).</summary>
    private async Task RunFxCheck(string dir)
    {
        _autoDir = System.IO.Path.GetFullPath(dir);
        System.IO.Directory.CreateDirectory(_autoDir);
        await Wait(0.5f);
        Begin();
        var square = World.FindPlace("square")!;
        _player.Position = WorldMap.ToWorld(square.Position) + new Vector2(0, 40);
        _player.Agent.Position = WorldMap.ToSim(_player.Position);
        _camera.ResetSmoothing();
        _speed = 2;
        await Until(() => World.Hour >= 19, 90f);
        _speed = 0;
        var fest = WorldEvents.TryStart(World, WorldEvents.Festival, "square", 3 * World.TicksPerHour, "fx check", null, out _);
        if (fest != null) AnnounceEvent(fest, "Paper lanterns rise over the square.");
        await Wait(6f);
        await Shot("festival");
        var storm = WorldEvents.TryStart(World, WorldEvents.Storm, null, 3 * World.TicksPerHour, "fx check", null, out _);
        if (storm != null) AnnounceEvent(storm, "Thunder rolls down from the mountains.");
        await Wait(4f);
        await Shot("storm");
        GetTree().Quit();
    }

    private async Task Wait(float seconds) => await ToSignal(GetTree().CreateTimer(seconds), SceneTreeTimer.SignalName.Timeout);

    private async Task Until(Func<bool> condition, float timeout)
    {
        float waited = 0;
        while (!condition() && waited < timeout) { await Wait(0.25f); waited += 0.25f; }
    }

    private async Task Shot(string name)
    {
        await ToSignal(RenderingServer.Singleton, RenderingServer.SignalName.FramePostDraw);
        var image = GetViewport().GetTexture().GetImage();
        string path = System.IO.Path.Combine(_autoDir!, $"{++_shot:00}_{name}.png");
        image.SavePng(path);
        GD.Print($"[autoplay] {path}");
    }

    private void TeleportNear(Actor target, Vector2 offset)
    {
        _player.Position = WorldMap.CellCenter(_map.NearestFree(WorldMap.Cell(target.GlobalPosition + offset)));
        _player.Agent.Position = WorldMap.ToSim(_player.Position);
        _camera.ResetSmoothing();
    }

    private async Task RunAutoplay()
    {
        await Wait(1.0f);
        await Shot("title");
        Begin();
        await Wait(1.5f);
        _autoMove = Vector2.Right;
        await Wait(3.2f);
        _autoMove = Vector2.Zero;
        await Wait(0.5f);
        await Shot("arrival");

        // free conversation with Mira
        var mira = _actors["mira"];
        TeleportNear(mira, new Vector2(18, 4));
        await Wait(0.8f);
        OpenDialogue(mira);
        await Wait(0.3f);
        SayToNpc(L10n.French ? "Quelque chose te tracasse ? Que se passe-t-il dans ce village ?" : "You look worried. What's going on in this village?");
        await Shot("thinking");
        await Until(() => _waitingTicket < 0, 40f);
        await Wait(2.5f);
        await Shot("dialogue");
        SayToNpc(L10n.French ? "Je peux t'aider ? Je sais retrouver ce qui a disparu." : "Can I help you with anything? I'm good at finding things.");
        await Until(() => _waitingTicket < 0, 40f);
        await Wait(3f);
        await Shot("dialogue_2");
        var offered = World.Quests.All.FirstOrDefault(q => q.GiverId == "mira" && q.Status == QuestStatus.Offered);
        if (offered != null) AcceptQuest(offered);
        CloseDialogue();
        OpenMind(mira);
        await Wait(1.2f);
        await Shot("mind");
        _hud.MindPanel.Visible = false;
        _mindOf = null;

        // let the village live for a while
        _speed = 1;
        var square = World.FindPlace("square")!;
        _player.Position = WorldMap.ToWorld(square.Position);
        _player.Agent.Position = square.Position;
        _camera.ResetSmoothing();
        await Wait(14f);
        await Shot("village_life");
        await Wait(12f);
        await Shot("village_life_2");

        // a raid, forced for the stills (the director would pick it on its own)
        _speed = 0;
        WorldEvents.TryStart(World, WorldEvents.BanditRaid, "square", 3 * World.TicksPerHour, "autoplay: forced raid", null, out _);
        await Wait(1f);
        var bandit = _actors.Values.FirstOrDefault(a => a.Agent.Has(WorldEvents.HostileTag) && a.Agent.Present);
        await Wait(4f);
        if (bandit != null)
        {
            TeleportNear(bandit, new Vector2(-16, 0));
            await Wait(0.4f);
            await Shot("raid");
            for (int i = 0; i < 3; i++)
            {
                _player.Face(bandit.GlobalPosition - _player.GlobalPosition);
                _attackCooldown = 0;
                Strike();
                await Wait(0.12f);
                if (i == 0) await Shot("combat");
                await Wait(0.4f);
            }
        }
        await Wait(3f);

        // night falls
        _speed = 2;
        await Until(() => World.Hour >= 21 || World.Hour < 4, 60f);
        _speed = 0;
        await Wait(2.5f);
        await Shot("night");

        _brain.RequestChronicle();
        await Until(() => _hud.ChroniclePanel.Visible, 60f);
        await Wait(1f);
        await Shot("chronicle");
        CloseChronicle();
        EndStory();
        await Until(() => _ended, 90f);
        await Wait(1.5f);
        await Shot("epilogue");

        GD.Print($"[autoplay] brain: {_brain.Stats} | by task: {string.Join(", ", _brain.Stats.CallsByTask.Select(kv => kv.Key + "=" + kv.Value))}");
        GetTree().Quit();
    }
}
