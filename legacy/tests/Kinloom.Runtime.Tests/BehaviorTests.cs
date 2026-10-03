using System.Diagnostics;
using System.Text.Json.Nodes;
using Kinloom.Schema;

namespace Kinloom.Runtime.Tests;

public class BehaviorTests
{
    private static readonly LambdaHandler OkAll = new LambdaHandler(_ => EffectResult.Ok());

    /// <summary>Applies everything and returns how many calls of <paramref name="function"/> the pump produced.</summary>
    private static int Calls(KinloomSession s, double time, string function)
    {
        int n = 0;
        s.Pump(time, new LambdaHandler(e => { if (e.Kind == EffectKind.Invoke && e.Member == function) n++; return EffectResult.Ok(); }));
        return n;
    }

    private static BehaviorDecl B(string json)
    {
        var errors = new List<ManifestError>();
        var b = BehaviorDecl.Parse(JsonNode.Parse(json), "b", errors);
        Assert.Empty(errors);
        return b;
    }

    private static IReadOnlyList<Permission> Can(params string[] items) => items.Select(Permission.Parse).ToList();

    private const string Rage = """
        {"id":"rage","owner":"truck_2","rules":[{"when":"player.idle_seconds > 3",
          "do":[{"set":"self.aggression","to":"lerp(self.aggression, 1, 0.5)"}]}]}
        """;

    [Fact]
    public void A_rule_steers_a_param_every_pump_while_true()
    {
        var s = SessionTests.Trucks();
        Assert.Empty(s.InstallBehavior(B(Rage), "game", null));
        s.Update("player", JsonNode.Parse("""{"idle_seconds": 1}""")!.AsObject());
        s.Pump(1, OkAll);
        Assert.Equal(0.5, s.Things.Find("truck_2")!.Params["aggression"]!.GetValue<double>());
        s.Update("player", JsonNode.Parse("""{"idle_seconds": 5}""")!.AsObject());
        s.Pump(2, OkAll);
        Assert.Equal(0.75, s.Things.Find("truck_2")!.Params["aggression"]!.GetValue<double>(), 6);
        s.Pump(3, OkAll);
        Assert.Equal(0.875, s.Things.Find("truck_2")!.Params["aggression"]!.GetValue<double>(), 6);
    }

    [Fact]
    public void An_unchanged_value_produces_no_effect()
    {
        var s = SessionTests.Trucks();
        s.InstallBehavior(B("""{"id":"calm","owner":"truck_2","rules":[{"when":"true","do":[{"set":"self.aggression","to":"0.5"}]}]}"""), "game", null);
        Assert.Empty(s.Pump(1));
    }

    [Fact]
    public void A_value_converging_on_its_target_stops_producing_effects()
    {
        var s = SessionTests.Trucks();
        s.InstallBehavior(B("""{"id":"creep","owner":"truck_2","rules":[{"when":"true","do":[{"set":"self.aggression","to":"lerp(self.aggression, 1, 0.5)"}]}]}"""), "game", null);
        int effects = 0;
        for (int t = 1; t <= 60; t++) effects += s.Pump(t, OkAll);
        Assert.InRange(effects, 5, 12); // 0.5 → 0.75 → ... until the change is under 0.1 % of the 0..1 range
    }

    [Fact]
    public void Continuous_steering_does_not_flood_the_journal()
    {
        var s = SessionTests.Trucks();
        s.InstallBehavior(B("""{"id":"ramp","owner":"truck_2","rules":[{"when":"true","do":[{"set":"self.aggression","to":"now() / 10"}]}]}"""), "game", null);
        int effects = 0;
        for (int i = 1; i <= 90; i++) effects += s.Pump(i * 0.05, OkAll); // 90 frames over 4.5 game seconds
        Assert.True(effects > 60, $"{effects} effects");
        int lines = s.Journal.Recent(2000).Count(j => (j.Kind == "effect" || j.Kind == "resolved") && j.Source == "behavior:ramp");
        Assert.InRange(lines, 1, 8);
    }

    [Fact]
    public void A_pending_set_is_not_proposed_twice()
    {
        var s = SessionTests.Trucks();
        s.InstallBehavior(B("""{"id":"max","owner":"truck_2","rules":[{"when":"true","do":[{"set":"self.aggression","to":"1"}]}]}"""), "game", null);
        Assert.Single(s.Pump(1));
        Assert.Empty(s.Pump(2));
    }

    [Fact]
    public void Invokes_fire_on_the_rising_edge_then_every_cooldown()
    {
        var s = SessionTests.Trucks();
        s.InstallBehavior(B("""{"id":"honker","owner":"truck_2","rules":[{"when":"player.idle_seconds > 3","cooldown":5,"do":[{"invoke":"self.honk"}]}]}"""), "game", null);
        s.Update("player", JsonNode.Parse("""{"idle_seconds": 9}""")!.AsObject());
        Assert.Equal(1, Calls(s, 1, "honk"));
        Assert.Equal(0, Calls(s, 2, "honk"));
        Assert.Equal(1, Calls(s, 6, "honk"));
    }

    [Fact]
    public void Without_cooldown_an_invoke_fires_once_per_rising_edge()
    {
        var s = SessionTests.Trucks();
        s.InstallBehavior(B("""{"id":"honker","owner":"truck_2","rules":[{"when":"player.idle_seconds > 3","do":[{"invoke":"self.honk"}]}]}"""), "game", null);
        s.Update("player", JsonNode.Parse("""{"idle_seconds": 9}""")!.AsObject());
        Assert.Equal(1, Calls(s, 1, "honk"));
        Assert.Equal(0, Calls(s, 50, "honk"));
        s.Update("player", JsonNode.Parse("""{"idle_seconds": 0}""")!.AsObject());
        Assert.Equal(0, Calls(s, 51, "honk"));
        s.Update("player", JsonNode.Parse("""{"idle_seconds": 9}""")!.AsObject());
        Assert.Equal(1, Calls(s, 52, "honk"));
    }

    [Fact]
    public void Invoke_args_are_expressions()
    {
        var s = SessionTests.Trucks();
        s.InstallBehavior(B("""{"id":"b","owner":"truck_2","rules":[{"when":"true","do":[{"invoke":"self.boost","args":{"seconds":"1 + 1"}}]}]}"""), "game", null);
        var e = s.Pump(1).Single();
        Assert.Equal(2, e.Args["seconds"]!.GetValue<double>());
    }

    [Fact]
    public void A_role_cannot_install_levers_outside_its_permissions()
    {
        var s = SessionTests.Trucks();
        var errors = s.InstallBehavior(B("""{"id":"b","owner":"truck_2","rules":[{"when":"true","do":[{"invoke":"hud.say","args":{"text":"'x'"}}]}]}"""),
            "role:rex", Can("behavior:self", "set:self.aggression"), "truck_2");
        Assert.NotEmpty(errors);
        Assert.Contains(errors, e => e.Contains("hud.say"));
        Assert.Empty(s.Behaviors);
    }

    [Fact]
    public void Bad_expressions_are_rejected_with_the_column()
    {
        var s = SessionTests.Trucks();
        var errors = s.InstallBehavior(B("""{"id":"b","owner":"truck_2","rules":[{"when":"self.lap >","do":[{"invoke":"self.honk"}]}]}"""), "game", null);
        Assert.Contains(errors, e => e.Contains("column"));
    }

    [Fact]
    public void Emit_raises_an_event_and_removal_stops_the_behavior()
    {
        var s = SessionTests.Trucks();
        s.InstallBehavior(B("""{"id":"alarm","owner":"truck_2","rules":[{"when":"self.lap >= 2","do":[{"emit":"final_lap","data":{"who":"self.name"}}]}]}"""), "game", null);
        s.Update("truck_2", JsonNode.Parse("""{"lap": 2}""")!.AsObject());
        s.Pump(1);
        var e = s.RecentEvents.Single(x => x.Type == "final_lap");
        Assert.Equal("Rex", e.Data["who"]!.GetValue<string>());
        Assert.Equal("behavior:alarm", e.Source);
        Assert.True(s.RemoveBehavior("alarm"));
        Assert.Empty(s.Behaviors);
    }

    [Fact]
    public void A_role_may_not_replace_a_game_behavior()
    {
        var s = SessionTests.Trucks();
        s.InstallBehavior(B(Rage), "game", null);
        var errors = s.InstallBehavior(B(Rage), "role:rex", Can("behavior:self", "set:self.aggression"), "truck_2");
        Assert.Contains(errors, e => e.Contains("game"));
    }

    [Fact]
    public void Behaviors_declared_in_the_manifest_are_installed()
    {
        var s = new KinloomSession();
        string json = TestData.Trucks.Replace("\"roles\": [", "\"behaviors\": [" + Rage + "], \"roles\": [");
        Assert.Empty(s.Declare(json));
        Assert.Single(s.Behaviors);
    }

    [Fact]
    public void Removing_the_owner_removes_its_behaviors()
    {
        var s = SessionTests.Trucks();
        s.InstallBehavior(B(Rage), "game", null);
        s.RemoveThing("truck_2");
        Assert.Empty(s.Behaviors);
    }

    [Fact]
    public void Out_of_range_results_are_refused_and_journaled_once()
    {
        var s = SessionTests.Trucks();
        s.InstallBehavior(B("""{"id":"b","owner":"truck_2","rules":[{"when":"true","do":[{"set":"self.aggression","to":"5"}]}]}"""), "game", null);
        s.Pump(1); s.Pump(2); s.Pump(3);
        Assert.Single(s.Journal.Recent(50), j => j.Kind == "refused");
    }

}
