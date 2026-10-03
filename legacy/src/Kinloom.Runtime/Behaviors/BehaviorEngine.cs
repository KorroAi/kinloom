using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Kinloom.Expressions;
using Kinloom.Schema;

namespace Kinloom.Behaviors
{
    /// <summary>Runs instant-tier behaviors every pump, locally, without model calls.
    /// Semantics: <c>set</c> actions apply continuously while the rule holds (an unchanged value sends nothing);
    /// <c>invoke</c>, <c>emit</c> and <c>wake</c> fire on the rising edge, then again every <c>cooldown</c> seconds while it still holds.
    /// With a cooldown, <c>set</c> actions also wait for it.</summary>
    internal sealed class BehaviorEngine
    {
        private static readonly IReadOnlyList<Permission> Trusted = new[] { Permission.Parse("set:*.*"), Permission.Parse("invoke:*.*") };
        private readonly KinloomSession _s;
        private readonly List<Installed> _installed = new List<Installed>();
        private readonly ThingScope _scope;
        /// <summary>Params changed by a behavior during the current step: who set them, to what (conflict detection).</summary>
        private readonly Dictionary<(string thing, string member), (string behavior, Value value)> _setThisStep = new Dictionary<(string, string), (string, Value)>();
        private readonly HashSet<string> _reportedConflicts = new HashSet<string>();

        public BehaviorEngine(KinloomSession session)
        {
            _s = session;
            _scope = new ThingScope(session);
        }

        public IReadOnlyList<Installed> All => _installed;

        internal sealed class Installed
        {
            public Installed(BehaviorDecl decl, string source, IReadOnlyList<Permission>? can, string? self, string ownerId, List<CompiledRule> rules)
            {
                Decl = decl; Source = source; Can = can; Self = self; OwnerId = ownerId; Rules = rules;
            }
            public BehaviorDecl Decl { get; }
            public string Source { get; }
            public IReadOnlyList<Permission>? Can { get; }
            public string? Self { get; }
            public string OwnerId { get; }
            public List<CompiledRule> Rules { get; }
        }

        internal sealed class CompiledRule
        {
            public CompiledRule(Expr when, double cooldown, List<CompiledAction> actions) { When = when; Cooldown = cooldown; Actions = actions; }
            public Expr When { get; }
            public double Cooldown { get; }
            public List<CompiledAction> Actions { get; }
            public bool WasTrue { get; set; }
            public double LastFired { get; set; } = double.NegativeInfinity;
            /// <summary>Last time invoke/emit/wake actions fired (rate limit for role-installed rules).</summary>
            public double LastEdge { get; set; } = double.NegativeInfinity;
            public bool RefusalReported { get; set; }
        }

        internal sealed class CompiledAction
        {
            public ActionDecl Decl { get; set; } = new ActionDecl();
            public string? Target { get; set; }
            public string? Member { get; set; }
            public Expr? To { get; set; }
            public List<KeyValuePair<string, Expr>> Args { get; } = new List<KeyValuePair<string, Expr>>();
        }

        public IReadOnlyList<string> Install(BehaviorDecl b, string source, IReadOnlyList<Permission>? can, string? self)
        {
            var errors = new List<string>();
            var existing = _installed.FirstOrDefault(x => x.Decl.Id == b.Id);
            if (existing != null && existing.Source != source)
                errors.Add($"behavior '{b.Id}' belongs to {existing.Source}; choose another id");
            string? ownerId = b.Owner == null || b.Owner == "self" ? self : b.Owner;
            if (ownerId == null || _s.Things.Find(ownerId) == null) errors.Add(ownerId == null ? "a behavior needs an owner thing" : $"unknown owner '{ownerId}'");
            if (can != null && errors.Count == 0) errors.AddRange(_s.Arbiter.CheckBehavior(b, can, self, source));

            var rules = new List<CompiledRule>();
            if (errors.Count == 0)
            {
                try
                {
                    foreach (var r in b.Rules)
                    {
                        var actions = new List<CompiledAction>();
                        foreach (var a in r.Do)
                        {
                            var ca = new CompiledAction { Decl = a };
                            string? reference = a.Set ?? a.Invoke;
                            if (reference != null)
                            {
                                int dot = reference.LastIndexOf('.');
                                if (dot <= 0) throw new ExprException($"'{reference}' must look like target.member", 1);
                                ca.Target = reference.Substring(0, dot);
                                ca.Member = reference.Substring(dot + 1);
                            }
                            if (a.To != null) ca.To = Expr.Parse(a.To);
                            foreach (var arg in a.Invoke != null ? a.Args : a.Data) ca.Args.Add(new KeyValuePair<string, Expr>(arg.Key, Expr.Parse(arg.Value)));
                            actions.Add(ca);
                        }
                        rules.Add(new CompiledRule(Expr.Parse(r.When), r.Cooldown, actions));
                    }
                }
                catch (ExprException e) { errors.Add($"{e.Message}"); }
            }
            if (errors.Count > 0)
            {
                _s.Log("refused", source, $"behavior {b.Id} refused: {string.Join("; ", errors)}");
                return errors;
            }
            if (existing != null) _installed.Remove(existing);
            ReplaceOverlapping(b, source, ownerId!);
            _installed.Add(new Installed(b, source, can, self, ownerId!, rules));
            _s.Log("behavior", source, $"installed behavior {b.Id} on {ownerId} ({b.Rules.Count} rules)", b.Raw.DeepClone());
            return errors;
        }

        /// <summary>A role keeps one reflex per param: a behavior installed by a role (or its fallback instinct) replaces that
        /// role's earlier behaviors setting any of the same params. Without this, reflexes pile up wake after wake and fight
        /// over the same param every frame (seen in real integrations: ~12,000 effects per race).</summary>
        private void ReplaceOverlapping(BehaviorDecl b, string source, string ownerId)
        {
            string? role = RoleOf(source);
            if (role == null) return;
            var mine = SetKeys(b, ownerId);
            if (mine.Count == 0) return;
            foreach (var old in _installed.Where(x => x.Decl.Id != b.Id && RoleOf(x.Source) == role).ToList())
            {
                var shared = SetKeys(old.Decl, old.OwnerId).Where(mine.Contains).ToList();
                if (shared.Count == 0) continue;
                _installed.Remove(old);
                _s.Log("behavior", source, $"behavior {old.Decl.Id} of {old.Source} replaced by {b.Id} (same params: {string.Join(", ", shared)})");
            }
        }

        /// <summary>The role a behavior belongs to: <c>role:x</c> and <c>fallback:x</c> both belong to x; the game's own to none.</summary>
        internal static string? RoleOf(string source) =>
            source.StartsWith("role:", StringComparison.Ordinal) ? source.Substring(5)
            : source.StartsWith("fallback:", StringComparison.Ordinal) ? source.Substring(9)
            : null;

        private static HashSet<string> SetKeys(BehaviorDecl b, string ownerId)
        {
            var keys = new HashSet<string>(StringComparer.Ordinal);
            foreach (var rule in b.Rules)
                foreach (var act in rule.Do)
                {
                    if (act.Set == null) continue;
                    int dot = act.Set.LastIndexOf('.');
                    if (dot <= 0) continue;
                    string target = act.Set.Substring(0, dot);
                    keys.Add((target == "self" ? ownerId : target) + "." + act.Set.Substring(dot + 1));
                }
            return keys;
        }

        public bool Remove(string id)
        {
            int removed = _installed.RemoveAll(x => x.Decl.Id == id);
            return removed > 0;
        }

        public void RemoveOwnedBy(string thingId) => _installed.RemoveAll(x => x.OwnerId == thingId);

        public void Step()
        {
            if (_setThisStep.Count > 0) _setThisStep.Clear();
            double now = _s.Now;
            for (int i = 0; i < _installed.Count; i++)
            {
                var b = _installed[i];
                var owner = _s.Things.Find(b.OwnerId);
                if (owner == null) continue;
                _scope.With(owner);
                foreach (var rule in b.Rules)
                {
                    bool holds = rule.When.Eval(_scope, _s.Random).Truthy;
                    bool rising = holds && !rule.WasTrue;
                    rule.WasTrue = holds;
                    if (!holds) continue;
                    bool cooled = now - rule.LastFired >= rule.Cooldown;
                    bool fireEdgeActions = rising || (rule.Cooldown > 0 && cooled);
                    // A role's rule may flip every frame (on purpose or not): its actions fire at most a few times per second.
                    if (fireEdgeActions && b.Can != null && now - rule.LastEdge < 1.0 / BehaviorLimits.MaxEdgeFiresPerSecond) fireEdgeActions = false;
                    bool fireSets = rule.Cooldown <= 0 || cooled;
                    bool fired = false;
                    foreach (var a in rule.Actions)
                    {
                        if (a.Decl.Set != null) { if (fireSets) fired |= DoSet(b, rule, owner, a); }
                        else if (fireEdgeActions) { DoEdge(b, rule, owner, a); fired = true; rule.LastEdge = now; }
                    }
                    if (fired) rule.LastFired = now;
                }
            }
        }

        private Thing? Resolve(string target, Thing owner) => target == "self" ? owner : _s.Things.Find(target);

        private bool DoSet(Installed b, CompiledRule rule, Thing owner, CompiledAction a)
        {
            var thing = Resolve(a.Target!, owner);
            if (thing == null) return false;
            var value = a.To!.Eval(_scope, _s.Random);
            if (value.Kind == ValueKind.Null) return false;
            var current = thing.Pending.TryGetValue(a.Member!, out var pending) ? Value.From(pending.value) : thing.Get(a.Member!);
            if (current.SameAs(value) || Negligible(thing, a.Member!, current, value)) return false;
            NoteSet(b.Decl.Id, thing.Id, a.Member!, value);
            var p = new Proposal(ProposalKind.Set, "behavior:" + b.Decl.Id)
            {
                Thing = thing.Id, Member = a.Member, Self = b.Self ?? owner.Id, Args = new JsonObject { ["value"] = value.ToJson() },
            };
            return Submit(b, rule, p);
        }

        /// <summary>A numeric change under 0.1 % of the param's range (or of its magnitude when unbounded) is not worth an effect:
        /// smoothing like <c>lerp(x, target, k)</c> would otherwise send a new value every frame forever.</summary>
        private static bool Negligible(Thing thing, string member, Value current, Value next)
        {
            if (current.Kind != ValueKind.Number || next.Kind != ValueKind.Number) return false;
            var spec = thing.Type.Params.Find(member);
            double scale = spec?.Min != null && spec.Max != null ? spec.Max.Value - spec.Min.Value : Math.Max(1, Math.Abs(current.Number));
            return Math.Abs(next.Number - current.Number) < 0.001 * scale;
        }

        /// <summary>Two behaviors setting one param to different values in the same step fight forever (an effect every frame,
        /// the param flickering). Journaled once per pair as an error so the developer gives each param one owner.</summary>
        private void NoteSet(string behavior, string thing, string member, Value value)
        {
            var key = (thing, member);
            if (_setThisStep.TryGetValue(key, out var earlier) && earlier.behavior != behavior && !earlier.value.SameAs(value))
            {
                string pair = string.CompareOrdinal(earlier.behavior, behavior) < 0 ? earlier.behavior + "|" + behavior : behavior + "|" + earlier.behavior;
                if (_reportedConflicts.Add(pair + "|" + thing + "." + member))
                    _s.Log("error", "behavior:" + behavior, $"behaviors {earlier.behavior} and {behavior} both set {thing}.{member} ({earlier.value} vs {value}) every frame: give each param one owner");
            }
            _setThisStep[key] = (behavior, value);
        }

        private void DoEdge(Installed b, CompiledRule rule, Thing owner, CompiledAction a)
        {
            string source = "behavior:" + b.Decl.Id;
            if (a.Decl.Invoke != null)
            {
                var thing = Resolve(a.Target!, owner);
                if (thing == null) return;
                var args = new JsonObject();
                foreach (var arg in a.Args) args[arg.Key] = arg.Value.Eval(_scope, _s.Random).ToJson();
                Submit(b, rule, new Proposal(ProposalKind.Invoke, source) { Thing = thing.Id, Member = a.Member, Self = b.Self ?? owner.Id, Args = args });
            }
            else if (a.Decl.Emit != null)
            {
                var data = new JsonObject();
                foreach (var d in a.Args) data[d.Key] = d.Value.Eval(_scope, _s.Random).ToJson();
                _s.Emit(new GameEvent(a.Decl.Emit, data) { Source = source });
            }
            else if (a.Decl.Wake != null)
                _s.RequestWake(a.Decl.Wake, $"woken by behavior {b.Decl.Id}");
        }

        private bool Submit(Installed b, CompiledRule rule, Proposal p)
        {
            var verdict = _s.Arbiter.Check(p, b.Can ?? Trusted, journal: !rule.RefusalReported);
            if (!verdict.Allowed) { rule.RefusalReported = true; return false; }
            rule.RefusalReported = false;
            _s.EnqueueEffect(verdict.Effect!, null);
            return true;
        }
    }
}
