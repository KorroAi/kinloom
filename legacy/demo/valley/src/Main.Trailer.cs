using Godot;
using Kinloom.Core;

namespace Valley;

/// <summary>--trailer: a short directed session for the Kinloom trailer (run with Godot's --write-movie).
/// Free talk, a murder in front of the village, a witness, the raid. Every NPC line and reaction is live.</summary>
public partial class Main
{
    /// <summary>Later arrests in the take: shown for 3 s, then paid (or jail when the purse is short).</summary>
    private async Task AutoResolveArrests()
    {
        while (true)
        {
            await Until(() => _hud.ArrestPanel.Visible, 600f);
            await Wait(3f);
            if (!_hud.ArrestPanel.Visible) continue;
            if (_player.Agent.Gold >= Fine()) PayFine(Fine()); else GoToJail();
            await Wait(1f);
        }
    }

    private async Task RunTrailer()
    {
        await Wait(2f);
        Begin();
        await Wait(2f);

        await WalkTo(WorldMap.ToWorld(new Vec2(24 + WorldMap.OX, 21)));
        await Wait(1f);

        // 1. say anything
        var mira = _actors["mira"];
        await WalkToActor(mira);
        OpenDialogue(mira);
        await Wait(1f);
        var only = System.Environment.GetEnvironmentVariable("KL_LINE");
        if (!string.IsNullOrEmpty(only))   // one-line take: the same line typed in every game
        {
            await TypeAndSay(only);
            await Wait(5f);
            GetTree().Quit();
            return;
        }
        await TypeAndSay("Quick question. Would you still love me if I was a worm?");
        await TypeAndSay("Be honest. Is this village a simulation?");
        CloseDialogue();
        await Wait(1f);

        // 2. a murder in broad daylight: pick the villager with the most people around
        Actor? Victim() => _actors.Values
            .Where(a => !a.Agent.IsPlayer && a.Agent.Active && a.Agent.Id != "mira" && !a.Agent.Has(Tags.Authority)
                        && !a.Agent.Has(Combat.ProtectedTag) && !a.Agent.Has(WorldEvents.HostileTag))
            .OrderByDescending(a => _actors.Values.Count(o => o != a && o.Agent.Active && !o.Agent.IsPlayer && o.GlobalPosition.DistanceTo(a.GlobalPosition) < 90f))
            .ThenBy(a => a.GlobalPosition.DistanceTo(_player.GlobalPosition))
            .FirstOrDefault();
        var victim = Victim();
        if (victim != null)
        {
            GD.Print($"[trailer] victim {victim.Agent.Id}");
            _speed = 0;
            await WalkTo(victim.GlobalPosition + new Vector2(-12, 0), 10f);
            for (int swing = 0; swing < 16 && victim.Agent.Active && victim.Agent.Health > 0; swing++)
            {
                if (victim.GlobalPosition.DistanceTo(_player.GlobalPosition) > 18f)
                    await WalkTo(victim.GlobalPosition + new Vector2(-12, 0), 2f);
                _player.Face(victim.GlobalPosition - _player.GlobalPosition);
                _attackCooldown = 0;
                Strike();
                await Wait(0.42f);
            }
            GD.Print($"[trailer] victim health {victim.Agent.Health} active {victim.Agent.Active}");
            await Wait(5f);
            // the guard comes: the arrest is read, then the traveller resists
            await Until(() => _hud.ArrestPanel.Visible, 25f);
            if (_hud.ArrestPanel.Visible)
            {
                GD.Print("[trailer] arrest");
                await Wait(3.5f);
                Resist();
                for (int swing = 0; swing < 10; swing++)
                {
                    var guard = _actors.Values.Where(a => a.Agent.Active && a.Agent.Has(Tags.Authority))
                        .OrderBy(a => a.GlobalPosition.DistanceTo(_player.GlobalPosition)).FirstOrDefault();
                    if (guard == null || guard.GlobalPosition.DistanceTo(_player.GlobalPosition) > 60f) break;
                    _player.Face(guard.GlobalPosition - _player.GlobalPosition);
                    _attackCooldown = 0;
                    Strike();
                    await Wait(0.45f);
                }
                await Wait(4f);
            }
        }
        _ = AutoResolveArrests();

        // 3. the world saw it
        var witness = World.Agents.Where(a => !a.IsPlayer && a.Active && !a.Has(Tags.Authority) && a.Mind.Memories.Any(m => m.ActorId == _player.Agent.Id && m.IsCrime))
            .OrderBy(a => a.Position.DistanceTo(_player.Agent.Position)).FirstOrDefault();
        if (witness != null)
        {
            GD.Print($"[trailer] witness {witness.Id}");
            var w = _actors[witness.Id];
            await WalkToActor(w);
            OpenDialogue(w);
            await Wait(1f);
            await TypeAndSay("You saw nothing. We good?");
            await TypeAndSay("What if I pay you in exposure?");
            CloseDialogue();
            OpenMind(w);
            await Wait(5f);
            _hud.MindPanel.Visible = false;
            _mindOf = null;
        }

        // 4. rumours travel
        _speed = 2;
        await Wait(6f);
        _speed = 1;

        // 5. the raid
        _speed = 0;
        var ev = WorldEvents.TryStart(World, WorldEvents.BanditRaid, "square", 3 * World.TicksPerHour, "Crow's gang comes to collect what Riku owes", null, out _);
        if (ev != null) AnnounceEvent(ev, "Masked figures slip out of the forest.");
        await Wait(4f);
        for (int round = 0; round < 14; round++)
        {
            var bandit = _actors.Values.Where(a => a.Agent.Active && a.Agent.Has(WorldEvents.HostileTag))
                .OrderBy(a => a.GlobalPosition.DistanceTo(_player.GlobalPosition)).FirstOrDefault();
            if (bandit == null) break;
            await WalkTo(bandit.GlobalPosition + new Vector2(-12, 0), 4f);
            _player.Face(bandit.GlobalPosition - _player.GlobalPosition);
            if (StrikeTarget() is { } target && target.Agent.Has(WorldEvents.HostileTag))
            {
                _attackCooldown = 0;
                Strike();
            }
            await Wait(0.4f);
        }
        await Wait(3f);

        // 6. the chronicle
        _speed = 2;
        await Until(() => World.Hour >= 21 || World.Hour < 4, 40f);
        _speed = 0;
        await Wait(2f);
        _brain.RequestChronicle();
        await Until(() => _hud.ChroniclePanel.Visible, 60f);
        await Wait(8f);
        GD.Print($"[trailer] brain: {_brain.Stats}");
        GetTree().Quit();
    }
}
