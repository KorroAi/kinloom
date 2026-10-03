using System.Text.Json.Nodes;
using Kinloom.Schema;

namespace Kinloom.Runtime.Tests;

public class FieldSpecTests
{
    private static FieldSpec Spec(string json)
    {
        var errors = new List<ManifestError>();
        var spec = FieldSpec.Parse(JsonNode.Parse(json), "f", errors);
        Assert.Empty(errors);
        return spec;
    }

    private static string? Check(string spec, string value) => Spec(spec).Validate(JsonNode.Parse(value), "v");

    [Theory]
    [InlineData("""{"type":"number","min":0,"max":1}""", "0.5", true)]
    [InlineData("""{"type":"number","min":0,"max":1}""", "1.5", false)]
    [InlineData("""{"type":"number"}""", "\"fast\"", false)]
    [InlineData("\"integer\"", "3", true)]
    [InlineData("\"integer\"", "3.5", false)]
    [InlineData("\"boolean\"", "true", true)]
    [InlineData("\"boolean\"", "1", false)]
    [InlineData("""{"type":"string","max":3}""", "\"abc\"", true)]
    [InlineData("""{"type":"string","max":3}""", "\"abcd\"", false)]
    [InlineData("""{"type":"enum","options":["a","b"]}""", "\"b\"", true)]
    [InlineData("""{"type":"enum","options":["a","b"]}""", "\"c\"", false)]
    [InlineData("\"vec2\"", "[1,2]", true)]
    [InlineData("\"vec2\"", """{"x":1,"y":2}""", true)]
    [InlineData("\"vec2\"", "[1,2,3]", false)]
    [InlineData("\"vec3\"", "[1,2,3]", true)]
    [InlineData("\"vec3\"", """{"x":1,"y":2}""", false)]
    [InlineData("\"color\"", "\"#ff8800\"", true)]
    [InlineData("\"color\"", "[1,0.5,0]", true)]
    [InlineData("\"color\"", "\"orange\"", false)]
    [InlineData("\"ref\"", "\"truck_2\"", true)]
    [InlineData("\"ref\"", "5", false)]
    [InlineData("""{"type":"list","items":"number","max":2}""", "[1,2]", true)]
    [InlineData("""{"type":"list","items":"number","max":2}""", "[1,2,3]", false)]
    [InlineData("""{"type":"list","items":"number"}""", "[1,\"x\"]", false)]
    [InlineData("""{"type":"object","fields":{"a":"number"},"required":["a"]}""", """{"a":1}""", true)]
    [InlineData("""{"type":"object","fields":{"a":"number"},"required":["a"]}""", """{}""", false)]
    [InlineData("\"any\"", """{"whatever":[1]}""", true)]
    public void Values_are_validated_by_kind(string spec, string value, bool valid)
    {
        Assert.Equal(valid, Check(spec, value) == null);
    }

    [Fact]
    public void Range_errors_name_the_path_and_the_bound()
    {
        Assert.Equal("v must be ≤ 1", Check("""{"type":"number","min":0,"max":1}""", "2"));
        Assert.Equal("v.a must be a number", Check("""{"type":"object","fields":{"a":"number"}}""", """{"a":"x"}"""));
        Assert.Equal("v[1] must be a number", Check("""{"type":"list","items":"number"}""", "[1,true]"));
    }

    [Fact]
    public void Bad_specs_report_their_path()
    {
        var errors = new List<ManifestError>();
        FieldSpec.Parse(JsonNode.Parse("""{"type":"number","min":2,"max":1}"""), "types.Truck.params.aggression", errors);
        FieldSpec.Parse(JsonNode.Parse("""{"type":"enum"}"""), "types.Truck.params.mood", errors);
        FieldSpec.Parse(JsonNode.Parse("\"numbr\""), "types.Truck.properties.speed", errors);
        Assert.Contains(errors, e => e.Path == "types.Truck.params.aggression.max" && e.Message.Contains("≥ min"));
        Assert.Contains(errors, e => e.Path == "types.Truck.params.mood.options");
        Assert.Contains(errors, e => e.Path == "types.Truck.properties.speed.type" && e.Message.Contains("numbr"));
    }

    [Fact]
    public void Json_schema_is_produced_for_tools_and_generators()
    {
        var schema = Spec("""{"type":"object","fields":{"n":{"type":"integer","min":1},"tags":{"type":"list","items":"string"},"k":{"type":"enum","options":["a"]}},"required":["n"]}""").ToJsonSchema();
        Assert.Equal("object", schema["type"]!.GetValue<string>());
        Assert.Equal("integer", schema["properties"]!["n"]!["type"]!.GetValue<string>());
        Assert.Equal(1, schema["properties"]!["n"]!["minimum"]!.GetValue<double>());
        Assert.Equal("string", schema["properties"]!["tags"]!["items"]!["type"]!.GetValue<string>());
        Assert.Equal("a", schema["properties"]!["k"]!["enum"]![0]!.GetValue<string>());
        Assert.Equal("n", schema["required"]![0]!.GetValue<string>());
    }
}
