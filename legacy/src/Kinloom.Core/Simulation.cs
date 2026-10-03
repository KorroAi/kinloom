using System.Collections.Generic;
using System.Linq;

namespace Kinloom.Core
{
    public sealed class PlayerCommand
    {
        public PlayerCommand(int tick, string action, string? placeId, string? deed, string? targetId, string? itemId, float price)
        {
            Tick = tick;
            Action = action;
            PlaceId = placeId;
            Deed = deed;
            TargetId = targetId;
            ItemId = itemId;
            Price = price;
        }

        public int Tick { get; }
        public string Action { get; }
        public string? PlaceId { get; }
        public string? Deed { get; }
        public string? TargetId { get; }
        public string? ItemId { get; }
        public float Price { get; }
    }

    public sealed class AgentFrame
    {
        public AgentFrame(string id, float x, float y, string intent, float fear, float anger, float opinionOfPlayer, string? bark)
        {
            Id = id;
            X = x;
            Y = y;
            Intent = intent;
            Fear = fear;
            Anger = anger;
            OpinionOfPlayer = opinionOfPlayer;
            Bark = bark;
        }

        public string Id { get; }
        public float X { get; }
        public float Y { get; }
        public string Intent { get; }
        public float Fear { get; }
        public float Anger { get; }
        public float OpinionOfPlayer { get; }
        public string? Bark { get; }
    }

    public sealed class Frame
    {
        public Frame(int tick) { Tick = tick; }
        public int Tick { get; }
        public List<AgentFrame> Agents { get; } = new List<AgentFrame>();
    }

    public sealed class TradeLog
    {
        public TradeLog(int tick, string traderId, string buyerId, TradeResult result)
        {
            Tick = tick;
            TraderId = traderId;
            BuyerId = buyerId;
            Result = result;
        }

        public int Tick { get; }
        public string TraderId { get; }
        public string BuyerId { get; }
        public TradeResult Result { get; }
    }

    public sealed class Simulation
    {
        private readonly List<PlayerCommand> _script;
        private readonly Dictionary<string, Vec2> _slotOffsets = new Dictionary<string, Vec2>();
        private int _next;
        private string? _destinationName;

        public Simulation(World world, IEnumerable<PlayerCommand> script)
        {
            World = world;
            _script = script.OrderBy(c => c.Tick).ToList();
            for (int i = 0; i < world.Agents.Count; i++)
            {
                var agent = world.Agents[i];
                if (agent.IsPlayer && Player == null) Player = agent;
                double angle = i * 2.39996; // golden angle: agents at the same place do not overlap
                _slotOffsets[agent.Id] = new Vec2((float)(System.Math.Cos(angle) * 1.2), (float)(System.Math.Sin(angle) * 1.2));
            }
        }

        public World World { get; }
        public Agent? Player { get; }
        public List<Frame> Frames { get; } = new List<Frame>();
        public List<TradeLog> Trades { get; } = new List<TradeLog>();
        public bool CaptureFrames { get; set; } = true;
        /// <summary>The host (a game engine) moves bodies and writes positions back; the simulation only decides destinations.</summary>
        public bool ExternalMovement { get; set; }

        /// <summary>Capture one frame every N ticks (1 = every tick). Bounds replay memory on long runs.</summary>
        public int FrameInterval
        {
            get => _frameInterval;
            set
            {
                if (value < 1) throw new System.ArgumentOutOfRangeException(nameof(value), "FrameInterval must be at least 1");
                _frameInterval = value;
            }
        }

        private int _frameInterval = 1;

        public void Run(int ticks)
        {
            for (int i = 0; i < ticks; i++) Step();
        }

        public void Step()
        {
            RunDueCommands();
            Recognize();
            ResolveIntents();
            ExecutePlans();
            if (!ExternalMovement) Move();
            Rumors.Spread(World);
            foreach (var agent in World.Agents)
            {
                agent.Mind.Emotions.Decay(World.Tuning.EmotionDecay);
                agent.Mind.DriftOpinions(World.Tuning.OpinionDrift);
            }
            Companions.Update(World);
            World.Quests.Check(World);
            WorldEvents.Update(World);
            if (CaptureFrames && World.Tick % _frameInterval == 0) Frames.Add(Capture());
            World.AdvanceTick();
        }

        private void RunDueCommands()
        {
            while (_next < _script.Count && _script[_next].Tick <= World.Tick)
            {
                var c = _script[_next++];
                if (Player == null) { Error(null, "Script command ignored: no player agent"); continue; }
                switch (c.Action)
                {
                    case "goto":
                        var place = World.FindPlace(c.PlaceId);
                        if (place == null) Error(Player.Id, $"Unknown place '{c.PlaceId}'");
                        else { Player.Destination = place.Position; _destinationName = place.Name; }
                        break;
                    case "deed":
                        WarnIfStillWalking(c);
                        Actions.PerformDeed(World, Player, c.Deed ?? "", c.TargetId, c.ItemId);
                        break;
                    case "buy":
                        WarnIfStillWalking(c);
                        var trader = World.FindAgent(c.TargetId);
                        if (trader == null || !trader.Has(Tags.Trader)) Error(Player.Id, $"'{c.TargetId}' is not a trader");
                        else if (trader.Position.DistanceTo(Player.Position) > World.Tuning.TalkRadius * 2) Error(Player.Id, $"{trader.Name} is too far to trade");
                        else Trades.Add(new TradeLog(World.Tick, trader.Id, Player.Id, Commerce.Trade(World, Player, trader, c.Price)));
                        break;
                    default:
                        Error(Player.Id, $"Unknown action '{c.Action}'");
                        break;
                }
            }
        }

        /// <summary>A scripted deed happens where the player is now; flag it when they have not reached their last destination yet.</summary>
        private void WarnIfStillWalking(PlayerCommand c)
        {
            if (Player?.Destination == null || Player.Position.DistanceTo(Player.Destination.Value) <= World.Tuning.ReachDistance) return;
            World.Journal.Add(World.Tick, "warning", Player.Id,
                $"{Player.Name} is still on the way to {_destinationName}: '{c.Deed ?? c.Action}' happens where they are now");
        }

        private void Recognize()
        {
            foreach (var guard in World.Agents)
            {
                if (!guard.Has(Tags.Authority) || !guard.Active || guard.Intent.Kind != IntentKind.Routine) continue;
                foreach (var other in World.Agents)
                {
                    if (other == guard || !other.Active || guard.Position.DistanceTo(other.Position) > World.Tuning.SightRadius) continue;
                    var crime = guard.Mind.CrimeBy(other.Id, World.Tuning.MinCrimeConfidence);
                    if (crime == null) continue;
                    string how = crime.Firsthand ? "saw it" : $"heard from {World.NameOf(crime.SourceId)}";
                    int entry = World.Journal.Add(World.Tick, "reaction", guard.Id,
                        $"{guard.Name} recognizes {other.Name} ({how}: {crime.Kind})", crime.EntryId);
                    guard.Intent = new Intent(IntentKind.Approach, other.Id, crime.Key, World.Tick + World.Tuning.PursuitTicks, entry);
                    guard.Say(World.Pack.Bark("recognize", World.Random), World.Tick);
                    break;
                }
            }
        }

        private void ResolveIntents()
        {
            foreach (var agent in World.Agents)
            {
                var intent = agent.Intent;
                if (agent.IsPlayer || intent.Kind == IntentKind.Routine) continue;
                if (!agent.Active) { agent.Intent = Intent.Routine(); continue; }
                if (World.Tick >= intent.UntilTick)
                {
                    agent.Intent = Intent.Routine();
                    World.Journal.Add(World.Tick, "intent", agent.Id, $"{agent.Name} stops ({intent})", intent.CauseEntryId);
                    continue;
                }
                var target = World.FindAgent(intent.TargetId);
                if (target == null || !target.Active) { agent.Intent = Intent.Routine(); continue; }
                if (intent.Kind == IntentKind.Flee) continue;
                if (agent.Position.DistanceTo(target.Position) > World.Tuning.ReachDistance) continue;

                if (intent.Kind == IntentKind.Approach && target.Has(WorldEvents.HostileTag))
                {
                    Combat.Attack(World, agent, target, World.Tuning.AttackDamage); // guards fight raiders until they fall or leave
                    continue;
                }
                if (intent.Kind == IntentKind.Approach) Confront(agent, target, intent);
                else if (intent.Kind == IntentKind.Report) Report(agent, target, intent);
                agent.Intent = Intent.Routine();
            }
        }

        private void Confront(Agent guard, Agent target, Intent intent)
        {
            var memory = guard.Mind.Recall(intent.MemoryKey);
            int entry = World.Journal.Add(World.Tick, "consequence", guard.Id,
                $"{guard.Name} confronts {target.Name} about {memory?.Kind ?? "their behaviour"}", intent.CauseEntryId);
            if (World.Tuning.Arrests && target.IsPlayer && guard.Has(Tags.Authority) && memory != null && memory.IsCrime)
                World.Journal.Add(World.Tick, "arrest", guard.Id, $"{guard.Name} arrests {target.Name} for {memory.Kind}", entry, target.Id);
            guard.Say(World.Pack.Bark("confront", World.Random), World.Tick);
            if (memory == null) return;

            guard.Mind.HandledCrimes.Add(memory.Key);
            var item = World.FindItem(memory.ItemId);
            if (memory.IsCrime && item != null && item.OwnerId == target.Id && memory.TargetId != null)
            {
                item.OwnerId = memory.TargetId;
                World.Journal.Add(World.Tick, "consequence", guard.Id,
                    $"{item.Name} returned to {World.NameOf(memory.TargetId)}", entry);
            }
        }

        private void Report(Agent reporter, Agent authority, Intent intent)
        {
            var memory = reporter.Mind.Recall(intent.MemoryKey);
            if (memory == null) return;
            int entry = World.Journal.Add(World.Tick, "report", authority.Id,
                $"{reporter.Name} reports to {authority.Name}: {World.NameOf(memory.ActorId)} {memory.Kind}", intent.CauseEntryId);
            Learning.Learn(World, authority, memory.Retold(reporter.Id, World.Tuning.ReportConfidence, entry));
        }

        private void ExecutePlans()
        {
            foreach (var agent in World.Agents)
            {
                if (agent.IsPlayer || !agent.Active || agent.Intent.Kind != IntentKind.Routine) continue;
                var plan = CurrentPlan(agent);
                var step = plan?.ActiveStep(World.MinuteOfDay);
                if (step == null || step.Done || Verbs.TargetsPlace(step.Verb)) continue;
                var target = StepTarget(step);
                if (target == null) { StepError(agent, step, $"cannot {step.Verb}: '{step.TargetId ?? step.ItemId}' is not here"); continue; }
                if (agent.Position.DistanceTo(target.Value) > World.Tuning.ReachDistance) continue;
                RunStep(agent, step, plan!.CauseEntryId);
                step.Done = true;
            }
        }

        private void RunStep(Agent agent, PlanStep step, int? cause)
        {
            var other = World.FindAgent(step.TargetId);
            switch (step.Verb)
            {
                case Verbs.Talk:
                    World.Journal.Add(World.Tick, "meet", agent.Id,
                        $"{agent.Name} meets {other!.Name}" + (string.IsNullOrEmpty(step.Note) ? "" : $": {step.Note}"), cause, other.Id);
                    break;
                case Verbs.Give:
                    Actions.Give(World, agent, other!, step.ItemId);
                    break;
                case Verbs.Steal:
                    var loot = World.FindItem(step.ItemId);
                    if (loot == null || loot.OwnerId == agent.Id) { StepError(agent, step, $"nothing to steal ({World.NameOf(step.ItemId)})"); return; }
                    if (agent.Has(WorldEvents.HostileTag) && World.FindAgent(loot.OwnerId)?.Has(WorldEvents.HostileTag) == true) return; // already in the gang's hands
                    Actions.PerformDeed(World, agent, "steal", loot.OwnerId, loot.Id);
                    break;
                case Verbs.Attack:
                    Combat.Attack(World, agent, other!, World.Tuning.AttackDamage);
                    break;
            }
        }

        private void StepError(Agent agent, PlanStep step, string message)
        {
            step.Done = true;
            Error(agent.Id, message);
        }

        private Plan? CurrentPlan(Agent agent)
        {
            foreach (var fixedPlan in agent.FixedPlans)
                if (fixedPlan.Day == World.Day && fixedPlan.InWindow(World.MinuteOfDay)) return fixedPlan;
            var plan = agent.Plan;
            return plan != null && (plan.Day == 0 || plan.Day == World.Day) ? plan : null;
        }

        /// <summary>Where a step happens: its place, the other agent, or the item (or whoever carries it).</summary>
        private Vec2? StepTarget(PlanStep step)
        {
            if (Verbs.TargetsPlace(step.Verb)) return World.FindPlace(step.TargetId)?.Position;
            if (step.Verb == Verbs.Steal)
            {
                var item = World.FindItem(step.ItemId);
                if (item == null) return null;
                var owner = World.FindAgent(item.OwnerId);
                return owner != null && owner.Active ? owner.Position : item.Position;
            }
            var other = World.FindAgent(step.TargetId);
            return other != null && other.Active ? other.Position : (Vec2?)null;
        }

        /// <summary>Where this agent wants to be right now (null = stay). Hosts with ExternalMovement read this every frame.</summary>
        public Vec2? DestinationOf(Agent agent) => DestinationFor(agent);

        private void Move()
        {
            foreach (var agent in World.Agents)
            {
                var destination = DestinationFor(agent);
                if (destination.HasValue) agent.Position = agent.Position.MoveTowards(destination.Value, agent.Speed);
            }
        }

        private Vec2? DestinationFor(Agent agent)
        {
            if (agent.IsPlayer) return agent.Destination;
            if (!agent.Active) return null;
            switch (agent.Intent.Kind)
            {
                case IntentKind.Flee:
                    var home = World.FindPlace(agent.HomePlaceId);
                    if (home != null) return home.Position;
                    var threat = World.FindAgent(agent.Intent.TargetId);
                    if (threat == null) return null;
                    float dx = agent.Position.X - threat.Position.X, dy = agent.Position.Y - threat.Position.Y;
                    float length = (float)System.Math.Sqrt(dx * dx + dy * dy);
                    if (length < 0.01f) return null;
                    return agent.Position.Offset(dx / length * 10f, dy / length * 10f);
                case IntentKind.Approach:
                case IntentKind.Report:
                    return World.FindAgent(agent.Intent.TargetId)?.Position;
                default:
                    var offset = _slotOffsets.TryGetValue(agent.Id, out var o) ? o : new Vec2(0, 0);
                    var leader = agent.FollowId != null ? World.FindAgent(agent.FollowId) : null;
                    if (leader != null && leader.Active && World.Tick < agent.FollowUntilTick)
                        return leader.Position.Offset(offset.X, offset.Y);
                    var gathering = WorldEvents.Override(World, agent);
                    if (gathering != null) return gathering.Position.Offset(offset.X, offset.Y);
                    var plan = CurrentPlan(agent);
                    if (plan != null)
                    {
                        var step = plan.ActiveStep(World.MinuteOfDay);
                        var target = step == null ? null : StepTarget(step);
                        if (target == null) return null;
                        return Verbs.TargetsPlace(step!.Verb) ? target.Value.Offset(offset.X, offset.Y) : target;
                    }
                    var place = World.FindPlace(agent.Schedule?.PlaceAt(World.Hour));
                    if (place == null) return null;
                    return place.Position.Offset(offset.X, offset.Y);
            }
        }

        private Frame Capture()
        {
            var frame = new Frame(World.Tick);
            foreach (var a in World.Agents)
            {
                float opinion = Player == null || a.IsPlayer ? 0f : a.Mind.OpinionOf(Player.Id);
                frame.Agents.Add(new AgentFrame(a.Id, a.Position.X, a.Position.Y, a.Intent.ToString(),
                    a.Mind.Emotions.Fear, a.Mind.Emotions.Anger, opinion, a.CurrentBark(World.Tick)));
            }
            return frame;
        }

        private void Error(string? agentId, string message) => World.Journal.Add(World.Tick, "error", agentId, message);
    }
}
