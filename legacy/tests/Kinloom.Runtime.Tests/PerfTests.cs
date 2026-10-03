using System.Diagnostics;
using System.Text.Json.Nodes;
using Kinloom.Expressions;
using Kinloom.Schema;

namespace Kinloom.Runtime.Tests;

[CollectionDefinition("Perf", DisableParallelization = true)]
public class PerfCollection { }

/// <summary>Timing tests run alone so other tests do not skew them.</summary>
[Collection("Perf")]
public class PerfTests
{
    private static readonly Random Rng = new Random(1);
    private static readonly LambdaHandler OkAll = new LambdaHandler(_ => EffectResult.Ok());

    private static BehaviorDecl B(string json)
    {
        var errors = new List<ManifestError>();
        var b = BehaviorDecl.Parse(JsonNode.Parse(json), "b", errors);
        Assert.Empty(errors);
        return b;
    }

    [Fact]
    public void Evaluation_is_fast_enough_for_every_frame()
    {
        var expr = Expr.Parse("player.idle_seconds > 3 && self.health < 0.5 && dist(self.pos, player.pos) < 10 || self.mood == 'angry'");
        var scope = new DictScope("""{"self":{"health":0.4,"pos":[0,0,0],"mood":"calm"},"player":{"idle_seconds":5,"pos":[1,1,1]}}""");
        for (int i = 0; i < 20_000; i++) expr.Eval(scope, Rng); // let tiered JIT settle
        // Best of 5 batches: other test assemblies may share the CPU; the fastest batch is the code's real cost.
        double best = double.MaxValue;
        for (int batch = 0; batch < 5; batch++)
        {
            var watch = Stopwatch.StartNew();
            for (int i = 0; i < 10_000; i++) expr.Eval(scope, Rng);
            best = Math.Min(best, watch.Elapsed.TotalMilliseconds);
        }
        Assert.True(best < 50, $"{best:0.0} ms");
    }

    [Fact]
    public void Two_hundred_things_with_five_rules_pump_fast()
    {
        var s = new KinloomSession();
        var things = string.Join(",", Enumerable.Range(0, 200).Select(i => $$"""{"id":"m{{i}}","type":"M"}"""));
        Assert.Empty(s.Declare("""{"types":{"M":{"properties":{"hp":"number","pos":"vec2"},"params":{"speed":{"type":"number","min":0,"max":10,"default":1}}}},"things":[""" + things + "]}"));
        for (int i = 0; i < 200; i++)
        {
            s.Update("m" + i, JsonNode.Parse($$"""{"hp": {{i % 10}}, "pos": [{{i}}, 0]}""")!.AsObject());
            var rules = string.Join(",", Enumerable.Range(0, 5).Select(r => $$"""{"when":"self.hp > {{r}} && dist(self.pos, [0,0]) < 500","do":[{"set":"self.speed","to":"clamp(self.hp / 2, 0, 10)"}]}"""));
            Assert.Empty(s.InstallBehavior(B($$"""{"id":"b{{i}}","owner":"m{{i}}","rules":[{{rules}}]}"""), "game", null));
        }
        for (int w = 0; w < 300; w++) s.Pump(0, OkAll); // let tiered JIT settle
        double best = double.MaxValue;
        for (int batch = 0; batch < 5; batch++)
        {
            var watch = Stopwatch.StartNew();
            for (int t = 1; t <= 50; t++) s.Pump(batch * 50 + t, OkAll);
            best = Math.Min(best, watch.Elapsed.TotalMilliseconds / 50);
        }
        Assert.True(best < 5, $"{best:0.00} ms per pump");
    }

    [Fact]
    public void Pumping_an_unchanged_world_allocates_nothing()
    {
        // Engines with a stop-the-world GC (Unity, Mono) stutter when every frame allocates: behaviors must not.
        var s = new KinloomSession();
        var things = string.Join(",", Enumerable.Range(0, 500).Select(i => $$"""{"id":"m{{i}}","type":"M"}"""));
        Assert.Empty(s.Declare("""{"types":{"M":{"properties":{"hp":"number","pos":"vec2"},"params":{"speed":{"type":"number","min":0,"max":10,"default":1}}}},"things":[""" + things + "]}"));
        for (int i = 0; i < 500; i++)
        {
            s.Update("m" + i, JsonNode.Parse($$"""{"hp": {{i % 10}}, "pos": [{{i}}, 0]}""")!.AsObject());
            const string rules = """
                [{"when":"self.hp > 2 && dist(self.pos, [0,0]) < 400 || min(self.hp, 3) == 3","do":[{"set":"self.speed","to":"clamp(self.hp / 2 + abs(-1) - 1, 0, 10)"}]},
                 {"when":"max(self.pos.x, 1) > 100000 && lerp(0, 10, 0.5) * 2 % 7 > -1","do":[{"set":"self.speed","to":"0"}]}]
                """;
            Assert.Empty(s.InstallBehavior(B($$"""{"id":"b{{i}}","owner":"m{{i}}","rules":{{rules}}}"""), "game", null));
        }
        for (int w = 0; w < 100; w++) s.Pump(w / 60.0, OkAll);
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int t = 0; t < 60; t++) s.Pump((100 + t) / 60.0, OkAll);
        long perPump = (GC.GetAllocatedBytesForCurrentThread() - before) / 60;
        Assert.True(perPump < 1024, $"{perPump} bytes allocated per pump");
    }
}
