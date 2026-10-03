using Godot;
using Kinloom.Core;

namespace Valley;

/// <summary>--film: a directed ~3 minute session for the demo video (run with Godot's --write-movie).
/// The player walks, types and acts like a person would; every NPC line and decision is live from the Brain.</summary>
public partial class Main
{
    private async Task WalkTo(Vector2 target, float timeout = 20f)
    {
        var path = _map.Path(_player.GlobalPosition, target);
        float waited = 0;
        foreach (var point in path)
        {
            while (_player.GlobalPosition.DistanceTo(point) > 3f && waited < timeout)
            {
                _autoMove = (point - _player.GlobalPosition).Normalized();
                await ToSignal(GetTree(), SceneTree.SignalName.ProcessFrame);
                waited += (float)GetProcessDeltaTime();
            }
        }
        _autoMove = Vector2.Zero;
    }

    private async Task WalkToActor(Actor who) => await WalkTo(who.GlobalPosition + new Vector2(14, 6));

    private async Task TypeAndSay(string text)
    {
        _hud.DialogueInput.Text = "";
        foreach (char c in text)
        {
            _hud.DialogueInput.Text += c;
            _hud.DialogueInput.CaretColumn = _hud.DialogueInput.Text.Length;
            await Wait(0.045f);
        }
        await Wait(0.4f);
        SayToNpc(text);
        await Until(() => _waitingTicket < 0, 45f);
        await Until(() => !_hud.Typing, 20f);
        await Wait(3.5f);
    }

    private async Task RunFilm()
    {
        await Wait(3f);
        Begin();
        await Wait(3f);

        // 1. arrival: cross the bridge into a village that is already alive
        await WalkTo(WorldMap.ToWorld(new Vec2(24 + WorldMap.OX, 21)));
        await Wait(2f);

        // 2. free conversation that turns into a request
        var mira = _actors["mira"];
        await WalkToActor(mira);
        OpenDialogue(mira);
        await Wait(1.2f);
        await TypeAndSay(L10n.French ? "Quelque chose te tracasse ? Que se passe-t-il dans ce village ?" : "You look worried. What's going on in this village?");
        await TypeAndSay(L10n.French ? "Je peux t'aider ? Je sais retrouver ce qui a disparu." : "Can I help? I'm good at finding things.");
        var offered = World.Quests.All.FirstOrDefault(q => q.GiverId == "mira" && q.Status == QuestStatus.Offered);
        if (offered != null) { AcceptQuest(offered); await Wait(2f); }
        CloseDialogue();

        // 3. look inside a mind
        OpenMind(mira);
        await Wait(6f);
        _hud.MindPanel.Visible = false;
        _mindOf = null;

        // 4. a theft in broad daylight
        _speed = 1;
        var silk = World.FindItem("silk")!;
        await WalkTo(_itemProps["silk"].GlobalPosition + new Vector2(10, 0));
        _speed = 0;
        await Wait(1f);
        TryTake();
        await Wait(7f);
        var witness = World.Agents.Where(a => !a.IsPlayer && a.Active && !a.Has(Tags.Authority) && a.Mind.Memories.Any(m => m.ActorId == _player.Agent.Id && m.IsCrime))
            .OrderBy(a => a.Position.DistanceTo(_player.Agent.Position)).FirstOrDefault();
        _ = silk;

        // 5. the world noticed: ask a witness
        if (witness != null)
        {
            var w = _actors[witness.Id];
            await WalkToActor(w);
            OpenDialogue(w);
            await Wait(1f);
            await TypeAndSay(L10n.French ? "Pourquoi tu me regardes comme ça ?" : "Why are you looking at me like that?");
            CloseDialogue();
            OpenMind(w);
            await Wait(5f);
            _hud.MindPanel.Visible = false;
            _mindOf = null;
        }

        // 6. the village lives on; rumours travel
        _speed = 2;
        await Wait(8f);
        _speed = 1;
        await Wait(6f);

        // 7. dusk raid (forced here so it lands on camera; in play the director decides)
        _speed = 0;
        var ev = WorldEvents.TryStart(World, WorldEvents.BanditRaid, "square", 3 * World.TicksPerHour, "Crow's gang comes to collect what Riku owes", null, out _);
        if (ev != null) AnnounceEvent(ev, "Masked figures slip out of the forest while the village sleeps uneasy.");
        await Wait(5f);
        for (int round = 0; round < 12; round++)
        {
            var bandit = _actors.Values.Where(a => a.Agent.Active && a.Agent.Has(WorldEvents.HostileTag))
                .OrderBy(a => a.GlobalPosition.DistanceTo(_player.GlobalPosition)).FirstOrDefault();
            if (bandit == null) break;
            await WalkTo(bandit.GlobalPosition + new Vector2(-12, 0), 4f);
            _player.Face(bandit.GlobalPosition - _player.GlobalPosition);
            // only swing when the raider is the one in front: the traveller of this film does not hurt villagers
            if (StrikeTarget() is { } target && target.Agent.Has(WorldEvents.HostileTag))
            {
                _attackCooldown = 0;
                Strike();
            }
            await Wait(0.45f);
        }
        await Wait(3f);

        // 8. night, the chronicle, the legend
        _speed = 2;
        await Until(() => World.Hour >= 21 || World.Hour < 4, 60f);
        _speed = 0;
        await Wait(4f);
        _brain.RequestChronicle();
        await Until(() => _hud.ChroniclePanel.Visible, 60f);
        await Wait(9f);
        CloseChronicle();
        EndStory();
        await Until(() => _ended, 90f);
        await Wait(10f);
        GD.Print($"[film] brain: {_brain.Stats}");
        GetTree().Quit();
    }
}
