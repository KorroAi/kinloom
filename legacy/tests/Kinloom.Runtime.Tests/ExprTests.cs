using System.Diagnostics;
using System.Text.Json.Nodes;
using Kinloom.Expressions;
using Kinloom.Schema;

namespace Kinloom.Runtime.Tests;

/// <summary>Test scope over a JSON object. Like the runtime's registry, it converts each root value once.</summary>
internal sealed class DictScope : IExprScope
{
    private readonly Dictionary<string, Value> _roots = new();
    public DictScope(string json, double now = 0)
    {
        foreach (var p in JsonNode.Parse(json)!.AsObject()) _roots[p.Key] = Value.From(p.Value?.DeepClone());
        Now = now;
    }
    public double Now { get; }
    public Value Resolve(IReadOnlyList<string> path) => _roots.TryGetValue(path[0], out var v) ? v.Navigate(path, 1) : Value.Null;
}

public class ExprTests
{
    private static readonly Random Rng = new Random(1);
    private static Value Eval(string source, string scope = "{}", double now = 0) => Expr.Parse(source).Eval(new DictScope(scope, now), Rng);

    [Theory]
    [InlineData("1+2*3==7")]
    [InlineData("(1+2)*3==9")]
    [InlineData("10 % 4 == 2")]
    [InlineData("-2 < 1")]
    [InlineData("!false")]
    [InlineData("true || undefined_thing.x > 1")]
    [InlineData("!(false && ghost.x > 1)")]
    [InlineData("'a' + \"b\" == 'ab'")]
    [InlineData("1 < 2 ? true : false")]
    [InlineData("null == null")]
    [InlineData("3 >= 3 && 2 <= 2 && 1 != 2")]
    public void Operators_follow_usual_precedence(string source)
    {
        Assert.True(Eval(source).Truthy, source);
    }

    [Fact]
    public void Paths_read_through_the_scope()
    {
        string scope = """{"self":{"health":0.4,"pos":[1,2,3]},"player":{"idle_seconds":5},"list":[10,20]}""";
        Assert.True(Eval("player.idle_seconds > 3 && self.health < 0.5", scope).Truthy);
        Assert.Equal(2, Eval("self.pos.y", scope).Number);
        Assert.Equal(20, Eval("list[1]", scope).Number);
        Assert.Equal(2, Eval("len(list)", scope).Number);
    }

    [Fact]
    public void Backticks_quote_identifiers_with_dashes()
    {
        Assert.Equal(7, Eval("`truck-2`.speed", """{"truck-2":{"speed":7}}""").Number);
    }

    [Fact]
    public void Vectors_support_distance_components_and_arithmetic()
    {
        Assert.Equal(5, Eval("dist([0,0],[3,4])").Number);
        Assert.Equal(4, Eval("([1,1] + [2,3]).y").Number);
        Assert.Equal(6, Eval("([1,2,3] * 2).z").Number);
        Assert.Equal(1, Eval("p.x", """{"p":{"x":1,"y":2}}""").Number);
    }

    [Fact]
    public void Functions_cover_math_time_and_collections()
    {
        Assert.Equal(1, Eval("clamp(5, 0, 1)").Number);
        Assert.Equal(0.55, Eval("lerp(0.5, 1, 0.1)").Number, 6);
        Assert.Equal(3, Eval("max(1, 3, 2)").Number);
        Assert.Equal(-1, Eval("sign(-4)").Number);
        Assert.Equal(3, Eval("round(2.6)").Number);
        Assert.Equal(4, Eval("since(6)", now: 10).Number);
        Assert.Equal(10, Eval("now()", now: 10).Number);
        Assert.True(Eval("contains(['a','b'], 'b')").Truthy);
        Assert.True(Eval("contains('hello', 'ell')").Truthy);
        double r = Eval("rand(2, 3)").Number;
        Assert.InRange(r, 2, 3);
        Assert.True(Eval("exists(a) && !exists(b)", """{"a":0}""").Truthy);
    }

    [Fact]
    public void Trigonometry_and_scalar_distance_are_available()
    {
        Assert.Equal(0, Eval("sin(0)").Number, 9);
        Assert.Equal(1, Eval("cos(0)").Number, 9);
        Assert.Equal(Math.PI, Eval("pi()").Number, 9);
        Assert.Equal(8, Eval("pow(2, 3)").Number, 9);
        Assert.Equal(Math.PI / 4, Eval("atan2(1, 1)").Number, 9);
        Assert.Equal(5, Eval("dist(0, 0, 3, 4)").Number, 9);
        Assert.Equal(1, Eval("tan(pi() / 4)").Number, 9);
    }

    [Fact]
    public void Missing_values_are_null_and_never_throw()
    {
        Assert.Equal(ValueKind.Null, Eval("ghost.hp + 1").Kind);
        Assert.False(Eval("ghost.hp > 1").Truthy);
        Assert.False(Eval("ghost.hp < 1").Truthy);
        Assert.Equal(0, Eval("1 / 0").Number);
    }

    [Fact]
    public void Parse_errors_report_the_column()
    {
        var e = Assert.Throws<ExprException>(() => Expr.Parse("a +* b"));
        Assert.Equal(4, e.Column);
        Assert.Throws<ExprException>(() => Expr.Parse("unknown_fn(1)"));
        Assert.Throws<ExprException>(() => Expr.Parse("(1 + 2"));
        Assert.Throws<ExprException>(() => Expr.Parse(""));
    }

    [Fact]
    public void Paths_used_by_an_expression_are_listed()
    {
        var expr = Expr.Parse("self.hp < 1 && player.pos.x > 0");
        Assert.Contains(expr.Paths, p => string.Join(".", p) == "self.hp");
        Assert.Contains(expr.Paths, p => string.Join(".", p) == "player.pos.x");
    }

    [Fact]
    public void Manifest_check_reports_expression_errors_with_their_path()
    {
        string json = """
        {"types":{"T":{"params":{"a":"number"}}},"things":[{"id":"t","type":"T"}],
         "behaviors":[{"id":"b","owner":"t","rules":[{"when":"self.a >","do":[{"set":"self.a","to":"1 +"}]}]}],
         "roles":[{"id":"r","mission":"m","wake":[{"when":"(("}]}]}
        """;
        var errors = new List<ManifestError>();
        var d = Manifest.Parse(json, "x.json", errors);
        Manifest.Check(d, errors);
        Assert.Contains(errors, e => e.Path == "behaviors[0].rules[0].when");
        Assert.Contains(errors, e => e.Path == "behaviors[0].rules[0].do[0].to");
        Assert.Contains(errors, e => e.Path == "roles[0].wake[0].when");
    }
}
