using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Kinloom.Llm;
using Kinloom.Core;

namespace Kinloom.Brain
{
    /// <summary>The slow, thinking layer of a Kinloom world. Call Update() after each simulation step (or every frame):
    /// it turns journal entries and the clock into cognition jobs, runs them on the LLM without blocking,
    /// passes the answers through the Arbiter and applies them to the world. Without a client, rules take over.</summary>
    public sealed class Brain
    {
        private readonly List<CognitionJob> _queue = new List<CognitionJob>();
        private readonly List<(CognitionJob Job, Task<LlmResponse> Call)> _inFlight = new List<(CognitionJob, Task<LlmResponse>)>();
        private readonly HashSet<string> _pending = new HashSet<string>();
        private readonly Dictionary<string, AgentState> _states = new Dictionary<string, AgentState>();
        private readonly Dictionary<string, int> _pairCooldown = new Dictionary<string, int>();
        private readonly List<BrainEvent> _events = new List<BrainEvent>();
        private readonly Random _random;
        private int _journalRead;
        private int _lastTick = -1;
        private int _nextTicket = 1;
        private int _lastDirectorTick;
        private int _lastChronicleDay;
        private int _budgetHour = -1;
        private long _budgetUsed;
        private long _sequence;
        private int _ambientHour = -1;
        private int _ambientThisHour;

        public Brain(Simulation sim, ILlmClient? client, BrainOptions? options = null)
        {
            Sim = sim;
            Client = client;
            Options = options ?? new BrainOptions();
            Prompts = new PromptBuilder(sim, Options);
            _random = new Random(Options.Seed);
            _journalRead = sim.World.Journal.Entries.Count;
            _lastDirectorTick = sim.World.Tick;
        }

        public Simulation Sim { get; }
        public World World => Sim.World;
        public ILlmClient? Client { get; }
        public BrainOptions Options { get; }
        public PromptBuilder Prompts { get; }
        public BrainStats Stats { get; } = new BrainStats();
        public bool Enabled => Client != null;
        public int InFlight => _inFlight.Count;
        public int Queued => _queue.Count;
        public string? PlayerId => Sim.Player?.Id;

        public AgentState StateOf(string agentId)
        {
            if (!_states.TryGetValue(agentId, out var s)) _states[agentId] = s = new AgentState();
            return s;
        }

        /// <summary>Takes the events produced since the last call (the host displays them).</summary>
        public List<BrainEvent> DrainEvents()
        {
            var list = new List<BrainEvent>(_events);
            _events.Clear();
            return list;
        }

        /// <summary>The player says something to an NPC. The answer arrives later as a "reply" event with this ticket.</summary>
        public int Talk(string npcId, string text)
        {
            int ticket = _nextTicket++;
            Enqueue(new IntentJob(npcId, text, ticket)); // what the words do first, then the answer
            if (Options.Lockstep) Update();
            return ticket;
        }

        /// <summary>Asks the story director to consider an event now (it may choose nothing).</summary>
        public void RequestDirector() => Enqueue(new DirectorJob());

        /// <summary>End of the story: the legend the village will tell about the player, from what each villager really thinks.</summary>
        public void RequestEpilogue() => Enqueue(new EpilogueJob());

        /// <summary>Asks for the chronicle of a day (default: today so far).</summary>
        public void RequestChronicle(int? day = null) => Enqueue(new ChronicleJob(day ?? World.Day));

        public void Update()
        {
            Harvest();
            ScanJournal();
            if (World.Tick != _lastTick)
            {
                _lastTick = World.Tick;
                ClockTriggers();
                AmbientConversations();
            }
            Dispatch();
            while (Options.Lockstep && (_inFlight.Count > 0 || _queue.Count > 0))
            {
                if (_inFlight.Count > 0) Task.WaitAll(_inFlight.Select(f => (Task)f.Call).ToArray());
                Harvest();
                ScanJournal();
                Dispatch();
            }
        }

        /// <summary>Waits for every running job and applies it (for headless runs and tests).</summary>
        public void Flush()
        {
            bool lockstep = Options.Lockstep;
            Options.Lockstep = true;
            try { Update(); }
            finally { Options.Lockstep = lockstep; }
        }

        // ---------- plumbing used by jobs ----------

        internal void Emit(BrainEvent e) => _events.Add(e);

        internal void Emit(string kind, string? agentId, string? targetId, string text, int order = 0, string? emotion = null, int? entry = null, int? ticket = null) =>
            _events.Add(new BrainEvent(kind, agentId, targetId, text, World.Tick, order, emotion, entry, ticket));

        internal void Reject(string? agentId, string task, string reason, int? cause)
        {
            Stats.Rejections++;
            int entry = World.Journal.Add(World.Tick, "rejected", agentId, $"Arbiter refused ({task}): {reason}", cause);
            Emit("rejected", agentId, null, reason, entry: entry);
        }

        internal void Enqueue(CognitionJob job)
        {
            if (!_pending.Add(job.Key)) return;
            job.Sequence = _sequence++;
            _queue.Add(job);
        }

        internal bool IsCognitive(Agent a) => !a.IsPlayer && a.Active && !a.Has(WorldEvents.HostileTag);

        // ---------- scheduling ----------

        private void Dispatch()
        {
            if (_queue.Count == 0) return;
            _queue.Sort((a, b) => a.Priority != b.Priority ? a.Priority.CompareTo(b.Priority) : a.Sequence.CompareTo(b.Sequence));
            int hour = World.Tick / World.TicksPerHour;
            if (hour != _budgetHour) { _budgetHour = hour; _budgetUsed = 0; }

            while (_queue.Count > 0 && _inFlight.Count < Math.Max(1, Options.MaxConcurrent))
            {
                var job = _queue[0];
                _queue.RemoveAt(0);
                if (!job.StillRelevant(this)) { _pending.Remove(job.Key); continue; }
                bool overBudget = Options.TokensPerGameHour > 0 && _budgetUsed >= Options.TokensPerGameHour && job.Priority > 0;
                if (Client == null || overBudget)
                {
                    Stats.Fallbacks++;
                    job.Fallback(this);
                    _pending.Remove(job.Key);
                    continue;
                }
                var request = job.Build(this);
                if (request == null) { _pending.Remove(job.Key); continue; }
                if (job.AgentId != null) Emit("thinking", job.AgentId, job.TargetId, job.Task);
                _inFlight.Add((job, Client.CompleteAsync(request)));
            }
        }

        private void Harvest()
        {
            for (int i = 0; i < _inFlight.Count; i++)
            {
                var (job, call) = _inFlight[i];
                if (!call.IsCompleted) continue;
                _inFlight.RemoveAt(i--);
                _pending.Remove(job.Key);
                var response = call.Status == TaskStatus.RanToCompletion ? call.Result : LlmResponse.Failure(call.Exception?.GetBaseException().Message ?? "cancelled");
                Stats.Calls++;
                Stats.CallsByTask[job.Task] = Stats.CallsByTask.TryGetValue(job.Task, out int n) ? n + 1 : 1;
                Stats.InputTokens += response.InputTokens;
                Stats.OutputTokens += response.OutputTokens;
                Stats.TotalLatencyMs += response.LatencyMs;
                Stats.CachedInputTokens += response.CachedInputTokens;
                if (Options.Prices != null) Stats.Cost = (Stats.Cost ?? 0) + Options.Prices.CostOf(response.InputTokens, response.CachedInputTokens, response.OutputTokens);
                _budgetUsed += response.InputTokens + response.OutputTokens;

                bool applied = false;
                if (response.Ok)
                {
                    using var doc = Json.Parse(response.Text);
                    if (doc != null && job.StillRelevant(this))
                    {
                        try { applied = job.Apply(this, doc.RootElement); }
                        catch (Exception e) { Emit("error", job.AgentId, null, $"{job.Task}: {e.Message}"); }
                    }
                }
                if (!applied)
                {
                    Stats.Failures++;
                    if (!response.Ok) Emit("error", job.AgentId, null, $"{job.Task}: {response.Error}");
                    Stats.Fallbacks++;
                    if (job.StillRelevant(this)) job.Fallback(this);
                }
            }
        }

        // ---------- triggers ----------

        private void ScanJournal()
        {
            var entries = World.Journal.Entries;
            for (; _journalRead < entries.Count; _journalRead++)
            {
                var e = entries[_journalRead];
                switch (e.Kind)
                {
                    case "witness": Salience(e.AgentId, 1f, e.Id); break;
                    case "rumor": Salience(e.AgentId, 0.6f, e.Id); break;
                    case "tell":
                    case "lie": Salience(e.TargetId, 0.7f, e.Id); break;
                    case "consequence":
                    case "report": Salience(e.AgentId, 0.5f, e.Id); break;
                    case "quest": Salience(e.AgentId, 0.8f, e.Id); break;
                    case "death": Salience(e.TargetId, 1.5f, e.Id); if (World.Tick - _lastDirectorTick >= World.TicksPerHour * 2) Enqueue(new DirectorJob()); break;
                    case "meet":
                        if (e.AgentId != null && e.TargetId != null) Enqueue(new ConverseJob(e.AgentId, e.TargetId, e.Id, Priority(e.AgentId, e.TargetId)));
                        break;
                }
            }
        }

        private void Salience(string? agentId, float amount, int entryId)
        {
            var a = World.FindAgent(agentId);
            if (a == null || !IsCognitive(a)) return;
            var s = StateOf(a.Id);
            s.PendingSalience += amount;
            s.LastTriggerEntry = entryId;
            if (s.PendingSalience >= Options.ReflectThreshold && World.Tick - s.LastReflectTick >= Options.ReflectCooldownTicks)
                Enqueue(new ReflectJob(a.Id, NearPlayer(a) ? 1 : 3));
        }

        private void ClockTriggers()
        {
            if (World.Hour >= Options.PlanHour)
                foreach (var a in World.Agents)
                {
                    if (!IsCognitive(a)) continue;
                    var s = StateOf(a.Id);
                    if (s.LastPlanDay == World.Day) continue;
                    s.LastPlanDay = World.Day;
                    Enqueue(new DayPlanJob(a.Id, NearPlayer(a) ? 2 : 4));
                }
            if (World.Tick - _lastDirectorTick >= Options.DirectorEveryHours * World.TicksPerHour)
            {
                _lastDirectorTick = World.Tick;
                Enqueue(new DirectorJob());
            }
            if (World.Hour >= Options.ChronicleHour && _lastChronicleDay != World.Day)
            {
                _lastChronicleDay = World.Day;
                Enqueue(new ChronicleJob(World.Day));
            }
        }

        internal void DirectorRan() => _lastDirectorTick = World.Tick;

        private void AmbientConversations()
        {
            var agents = World.Agents;
            float radius = World.Tuning.TalkRadius * 1.5f;
            for (int i = 0; i < agents.Count; i++)
            {
                var a = agents[i];
                if (!IsCognitive(a) || a.Intent.Kind != IntentKind.Routine) continue;
                for (int j = i + 1; j < agents.Count; j++)
                {
                    var b = agents[j];
                    if (!IsCognitive(b) || b.Intent.Kind != IntentKind.Routine) continue;
                    if (a.Position.DistanceTo(b.Position) > radius) continue;
                    string pair = PairKey(a.Id, b.Id);
                    if (_pairCooldown.TryGetValue(pair, out int until) && World.Tick < until) continue;
                    float sociable = (a.Mind.Personality.Sociability + b.Mind.Personality.Sociability) / 2f;
                    if (_random.NextDouble() > Options.AmbientTalkChance * (0.5f + sociable)) continue;
                    int hour = World.Tick / World.TicksPerHour;
                    if (hour != _ambientHour) { _ambientHour = hour; _ambientThisHour = 0; }
                    if (_ambientThisHour >= Options.MaxAmbientTalksPerHour) return;
                    _ambientThisHour++;
                    Enqueue(new ConverseJob(a.Id, b.Id, null, Priority(a.Id, b.Id)));
                }
            }
        }

        internal void CoolPair(string a, string b)
        {
            _pairCooldown[PairKey(a, b)] = World.Tick + Options.PairTalkCooldownTicks;
            _lastTalk[PairKey(a, b)] = World.Tick;
        }

        /// <summary>Did these two already talk in the last <paramref name="ticks"/>? (planned meetings do not repeat a fresh talk)</summary>
        internal bool TalkedWithin(string a, string b, int ticks) => _lastTalk.TryGetValue(PairKey(a, b), out int at) && World.Tick - at < ticks;

        private readonly Dictionary<string, int> _lastTalk = new Dictionary<string, int>();

        internal bool PairCooling(string a, string b) => _pairCooldown.TryGetValue(PairKey(a, b), out int until) && World.Tick < until;

        private static string PairKey(string a, string b) => string.CompareOrdinal(a, b) < 0 ? a + "|" + b : b + "|" + a;

        private int Priority(string a, string b)
        {
            var x = World.FindAgent(a);
            var y = World.FindAgent(b);
            return (x != null && NearPlayer(x)) || (y != null && NearPlayer(y)) ? 1 : 3;
        }

        internal bool NearPlayer(Agent a)
        {
            var p = Sim.Player;
            return p != null && p.Position.DistanceTo(a.Position) <= World.Tuning.SightRadius * 1.5f;
        }

        internal int NextRandom(int max) => _random.Next(max);
    }
}
