using System.Linq;
using Kinloom.Brain;
using Kinloom.Llm;
using Kinloom.Core;

namespace Kinloom.Brain.Tests;

/// <summary>What the player writes can be an act (paying, handing over, threatening, accusing): checked against the world, then done.</summary>
public class IntentTests
{
    private static Brain NewBrain(Simulation sim, ILlmClient? client) =>
        new(sim, client, new BrainOptions { Lockstep = true, AmbientTalkChance = 0f, DirectorEveryHours = 1000, ChronicleHour = 99, PlanHour = 99, ReflectThreshold = 99f });

    private static ScriptedLlmClient Client(string intent, string reply = """{"reply":"Hm."}""") =>
        new(r => r.Task == "intent" ? intent : r.Task == "dialogue" ? reply : "{}");

    [Fact]
    public void Giving_gold_in_words_moves_the_gold_and_the_npc_knows_it_happened()
    {
        var (sim, mira, _, _, player) = BrainTests.Village();
        player.Gold = 20;
        int miraGold = mira.Gold;
        var client = Client("""{"actions":[{"type":"give_gold","amount":5}]}""");
        var brain = NewBrain(sim, client);
        brain.Talk("mira", "Here, take 5 coins for your trouble.");
        Assert.Equal(15, player.Gold);
        Assert.Equal(miraGold + 5, mira.Gold);
        var dialogue = client.Requests.Single(r => r.Task == "dialogue").User;
        Assert.Contains("gave you 5 gold", dialogue);
        Assert.Contains(sim.World.Journal.Entries, e => e.Kind == "deed" && e.Text.Contains("pay"));
    }

    [Fact]
    public void Promising_gold_you_do_not_have_moves_nothing_and_the_npc_is_told()
    {
        var (sim, mira, _, _, player) = BrainTests.Village();
        player.Gold = 3;
        var client = Client("""{"actions":[{"type":"give_gold","amount":50}]}""");
        var brain = NewBrain(sim, client);
        brain.Talk("mira", "I give you 50 gold.");
        Assert.Equal(3, player.Gold);
        Assert.Contains("did not", client.Requests.Single(r => r.Task == "dialogue").User);
    }

    [Fact]
    public void Handing_over_an_item_in_words_transfers_it()
    {
        var (sim, mira, _, _, player) = BrainTests.Village();
        var cake = sim.World.Add(new Item("cake", "Cake", new Vec2(0, 0), 2f, "player"));
        var brain = NewBrain(sim, Client("""{"actions":[{"type":"give_item","item":"Cake"}]}"""));
        brain.Talk("mira", "This cake is for you.");
        Assert.Equal("mira", cake.OwnerId);
    }

    [Fact]
    public void Accusing_the_culprit_in_words_solves_the_investigation()
    {
        var (sim, mira, tob, _, player) = BrainTests.Village();
        mira.Gold = 30;
        var q = sim.World.Quests.Offer(sim.World, "mira", QuestKinds.Accuse, "tob", null, 10, "Who took my rice?", null);
        sim.World.Quests.Accept(sim.World, q.Id, "player");
        var client = Client("""{"actions":[{"type":"accuse","person":"Tob"}]}""");
        var brain = NewBrain(sim, client);
        brain.Talk("mira", "It was Tob. I'm sure of it.");
        Assert.Equal(QuestStatus.Completed, q.Status);
        Assert.Contains("accuses Tob", client.Requests.Single(r => r.Task == "dialogue").User);
    }

    [Fact]
    public void An_npc_can_agree_to_come_along()
    {
        var (sim, mira, _, _, player) = BrainTests.Village();
        var brain = NewBrain(sim, Client("""{"actions":[{"type":"ask_follow"}]}""", """{"reply":"Lead the way.","actions":[{"type":"follow","hours":3}]}"""));
        brain.Talk("mira", "Come with me to the forest.");
        Assert.Equal("player", mira.FollowId);
    }

    [Fact]
    public void Without_a_model_simple_payments_still_work()
    {
        var (sim, mira, _, _, player) = BrainTests.Village();
        player.Gold = 10;
        var brain = NewBrain(sim, null);
        brain.Talk("mira", "Je te donne 4 pièces.");
        Assert.Equal(6, player.Gold);
    }
}
