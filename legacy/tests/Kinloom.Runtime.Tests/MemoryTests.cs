using System.Text.Json.Nodes;
using Kinloom.Memory;
using Kinloom.Schema;

namespace Kinloom.Runtime.Tests;

public class MemoryTests
{
    private static MemoryEntry M(double t, string text, double importance) => new MemoryEntry(t, text, importance);

    [Fact]
    public void Recall_prefers_relevant_and_important_memories()
    {
        var store = new MemoryStore();
        store.Add("role:rex", M(0, "The player rammed me on the bridge", 0.9), 50);
        store.Add("role:rex", M(10, "It started to rain", 0.2), 50);
        store.Add("role:rex", M(20, "Mo waved at the crowd", 0.3), 50);
        var top = store.Recall("role:rex", "player bridge", 2, now: 30);
        Assert.Equal("The player rammed me on the bridge", top[0].Text);
        Assert.Equal(2, top.Count);
    }

    [Fact]
    public void Recent_memories_win_when_nothing_else_differs()
    {
        var store = new MemoryStore();
        store.Add("s", M(0, "old thing", 0.5), 50);
        store.Add("s", M(1000, "new thing", 0.5), 50);
        Assert.Equal("new thing", store.Recall("s", "", 1, now: 1000)[0].Text);
    }

    [Fact]
    public void Eviction_keeps_the_important_ones()
    {
        var store = new MemoryStore();
        store.Add("s", M(0, "crucial", 1.0), 3);
        for (int i = 1; i <= 10; i++) store.Add("s", M(i, "noise " + i, 0.1), 3);
        var all = store.All("s");
        Assert.Equal(3, all.Count);
        Assert.Contains(all, m => m.Text == "crucial");
        Assert.Contains(all, m => m.Text == "noise 10");
    }

    [Fact]
    public void Save_then_load_restores_memories_and_role_behaviors()
    {
        var s = SessionTests.Trucks();
        s.Tick(100);
        s.Memory.Add("role:rex", M(90, "The player cheated", 0.8), 50);
        var errors = new List<ManifestError>();
        var b = BehaviorDecl.Parse(JsonNode.Parse("""{"id":"grudge","owner":"truck_2","rules":[{"when":"true","do":[{"set":"self.aggression","to":"0.9"}]}]}"""), "b", errors);
        Assert.Empty(s.InstallBehavior(b, "role:rex", new[] { Permission.Parse("behavior:self"), Permission.Parse("set:self.aggression") }, "truck_2"));
        string save = s.Save();

        var fresh = SessionTests.Trucks();
        fresh.Tick(5);
        fresh.Load(save);
        var m = fresh.Memory.All("role:rex").Single();
        Assert.Equal("The player cheated", m.Text);
        Assert.Equal(-5, m.Time, 6); // same age (10 s) relative to the new clock
        var restored = fresh.Behaviors.Single();
        Assert.Equal("grudge", restored.behavior.Id);
        Assert.Equal("role:rex", restored.source);
    }

    [Fact]
    public void Game_behaviors_are_not_saved()
    {
        var s = SessionTests.Trucks();
        var errors = new List<ManifestError>();
        s.InstallBehavior(BehaviorDecl.Parse(JsonNode.Parse("""{"id":"g","owner":"truck_2","rules":[]}"""), "b", errors), "game", null);
        var save = JsonNode.Parse(s.Save())!;
        Assert.Empty(save["behaviors"]!.AsArray());
    }

    [Fact]
    public void Memories_of_non_persistent_roles_are_not_saved()
    {
        var s = new KinloomSession();
        Assert.Empty(s.Declare(TestData.Trucks.Replace("\"persist\": true", "\"persist\": false")));
        s.Memory.Add("role:rex", M(0, "fleeting", 0.5), 50);
        s.Memory.Add("shared", M(0, "kept", 0.5), 50);
        var fresh = SessionTests.Trucks();
        fresh.Load(s.Save());
        Assert.Empty(fresh.Memory.All("role:rex"));
        Assert.Single(fresh.Memory.All("shared"));
    }

    [Fact]
    public void Loading_garbage_fails_with_a_clear_message()
    {
        var s = SessionTests.Trucks();
        var e1 = Assert.Throws<InvalidOperationException>(() => s.Load("not json"));
        Assert.Contains("Kinloom save", e1.Message);
        var e2 = Assert.Throws<InvalidOperationException>(() => s.Load("""{"version": 99}"""));
        Assert.Contains("version", e2.Message);
    }
}
