using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Kinloom.Behaviors;
using Kinloom.Llm;
using Kinloom.Memory;
using Kinloom.Scheduling;
using Kinloom.Schema;

namespace Kinloom.Roles
{
    /// <summary>Wakes roles (events, intervals, conditions, asks, behaviors), calls their model off the game thread, and applies
    /// answers during Pump: every action goes through the Arbiter; invalid answers get one repair call; over budget or without
    /// a model, the role's fallback runs instead.</summary>
    internal sealed class RoleEngine
    {
        private readonly KinloomSession _s;
        private readonly Dictionary<string, RoleState> _roles = new Dictionary<string, RoleState>();
        private readonly ConcurrentQueue<Completion> _done = new ConcurrentQueue<Completion>();
        private readonly Budget _budget;
        private readonly ThingScope _scope;
        private int _inFlight;

        public RoleEngine(KinloomSession session, Budget budget)
        {
            _s = session;
            _budget = budget;
            _scope = new ThingScope(session);
        }

        public IReadOnlyCollection<RoleState> Roles => _roles.Values;
        public RoleState? Find(string id) => _roles.TryGetValue(id, out var r) ? r : null;
        public bool Busy => _inFlight > 0 || !_done.IsEmpty || _roles.Values.Any(r => r.InFlight || r.Asks.Count > 0);

        private sealed class Completion
        {
            public Completion(RoleState role, Trigger trigger, LlmRequest request, LlmResponse response, int attempt, Carry carry)
            {
                Role = role; Trigger = trigger; Request = request; Response = response; Attempt = attempt; Carry = carry;
            }
            public RoleState Role { get; }
            public Trigger Trigger { get; }
            public LlmRequest Request { get; }
            public LlmResponse Response { get; }
            public int Attempt { get; }
            public Carry Carry { get; }
        }

        /// <summary>What earlier attempts of the same thought already produced.</summary>
        private sealed class Carry
        {
            public List<Effect> Effects { get; } = new List<Effect>();
            public List<string> Said { get; } = new List<string>();
            public List<string> Applied { get; } = new List<string>();
        }

        public void Declare(IEnumerable<RoleDecl> roles)
        {
            foreach (var r in roles) _roles[r.Id] = new RoleState(r, _s.Now);
        }

        // ---------------- wakes ----------------

        public void OnEvent(GameEvent e)
        {
            foreach (var role in _roles.Values)
            {
                if (!RolePrompt.Knows(role, e)) continue;
                for (int i = 0; i < role.Decl.Wake.Count; i++)
                {
                    var w = role.Decl.Wake[i];
                    if (w.On == null || (w.On != "event:" + e.Type && w.On != "event:*")) continue;
                    if (e.Source == role.Source) continue;
                    if (role.Where[i] != null && !role.Where[i]!.Eval(_scope.With(Self(role), e), _s.Random).Truthy) continue;
                    Wake(role, new Trigger("event " + e.Type) { Event = e });
                    break;
                }
            }
        }

        public void Step()
        {
            while (_done.TryDequeue(out var c)) Process(c);
            foreach (var role in _roles.Values)
            {
                for (int i = 0; i < role.Decl.Wake.Count; i++)
                {
                    var w = role.Decl.Wake[i];
                    if (w.Every.HasValue && _s.Now >= role.NextEvery[i])
                    {
                        role.NextEvery[i] = Math.Max(role.NextEvery[i] + w.Every.Value, _s.Now + w.Every.Value * 0.5);
                        Wake(role, new Trigger("Regular check-in."));
                    }
                    else if (role.When[i] != null)
                    {
                        bool holds = role.When[i]!.Eval(_scope.With(Self(role)), _s.Random).Truthy;
                        if (holds && !role.WhenWasTrue[i]) Wake(role, new Trigger($"This became true: {w.When}"));
                        role.WhenWasTrue[i] = holds;
                    }
                }
                if (role.Pending != null && !role.InFlight && _s.Now - role.LastCall >= role.Decl.MinInterval)
                {
                    var pending = role.Pending;
                    role.Pending = null;
                    Wake(role, pending);
                }
            }
        }

        public Task<AskResult> Ask(string roleId, string input, string? from)
        {
            if (!_roles.TryGetValue(roleId, out var role))
                return Task.FromResult(new AskResult(null, Array.Empty<Effect>(), false, $"unknown role '{roleId}'"));
            var trigger = new Trigger("ask")
            {
                AskInput = input, From = from,
                Reply = new TaskCompletionSource<AskResult>(TaskCreationOptions.RunContinuationsAsynchronously),
            };
            Wake(role, trigger);
            return trigger.Reply.Task;
        }

        public void Wake(string roleId, string reason)
        {
            if (_roles.TryGetValue(roleId, out var role)) Wake(role, new Trigger(reason));
        }

        private void Wake(RoleState role, Trigger trigger)
        {
            if (role.InFlight)
            {
                if (!trigger.IsAsk) role.Pending = trigger;
                else if (role.Asks.Count < RoleLimits.MaxQueuedAsks) role.Asks.Enqueue(trigger);
                else Fallback(role, trigger, "too many questions waiting");
                return;
            }
            if (!trigger.IsAsk && _s.Now - role.LastCall < role.Decl.MinInterval) { role.Pending = trigger; return; }

            var client = ClientFor(role.Decl.Tier);
            string? denied = client == null ? "no model configured" : _budget.Deny(role.Source, role.Decl.Budget.CallsPerMinute, _s.Options.MaxCallsPerMinute, _s.Options.Prices != null ? _s.Options.MaxCostPerHour : null);
            if (denied != null) { Fallback(role, trigger, denied); return; }
            Start(role, trigger, client!, 0, new Carry(), null);
        }

        private ILlmClient? ClientFor(string tier) => tier == "deep" ? _s.Options.Deep ?? _s.Options.Fast : _s.Options.Fast ?? _s.Options.Deep;

        private Thing? Self(RoleState role) => role.Decl.Inhabits != null ? _s.Things.Find(role.Decl.Inhabits) : null;

        // ---------------- calls ----------------

        private void Start(RoleState role, Trigger trigger, ILlmClient client, int attempt, Carry carry, string? repair)
        {
            role.InFlight = true;
            role.LastCall = _s.Now;
            string system = RolePrompt.System(_s, role);
            string user = RolePrompt.User(_s, role, trigger) + (repair != null ? "\n\n" + repair : "");
            var request = new LlmRequest(role.Source, system, user, role.Decl.Tier == "deep" ? 2000 : 1000, 0.7f, RoleTools.For(role.Can, role.Decl.Inhabits != null));
            _budget.RecordCall(role.Source);
            System.Threading.Interlocked.Increment(ref _inFlight);
            _s.Log("call", role.Source, attempt == 0 ? $"thinking ({trigger.Reason})" : "repairing its answer");
            double timeout = role.Decl.Tier == "deep" ? _s.Options.DeepTimeout : _s.Options.FastTimeout;
            Task.Run(async () =>
            {
                var response = await ModelCall.Run(client, request, timeout).ConfigureAwait(false);
                _done.Enqueue(new Completion(role, trigger, request, response, attempt, carry));
                System.Threading.Interlocked.Decrement(ref _inFlight);
            });
        }

        private void Process(Completion c)
        {
            var role = c.Role;
            _s.CountCall(role.Source, c.Response, _budget);
            if (!c.Response.Ok)
            {
                _s.Log("error", role.Source, "model call failed: " + c.Response.Error);
                role.InFlight = false;
                if (c.Carry.Effects.Count > 0 || c.Carry.Said.Count > 0) Finish(role, c.Trigger, c.Carry, false, c.Response.Error);
                else Fallback(role, c.Trigger, "model call failed");
                return;
            }

            // The model is answering again: a fallback behavior stops so it does not fight the role.
            if (role.Decl.Fallback?.Behavior is string fallbackBehavior
                && _s.Behaviors.Any(b => b.behavior.Id == fallbackBehavior && b.source == FallbackSource(role)))
                _s.RemoveBehavior(fallbackBehavior);

            var output = RoleOutput.Parse(c.Response.Text);
            var errors = new List<string>();
            if (output.Error != null) errors.Add(output.Error);
            if (output.Thought != null) _s.Log("thought", role.Source, output.Thought);
            if (output.Prose != null)
            {
                if (role.Can.Any(p => p.Verb == Verb.Say)) Apply(role, "say", new JsonObject { ["text"] = output.Prose }, c.Carry, errors);
                else _s.Log("thought", role.Source, output.Prose);
            }
            foreach (var (tool, args) in output.Actions) Apply(role, tool, args, c.Carry, errors);
            if (c.Trigger.IsAsk && c.Carry.Said.Count == 0 && errors.Count == 0 && role.Can.Any(p => p.Verb == Verb.Say))
                errors.Add("they are waiting for your reply: call say with one short line");

            var client = ClientFor(role.Decl.Tier);
            if (errors.Count > 0 && c.Attempt == 0 && client != null)
            {
                _s.Stats.Repairs++;
                var repair = new StringBuilder();
                repair.AppendLine("Your previous answer had problems:");
                foreach (var e in errors) repair.AppendLine("- " + e);
                if (c.Carry.Applied.Count > 0) repair.AppendLine("Already done (do not repeat): " + string.Join("; ", c.Carry.Applied));
                repair.Append("Answer again with valid tool calls only for what is still needed (or none).");
                Start(role, c.Trigger, client, 1, c.Carry, repair.ToString());
                return;
            }
            foreach (var e in errors.Where(e => !e.StartsWith("refused:", StringComparison.Ordinal))) _s.Log("refused", role.Source, e);
            role.InFlight = false;
            // Someone is waiting for an answer and the model could not give a usable one: the fallback answers instead.
            if (c.Trigger.IsAsk && c.Carry.Said.Count == 0 && c.Carry.Effects.Count == 0 && errors.Count > 0) { Fallback(role, c.Trigger, "no usable answer"); return; }
            Finish(role, c.Trigger, c.Carry, false, null);
        }

        /// <summary>Turns one tool call into a proposal, checks it and applies it. Problems are added to <paramref name="errors"/>.</summary>
        private void Apply(RoleState role, string tool, JsonObject args, Carry carry, List<string> errors)
        {
            if (args.ContainsKey("_raw")) { errors.Add($"the arguments of {tool} were not valid JSON: {args["_raw"]}"); return; }
            if (!RoleTools.Names.Contains(tool)) { errors.Add($"unknown tool '{tool}' (available: {string.Join(", ", RoleTools.For(role.Can).Select(t => t.Name))})"); return; }
            if (!RoleTools.Allowed(tool, role.Can)) { errors.Add($"the tool '{tool}' is not allowed for you"); return; }
            string? Str(string key) => args[key] is JsonValue v && v.TryGetValue(out string? s) ? s : args[key]?.ToJsonString();

            Proposal p;
            switch (tool)
            {
                case "set_param":
                    p = new Proposal(ProposalKind.Set, role.Source) { Thing = Str("thing"), Member = Str("param"), Args = new JsonObject { ["value"] = args["value"]?.DeepClone() } };
                    if (!args.ContainsKey("value")) p.Args.Remove("value");
                    break;
                case "invoke":
                    p = new Proposal(ProposalKind.Invoke, role.Source) { Thing = Str("thing"), Member = Str("function"), Args = (args["args"] as JsonObject)?.DeepClone() as JsonObject ?? new JsonObject() };
                    break;
                case "create":
                    p = new Proposal(ProposalKind.Create, role.Source) { Member = Str("type"), Args = (args["args"] as JsonObject)?.DeepClone() as JsonObject ?? new JsonObject(), Text = Str("name") };
                    break;
                case "destroy":
                    p = new Proposal(ProposalKind.Destroy, role.Source) { Thing = Str("thing") };
                    break;
                case "say":
                    p = new Proposal(ProposalKind.Say, role.Source) { Text = Str("text"), To = Str("to") };
                    break;
                case "remember":
                    p = new Proposal(ProposalKind.Remember, role.Source) { Text = Str("text") };
                    break;
                case "generate":
                    p = new Proposal(ProposalKind.Generate, role.Source) { Member = Str("generator"), Text = Str("brief") };
                    break;
                case "request_media":
                    p = new Proposal(ProposalKind.Media, role.Source) { Member = Str("kind"), Text = Str("prompt"), Args = (args["spec"] as JsonObject)?.DeepClone() as JsonObject ?? new JsonObject() };
                    break;
                case "remove_behavior":
                {
                    string id = Str("id") ?? "";
                    var mine = _s.Behaviors.FirstOrDefault(b => b.behavior.Id == id);
                    if (mine.behavior == null) errors.Add($"remove_behavior: no behavior '{id}'");
                    else if (mine.source != role.Source) errors.Add($"remove_behavior: '{id}' was not installed by you");
                    else { _s.RemoveBehavior(id); carry.Applied.Add("removed behavior " + id); }
                    return;
                }
                case "set_behavior":
                {
                    var parseErrors = new List<ManifestError>();
                    var decl = BehaviorDecl.Parse(args, "set_behavior", parseErrors);
                    if (parseErrors.Count > 0) { errors.Add("set_behavior: " + string.Join("; ", parseErrors)); return; }
                    var installErrors = _s.InstallBehavior(decl, role.Source, role.Can, role.Decl.Inhabits);
                    if (installErrors.Count > 0) { errors.Add("refused: set_behavior " + decl.Id + ": " + string.Join("; ", installErrors)); return; }
                    carry.Applied.Add("installed behavior " + decl.Id);
                    return;
                }
                default:
                    errors.Add($"unknown tool '{tool}'");
                    return;
            }
            p.Self = role.Decl.Inhabits;
            SplitDottedMember(p, role);
            var verdict = _s.Arbiter.Check(p, role.Can);
            if (!verdict.Allowed)
            {
                string what = $"{tool} {(p.Thing ?? p.Member ?? "")}{(p.Thing != null && p.Member != null ? "." + p.Member : "")}".Trim();
                errors.Add($"refused: {what}: {verdict.Reason}");
                role.AddRefusal($"{what}: {verdict.Reason}");
                return;
            }
            switch (p.Kind)
            {
                case ProposalKind.Remember:
                {
                    double importance = args["importance"] is JsonValue iv && iv.TryGetValue(out double d) ? d : 0.5;
                    if (role.MemoryScope != null) _s.Memory.Add(role.MemoryScope, new MemoryEntry(_s.Now, p.Text!.Trim(), importance), role.Decl.Memory.Max);
                    _s.Log("memory", role.Source, p.Text!.Trim());
                    carry.Applied.Add("remembered a note");
                    return;
                }
                case ProposalKind.Generate:
                    _s.StartGeneration(p.Member!, new JsonObject { ["brief"] = p.Text }, role.Source);
                    carry.Applied.Add("asked generator " + p.Member);
                    return;
                case ProposalKind.Media:
                    _s.StartMedia(p.Member!, p.Text!, p.Args, role.Source, role.Decl.Inhabits);
                    carry.Applied.Add("requested " + p.Member + " media");
                    return;
            }
            var effect = _s.EnqueueEffect(verdict.Effect!, result => OnResolved(role, verdict.Effect!, result));
            carry.Effects.Add(effect);
            carry.Applied.Add(effect.ToString());
            if (effect.Kind == EffectKind.Say) carry.Said.Add(effect.Text!);
        }

        /// <summary>Lenient reading of <c>{thing: "self" or nothing, param/function: "hud.show"}</c> as thing <c>hud</c>, member <c>show</c>.</summary>
        private static void SplitDottedMember(Proposal p, RoleState role)
        {
            if ((p.Kind != ProposalKind.Set && p.Kind != ProposalKind.Invoke) || p.Member == null) return;
            int dot = p.Member.LastIndexOf('.');
            bool vagueTarget = string.IsNullOrEmpty(p.Thing) || (p.Thing == "self" && role.Decl.Inhabits == null);
            if (dot <= 0 || dot == p.Member.Length - 1 || !vagueTarget) return;
            p.Thing = p.Member.Substring(0, dot);
            p.Member = p.Member.Substring(dot + 1);
        }

        private void OnResolved(RoleState role, Effect effect, EffectResult result)
        {
            if (result.Status == ResolveStatus.Ok) return;
            string text = $"The game {(result.Status == ResolveStatus.Refused ? "refused" : "could not do")} {effect}: {result.Reason}";
            role.AddRefusal(text);
            if (role.MemoryScope != null) _s.Memory.Add(role.MemoryScope, new MemoryEntry(_s.Now, text, 0.6), role.Decl.Memory.Max);
        }

        private void Finish(RoleState role, Trigger trigger, Carry carry, bool usedFallback, string? error)
        {
            if (role.MemoryScope != null)
            {
                int max = role.Decl.Memory.Max;
                if (trigger.IsAsk) _s.Memory.Add(role.MemoryScope, new MemoryEntry(_s.Now, $"{trigger.From ?? "Someone"} said to me: \"{trigger.AskInput}\"", 0.6), max);
                else if (trigger.Event != null) _s.Memory.Add(role.MemoryScope, new MemoryEntry(_s.Now, "I noticed: " + trigger.Event.Describe(), trigger.Event.Importance), max);
                foreach (var line in carry.Said) _s.Memory.Add(role.MemoryScope, new MemoryEntry(_s.Now, $"I said: \"{line}\"", 0.5), max);
            }
            string? reply = carry.Said.Count > 0 ? string.Join(" ", carry.Said) : null;
            if (reply != null) _s.Log("reply", role.Source, reply);
            trigger.Reply?.TrySetResult(new AskResult(reply, carry.Effects.ToList(), usedFallback, error));

            if (role.InFlight) return; // a fallback answered while the model is still thinking: the queue waits for it
            if (role.Asks.Count > 0) Wake(role, role.Asks.Dequeue());
            else if (role.Pending != null && _s.Now - role.LastCall >= role.Decl.MinInterval)
            {
                var pending = role.Pending;
                role.Pending = null;
                Wake(role, pending);
            }
        }

        private static string FallbackSource(RoleState role) => "fallback:" + role.Id;

        private void Fallback(RoleState role, Trigger trigger, string why)
        {
            _s.Stats.Fallbacks++;
            _s.Log("fallback", role.Source, why);
            var carry = new Carry();
            var fb = role.Decl.Fallback;
            if (fb?.Behavior != null && _s.Behaviors.All(b => b.behavior.Id != fb.Behavior))
            {
                var decl = _s.Declared.Behaviors.FirstOrDefault(b => b.Id == fb.Behavior);
                if (decl != null) _s.InstallBehavior(decl, FallbackSource(role), null);
            }
            if (fb != null && fb.Say.Count > 0)
            {
                // Never the same canned line twice in a row when there is a choice.
                int pick = _s.Random.Next(fb.Say.Count);
                if (fb.Say.Count > 1 && fb.Say[pick] == role.LastFallbackLine) pick = (pick + 1 + _s.Random.Next(fb.Say.Count - 1)) % fb.Say.Count;
                string line = fb.Say[pick];
                role.LastFallbackLine = line;
                var effect = _s.EnqueueEffect(new Effect(EffectKind.Say, role.Decl.Inhabits ?? Manifest.WorldId, null, null, role.Source, line), null);
                carry.Effects.Add(effect);
                carry.Said.Add(line);
            }
            Finish(role, trigger, carry, true, null);
        }

        // ---------------- persistence ----------------

        public JsonObject Save()
        {
            var o = new JsonObject();
            foreach (var r in _roles.Values)
                o[r.Id] = new JsonObject
                {
                    ["mission"] = r.Mission == r.Decl.Mission ? null : r.Mission,
                    ["refusals"] = new JsonArray(r.RecentRefusals.Select(x => (JsonNode)JsonValue.Create(x)!).ToArray()),
                };
            return o;
        }

        public void Load(JsonObject? state)
        {
            if (state == null) return;
            foreach (var p in state)
            {
                if (!_roles.TryGetValue(p.Key, out var role) || !(p.Value is JsonObject o)) continue;
                if (o["mission"] is JsonValue m && m.TryGetValue(out string? mission) && mission != null) role.Mission = mission;
                role.RecentRefusals.Clear();
                foreach (var r in o["refusals"] as JsonArray ?? new JsonArray()) if (r != null) role.RecentRefusals.Add(r.GetValue<string>());
            }
        }
    }
}
