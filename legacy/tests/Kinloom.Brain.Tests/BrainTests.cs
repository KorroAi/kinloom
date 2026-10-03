using System.Collections.Concurrent;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Kinloom.Brain;
using Kinloom.Llm;
using Kinloom.Core;

namespace Kinloom.Brain.Tests;

public class BrainTests
{
    // ---------- fixtures ----------

    internal static PackDefinition Pack() => new()
    {
        Name = "test",
        Deeds =
        {
            new DeedDefinition { Kind = "steal", Valence = -0.8f, Threat = 0.1f, Radius = 8f, IsCrime = true, TransfersItem = true },
            new DeedDefinition { Kind = "help", Valence = 0.7f, Radius = 6f },
            new DeedDefinition { Kind = "give", Valence = 0.5f, Radius = 5f },
            new DeedDefinition { Kind = "attack", Valence = -0.9f, Threat = 0.9f, Radius = 10f, IsCrime = true },
        },
    };

    /// <summary>Mira (baker) saw Tob steal her rice. Ben (guard) knows nothing. The player stands next to Mira.</summary>
    internal static (Simulation Sim, Agent Mira, Agent Tob, Agent Ben, Agent Player) Village()
    {
        var w = new World(Pack(), 3);
        w.Add(new Place("bakery", "Bakery", new Vec2(0, 0), 3f));
        w.Add(new Place("forge", "Forge", new Vec2(40, 0), 3f));
        var mira = w.Add(new Agent("mira", "Mira", new Vec2(0, 0), new Personality(0.4f, 0.8f, 0.5f)));
        mira.Profile.Role = "baker";
        mira.Gold = 30;
        var tob = w.Add(new Agent("tob", "Tob", new Vec2(1, 0), new Personality(0.6f, 0.5f, 0.3f)));
        tob.Profile.Role = "farmhand";
        tob.Profile.Secrets.Add("owes money to bandits");
        var ben = w.Add(new Agent("ben", "Ben", new Vec2(60, 0), new Personality(0.8f, 0.4f, 0.5f), false, new[] { Tags.Authority }));
        ben.Profile.Role = "guard";
        var player = w.Add(new Agent("player", "Traveller", new Vec2(1, 1), new Personality(0.5f, 0.5f, 0.5f), true));
        w.Add(new Item("rice", "Rice sack", new Vec2(0, 0), 3f, "mira"));
        w.Add(new Item("knife", "Knife", new Vec2(0, 0), 3f, "tob"));
        var sim = new Simulation(w, new PlayerCommand[0]) { ExternalMovement = true };
        Actions.PerformDeed(w, tob, "steal", "mira", "rice"); // Mira witnesses; Ben is too far
        return (sim, mira, tob, ben, player);
    }

    private static Brain NewBrain(Simulation sim, ILlmClient? client, System.Action<BrainOptions>? tune = null)
    {
        var options = new BrainOptions { Lockstep = true, AmbientTalkChance = 0f, DirectorEveryHours = 1000, ChronicleHour = 99, PlanHour = 99, ReflectThreshold = 99f };
        tune?.Invoke(options);
        return new Brain(sim, client, options);
    }

    private static string Reply(LlmRequest r, string task, string json) => r.Task == task ? json : "{}";

    // ---------- knowledge isolation ----------

    [Fact]
    public void A_prompt_contains_what_the_agent_knows_and_never_what_it_does_not()
    {
        var (sim, mira, _, ben, _) = Village();
        var client = new ScriptedLlmClient(_ => "{}");
        var brain = NewBrain(sim, client);
        brain.Enqueue(new DayPlanJob("ben", 1));
        brain.Enqueue(new DayPlanJob("mira", 1));
        brain.Update();
        var benPrompt = client.Requests.Single(r => r.User.Contains("You are Ben")).User;
        var miraPrompt = client.Requests.Single(r => r.User.Contains("You are Mira")).User;
        Assert.Contains("Tob steal -> Mira", miraPrompt);
        Assert.DoesNotContain("Tob steal", benPrompt);
        Assert.DoesNotContain("owes money to bandits", miraPrompt); // Tob's secret stays Tob's
    }

    [Fact]
    public void Who_holds_a_stolen_item_is_not_common_knowledge()
    {
        var (sim, _, _, ben, _) = BrainTests.Village(); // Tob stole Mira's rice; Ben saw nothing
        var client = new ScriptedLlmClient(_ => "{}");
        var brain = NewBrain(sim, client);
        brain.Enqueue(new DayPlanJob("ben", 1));
        brain.Update();
        var prompt = client.Requests.Single().User;
        Assert.Contains("Rice sack (belongs to Mira)", prompt);
        Assert.DoesNotContain("Tob's", prompt);
    }

    // ---------- day plans + arbiter ----------

    [Fact]
    public void A_day_plan_becomes_a_real_plan_and_illegal_steps_are_refused_with_reasons()
    {
        var (sim, mira, _, _, _) = Village();
        var client = new ScriptedLlmClient(r => Reply(r, "plan", """
            {"intention":"Find out who took my rice","thought":"Tob looked guilty.",
             "steps":[{"time":"08:00","verb":"work","target":"bakery","note":"bake"},
                      {"time":"10:00","verb":"talk","target":"ben","note":"report Tob"},
                      {"time":"11:00","verb":"goto","target":"moon"},
                      {"time":"12:00","verb":"give","target":"tob","item":"knife"},
                      {"time":"13:00","verb":"attack","target":"ben"}]}
            """));
        var brain = NewBrain(sim, client);
        mira.Mind.Emotions.Decay(0f); // calm again: rage would make the attack legal
        brain.Enqueue(new DayPlanJob("mira", 1));
        brain.Update();
        Assert.NotNull(mira.Plan);
        Assert.Equal("Find out who took my rice", mira.Plan!.Intention);
        Assert.Equal(new[] { "work", "talk" }, mira.Plan.Steps.Select(s => s.Verb));
        var rejected = sim.World.Journal.Entries.Where(e => e.Kind == "rejected").Select(e => e.Text).ToList();
        Assert.Contains(rejected, t => t.Contains("unknown place 'moon'"));
        Assert.Contains(rejected, t => t.Contains("does not own 'knife'"));
        Assert.Contains(rejected, t => t.Contains("not angry enough"));
        var events = brain.DrainEvents();
        Assert.Contains(events, e => e.Kind == "plan" && e.AgentId == "mira");
        Assert.Contains(events, e => e.Kind == "thought" && e.Text == "Tob looked guilty.");
    }

    [Fact]
    public void Loose_names_from_the_model_are_resolved_to_real_ids()
    {
        var (sim, _, _, _, _) = Village();
        var w = sim.World;
        Assert.Equal("forge", Ids.Place(w, "Forge"));
        Assert.Equal("forge", Ids.Place(w, "[forge]"));
        Assert.Equal("bakery", Ids.Place(w, "the bakery"));
        Assert.Equal("mira", Ids.Agent(w, "Mira"));
        Assert.Equal("rice", Ids.Item(w, "Rice sack"));
        Assert.Null(Ids.Place(w, "moon"));
        Assert.Null(Ids.Agent(w, null));
    }

    [Fact]
    public void Plans_are_triggered_once_per_day_at_the_plan_hour()
    {
        var (sim, _, _, _, _) = Village();
        var client = new ScriptedLlmClient(_ => "{}");
        var brain = NewBrain(sim, client, o => o.PlanHour = 5);
        for (int i = 0; i < 7 * World.TicksPerHour; i++) { sim.Step(); brain.Update(); }
        Assert.Equal(3, client.Requests.Count(r => r.Task == "plan")); // mira, tob, ben — not the player
    }

    // ---------- conversation ----------

    [Fact]
    public void A_meeting_becomes_a_conversation_that_shares_only_what_the_speaker_knows()
    {
        var (sim, mira, tob, ben, _) = Village();
        ben.Position = new Vec2(1, 0);
        var client = new ScriptedLlmClient(r => Reply(r, "converse", """
            {"lines":[{"speaker":"mira","text":"Ben, Tob took my rice!"},{"speaker":"ben","text":"I'll look into it."}],
             "shared":[{"from":"mira","memory":"a1"},{"from":"ben","memory":"a1"}],
             "opinion_changes":[{"who":"ben","about":"tob","delta":-0.9,"why":"thief"}],
             "summary":"Mira tells Ben about the theft."}
            """));
        var brain = NewBrain(sim, client);
        mira.Plan = new Plan("Report", 0, new[] { new PlanStep(0, 0, Verbs.Talk, "ben", null, "report the theft") });
        sim.Step();
        brain.Update();
        Assert.Contains(ben.Mind.Memories, m => m.Kind == "steal" && m.ActorId == "tob" && m.SourceId == "mira");
        Assert.Contains(sim.World.Journal.Entries, e => e.Kind == "rejected" && e.Text.Contains("Ben cannot tell 'a1'"));
        Assert.True(ben.Mind.OpinionOf("tob") >= -0.2f - 0.4f); // clamped model shift (-0.2) + rule-level hearsay shift
        var says = brain.DrainEvents().Where(e => e.Kind == "say").ToList();
        Assert.Equal(2, says.Count);
        Assert.Equal(new[] { 0, 1 }, says.Select(s => s.Order));
    }

    [Fact]
    public void A_lie_in_conversation_plants_a_false_memory()
    {
        var (sim, mira, tob, _, _) = Village();
        var client = new ScriptedLlmClient(r => Reply(r, "converse", """
            {"lines":[{"speaker":"tob","text":"It was Ben who took it, I swear."}],
             "lies":[{"from":"tob","deed":"steal","actor":"ben","target":"mira","item":"rice"}],"summary":"Tob blames Ben."}
            """));
        var brain = NewBrain(sim, client);
        brain.Enqueue(new ConverseJob("tob", "mira", null, 1));
        brain.Update();
        var lie = mira.Mind.Memories.Single(m => m.ActorId == "ben");
        Assert.True(lie.IsLie);
        Assert.Contains(sim.World.Journal.Entries, e => e.Kind == "lie" && e.AgentId == "tob");
    }

    [Fact]
    public void An_agreement_adds_a_step_to_todays_plan()
    {
        var (sim, mira, _, ben, _) = Village();
        var client = new ScriptedLlmClient(r => Reply(r, "converse", """
            {"lines":[{"speaker":"ben","text":"Meet me at the forge at noon."}],
             "agreement":{"who":"mira","time":"12:00","verb":"goto","target":"forge","note":"meet Ben"},"summary":"A meeting is set."}
            """));
        var brain = NewBrain(sim, client);
        brain.Enqueue(new ConverseJob("ben", "mira", null, 1));
        brain.Update();
        Assert.Contains(mira.Plan!.Steps, s => s.Verb == "goto" && s.TargetId == "forge" && s.Hour == 12);
    }

    // ---------- dialogue with the player ----------

    [Fact]
    public void Talking_to_an_npc_returns_a_reply_and_its_actions_go_through_the_arbiter()
    {
        var (sim, mira, _, _, player) = Village();
        var client = new ScriptedLlmClient(r => Reply(r, "dialogue", """
            {"reply":"Tob. Tob took my rice. Bring it back and the bread is on me.","emotion":"angry",
             "actions":[{"type":"share","memory":"m1"},{"type":"opinion","delta":0.9,"why":"listens to me"},
                        {"type":"offer_quest","kind":"retrieve_item","target":"tob","item":"rice","reward":500,"reason":"Get my rice back from Tob"},
                        {"type":"give","item":"knife"}]}
            """));
        var brain = NewBrain(sim, client);
        int ticket = brain.Talk("mira", "Why do you look so upset?");
        var events = brain.DrainEvents();
        var reply = events.Single(e => e.Kind == "reply");
        Assert.Equal(ticket, reply.Ticket);
        Assert.Equal("angry", reply.Emotion);
        Assert.Contains(player.Mind.Memories, m => m.ActorId == "tob" && m.Kind == "steal");
        Assert.Equal(0.15f, mira.Mind.OpinionOf("player"), 3);
        var quest = sim.World.Quests.All.Single();
        Assert.Equal(30, quest.Reward); // capped to what Mira owns
        Assert.Contains(events, e => e.Kind == "quest");
        Assert.Equal("tob", sim.World.FindItem("knife")!.OwnerId); // at most 3 actions are read: the 4th never happens
    }

    [Fact]
    public void Without_a_model_npcs_still_answer_from_rules()
    {
        var (sim, mira, _, _, _) = Village();
        var brain = NewBrain(sim, null);
        int ticket = brain.Talk("mira", "Hello!");
        var reply = brain.DrainEvents().Single(e => e.Kind == "reply");
        Assert.Equal(ticket, reply.Ticket);
        Assert.False(string.IsNullOrWhiteSpace(reply.Text));
        Assert.Equal(2, brain.Stats.Fallbacks); // intent + dialogue, both by rules
    }

    [Fact]
    public void A_broken_answer_falls_back_to_rules()
    {
        var (sim, _, _, _, _) = Village();
        var brain = NewBrain(sim, new ScriptedLlmClient(_ => "I am not JSON"));
        brain.Talk("mira", "Hello!");
        Assert.Single(brain.DrainEvents(), e => e.Kind == "reply");
        Assert.Equal(2, brain.Stats.Failures); // intent and dialogue both unreadable
    }

    // ---------- reflection ----------

    [Fact]
    public void Salient_events_trigger_a_reflection_that_changes_heart_goal_and_asks_for_help()
    {
        var (sim, mira, tob, _, _) = Village();
        var client = new ScriptedLlmClient(r => Reply(r, "reflect", """
            {"thoughts":["Tob betrayed me."],"emotion":"angry","opinion_changes":[{"who":"tob","delta":-1,"why":"stole my rice"}],
             "goal":"Get my rice back","replan":false,
             "quest":{"kind":"retrieve_item","target":"tob","item":"rice","reward":10,"reason":"Please get my rice back from Tob."}}
            """));
        var brain = NewBrain(sim, client, o => o.ReflectThreshold = 1f);
        sim.World.Add(new Item("bread", "Bread", new Vec2(0, 0), 1f, "mira"));
        Actions.PerformDeed(sim.World, tob, "steal", "mira", "bread"); // happens while the brain is running
        float before = mira.Mind.OpinionOf("tob");
        brain.Update();
        Assert.Equal(before - 0.3f, mira.Mind.OpinionOf("tob"), 3);
        Assert.Equal("Get my rice back", brain.StateOf("mira").Goal);
        Assert.Contains("Tob betrayed me.", brain.StateOf("mira").Beliefs);
        Assert.Equal(QuestStatus.Offered, sim.World.Quests.All.Single().Status);
        var why = sim.World.Journal.Why(sim.World.Journal.Entries.Last(e => e.Kind == "thought").Id);
        Assert.Contains(why, e => e.Kind == "witness"); // the thought is explained by what Mira saw
    }

    // ---------- director ----------

    [Fact]
    public void The_director_starts_a_coherent_event_and_is_refused_when_too_soon()
    {
        var (sim, _, _, _, _) = Village();
        var client = new ScriptedLlmClient(r => Reply(r, "director", """
            {"event":{"kind":"festival","where":"bakery","duration_hours":2,"reason":"to heal the rift","announcement":"Lanterns rise over the bakery."}}
            """));
        var brain = NewBrain(sim, client);
        brain.RequestDirector();
        brain.Update();
        Assert.Single(sim.World.Events.Active);
        Assert.Contains(brain.DrainEvents(), e => e.Kind == "event" && e.Text.Contains("Lanterns"));
        brain.RequestDirector();
        brain.Update();
        Assert.Single(sim.World.Events.History);
        Assert.Contains(sim.World.Journal.Entries, e => e.Kind == "rejected" && e.Text.Contains("too soon"));
    }

    [Fact]
    public void The_director_cannot_start_an_impossible_event()
    {
        var (sim, _, _, _, _) = Village();
        var client = new ScriptedLlmClient(r => Reply(r, "director", """{"event":{"kind":"bandit_raid","where":"bakery","duration_hours":2}}"""));
        var brain = NewBrain(sim, client);
        brain.RequestDirector();
        brain.Update();
        Assert.Empty(sim.World.Events.History);
        Assert.Contains(sim.World.Journal.Entries, e => e.Kind == "rejected" && e.Text.Contains("no reserve bandits"));
    }

    // ---------- chronicle ----------

    [Fact]
    public void The_chronicle_is_built_from_the_journal()
    {
        var (sim, _, _, _, _) = Village();
        var client = new ScriptedLlmClient(r => Reply(r, "chronicle", """{"title":"The Rice Affair","paragraphs":["Tob took Mira's rice."]}"""));
        var brain = NewBrain(sim, client);
        brain.RequestChronicle();
        brain.Update();
        Assert.Contains("Tob steal", client.Requests.Single().User);
        Assert.Contains(brain.DrainEvents(), e => e.Kind == "chronicle" && e.Text.StartsWith("The Rice Affair"));
    }

    [Fact]
    public void The_epilogue_is_the_legend_of_the_player_built_from_what_villagers_really_think()
    {
        var (sim, mira, _, _, _) = Village();
        mira.Mind.ShiftOpinion("player", 0.7f);
        var client = new ScriptedLlmClient(r => Reply(r, "epilogue", """{"title":"The Kind Stranger","epithet":"Friend of Bakers","paragraphs":["They helped Mira."]}"""));
        var brain = NewBrain(sim, client);
        brain.RequestEpilogue();
        brain.Update();
        var prompt = client.Requests.Single().User;
        Assert.Contains("Mira", prompt);
        Assert.Contains("love", prompt); // Mira's real feeling about the player is in the prompt
        var e = brain.DrainEvents().Single(x => x.Kind == "epilogue");
        Assert.StartsWith("The Kind Stranger", e.Text);
        Assert.Contains("Friend of Bakers", e.Text);
    }

    // ---------- scheduling ----------

    [Fact]
    public void Concurrency_is_capped_and_the_player_goes_first()
    {
        var (sim, _, _, _, _) = Village();
        var gate = new TaskCompletionSource<LlmResponse>();
        var client = new PendingClient(gate.Task);
        var brain = new Brain(sim, client, new BrainOptions { MaxConcurrent = 2, AmbientTalkChance = 0f, PlanHour = 99, ReflectThreshold = 99f, DirectorEveryHours = 1000, ChronicleHour = 99 });
        brain.Enqueue(new DayPlanJob("mira", 4));
        brain.Enqueue(new DayPlanJob("tob", 4));
        brain.Enqueue(new DayPlanJob("ben", 4));
        brain.Talk("mira", "hi");
        brain.Update();
        Assert.Equal(2, brain.InFlight);
        Assert.Equal("intent", client.Tasks.First());
        gate.SetResult(LlmResponse.Success("{}", 1, 1, 1));
    }

    [Fact]
    public void Over_budget_background_jobs_fall_back_but_the_player_is_still_served()
    {
        var (sim, mira, _, _, _) = Village();
        var client = new ScriptedLlmClient(r => r.Task == "dialogue" ? """{"reply":"Hm?"}""" : "{}");
        var brain = NewBrain(sim, client, o => o.TokensPerGameHour = 1);
        brain.Talk("mira", "hello"); // intent + dialogue: spends the budget
        brain.Enqueue(new DayPlanJob("tob", 4));
        brain.Update();
        Assert.Equal(2, client.Requests.Count);
        brain.Talk("mira", "hello again");
        Assert.Equal(4, client.Requests.Count);
    }

    private sealed class PendingClient : ILlmClient
    {
        private readonly Task<LlmResponse> _result;
        public PendingClient(Task<LlmResponse> result) { _result = result; }
        public ConcurrentQueue<string> Tasks { get; } = new();
        public string Name => "pending";
        public Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellation = default)
        {
            Tasks.Enqueue(request.Task);
            return _result;
        }
    }
}
