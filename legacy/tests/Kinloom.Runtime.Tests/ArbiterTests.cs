using System.Text.Json.Nodes;
using Kinloom.Schema;

namespace Kinloom.Runtime.Tests;

public class ArbiterTests
{
    private static IReadOnlyList<Permission> Can(params string[] items) => items.Select(Permission.Parse).ToList();

    private static Proposal SetP(string thing, string param, JsonNode? value, string self = "truck_2") =>
        new Proposal(ProposalKind.Set, "role:rex") { Thing = thing, Member = param, Args = new JsonObject { ["value"] = value }, Self = self };

    private static Proposal InvokeP(string thing, string fn, string args = "{}", string self = "truck_2") =>
        new Proposal(ProposalKind.Invoke, "role:rex") { Thing = thing, Member = fn, Args = JsonNode.Parse(args)!.AsObject(), Self = self };

    [Fact]
    public void A_set_within_range_is_allowed_and_becomes_an_effect()
    {
        var s = SessionTests.Trucks();
        var v = s.Arbiter.Check(SetP("self", "aggression", 0.9), Can("set:self.aggression"));
        Assert.True(v.Allowed, v.Reason);
        Assert.Equal(EffectKind.Set, v.Effect!.Kind);
        Assert.Equal("truck_2", v.Effect.Thing);
        Assert.Equal(0.9, v.Effect.Args["value"]!.GetValue<double>());
    }

    [Fact]
    public void Out_of_range_values_are_refused_with_the_bound()
    {
        var s = SessionTests.Trucks();
        var v = s.Arbiter.Check(SetP("truck_2", "aggression", 1.5), Can("set:self.aggression"));
        Assert.False(v.Allowed);
        Assert.Equal("aggression must be ≤ 1", v.Reason);
    }

    [Fact]
    public void Unknown_members_are_refused()
    {
        var s = SessionTests.Trucks();
        Assert.False(s.Arbiter.Check(SetP("truck_2", "nitro", 1), Can("set:self.*")).Allowed);
        Assert.False(s.Arbiter.Check(InvokeP("truck_2", "fly"), Can("invoke:self.*")).Allowed);
    }

    [Fact]
    public void Self_only_means_the_inhabited_thing()
    {
        var s = SessionTests.Trucks();
        var v = s.Arbiter.Check(SetP("truck_3", "aggression", 0.2), Can("set:self.aggression"));
        Assert.False(v.Allowed);
        Assert.Contains("not allowed", v.Reason);
    }

    [Fact]
    public void Type_tag_and_wildcard_targets_match()
    {
        var s = SessionTests.Trucks();
        Assert.True(s.Arbiter.Check(SetP("truck_3", "aggression", 0.2), Can("set:Truck.aggression")).Allowed);
        Assert.True(s.Arbiter.Check(SetP("truck_3", "mood", "angry"), Can("set:tag:rival.*")).Allowed);
        Assert.True(s.Arbiter.Check(InvokeP("hud", "say", """{"text":"hi"}"""), Can("invoke:*.say")).Allowed);
        Assert.False(s.Arbiter.Check(InvokeP("hud", "say", """{"text":"hi"}"""), Can("invoke:Truck.*")).Allowed);
    }

    [Fact]
    public void Function_args_are_validated_and_defaults_needed()
    {
        var s = SessionTests.Trucks();
        Assert.False(s.Arbiter.Check(InvokeP("self", "boost", """{"seconds": 9}"""), Can("invoke:self.boost")).Allowed);
        Assert.False(s.Arbiter.Check(InvokeP("self", "boost", """{}"""), Can("invoke:self.boost")).Allowed);
        Assert.False(s.Arbiter.Check(InvokeP("self", "boost", """{"seconds": 1, "turbo": true}"""), Can("invoke:self.boost")).Allowed);
        Assert.True(s.Arbiter.Check(InvokeP("self", "boost", """{"seconds": 1}"""), Can("invoke:self.boost")).Allowed);
    }

    [Fact]
    public void Cooldowns_refuse_then_allow_after_time_passes()
    {
        var s = SessionTests.Trucks();
        var can = Can("invoke:self.boost");
        Assert.True(s.Arbiter.Check(InvokeP("self", "boost", """{"seconds": 1}"""), can).Allowed);
        s.Tick(4);
        var again = s.Arbiter.Check(InvokeP("self", "boost", """{"seconds": 1}"""), can);
        Assert.False(again.Allowed);
        Assert.Contains("cooling down", again.Reason);
        s.Tick(11);
        Assert.True(s.Arbiter.Check(InvokeP("self", "boost", """{"seconds": 1}"""), can).Allowed);
    }

    [Fact]
    public void Creation_respects_the_type_maximum()
    {
        var s = SessionTests.Trucks();
        var can = Can("create:Truck");
        for (int i = 0; i < 3; i++)
        {
            var v = s.Arbiter.Check(new Proposal(ProposalKind.Create, "role:director") { Member = "Truck", Args = JsonNode.Parse("""{"position":[0,0,0]}""")!.AsObject() }, can);
            Assert.True(v.Allowed, v.Reason);
            s.EnqueueEffect(v.Effect!, null);
        }
        var over = s.Arbiter.Check(new Proposal(ProposalKind.Create, "role:director") { Member = "Truck", Args = JsonNode.Parse("""{"position":[0,0,0]}""")!.AsObject() }, can);
        Assert.False(over.Allowed);
        Assert.Contains("3", over.Reason);
    }

    [Fact]
    public void Destroy_own_only_touches_things_this_source_created()
    {
        var s = SessionTests.Trucks();
        var can = Can("create:Truck", "destroy:own");
        var created = s.Arbiter.Check(new Proposal(ProposalKind.Create, "role:director") { Member = "Truck", Args = JsonNode.Parse("""{"position":[0,0,0]}""")!.AsObject() }, can);
        var e = s.EnqueueEffect(created.Effect!, null);
        s.Pump(1);
        s.Resolve(e.Id, EffectResult.Ok());
        Assert.NotNull(s.Things.Find(e.Thing));
        Assert.True(s.Arbiter.Check(new Proposal(ProposalKind.Destroy, "role:director") { Thing = e.Thing }, can).Allowed);
        Assert.False(s.Arbiter.Check(new Proposal(ProposalKind.Destroy, "role:director") { Thing = "truck_2" }, can).Allowed);
        Assert.False(s.Arbiter.Check(new Proposal(ProposalKind.Destroy, "role:other") { Thing = e.Thing }, can).Allowed);
    }

    [Fact]
    public void Say_needs_permission_and_reasonable_text()
    {
        var s = SessionTests.Trucks();
        Assert.True(s.Arbiter.Check(new Proposal(ProposalKind.Say, "role:rex") { Text = "Out of my way!", Self = "truck_2" }, Can("say")).Allowed);
        Assert.False(s.Arbiter.Check(new Proposal(ProposalKind.Say, "role:rex") { Text = "hi", Self = "truck_2" }, Can("remember")).Allowed);
        Assert.False(s.Arbiter.Check(new Proposal(ProposalKind.Say, "role:rex") { Text = "  ", Self = "truck_2" }, Can("say")).Allowed);
        Assert.False(s.Arbiter.Check(new Proposal(ProposalKind.Say, "role:rex") { Text = new string('a', 601), Self = "truck_2" }, Can("say")).Allowed);
    }

    [Fact]
    public void Behavior_levers_are_checked_against_the_permissions()
    {
        var s = SessionTests.Trucks();
        var errors = new List<ManifestError>();
        var ok = BehaviorDecl.Parse(JsonNode.Parse("""{"id":"b","owner":"truck_2","rules":[{"when":"true","do":[{"set":"self.aggression","to":"1"}]}]}"""), "b", errors);
        var bad = BehaviorDecl.Parse(JsonNode.Parse("""{"id":"b2","owner":"truck_2","rules":[{"when":"true","do":[{"invoke":"hud.say","args":{"text":"'x'"}}]}]}"""), "b2", errors);
        Assert.Empty(errors);
        var can = Can("behavior:self", "set:self.aggression");
        Assert.True(s.Arbiter.CheckBehavior(ok, can, "truck_2", "role:rex").Count == 0);
        Assert.NotEmpty(s.Arbiter.CheckBehavior(bad, can, "truck_2", "role:rex"));
        var otherOwner = BehaviorDecl.Parse(JsonNode.Parse("""{"id":"b3","owner":"truck_3","rules":[]}"""), "b3", errors);
        Assert.NotEmpty(s.Arbiter.CheckBehavior(otherOwner, can, "truck_2", "role:rex"));
    }

    [Fact]
    public void Every_refusal_is_journaled_and_counted()
    {
        var s = SessionTests.Trucks();
        s.Arbiter.Check(SetP("truck_2", "aggression", 7), Can("set:self.aggression"));
        Assert.Contains(s.Journal.Recent(10), j => j.Kind == "refused" && j.Text.Contains("aggression"));
        Assert.Equal(1, s.Stats.Refusals);
    }

    [Fact]
    public void Unbound_targets_are_refused_when_binding_is_required()
    {
        var s = SessionTests.Trucks(new SessionOptions { RequireBind = true });
        Assert.False(s.Arbiter.Check(SetP("truck_2", "aggression", 0.1), Can("set:self.aggression")).Allowed);
    }
}
