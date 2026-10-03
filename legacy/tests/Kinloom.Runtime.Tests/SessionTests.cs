using System.Text.Json.Nodes;

namespace Kinloom.Runtime.Tests;

public class SessionTests
{
    internal static KinloomSession Trucks(SessionOptions? options = null)
    {
        var s = new KinloomSession(options ?? new SessionOptions());
        var errors = s.Declare(TestData.Trucks);
        Assert.Empty(errors);
        return s;
    }

    private static JsonObject Obj(string json) => JsonNode.Parse(json)!.AsObject();

    [Fact]
    public void Declared_things_exist_with_param_defaults()
    {
        var s = Trucks();
        var rex = s.Things.Find("truck_2")!;
        Assert.Equal("Rex", rex.Name);
        Assert.Equal(0.5, rex.Params["aggression"]!.GetValue<double>());
        Assert.Equal("calm", rex.Params["mood"]!.GetValue<string>());
        Assert.Equal(2, s.Things.OfType("Truck").Count());
        Assert.Equal(2, s.Things.WithTag("rival").Count());
        Assert.NotNull(s.Things.Find("world"));
    }

    [Fact]
    public void Updates_are_stored_and_readable()
    {
        var s = Trucks();
        s.Update("truck_2", Obj("""{"speed": 120, "lap": 2}"""));
        Assert.Equal(120, s.Things.Find("truck_2")!.Properties["speed"]!.GetValue<double>());
        s.Update("world", Obj("""{"weather": "rain"}"""));
        Assert.Equal("rain", s.Things.Find("world")!.Properties["weather"]!.GetValue<string>());
    }

    [Fact]
    public void Updating_an_unknown_thing_or_property_is_journaled_once()
    {
        var s = Trucks();
        s.Update("ghost", Obj("""{"x": 1}"""));
        s.Update("truck_2", Obj("""{"nitro": 1}"""));
        s.Update("truck_2", Obj("""{"nitro": 2}"""));
        Assert.Single(s.Journal.Recent(50), e => e.Kind == "error" && e.Text.Contains("ghost"));
        Assert.Single(s.Journal.Recent(50), e => e.Kind == "error" && e.Text.Contains("nitro"));
    }

    [Fact]
    public void A_bad_manifest_changes_nothing()
    {
        var s = Trucks();
        var errors = s.Declare("""{"things":[{"id":"x","type":"Ghost"}]}""");
        Assert.NotEmpty(errors);
        Assert.Null(s.Things.Find("x"));
    }

    [Fact]
    public void Things_can_be_added_and_removed_at_run_time()
    {
        var s = Trucks();
        var errors = s.Declare("""{"things":[{"id":"truck_9","type":"Truck"}]}""");
        Assert.Empty(errors);
        Assert.NotNull(s.Things.Find("truck_9"));
        Assert.True(s.RemoveThing("truck_9"));
        Assert.Null(s.Things.Find("truck_9"));
    }

    [Fact]
    public void Events_are_journaled_with_declared_importance()
    {
        var s = Trucks();
        s.Tick(5);
        s.Emit(new GameEvent("crash", Obj("""{"who":"truck_3"}""")));
        var e = s.RecentEvents.Single();
        Assert.Equal(0.9, e.Importance);
        Assert.Equal(5, e.Time);
        Assert.Contains(s.Journal.Recent(10), j => j.Kind == "event" && j.Text.Contains("crash"));
    }

    [Fact]
    public void An_effect_is_handed_out_once_and_its_result_comes_back()
    {
        var s = Trucks();
        EffectResult? got = null;
        s.EnqueueEffect(new Effect(EffectKind.Invoke, "truck_2", "honk", new JsonObject(), "test"), r => got = r);
        var batch = s.Pump(1);
        Assert.Single(batch);
        Assert.Empty(s.Pump(2));
        s.Resolve(batch[0].Id, EffectResult.Ok());
        Assert.Equal(ResolveStatus.Ok, got!.Status);
    }

    [Fact]
    public void A_resolved_set_updates_the_param()
    {
        var s = Trucks();
        s.EnqueueEffect(new Effect(EffectKind.Set, "truck_2", "aggression", new JsonObject { ["value"] = 0.8 }, "test"), null);
        var e = s.Pump(1).Single();
        Assert.Equal(0.5, s.Things.Find("truck_2")!.Params["aggression"]!.GetValue<double>());
        s.Resolve(e.Id, EffectResult.Ok());
        Assert.Equal(0.8, s.Things.Find("truck_2")!.Params["aggression"]!.GetValue<double>());
    }

    [Fact]
    public void An_effect_on_a_removed_thing_is_dropped_and_journaled()
    {
        var s = Trucks();
        EffectResult? got = null;
        s.EnqueueEffect(new Effect(EffectKind.Invoke, "truck_3", "honk", new JsonObject(), "test"), r => got = r);
        s.RemoveThing("truck_3");
        Assert.Empty(s.Pump(1));
        Assert.Equal(ResolveStatus.Failed, got!.Status);
        Assert.Contains(s.Journal.Recent(10), j => j.Kind == "dropped" && j.Text.Contains("truck_3"));
    }

    [Fact]
    public void Unbound_things_get_no_effects_when_binding_is_required()
    {
        var s = Trucks(new SessionOptions { RequireBind = true });
        s.EnqueueEffect(new Effect(EffectKind.Invoke, "truck_2", "honk", new JsonObject(), "test"), null);
        Assert.Empty(s.Pump(1));
        s.Bind("truck_2");
        s.EnqueueEffect(new Effect(EffectKind.Invoke, "truck_2", "honk", new JsonObject(), "test"), null);
        Assert.Single(s.Pump(2));
    }

    [Fact]
    public void Unresolved_effects_expire_after_the_timeout()
    {
        var s = Trucks(new SessionOptions { EffectTimeout = 10 });
        EffectResult? got = null;
        s.EnqueueEffect(new Effect(EffectKind.Invoke, "truck_2", "honk", new JsonObject(), "test"), r => got = r);
        s.Pump(1);
        s.Pump(5);
        Assert.Null(got);
        s.Pump(12);
        Assert.Equal(ResolveStatus.Failed, got!.Status);
        Assert.Equal("timeout", got.Reason);
        Assert.Equal(0, s.OutstandingEffects);
    }

    [Fact]
    public void Time_never_moves_backward()
    {
        var s = Trucks();
        s.Tick(10);
        s.Tick(3);
        Assert.Equal(10, s.Now);
    }

    [Fact]
    public void The_handler_overload_applies_and_resolves()
    {
        var s = Trucks();
        s.EnqueueEffect(new Effect(EffectKind.Set, "truck_2", "aggression", new JsonObject { ["value"] = 1.0 }, "test"), null);
        int applied = s.Pump(1, new LambdaHandler(e => EffectResult.Ok()));
        Assert.Equal(1, applied);
        Assert.Equal(1.0, s.Things.Find("truck_2")!.Params["aggression"]!.GetValue<double>());
    }

    [Fact]
    public void The_journal_is_a_bounded_ring()
    {
        var s = new KinloomSession(new SessionOptions { JournalCapacity = 5 });
        for (int i = 0; i < 20; i++) s.Journal.Add(new JournalEntry(0, "note", "test", "n" + i));
        Assert.Equal(5, s.Journal.Recent(100).Count);
        Assert.Equal("n19", s.Journal.Recent(1)[0].Text);
    }
}

internal sealed class LambdaHandler : IEffectHandler
{
    private readonly Func<Effect, EffectResult> _f;
    public LambdaHandler(Func<Effect, EffectResult> f) { _f = f; }
    public EffectResult Apply(Effect effect) => _f(effect);
}

public class CodeCreatedNumberTests
{
    [Fact]
    public void Integers_created_in_code_are_read_like_parsed_numbers()
    {
        var s = SessionTests.Trucks();
        s.Update("truck_2", new JsonObject { ["lap"] = JsonValue.Create(3L), ["speed"] = JsonValue.Create(120) });
        Assert.Contains("lap=3", s.Things.Find("truck_2")!.Describe());
        Assert.Equal(3, s.Things.Find("truck_2")!.Get("lap").Number);
        var v = s.Arbiter.Check(new Proposal(ProposalKind.Set, "role:rex") { Thing = "truck_2", Member = "aggression", Args = new JsonObject { ["value"] = JsonValue.Create(1L) }, Self = "truck_2" },
            new[] { Kinloom.Schema.Permission.Parse("set:self.aggression") });
        Assert.True(v.Allowed, v.Reason);
        Assert.Equal(2.5f, JsonNumber.ToDouble(JsonValue.Create(2.5f)), 3);
        Assert.Equal(7, JsonNumber.ToDouble(JsonValue.Create((byte)7)));
    }
}
