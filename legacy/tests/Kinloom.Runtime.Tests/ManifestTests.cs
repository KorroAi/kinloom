using System.IO;
using Kinloom.Schema;

namespace Kinloom.Runtime.Tests;

public class ManifestTests
{
    private static (Declarations d, List<ManifestError> errors) Load(string json)
    {
        var errors = new List<ManifestError>();
        var d = Manifest.Parse(json, "test.json", errors);
        Manifest.Check(d, errors);
        return (d, errors);
    }

    [Fact]
    public void The_truck_example_parses_cleanly()
    {
        var (d, errors) = Load(TestData.Trucks);
        Assert.Empty(errors);
        var truck = d.Types["Truck"];
        Assert.Equal(FieldKind.Number, truck.Properties.Find("speed")!.Kind);
        Assert.Equal("km/h", truck.Properties.Find("speed")!.Unit);
        Assert.Equal(1, truck.Params.Find("aggression")!.Max);
        Assert.Equal(10, truck.Functions["boost"].Cooldown);
        Assert.Equal("seconds", truck.Functions["boost"].Args.Names[0]);
        Assert.Equal(3, truck.Creatable!.Max);
        Assert.Equal(4, d.Things.Count);
        Assert.Equal(0.9, d.Events["crash"].Importance);
        var rex = d.Roles.Single();
        Assert.Equal("truck_2", rex.Inhabits);
        Assert.Equal(20, rex.Wake[1].Every);
        Assert.Equal("Grr.", rex.Fallback!.Say[0]);
    }

    [Fact]
    public void Unknown_thing_type_is_reported_with_its_path()
    {
        var (_, errors) = Load("""{"things":[{"id":"a","type":"Ghost"}]}""");
        Assert.Contains(errors, e => e.Path == "things[0].type" && e.Message.Contains("Ghost"));
    }

    [Fact]
    public void A_role_asking_for_an_unknown_lever_is_reported()
    {
        string json = TestData.Trucks.Replace("\"set:self.aggression\"", "\"set:Truck.nitro\"");
        var (_, errors) = Load(json);
        Assert.Contains(errors, e => e.Path == "roles[0].can[0]" && e.Message.Contains("nitro"));
    }

    [Fact]
    public void A_role_seeing_an_unknown_thing_is_reported()
    {
        string json = TestData.Trucks.Replace("\"thing:player\"", "\"thing:plaeyr\"");
        var (_, errors) = Load(json);
        Assert.Contains(errors, e => e.Path == "roles[0].sees[1]");
    }

    [Fact]
    public void Self_needs_an_inhabited_thing()
    {
        string json = TestData.Trucks.Replace("\"inhabits\": \"truck_2\",", "");
        var (_, errors) = Load(json);
        Assert.Contains(errors, e => e.Path == "roles[0].can[0]" && e.Message.Contains("inhabits"));
    }

    [Fact]
    public void Wake_entries_need_exactly_one_trigger()
    {
        string json = TestData.Trucks.Replace("{ \"every\": 20 }", "{ \"every\": 20, \"on\": \"ask\" }");
        var (_, errors) = Load(json);
        Assert.Contains(errors, e => e.Path == "roles[0].wake[1]");
    }

    [Fact]
    public void Merging_two_files_with_the_same_thing_id_is_an_error()
    {
        var errors = new List<ManifestError>();
        var a = Manifest.Parse(TestData.Trucks, "a.json", errors);
        var b = Manifest.Parse("""{"things":[{"id":"hud","type":"Hud"}]}""", "b.json", errors);
        a.Merge(b, errors);
        Assert.Contains(errors, e => e.Message.Contains("hud") && e.Message.Contains("b.json"));
    }

    [Fact]
    public void The_world_id_is_reserved()
    {
        var (_, errors) = Load("""{"types":{"T":{}},"things":[{"id":"world","type":"T"}]}""");
        Assert.Contains(errors, e => e.Path == "things[0].id");
    }

    [Fact]
    public void Broken_json_is_an_error_not_an_exception()
    {
        var (_, errors) = Load("{ \"types\": ");
        Assert.Single(errors);
        Assert.Equal("test.json", errors[0].Path);
    }

    [Fact]
    public void Unknown_top_level_keys_are_reported()
    {
        var (_, errors) = Load("""{"thigns":[]}""");
        Assert.Contains(errors, e => e.Path == "thigns");
    }

    [Fact]
    public void A_directory_of_files_is_merged_and_tests_are_ignored()
    {
        string dir = Path.Combine(Path.GetTempPath(), "kinloom-manifest-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(dir, "tests"));
        try
        {
            File.WriteAllText(Path.Combine(dir, "types.json"), """{"types":{"Door":{"params":{"open":"boolean"}}}}""");
            File.WriteAllText(Path.Combine(dir, "things.json"), """{"things":[{"id":"door_1","type":"Door"}]}""");
            File.WriteAllText(Path.Combine(dir, "tests", "t.test.json"), "not a manifest");
            var errors = new List<ManifestError>();
            var d = Manifest.LoadDirectory(dir, errors);
            Manifest.Check(d, errors);
            Assert.Empty(errors);
            Assert.Single(d.Things);
        }
        finally { Directory.Delete(dir, true); }
    }
}
