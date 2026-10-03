using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Text.Json;
using Kinloom.Llm;
using Kinloom.Core;

namespace Kinloom.Brain
{
    /// <summary>One unit of thinking: built on the main thread, answered by the model off-thread, applied on the main thread.</summary>
    public abstract class CognitionJob
    {
        protected CognitionJob(string task, string key, int priority, string? agentId, string? targetId)
        {
            Task = task;
            Key = key;
            Priority = priority;
            AgentId = agentId;
            TargetId = targetId;
        }

        public string Task { get; }
        public string Key { get; }
        /// <summary>0 = the player is waiting; higher = can wait.</summary>
        public int Priority { get; }
        public string? AgentId { get; }
        public string? TargetId { get; }
        internal long Sequence { get; set; }
        protected MemoryHandles Handles { get; } = new MemoryHandles();

        internal virtual bool StillRelevant(Brain brain)
        {
            var a = brain.World.FindAgent(AgentId);
            return AgentId == null || (a != null && a.Active);
        }

        internal abstract LlmRequest? Build(Brain brain);
        /// <summary>Returns false if the answer was unusable (then the rule fallback runs).</summary>
        internal abstract bool Apply(Brain brain, JsonElement root);
        internal virtual void Fallback(Brain brain) { }

        protected static string Deeds(World w) => string.Join(", ", w.Pack.Deeds.Select(d => d.Kind));
    }

    // =====================================================================================

    /// <summary>Morning (or after a shock): the agent plans the rest of its day.</summary>
    public sealed class DayPlanJob : CognitionJob
    {
        public DayPlanJob(string agentId, int priority) : base("plan", "plan|" + agentId, priority, agentId, null) { }

        internal override LlmRequest? Build(Brain brain)
        {
            var w = brain.World;
            var a = w.GetAgent(AgentId!);
            var p = brain.Prompts;
            var user = new StringBuilder()
                .Append(p.Persona(a)).Append('\n')
                .Append(p.Clock()).Append(' ').Append(p.State(a, brain.StateOf(a.Id))).Append('\n')
                .Append(p.People(a)).Append(p.Places()).Append(p.Items())
                .Append(p.Memories(a, Handles, "m", "WHAT YOU KNOW")).Append('\n')
                .Append(PromptBuilder.VerbGuide).Append("\n\n")
                .Append("Plan the rest of your day, from now until night, as 3 to 7 steps in time order. ")
                .Append("Make it fit who you are, your goals and what you know; involve other people. Steps before the current time are wasted.\n")
                .Append("JSON schema: {\"intention\": string (one sentence, first person), \"thought\": string (private, first person, under 20 words), ")
                .Append("\"steps\": [{\"time\": \"HH:MM\", \"verb\": string, \"target\": string|null, \"item\": string|null, \"note\": string}]}");
            return new LlmRequest(Task, p.Rules + "\n" + p.Setting, user.ToString(), 700);
        }

        internal override bool Apply(Brain brain, JsonElement root)
        {
            var w = brain.World;
            var a = w.GetAgent(AgentId!);
            string intention = Json.Str(root, "intention") ?? "Get through the day";
            var steps = new List<PlanStep>();
            foreach (var e in Json.Arr(root, "steps").Take(8))
            {
                var step = Arbiter.Step(w, a, e, out string error);
                if (step == null) brain.Reject(a.Id, Task, error, null);
                else steps.Add(step);
            }
            if (steps.Count == 0) return false;
            int entry = w.Journal.Add(w.Tick, "plan", a.Id, $"{a.Name} plans: {intention}", brain.StateOf(a.Id).LastTriggerEntry >= 0 && brain.Options.PlanHour != w.Hour ? brain.StateOf(a.Id).LastTriggerEntry : (int?)null);
            a.Plan = new Plan(intention, w.Day, steps, entry);
            brain.Emit("plan", a.Id, null, intention, entry: entry);
            string? thought = Json.Str(root, "thought");
            if (thought != null)
            {
                brain.StateOf(a.Id).LastThought = thought;
                brain.Emit("thought", a.Id, null, thought, entry: entry);
            }
            return true;
        }
    }

    // =====================================================================================

    /// <summary>After salient experiences: the agent makes sense of them — thoughts, changes of heart, new goals, a plea for help.</summary>
    public sealed class ReflectJob : CognitionJob
    {
        public ReflectJob(string agentId, int priority) : base("reflect", "reflect|" + agentId, priority, agentId, null) { }

        internal override LlmRequest? Build(Brain brain)
        {
            var w = brain.World;
            var a = w.GetAgent(AgentId!);
            var s = brain.StateOf(a.Id);
            s.PendingSalience = 0f;
            s.LastReflectTick = w.Tick;
            var p = brain.Prompts;
            string player = brain.PlayerId ?? "player";
            var user = new StringBuilder()
                .Append(p.Persona(a)).Append('\n')
                .Append(p.Clock()).Append(' ').Append(p.State(a, s)).Append('\n')
                .Append(p.People(a, PromptBuilder.Relevant(a))).Append(p.Items())
                .Append(p.Memories(a, Handles, "m", "WHAT YOU KNOW (most striking first)")).Append('\n')
                .Append("Something happened recently. Reflect privately, in character: what does it mean to you, who do you now trust or resent, what do you want to do?\n")
                .Append("JSON schema: {\"thoughts\": [1 to 3 short first-person thoughts], \"emotion\": \"happy|angry|afraid|sad|neutral|surprised|love|worried\", ")
                .Append("\"opinion_changes\": [{\"who\": person id, \"delta\": number from -0.3 to 0.3, \"why\": string}], ")
                .Append("\"goal\": string|null (what you now want, first person), \"replan\": boolean (true to change today's plan), ")
                .Append($"\"quest\": null or {{\"kind\": \"{string.Join("|", QuestKinds.All)}\", \"target\": person id, \"item\": item id|null, \"reward\": gold (0 to {a.Gold}), \"reason\": string (first person, what you ask of the traveller)}}}}\n")
                .Append($"Only fill \"quest\" if you truly need the traveller [{player}] to act for you (retrieve_item: get your item back; deliver_item: bring an item you own to someone; punish: hurt someone; persuade: make someone like you again; protect: keep someone alive).");
            return new LlmRequest(Task, p.Rules + "\n" + p.Setting, user.ToString(), 600);
        }

        internal override bool Apply(Brain brain, JsonElement root)
        {
            var w = brain.World;
            var a = w.GetAgent(AgentId!);
            var s = brain.StateOf(a.Id);
            int? cause = s.LastTriggerEntry >= 0 ? s.LastTriggerEntry : (int?)null;
            string? emotion = Json.Str(root, "emotion");
            var thoughts = Json.Strings(root, "thoughts").Take(3).ToList();
            if (thoughts.Count == 0) return false;
            int order = 0;
            foreach (var t in thoughts)
            {
                s.AddBelief(t, brain.Options.MaxBeliefs);
                s.LastThought = t;
                int entry = w.Journal.Add(w.Tick, "thought", a.Id, $"{a.Name} thinks: {t}", cause);
                brain.Emit("thought", a.Id, null, t, order++, emotion, entry);
            }
            foreach (var c in Json.Arr(root, "opinion_changes").Take(4))
            {
                string? who = Json.Str(c, "who");
                float? delta = Json.Num(c, "delta");
                if (who == null || delta == null) continue;
                if (Arbiter.ShiftOpinion(w, a, who, delta.Value, brain.Options.MaxOpinionShift, Json.Str(c, "why"), cause) == null && who != a.Id)
                    brain.Reject(a.Id, Task, $"opinion change about unknown '{who}'", cause);
            }
            string? goal = Json.Str(root, "goal");
            if (goal != null) s.Goal = goal;
            var quest = Json.Obj(root, "quest");
            if (quest != null && brain.PlayerId != null) OfferQuest(brain, a, quest.Value, cause, Task);
            if (Json.Bool(root, "replan")) brain.Enqueue(new DayPlanJob(a.Id, Priority));
            return true;
        }

        internal static void OfferQuest(Brain brain, Agent giver, JsonElement q, int? cause, string task)
        {
            var w = brain.World;
            string kind = Json.Str(q, "kind") ?? "";
            string target = Ids.Agent(w, Json.Str(q, "target")) ?? Json.Str(q, "target") ?? "";
            int reward = (int)System.Math.Max(0, System.Math.Min(giver.Gold, Json.Num(q, "reward") ?? 0));
            int? deadline = kind == QuestKinds.Protect ? w.Tick + World.TicksPerDay / 2 : (int?)null;
            var quest = w.Quests.TryOffer(w, giver.Id, kind, target, Ids.Item(w, Json.Str(q, "item")) ?? Json.Str(q, "item"), reward, Json.Str(q, "reason") ?? "", deadline, out string error, cause);
            if (quest == null) brain.Reject(giver.Id, task, "quest: " + error, cause);
            else brain.Emit("quest", giver.Id, quest.TargetId, quest.Reason, entry: quest.EntryId);
        }
    }

    // =====================================================================================

    /// <summary>Two villagers meet: one call writes the whole exchange, and what it changes (facts told, lies, feelings, a pact).</summary>
    public sealed class ConverseJob : CognitionJob
    {
        private readonly int? _cause;

        public ConverseJob(string a, string b, int? cause, int priority)
            : base("converse", "converse|" + (string.CompareOrdinal(a, b) < 0 ? a + "|" + b : b + "|" + a), priority, a, b)
        {
            _cause = cause;
        }

        internal override bool StillRelevant(Brain brain)
        {
            var a = brain.World.FindAgent(AgentId);
            var b = brain.World.FindAgent(TargetId);
            return a != null && b != null && a.Active && b.Active;
        }

        internal override LlmRequest? Build(Brain brain)
        {
            if (brain.PairCooling(AgentId!, TargetId!) && _cause == null) return null;
            if (_cause != null && brain.TalkedWithin(AgentId!, TargetId!, 2 * World.TicksPerHour)) return null;
            brain.CoolPair(AgentId!, TargetId!);
            var w = brain.World;
            var a = w.GetAgent(AgentId!);
            var b = w.GetAgent(TargetId!);
            var p = brain.Prompts;
            var place = p.PlaceOf(a);
            string note = _cause.HasValue ? w.Journal.Get(_cause.Value).Text : "";
            var user = new StringBuilder()
                .Append(p.Clock()).Append($" {a.Name} [{a.Id}] and {b.Name} [{b.Id}] meet at {(place != null ? place.Name : "the road")}.")
                .Append(note.Length > 0 ? $" ({note})" : "").Append("\n\n");
            foreach (var (self, other, prefix) in new[] { (a, b, "a"), (b, a, "b") })
            {
                if (self.IsPlayer)
                {
                    // the player's mind is theirs: no persona, no memories, and nobody speaks for them
                    user.Append($"=== THE TRAVELLER [{self.Id}] (the player) ===\nA traveller new to the valley. Only the player decides what the traveller says.\n\n");
                    continue;
                }
                user.Append($"=== {self.Name.ToUpperInvariant()} ===\n").Append(p.Persona(self))
                    .Append(p.State(self, brain.StateOf(self.Id)))
                    .Append($"{self.Name} {PromptBuilder.OpinionWord(self.Mind.OpinionOf(other.Id))} {other.Name}.\n")
                    .Append(p.Memories(self, Handles, prefix, $"WHAT {self.Name.ToUpperInvariant()} KNOWS (only {self.Name} can tell these)"))
                    .Append(p.Talks(brain.StateOf(self.Id), other.Id)).Append('\n');
            }
            // nobody can hear this one: ask only for what it changes (much cheaper than writing every line)
            _withPlayer = a.IsPlayer || b.IsPlayer;
            _brief = !_withPlayer && !brain.NearPlayer(a) && !brain.NearPlayer(b);
            var npc = a.IsPlayer ? b : a;
            user.Append(p.People(npc, PromptBuilder.Relevant(a, b)))
                .Append(_withPlayer
                    ? $"\nOnly {npc.Name} [{npc.Id}] speaks: 1 or 2 lines addressed to the traveller, in character. You must never write lines for the traveller. "
                    : _brief
                    ? "\nBRIEF: nobody overhears this conversation. Do not write the dialogue and do not include a \"lines\" field; only say what it changes. "
                    : "\nWrite their conversation as it really happens, in character: gossip, favours, quarrels, scheming, flirting, warnings — whatever these two would say now. ")
                .Append("They only share facts they know (their own handles). Someone may lie on purpose if it fits them.\n")
                .Append(_brief ? "JSON schema: {" : "JSON schema: {\"lines\": [{\"speaker\": person id, \"text\": string}] (2 to 5 lines), ")
                .Append("\"shared\": [{\"from\": person id, \"memory\": a handle such as a1 or b2 from that person's list — never free text}] (facts actually told), ")
                .Append($"\"lies\": [{{\"from\": person id, \"deed\": one of {Deeds(w)}, \"actor\": person id, \"target\": person id|null, \"item\": item id|null}}], ")
                .Append("\"opinion_changes\": [{\"who\": person id, \"about\": person id, \"delta\": number from -0.2 to 0.2, \"why\": string}], ")
                .Append("\"agreement\": null or {\"who\": person id, \"time\": \"HH:MM\", \"verb\": string, \"target\": string|null, \"item\": string|null, \"note\": string} (something one of them commits to do later today), ")
                .Append("\"summary\": string (one sentence, third person)}\n").Append(PromptBuilder.VerbGuide);
            return new LlmRequest(Task, p.Rules + "\n" + p.Setting, user.ToString(), _brief ? 350 : 800);
        }

        private bool _brief;
        private bool _withPlayer;

        internal override bool Apply(Brain brain, JsonElement root)
        {
            var w = brain.World;
            var a = w.GetAgent(AgentId!);
            var b = w.GetAgent(TargetId!);
            var lines = new List<(Agent Speaker, string Text)>();
            foreach (var l in Json.Arr(root, "lines").Take(6))
            {
                string? speaker = Ids.Agent(w, Json.Str(l, "speaker")) ?? Json.Str(l, "speaker");
                string? text = Json.Str(l, "text");
                if (text == null) continue;
                var who = speaker == b.Id ? b : speaker == a.Id ? a : null;
                if (who == null) { brain.Reject(a.Id, Task, $"line by '{speaker}' who is not in this conversation", _cause); continue; }
                if (who.IsPlayer) { brain.Reject(a.Id, Task, "a line was written for the traveller: only the player speaks for the traveller", _cause); continue; }
                if (_brief) continue; // nobody hears it: the lines are not shown
                lines.Add((who, text));
            }
            if (lines.Count == 0 && (!_brief || Json.Str(root, "summary") == null)) return false;
            string summary = Json.Str(root, "summary") ?? $"{a.Name} and {b.Name} talk.";
            int talk = w.Journal.Add(w.Tick, "talk", a.Id, $"{a.Name} and {b.Name}: {summary}", _cause, b.Id);
            for (int i = 0; i < lines.Count; i++)
            {
                var (speaker, text) = lines[i];
                var listener = speaker == a ? b : a;
                brain.Emit("say", speaker.Id, listener.Id, text, i, entry: talk);
                brain.StateOf(a.Id).AddTalk(b.Id, $"{speaker.Name}: {text}", 8);
                brain.StateOf(b.Id).AddTalk(a.Id, $"{speaker.Name}: {text}", 8);
            }

            foreach (var s in Json.Arr(root, "shared").Take(4))
            {
                var from = Pick(w, a, b, Json.Str(s, "from"));
                if (from == null) continue;
                var to = from == a ? b : a;
                if (!Handles.TryResolve(Json.Str(s, "memory"), from.Id, out string key)) { brain.Reject(from.Id, Task, $"{from.Name} cannot tell '{Json.Str(s, "memory")}': not something {from.Name} knows", talk); continue; }
                Knowledge.Tell(w, from, to, key, talk);
            }
            foreach (var l in Json.Arr(root, "lies").Take(2))
            {
                var liar = Pick(w, a, b, Json.Str(l, "from"));
                if (liar == null) continue;
                var dupe = liar == a ? b : a;
                if (Knowledge.Lie(w, liar, dupe, Json.Str(l, "deed") ?? "", Ids.Agent(w, Json.Str(l, "actor")) ?? "", Ids.Agent(w, Json.Str(l, "target")), Ids.Item(w, Json.Str(l, "item")), talk) < 0)
                    brain.Reject(liar.Id, Task, "lie about unknown deed, person or item", talk);
            }
            foreach (var c in Json.Arr(root, "opinion_changes").Take(4))
            {
                var holder = Pick(w, a, b, Json.Str(c, "who"));
                string? about = Json.Str(c, "about");
                float? delta = Json.Num(c, "delta");
                if (holder == null || about == null || delta == null) continue;
                Arbiter.ShiftOpinion(w, holder, about, delta.Value, 0.2f, Json.Str(c, "why"), talk);
            }
            var agreement = Json.Obj(root, "agreement");
            if (agreement != null)
            {
                var who = Pick(w, a, b, Json.Str(agreement.Value, "who"));
                if (who != null) AddToPlan(brain, who, agreement.Value, talk, Task);
            }
            return true;
        }

        internal override void Fallback(Brain brain)
        {
            var w = brain.World;
            var a = w.GetAgent(AgentId!);
            var b = w.GetAgent(TargetId!);
            brain.CoolPair(a.Id, b.Id);
            string greet = w.Pack.Bark("greet", w.Random) ?? "Good day.";
            brain.Emit("say", a.Id, b.Id, greet, 0);
        }

        private static Agent? Pick(World w, Agent a, Agent b, string? raw)
        {
            string? id = Ids.Agent(w, raw) ?? raw;
            var who = id == a.Id ? a : id == b.Id ? b : null;
            return who != null && who.IsPlayer ? null : who; // a model never acts, tells, lies or feels on the player's behalf
        }

        /// <summary>A commitment made in conversation becomes a real step in today's plan (if legal).</summary>
        internal static void AddToPlan(Brain brain, Agent who, JsonElement stepJson, int? cause, string task)
        {
            var w = brain.World;
            var step = Arbiter.Step(w, who, stepJson, out string error, $"{w.Hour:00}:{w.MinuteOfDay % 60:00}");
            if (step == null) { brain.Reject(who.Id, task, "agreement: " + error, cause); return; }
            var steps = who.Plan != null && who.Plan.Day == w.Day ? new List<PlanStep>(who.Plan.Steps) : new List<PlanStep>();
            steps.Add(step);
            int entry = w.Journal.Add(w.Tick, "plan", who.Id, $"{who.Name} commits to: {step}", cause);
            who.Plan = new Plan(who.Plan?.Intention ?? "Keep my word", w.Day, steps, entry);
            brain.Emit("plan", who.Id, step.TargetId, $"will {step.Verb} {w.NameOf(step.TargetId ?? step.ItemId)}" + (step.Note != null ? $" — {step.Note}" : ""), entry: entry);
        }
    }

    // =====================================================================================

    /// <summary>The player speaks freely to an NPC. The NPC answers as a person with its own knowledge and interests, and may act.</summary>
    public sealed class DialogueJob : CognitionJob
    {
        private readonly string _text;
        private readonly int _ticket;
        private readonly IReadOnlyList<string> _facts;

        public DialogueJob(string npcId, string text, int ticket, IReadOnlyList<string>? facts = null) : base("dialogue", "dialogue|" + npcId + "|" + ticket, 0, npcId, null)
        {
            _text = text;
            _ticket = ticket;
            _facts = facts ?? new List<string>();
        }

        internal override LlmRequest? Build(Brain brain)
        {
            var w = brain.World;
            var a = w.GetAgent(AgentId!);
            string player = brain.PlayerId ?? "player";
            var s = brain.StateOf(a.Id);
            var p = brain.Prompts;
            var open = w.Quests.All.Where(q => q.GiverId == a.Id && (q.Status == QuestStatus.Offered || q.Status == QuestStatus.Active))
                .Select(q => $"- {q.Id}: {q.Kind} {w.NameOf(q.TargetId)}{(q.ItemId != null ? " (" + w.NameOf(q.ItemId) + ")" : "")}, reward {q.Reward}, {q.Status.ToString().ToLowerInvariant()}: {q.Reason}").ToList();
            var user = new StringBuilder()
                .Append(p.Persona(a)).Append('\n')
                .Append(p.Clock()).Append(' ').Append(p.State(a, s)).Append('\n')
                .Append(p.People(a, PromptBuilder.Relevant(a))).Append(p.Items())
                .Append(p.Memories(a, Handles, "m", "WHAT YOU KNOW")).Append('\n')
                .Append(open.Count > 0 ? "Requests you made to the traveller:\n" + string.Join("\n", open) + "\n" : "")
                .Append(p.Talks(s, player))
                .Append($"\nThe traveller [{player}] says to you: \"{_text.Replace('"', '\'')}\"\n")
                .Append(_facts.Count > 0 ? "WHAT THE TRAVELLER ACTUALLY DID just now (checked by the world — this is the truth, react to it):\n- " + string.Join("\n- ", _facts) + "\n" : "")
                .Append('\n')
                .Append("Answer as this person truly would. You are not a helpful assistant: you have interests, fears and pride. ")
                .Append("You may refuse, bargain, lie, get angry, ask for something in return, or open up if you trust them. Only share facts you know (your handles).\n")
                .Append("JSON schema: {\"reply\": string, \"emotion\": \"happy|angry|afraid|sad|neutral|surprised|love|worried\", \"actions\": [...]}\n")
                .Append("Possible actions (0 to 3): {\"type\": \"share\", \"memory\": a handle like m1 from WHAT YOU KNOW} tell them something you know; ")
                .Append($"{{\"type\": \"lie\", \"deed\": one of {Deeds(w)}, \"actor\": person id, \"target\": person id|null, \"item\": item id|null}}; ")
                .Append("{\"type\": \"give\", \"item\": item you own}; {\"type\": \"opinion\", \"delta\": -0.15 to 0.15, \"why\": string} how this exchange changes your view of them; ")
                .Append($"{{\"type\": \"offer_quest\", \"kind\": \"{string.Join("|", QuestKinds.All)}\", \"target\": person id, \"item\": item id|null, \"reward\": gold (0 to {a.Gold}), \"reason\": string}}; ")
                .Append("{\"type\": \"agree\", \"time\": \"HH:MM\", \"verb\": string, \"target\": string|null, \"item\": string|null, \"note\": string} you commit to do something; ")
                .Append("{\"type\": \"call_guard\"} you report them for a crime you know they did; {\"type\": \"attack\"} only if enraged; {\"type\": \"end\"} you walk away; ")
                .Append($"{{\"type\": \"follow\", \"hours\": 1 to 8}} you agree to go along with the traveller; {{\"type\": \"give_gold\", \"amount\": number}} you pay the traveller (you have {a.Gold}).\n")
                .Append(PromptBuilder.VerbGuide);
            return new LlmRequest(Task, p.Rules + "\n" + p.Setting, user.ToString(), 600);
        }

        internal override bool Apply(Brain brain, JsonElement root)
        {
            var w = brain.World;
            var a = w.GetAgent(AgentId!);
            string? reply = Json.Str(root, "reply");
            if (reply == null) return false;
            string player = brain.PlayerId ?? "player";
            var hero = w.FindAgent(player);
            int said = w.Journal.Add(w.Tick, "said", a.Id, $"{a.Name} to {w.NameOf(player)}: \"{reply}\" (asked: \"{_text}\")", null, player);
            var s = brain.StateOf(a.Id);
            s.AddTalk(player, $"Traveller: {_text}", 10);
            s.AddTalk(player, $"{a.Name}: {reply}", 10);
            brain.Emit("reply", a.Id, player, reply, emotion: Json.Str(root, "emotion"), entry: said, ticket: _ticket);

            foreach (var act in Json.Arr(root, "actions").Take(3))
            {
                string type = Json.Str(act, "type") ?? "";
                switch (type)
                {
                    case "share":
                        if (hero == null) break;
                        if (Handles.TryResolve(Json.Str(act, "memory"), a.Id, out string key)) Knowledge.Tell(w, a, hero, key, said);
                        else brain.Reject(a.Id, Task, $"{a.Name} cannot share '{Json.Str(act, "memory")}': not something they know", said);
                        break;
                    case "lie":
                        if (hero == null) break;
                        if (Knowledge.Lie(w, a, hero, Json.Str(act, "deed") ?? "", Ids.Agent(w, Json.Str(act, "actor")) ?? "", Ids.Agent(w, Json.Str(act, "target")), Ids.Item(w, Json.Str(act, "item")), said) < 0)
                            brain.Reject(a.Id, Task, "lie about unknown deed, person or item", said);
                        break;
                    case "give":
                        if (hero == null) break;
                        if (Actions.Give(w, a, hero, Ids.Item(w, Json.Str(act, "item")) ?? Json.Str(act, "item")) < 0) brain.Reject(a.Id, Task, $"give: {a.Name} does not own '{Json.Str(act, "item")}'", said);
                        break;
                    case "opinion":
                        float? delta = Json.Num(act, "delta");
                        if (delta != null) Arbiter.ShiftOpinion(w, a, player, delta.Value, brain.Options.MaxDialogueOpinionShift, Json.Str(act, "why"), said);
                        break;
                    case "offer_quest":
                        ReflectJob.OfferQuest(brain, a, act, said, Task);
                        break;
                    case "agree":
                        ConverseJob.AddToPlan(brain, a, act, said, Task);
                        break;
                    case "follow":
                        if (hero == null) break;
                        int hours = (int)System.Math.Max(1, System.Math.Min(8, Json.Num(act, "hours") ?? 3));
                        Companions.Follow(w, a, hero, hours * World.TicksPerHour, said);
                        brain.Emit("follow", a.Id, player, a.Name, entry: said);
                        break;
                    case "give_gold":
                        if (hero == null) break;
                        int amount = (int)(Json.Num(act, "amount") ?? 0);
                        if (amount <= 0 || amount > a.Gold) { brain.Reject(a.Id, Task, $"give_gold: {a.Name} does not have {amount} gold", said); break; }
                        a.Gold -= amount;
                        hero.Gold += amount;
                        w.Journal.Add(w.Tick, "deed", a.Id, $"{a.Name} pay -> {hero.Name} ({amount} gold)", said, hero.Id);
                        brain.Emit("gold", a.Id, player, amount.ToString(CultureInfo.InvariantCulture), entry: said);
                        break;
                    case "call_guard":
                        CallGuard(brain, a, player, said);
                        break;
                    case "attack":
                        if (hero != null && Arbiter.MayAttack(a, hero)) Combat.Attack(w, a, hero, w.Tuning.AttackDamage);
                        else brain.Reject(a.Id, Task, $"attack: {a.Name} is not angry enough to strike", said);
                        break;
                    case "end":
                        brain.Emit("end", a.Id, player, "", ticket: _ticket);
                        break;
                }
            }
            return true;
        }

        private void CallGuard(Brain brain, Agent a, string player, int said)
        {
            var w = brain.World;
            var crime = a.Mind.CrimeBy(player, w.Tuning.MinCrimeConfidence);
            var authority = w.NearestWithTag(Tags.Authority, a.Position, a.Id);
            if (crime == null || authority == null) { brain.Reject(a.Id, Task, "call_guard: no known crime by the traveller, or no guard", said); return; }
            a.Intent = new Intent(IntentKind.Report, authority.Id, crime.Key, w.Tick + w.Tuning.PursuitTicks, said);
            brain.Emit("thought", a.Id, authority.Id, $"I'm fetching {authority.Name}.", emotion: "angry", entry: said);
        }

        internal override void Fallback(Brain brain)
        {
            var w = brain.World;
            var a = w.GetAgent(AgentId!);
            string player = brain.PlayerId ?? "player";
            float o = a.Mind.OpinionOf(player);
            string key = o <= Commerce.RefuseBelow ? "dialogue_hostile" : o < -0.2f ? "dialogue_cold" : o > 0.3f ? "dialogue_warm" : "dialogue_neutral";
            string reply = w.Pack.Bark(key, w.Random) ?? (o <= Commerce.RefuseBelow ? "Leave me be." : o < -0.2f ? "What do you want?" : o > 0.3f ? "Good to see you, friend." : "Yes?");
            var hero = w.FindAgent(player);
            if (o > 0.3f && hero != null)
            {
                var news = a.Mind.Memories.Where(m => !hero.Mind.Remembers(m.Key) && m.ActorId != player).OrderByDescending(m => m.Salience).FirstOrDefault();
                if (news != null)
                {
                    Knowledge.Tell(w, a, hero, news.Key, null);
                    reply += $" Did you hear? {Knowledge.Describe(w, news)}.";
                }
            }
            int said = w.Journal.Add(w.Tick, "said", a.Id, $"{a.Name} to {w.NameOf(player)}: \"{reply}\"", null, player);
            brain.Emit("reply", a.Id, player, reply, entry: said, ticket: _ticket);
        }
    }

    // =====================================================================================

    /// <summary>The story director: reads the tensions of the world and may start an event that follows from them.</summary>
    public sealed class DirectorJob : CognitionJob
    {
        public DirectorJob() : base("director", "director", 2, null, null) { }

        internal override LlmRequest? Build(Brain brain)
        {
            var w = brain.World;
            brain.DirectorRan();
            var p = brain.Prompts;
            var recent = Highlights(w, w.Tick - 12 * World.TicksPerHour, 40);
            var tensions = new List<string>();
            foreach (var a in w.Agents.Where(x => x.Active && !x.IsPlayer))
                foreach (var b in w.Agents.Where(x => x.Id != a.Id && x.Present))
                {
                    float o = a.Mind.OpinionOf(b.Id);
                    if (o <= -0.35f || o >= 0.6f) tensions.Add($"{a.Name} {PromptBuilder.OpinionWord(o)} {b.Name} ({o:+0.00;-0.00})");
                }
            var last = w.Events.History.LastOrDefault();
            var reserve = w.Agents.Where(a => !a.Present && a.IsAlive).ToList();
            var user = new StringBuilder()
                .Append("You are the story director of this world. Your job: make the players' story dramatic, surprising and coherent — events should follow from what is going on (grudges, crimes, fear, joy), not come from nowhere. Doing nothing is often right.\n")
                .Append(p.Clock()).Append('\n')
                .Append("Recent happenings:\n").Append(recent.Count > 0 ? string.Join("\n", recent) : "(quiet)").Append('\n')
                .Append("Tensions and bonds:\n").Append(tensions.Count > 0 ? string.Join("\n", tensions.Take(20)) : "(none strong)").Append('\n')
                .Append(last != null ? $"Last event: {last.Kind} at {World.Clock(last.StartTick)}.\n" : "No event yet.\n")
                .Append(p.Places())
                .Append("Villagers: ").Append(string.Join(", ", w.Agents.Where(a => a.Active && !a.IsPlayer && !a.Has(WorldEvents.HostileTag)).Select(a => $"[{a.Id}] {a.Name}"))).Append('\n')
                .Append($"Waiting in the wings: {(reserve.Count > 0 ? string.Join(", ", reserve.Select(a => a.Has(WorldEvents.HostileTag) ? a.Name + " (bandit)" : a.Name + " (stranger)")) : "nobody")}\n")
                .Append("Events you can start: festival (where: place; everyone gathers), storm (where: null; everyone shelters at home), ")
                .Append("bandit_raid (where: place; bandits come to steal — only if bandits are waiting), stranger_arrives (where: place; only if a stranger is waiting), illness (where: villager id; they fall sick).\n")
                .Append("JSON schema: {\"event\": null or {\"kind\": string, \"where\": string|null, \"duration_hours\": 1 to 6, \"reason\": string (why now, for the designers), \"announcement\": string (one evocative sentence shown to the player)}}");
            return new LlmRequest(Task, p.Rules + "\n" + p.Setting, user.ToString(), 400, 0.9f);
        }

        internal override bool Apply(Brain brain, JsonElement root)
        {
            var w = brain.World;
            var ev = Json.Obj(root, "event");
            if (ev == null) return true; // choosing nothing is a valid answer
            var last = w.Events.History.LastOrDefault();
            if (last != null && w.Tick - last.StartTick < brain.Options.DirectorMinGapHours * World.TicksPerHour)
            {
                brain.Reject(null, Task, $"too soon after the last event ({last.Kind})", null);
                return true;
            }
            string kind = Json.Str(ev.Value, "kind") ?? "";
            int hours = (int)System.Math.Max(1, System.Math.Min(6, Json.Num(ev.Value, "duration_hours") ?? 2));
            string reason = Json.Str(ev.Value, "reason") ?? "";
            string? where = Json.Str(ev.Value, "where");
            where = (kind == WorldEvents.Illness ? Ids.Agent(w, where) : Ids.Place(w, where)) ?? where;
            var started = WorldEvents.TryStart(w, kind, where, hours * World.TicksPerHour, reason, null, out string error);
            if (started == null) { brain.Reject(null, Task, error, null); return true; }
            brain.Emit("event", null, started.WhereId, Json.Str(ev.Value, "announcement") ?? reason, entry: started.EntryId);
            return true;
        }

        internal override void Fallback(Brain brain)
        {
            var w = brain.World;
            var last = w.Events.History.LastOrDefault();
            if (last != null && w.Tick - last.StartTick < brain.Options.DirectorMinGapHours * World.TicksPerHour) return;
            if (brain.NextRandom(2) == 0) return;
            var options = new List<(string Kind, string? Where)>();
            var square = w.Places.FirstOrDefault(pl => pl.Has("market")) ?? w.Places.FirstOrDefault();
            if (square != null) options.Add((WorldEvents.Festival, square.Id));
            options.Add((WorldEvents.Storm, null));
            if (square != null && w.Agents.Any(a => !a.Present && a.IsAlive && a.Has(WorldEvents.HostileTag))) options.Add((WorldEvents.BanditRaid, square.Id));
            var pick = options[brain.NextRandom(options.Count)];
            var ev = WorldEvents.TryStart(w, pick.Kind, pick.Where, 2 * World.TicksPerHour, "rule director", null, out _);
            if (ev != null) brain.Emit("event", null, ev.WhereId, $"A {ev.Kind.Replace('_', ' ')} begins.", entry: ev.EntryId);
        }

        internal static List<string> Highlights(World w, int sinceTick, int max)
        {
            var kinds = new HashSet<string> { "deed", "death", "quest", "event", "lie", "talk", "said", "plan", "report", "consequence", "arrival", "departure" };
            var list = new List<string>();
            foreach (var e in w.Journal.Entries)
            {
                if (e.Tick < sinceTick || !kinds.Contains(e.Kind)) continue;
                list.Add($"{World.Clock(e.Tick)} {e.Text}" + (e.Kind == "lie" ? " (a lie)" : ""));
            }
            return list.Count > max ? list.Skip(list.Count - max).ToList() : list;
        }
    }

    // =====================================================================================

    /// <summary>End of day: a storyteller turns the journal into a short chronicle (never inventing events).</summary>
    public sealed class ChronicleJob : CognitionJob
    {
        private readonly int _day;

        public ChronicleJob(int day) : base("chronicle", "chronicle|" + day, 5, null, null) { _day = day; }

        internal override LlmRequest? Build(Brain brain)
        {
            var w = brain.World;
            var lines = DirectorJob.Highlights(w, (_day - 1) * World.TicksPerDay, 80).Where(l => l.StartsWith($"D{_day} ")).ToList();
            if (lines.Count == 0) return null;
            var user = new StringBuilder()
                .Append($"Here is what truly happened on day {_day} (the journal; entries marked 'a lie' were lies told by someone):\n")
                .Append(string.Join("\n", lines)).Append("\n\n")
                .Append($"Write the chronicle of day {_day} as the village storyteller would tell it by the fire: a title and 2 or 3 short paragraphs (at most 60 words each), past tense, using people's names; keep only the most dramatic threads. ")
                .Append("Only tell what is in the journal; you may hint at secrets and lies. No he/she: use names or 'they'.\n")
                .Append("JSON schema: {\"title\": string, \"paragraphs\": [string]}");
            return new LlmRequest(Task, brain.Prompts.Rules + "\n" + brain.Prompts.Setting, user.ToString(), 900, 0.9f);
        }

        internal override bool Apply(Brain brain, JsonElement root)
        {
            string? title = Json.Str(root, "title");
            var paragraphs = Json.Strings(root, "paragraphs").ToList();
            if (title == null || paragraphs.Count == 0) return false;
            string text = title + "\n\n" + string.Join("\n\n", paragraphs);
            int entry = brain.World.Journal.Add(brain.World.Tick, "chronicle", null, $"Chronicle of day {_day}: {title}");
            brain.Emit("chronicle", null, null, text, entry: entry);
            return true;
        }

        internal override void Fallback(Brain brain)
        {
            var w = brain.World;
            var kinds = new HashSet<string> { "death", "quest", "event" };
            var lines = w.Journal.Entries.Where(e => World.DayOf(e.Tick) == _day && (kinds.Contains(e.Kind) || (e.Kind == "deed" && e.Text.Contains("steal")))).Select(e => "• " + e.Text).Take(12).ToList();
            string text = $"Day {_day} in the valley\n\n" + (lines.Count > 0 ? string.Join("\n", lines) : "A quiet day.");
            brain.Emit("chronicle", null, null, text);
        }
    }


    // =====================================================================================

    /// <summary>The end: what the valley will remember about the player, grounded in every villager's real opinion and memories.</summary>
    public sealed class EpilogueJob : CognitionJob
    {
        public EpilogueJob() : base("epilogue", "epilogue", 0, null, null) { }

        internal override LlmRequest? Build(Brain brain)
        {
            var w = brain.World;
            string? pid = brain.PlayerId;
            if (pid == null) return null;
            var views = new List<string>();
            foreach (var a in w.Agents.Where(x => !x.IsPlayer && !x.Has(WorldEvents.HostileTag) && x.Present))
            {
                float o = a.Mind.OpinionOf(pid);
                var known = a.Mind.Memories.Where(m => m.ActorId == pid).OrderByDescending(m => m.Salience).Take(3)
                    .Select(m => Knowledge.Describe(w, m) + (m.Firsthand ? " (saw it)" : $" (heard from {w.NameOf(m.SourceId)})")).ToList();
                views.Add($"- {a.Name} ({a.Profile.Role}){(a.IsAlive ? "" : " [dead]")}: {PromptBuilder.OpinionWord(o)} the traveller ({o.ToString("+0.00;-0.00;0.00", CultureInfo.InvariantCulture)})"
                    + (known.Count > 0 ? "; remembers: " + string.Join("; ", known) : ""));
            }
            var quests = w.Quests.All.Where(q => q.HeroId == pid)
                .Select(q => $"- {q.Status.ToString().ToLowerInvariant()}: {w.NameOf(q.GiverId)} asked to {q.Kind.Replace('_', ' ')} {w.NameOf(q.TargetId)} ({q.Reason})").ToList();
            var user = new StringBuilder()
                .Append($"The traveller [{pid}] is leaving Asagiri after {w.Day} day(s). What each villager truly thinks and remembers of the traveller:\n")
                .Append(string.Join("\n", views)).Append("\n\n")
                .Append(quests.Count > 0 ? "Requests the traveller took on:\n" + string.Join("\n", quests) + "\n\n" : "The traveller took on no requests.\n\n")
                .Append("The whole story of the valley (journal highlights):\n").Append(string.Join("\n", DirectorJob.Highlights(w, 0, 70))).Append("\n\n")
                .Append("Write the legend the villagers will tell about the traveller in years to come: a title, an epithet (a nickname such as 'the Thief in the Mist' or 'Friend of the Shrine'), and 3 short paragraphs (at most 60 words each). ")
                .Append("It must follow from what they really think and remember above: praise, fear, gossip, even lies. Never invent events. No he/she: say 'the traveller' or 'they'.\n")
                .Append("JSON schema: {\"title\": string, \"epithet\": string, \"paragraphs\": [string]}");
            return new LlmRequest(Task, brain.Prompts.Rules + "\n" + brain.Prompts.Setting, user.ToString(), 900, 0.9f);
        }

        internal override bool Apply(Brain brain, JsonElement root)
        {
            string? title = Json.Str(root, "title");
            var paragraphs = Json.Strings(root, "paragraphs").ToList();
            if (title == null || paragraphs.Count == 0) return false;
            string epithet = Json.Str(root, "epithet") ?? "the Traveller";
            brain.World.Journal.Add(brain.World.Tick, "chronicle", brain.PlayerId, $"Epilogue: {title} — {epithet}");
            brain.Emit("epilogue", brain.PlayerId, null, title + "\n" + epithet + "\n\n" + string.Join("\n\n", paragraphs));
            return true;
        }

        internal override void Fallback(Brain brain)
        {
            var w = brain.World;
            string? pid = brain.PlayerId;
            if (pid == null) return;
            var fans = w.Agents.Where(a => !a.IsPlayer && a.Mind.OpinionOf(pid) > 0.3f).Select(a => a.Name).ToList();
            var foes = w.Agents.Where(a => !a.IsPlayer && a.Mind.OpinionOf(pid) < -0.3f).Select(a => a.Name).ToList();
            string epithet = foes.Count > fans.Count ? "the Unwelcome" : fans.Count > 0 ? "the Friend of Asagiri" : "the Passing Stranger";
            string text = $"The Traveller\n{epithet}\n\n"
                + (fans.Count > 0 ? $"Remembered fondly by {string.Join(", ", fans)}. " : "")
                + (foes.Count > 0 ? $"Cursed by {string.Join(", ", foes)}." : "");
            brain.Emit("epilogue", pid, null, text);
        }
    }
}
