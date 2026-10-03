using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Kinloom.Brain;
using Kinloom.Llm;
using Kinloom.Core;

namespace Kinloom.Brain.Tests;

public class CostAndLanguageTests
{
    private static Brain NewBrain(Simulation sim, ILlmClient client, System.Action<BrainOptions>? tune = null)
    {
        var o = new BrainOptions { Lockstep = true, AmbientTalkChance = 0f, DirectorEveryHours = 1000, ChronicleHour = 99, PlanHour = 99, ReflectThreshold = 99f };
        tune?.Invoke(o);
        return new Brain(sim, client, o);
    }

    [Fact]
    public void Npcs_speak_the_configured_language()
    {
        var (sim, _, _, _, _) = BrainTests.Village();
        var client = new ScriptedLlmClient(_ => "{}");
        var brain = NewBrain(sim, client, o => o.Language = "French");
        brain.Talk("mira", "Bonjour !");
        Assert.Contains("in French", client.Requests.Single(r => r.Task == "dialogue").System);
    }

    [Fact]
    public void Cached_tokens_and_cost_are_tracked_with_the_integrators_prices()
    {
        var (sim, _, _, _, _) = BrainTests.Village();
        var brain = NewBrain(sim, new FixedClient(LlmResponse.Success("{\"reply\":\"Hi\"}", 1000, 100, 5, cachedInputTokens: 600)),
            o => o.Prices = new TokenPrices(0.3, 0.006, 1.2));
        brain.Talk("mira", "hello");
        int calls = brain.Stats.Calls; // intent + dialogue
        Assert.Equal(600 * calls, brain.Stats.CachedInputTokens);
        // per call: 400 uncached * 0.3 + 600 cached * 0.006 + 100 out * 1.2, per million tokens
        Assert.Equal(calls * (400 * 0.3 + 600 * 0.006 + 100 * 1.2) / 1_000_000, brain.Stats.Cost!.Value, 9);
    }

    [Fact]
    public void Without_prices_no_cost_is_invented()
    {
        var (sim, _, _, _, _) = BrainTests.Village();
        var brain = NewBrain(sim, new FixedClient(LlmResponse.Success("{\"reply\":\"Hi\"}", 1000, 100, 5)));
        brain.Talk("mira", "hello");
        Assert.Null(brain.Stats.Cost);
    }

    [Fact]
    public void Conversations_far_from_the_player_are_brief_and_still_change_the_world()
    {
        var (sim, mira, tob, ben, player) = BrainTests.Village();
        player.Position = new Vec2(200, 200); // far from everyone
        var client = new ScriptedLlmClient(r => r.Task == "converse"
            ? """{"summary":"Mira warns Ben about Tob.","shared":[{"from":"mira","memory":"a1"}]}"""
            : "{}");
        var brain = NewBrain(sim, client);
        ben.Position = new Vec2(1, 0);
        brain.Enqueue(new ConverseJob("mira", "ben", null, 3));
        brain.Update();
        var prompt = client.Requests.Single().User;
        Assert.Contains("BRIEF", prompt);
        Assert.DoesNotContain("\"lines\": [", prompt); // the schema has no lines (the instruction may name the field to forbid it)
        Assert.Contains(ben.Mind.Memories, m => m.ActorId == "tob" && m.SourceId == "mira");
        Assert.Contains(sim.World.Journal.Entries, e => e.Kind == "talk" && e.Text.Contains("warns Ben"));
        Assert.DoesNotContain(brain.DrainEvents(), e => e.Kind == "say");
    }

    [Fact]
    public void Conversations_near_the_player_are_written_out_line_by_line()
    {
        var (sim, _, _, ben, _) = BrainTests.Village();
        var client = new ScriptedLlmClient(_ => "{}");
        var brain = NewBrain(sim, client);
        ben.Position = new Vec2(1, 0);
        brain.Enqueue(new ConverseJob("mira", "ben", null, 1));
        brain.Update();
        Assert.Contains("\"lines\"", client.Requests.Single().User);
    }

    [Fact]
    public void Only_the_npc_speaks_when_it_hails_the_player()
    {
        var (sim, _, _, _, player) = BrainTests.Village();
        var client = new ScriptedLlmClient(r => r.Task == "converse"
            ? """{"lines":[{"speaker":"mira","text":"You there! A word?"},{"speaker":"player","text":"Sure, I'd love to help."}],"summary":"Mira hails the traveller."}"""
            : "{}");
        var brain = NewBrain(sim, client);
        brain.Enqueue(new ConverseJob("mira", "player", null, 1));
        brain.Update();
        Assert.Contains("never write lines for the traveller", client.Requests.Single().User);
        var says = brain.DrainEvents().Where(e => e.Kind == "say").ToList();
        Assert.Single(says);
        Assert.Equal("mira", says[0].AgentId);
        Assert.Contains(sim.World.Journal.Entries, e => e.Kind == "rejected" && e.Text.Contains("traveller"));
    }

    [Fact]
    public void Ambient_conversations_are_capped_per_game_hour()
    {
        var (sim, mira, tob, ben, _) = BrainTests.Village();
        foreach (var a in sim.World.Agents) a.Position = new Vec2(0, 0); // everyone together, all day
        var client = new ScriptedLlmClient(_ => """{"summary":"They chat.","lines":[{"speaker":"mira","text":"Hi."}]}""");
        var brain = new Brain(sim, client, new BrainOptions
        {
            Lockstep = true, AmbientTalkChance = 1f, MaxAmbientTalksPerHour = 2, PairTalkCooldownTicks = 0,
            DirectorEveryHours = 1000, ChronicleHour = 99, PlanHour = 99, ReflectThreshold = 99f,
        });
        for (int i = 0; i < World.TicksPerHour - 1; i++) { sim.Step(); brain.Update(); } // stay within one game hour
        Assert.Equal(2, client.Requests.Count(r => r.Task == "converse"));
    }

    [Fact]
    public void A_planned_meeting_right_after_a_talk_does_not_call_the_model_again()
    {
        var (sim, mira, _, ben, _) = BrainTests.Village();
        ben.Position = new Vec2(1, 0);
        var client = new ScriptedLlmClient(_ => """{"summary":"They talk.","lines":[{"speaker":"mira","text":"Hello Ben."}]}""");
        var brain = NewBrain(sim, client);
        brain.Enqueue(new ConverseJob("mira", "ben", null, 1));
        brain.Update();
        int meet = sim.World.Journal.Add(sim.World.Tick, "meet", "mira", "Mira meets Ben", null, "ben");
        brain.Enqueue(new ConverseJob("mira", "ben", meet, 1));
        brain.Update();
        Assert.Single(client.Requests);
    }

    private sealed class FixedClient : ILlmClient
    {
        private readonly LlmResponse _r;
        public FixedClient(LlmResponse r) { _r = r; }
        public string Name => "fixed";
        public Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellation = default) => Task.FromResult(_r);
    }
}
